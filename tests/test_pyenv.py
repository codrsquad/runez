import os
import re
import sys

import pytest
from mock import patch

import runez
from runez.pyenv import pyenv_scanner, PythonDepot, PythonSpec, Version


RE_VERSION = re.compile(r"^(.*)(\d+\.\d+.\d+)$")


def mk_python(basename, prefix=None, base_prefix=None, executable=True, content=None, folder=None, version=None):
    if version is None:
        m = RE_VERSION.match(basename)
        if m:
            if not folder:
                folder = os.path.join(".pyenv/versions", basename)

            version = m.group(2)
            basename = "python"

    if not folder:
        folder = ".pyenv/versions"

    path = runez.resolved_path(folder)
    if not prefix:
        prefix = path

    if not base_prefix:
        base_prefix = prefix

    path = os.path.join(path, "bin", basename)
    if not content:
        content = [version, prefix, base_prefix]

    content = "#!/bin/bash\n%s\n" % "\n".join("echo %s" % s for s in content)
    runez.write(path, content)
    if executable:
        runez.make_executable(path)


def check_find_python(depot, spec, expected):
    p = depot.find_python(spec)
    assert str(p) == expected


def test_empty_depot():
    depot = PythonDepot(use_path=False)
    assert str(depot) == "0 scanned"
    assert depot.from_path == []
    assert depot.scanned == []

    assert depot.find_python(PythonSpec(depot.invoker.executable)) is depot.invoker
    assert depot.find_python(PythonSpec("invoker")) is depot.invoker
    assert depot.find_python("invoker") is depot.invoker
    assert depot.find_python(depot.invoker.spec.family) is depot.invoker
    assert depot.representation() == ""

    p = depot.find_python("foo")
    assert p.representation() == "foo [not available]"
    assert p.problem == "not available"
    assert str(depot) == "0 scanned"


def test_depot(temp_folder, monkeypatch):
    # Create some pyenv-style python installation mocks (using version 8 so it sorts above any real version...)
    mk_python("8.6.1")
    mk_python("8.7.2")

    # Verify that if invoker is one of the pyenv-installations, it is properly detected
    depot = mocked_invoker(pyenv=".pyenv", base_prefix=".pyenv/versions/8.6.1")
    p8 = depot.find_python("8")
    p86 = depot.find_python("8.6")
    assert str(p8) == ".pyenv/versions/8.7.2 [cpython:8.7.2]"  # Latest version 8 (invoker doesn't take precedence)
    assert p86 is depot.invoker
    assert str(depot) == "2 scanned"
    assert depot.scanned == [p8, p86]
    assert depot.from_path == []

    mk_python("8.8.3", executable=False)
    mk_python("8.9.0")
    mk_python("miniconda3-4.7.12")

    # Create some PATH-style python installation mocks (using version 9 so it sorts higher than pyenv ones)
    mk_python("python", folder="foo", version="9.5.1")
    mk_python("python2", folder="foo", content=["foo; bar"])  # --version fails
    mk_python("python3", folder="foo", content=["foo"])  # Invalid: mocked _pv.py does not return the right number of lines
    mk_python("some-other-python-exe-name", folder="additional", version="8.5.0")
    mk_python("python2", folder="additional")  # Invalid version
    with runez.CurrentFolder("additional/bin"):
        runez.symlink("some-other-python-exe-name", "python")

    monkeypatch.setenv("PATH", "foo/bin:bar:additional/bin")
    scanner = pyenv_scanner(".pyenv:non-existent-folder")
    depot = PythonDepot(scanner=scanner, use_path=True)
    assert str(depot) == "4 scanned, 2 from PATH"
    r = depot.representation()
    assert "Available pythons:" in r
    assert "Available pythons from PATH:" in r

    assert len(depot.from_path) == 2
    assert len(depot.scanned) == 4
    assert depot.scan_path_env_var() is None  # Already scanned to try and find invoker
    p95 = depot.find_python("9.5.1")
    assert str(p95) == "foo/bin/python [cpython:9.5.1]"

    check_find_python(depot, "9", "foo/bin/python [cpython:9.5.1]")
    check_find_python(depot, "42.4", "42.4 [not available]")
    check_find_python(depot, "foo", "foo [not available]")
    check_find_python(depot, "python:43.0.0", "python:43.0.0 [not available]")

    with pytest.raises(runez.system.AbortException):
        depot.find_python("/bar", fatal=True)

    pbar = depot.find_python("/bar")
    assert str(pbar) == "/bar [not an executable]"
    assert pbar.problem
    assert not pbar.satisfies(depot.spec_from_text("python"))

    p8 = depot.find_python("8")
    p8a = depot.find_python(PythonSpec("8"))
    assert p8a is p8
    p86 = depot.find_python("8.6")
    p87 = depot.find_python("8.7")
    p88 = depot.find_python("8.8")
    p89 = depot.find_python("8.9")
    c = depot.find_python("conda")
    c47 = depot.find_python("conda:4.7")
    assert c47 is c
    assert depot.find_python(PythonSpec("conda47")) is c47
    assert depot.scanned == [p89, p87, p86, c47]

    assert p8.major == 8
    assert p88.major == 8
    assert str(p8) == ".pyenv/versions/8.9.0 [cpython:8.9.0]"
    assert str(p88) == "8.8 [not available]"
    assert str(c47) == ".pyenv/versions/miniconda3-4.7.12 [conda:4.7.12]"
    assert p8 is p89
    assert p8 == p89
    assert p8 != p88
    assert p8 != pbar
    assert p8.satisfies(PythonSpec("python"))
    assert p8.satisfies(PythonSpec("python8"))
    assert p8.satisfies(PythonSpec("py8.9.0"))
    assert not p8.satisfies(PythonSpec("py8.9.1"))
    assert c47.satisfies(PythonSpec("conda47"))
    assert len({p8, p89}) == 1
    assert len({p8, p89, p88}) == 2


def test_depot_adhoc(temp_folder, monkeypatch):
    depot = PythonDepot(use_path=False)
    p11 = depot.find_python("11.0.0")
    pfoo = depot.find_python("/foo")
    assert p11.problem == "not available"

    # Only paths are cached
    p11b = depot.find_python("11.0.0")
    assert p11 is not p11b
    assert p11 == p11b
    assert depot.find_python("/foo") == pfoo

    # Edge case: check we can still compare incomplete objects (missing spec.version here for 'pfoo')
    assert pfoo == pfoo
    assert not (pfoo < pfoo)
    assert not (pfoo > pfoo)
    assert pfoo < p11
    assert p11 > pfoo
    assert not (p11 < pfoo)
    assert not (pfoo > p11)

    # Edge case: comparison still works even when there is no spec
    pfoo.spec = None
    assert pfoo < p11

    mk_python("python", folder="some-path", version="11.0.0")
    py_path = os.path.realpath("some-path/bin/python")
    p11 = depot.find_python(py_path)
    assert depot.find_python("./some-path/") == p11
    assert depot.find_python("some-path/bin") == p11
    assert str(p11) == "some-path/bin/python [cpython:11.0.0]"


def mocked_invoker(**sysattrs):
    major = sysattrs.pop("major", 3)
    pyenv = sysattrs.pop("pyenv", None)
    use_path = sysattrs.pop("use_path", False)
    exe_exists = sysattrs.pop("exe_exists", True)
    sysattrs.setdefault("real_prefix", None)
    sysattrs.setdefault("base_prefix", "/usr")
    sysattrs.setdefault("prefix", sysattrs["base_prefix"])
    sysattrs.setdefault("executable", "%s/bin/python" % sysattrs["base_prefix"])
    sysattrs["version_info"] = (major, 7, 1)
    sysattrs["version"] = ".".join(str(s) for s in sysattrs["version_info"])
    scanner = None if not pyenv else pyenv_scanner(pyenv)
    with patch("runez.pyenv.os.path.realpath", side_effect=lambda x: x):
        with patch("runez.pyenv.sys") as mocked:
            for k, v in sysattrs.items():
                setattr(mocked, k, v)

            if isinstance(exe_exists, bool):
                with patch("runez.pyenv.is_executable", return_value=exe_exists):
                    return PythonDepot(scanner=scanner, use_path=use_path)

            with patch("runez.pyenv.is_executable", side_effect=exe_exists):
                return PythonDepot(scanner=scanner, use_path=use_path)


def test_invoker():
    depot = PythonDepot(use_path=False)
    assert depot.find_python(None) is depot.invoker
    assert depot.find_python("") is depot.invoker
    assert depot.find_python("py") is depot.invoker
    assert depot.find_python("python") is depot.invoker
    assert depot.find_python(depot.invoker.executable) is depot.invoker
    assert depot.find_python("invoker") is depot.invoker
    assert depot.find_python("%s" % sys.version_info[0]) is depot.invoker
    assert "invoker" in str(depot.invoker)

    # Linux case with py3
    depot = mocked_invoker()
    assert depot.invoker.executable == "/usr/bin/python3"
    assert depot.invoker.major == 3

    # Linux case without py3
    depot = mocked_invoker(major=2, real_prefix="/usr/local")
    assert depot.invoker.executable == "/usr/local/bin/python2"
    assert depot.invoker.major == 2

    # Linux case without py3 or py2 (but only /usr/bin/python)
    depot = mocked_invoker(major=2, exe_exists=lambda x: "python2" not in x)
    assert depot.invoker.executable == "/usr/bin/python"
    assert depot.invoker.major == 2

    # Use sys.executable when prefix can't be used to determine invoker
    depot = mocked_invoker(major=2, base_prefix=None, executable="/foo", exe_exists=False)
    assert depot.invoker.executable == "/foo"
    assert depot.invoker.major == 2

    # OSX py2 case
    depot = mocked_invoker(major=2, base_prefix="/System/Library/Frameworks/Python.framework/Versions/2.7")
    assert depot.invoker.executable == "/usr/bin/python2"
    assert depot.invoker.major == 2

    # OSX py3 case
    depot = mocked_invoker(base_prefix="/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.7")
    assert depot.invoker.executable == "/usr/bin/python3"
    assert depot.invoker.major == 3

    # OSX brew
    depot = mocked_invoker(base_prefix="/usr/local/Cellar/python@3.7/3.7.1_1/Frameworks/Python.framework/Versions/3.7")
    assert depot.invoker.executable == "/usr/local/bin/python3"
    assert depot.invoker.major == 3


def test_sorting(temp_folder):
    mk_python("3.6.1")
    mk_python("3.7.2")
    mk_python("3.8.3")
    mk_python("conda-4.6.1")
    mk_python("miniconda3-4.3.2")
    depot = PythonDepot(scanner=pyenv_scanner(".pyenv"), use_path=False)
    assert str(depot) == "5 scanned"
    versions = [p.spec.canonical for p in depot.scanned]
    assert versions == ["conda:4.6.1", "conda:4.3.2", "cpython:3.8.3", "cpython:3.7.2", "cpython:3.6.1"]


def check_spec(text, canonical):
    d = PythonSpec(text)
    assert d.text == text.strip()
    assert str(d) == canonical


def test_spec():
    assert PythonSpec.speccified(None) is None
    assert PythonSpec.speccified([]) is None
    assert PythonSpec.speccified([""]) == []
    assert PythonSpec.speccified(["", "foo"]) == [PythonSpec("foo")]
    assert PythonSpec.speccified(["", "foo"], strict=True) == []
    assert PythonSpec.speccified(["", "foo", "3.7"], strict=True) == [PythonSpec("3.7")]

    pnone = PythonSpec(None)
    assert str(pnone) == "cpython:"
    p37a = PythonSpec("py37")
    p37b = PythonSpec("python3.7")
    assert p37a == p37b
    assert pnone != p37a
    assert pnone < p37a
    assert not (pnone > p37a)
    assert len({p37a, p37b}) == 1
    assert len({p37a, p37b, pnone}) == 2

    invoker = PythonSpec("invoker")
    assert str(invoker) == "invoker"
    assert invoker.version.major == sys.version_info[0]

    p38 = PythonSpec("3.8")
    c38a = PythonSpec("conda:38")
    c38b = PythonSpec("conda:3.8")
    assert c38a != p38
    assert c38a.version == p38.version
    assert c38a == c38b

    check_spec("", "cpython:")
    check_spec(" ", "cpython:")
    check_spec(" : ", "cpython:")
    check_spec(" - ", "cpython:")
    check_spec("2", "cpython:2")
    check_spec("3", "cpython:3")
    check_spec("P3", "cpython:3")
    check_spec("py3", "cpython:3")
    check_spec(" pY 3 ", "cpython:3")
    check_spec("cpython:", "cpython:")
    check_spec("cpython-", "cpython:")
    check_spec("cpython3", "cpython:3")
    check_spec("python3", "cpython:3")
    check_spec(" python  3 ", "cpython:3")
    check_spec(" p3.7 ", "cpython:3.7")
    check_spec(" cpython:3.7 ", "cpython:3.7")

    # Various convenience notations
    check_spec("37", "cpython:3.7")
    check_spec("3.7", "cpython:3.7")
    check_spec("py37", "cpython:3.7")  # tox.ini style
    check_spec("py3.7", "cpython:3.7")
    check_spec("python37", "cpython:3.7")
    check_spec("python3.7", "cpython:3.7")

    # One separator OK
    check_spec(":37", "cpython:3.7")
    check_spec("-37", "cpython:3.7")
    check_spec("py:3.7", "cpython:3.7")
    check_spec("py-3.7", "cpython:3.7")

    # More than one separator not OK
    check_spec("::37", "?::37")
    check_spec(":-37", "?:-37")
    check_spec("--37", "?--37")
    check_spec("py::3.7", "?py::3.7")
    check_spec("py:-3.7", "?py:-3.7")
    check_spec("py--3.7", "?py--3.7")

    # Non-cpython families
    check_spec("pypy", "pypy:")
    check_spec("pypy36", "pypy:3.6")
    check_spec("pypy:37", "pypy:3.7")
    check_spec("pypy:3.8", "pypy:3.8")
    check_spec("conda", "conda:")
    check_spec("conda:38", "conda:3.8")
    check_spec("conda:3.9.1", "conda:3.9.1")
    check_spec("anaconda", "conda:")
    check_spec("anaconda3", "conda:")
    check_spec("miniconda", "conda:")
    check_spec("miniconda3", "conda:")
    check_spec("miniconda-3.18.3", "conda:3.18.3")
    check_spec("miniconda3-4.7.12", "conda:4.7.12")

    # Up to 3 version components are valid
    check_spec("391", "cpython:3.9.1")
    check_spec("3.9.1", "cpython:3.9.1")
    check_spec("py391", "cpython:3.9.1")

    # Invalid marked with starting '?' for canonical form
    check_spec("cpython:3.7a", "?cpython:3.7a")
    check_spec("miniconda3--4.7.1", "?miniconda3--4.7.1")
    check_spec("foo3.7", "?foo3.7")
    check_spec("3777", "?3777")  # Too many components
    check_spec("3.7.7.7", "?3.7.7.7")
    check_spec("python3:", "?python3:")  # Separator is in the wrong place
    check_spec("python3-", "?python3-")

    # Paths remain as-is
    check_spec("foo/python2.7", runez.short(runez.resolved_path("foo/python2.7")))
    check_spec("/foo/python2.7", "/foo/python2.7")
    check_spec("~/.pyenv/3.8.1", "~/.pyenv/3.8.1")


def import_pv():
    import runez._pv

    assert runez._pv


def test_venv(temp_folder, logged):
    depot = PythonDepot(use_path=False)
    import sys
    p = depot.find_python(sys.executable)
    assert p is depot.invoker
    assert not logged

    # Simulate an explicit reference to a venv python
    mk_python("8.6.1")
    mk_python("8.6.1", prefix="foo", base_prefix=".pyenv/versions/8.6.1", folder=".venv")
    assert str(depot) == "0 scanned"
    pvenv = depot.find_python(".venv/bin/python")
    assert str(depot) == "0 scanned"
    assert depot.find_python(".venv") == pvenv
    assert str(pvenv) == ".pyenv/versions/8.6.1 [cpython:8.6.1]"

    # Edge case: version is found via .pyenv first
    depot = PythonDepot(scanner=pyenv_scanner(".pyenv"), use_path=False)
    assert str(depot) == "1 scanned"
    pvenv = depot.find_python(".venv/bin/python")
    assert str(pvenv) == ".pyenv/versions/8.6.1 [cpython:8.6.1]"
    assert depot.scanned == [pvenv]

    # Trigger code coverage for private _pv module
    with runez.TempArgv(["dump"]):
        import_pv()
        assert logged


def test_unknown():
    depot = PythonDepot(use_path=False)
    p = depot.find_python("foo")
    assert str(p) == "foo [not available]"
    assert p.executable == "foo"
    assert p.major is None
    assert p.problem == "not available"
    assert p.spec.canonical == "?foo"
    assert p.spec.text == "foo"
    assert p.major is None
    assert p.version is None


def test_version():
    none = Version(None)
    assert str(none) == ""
    assert not none.is_valid

    empty = Version("")
    assert str(empty) == ""
    assert not empty.is_valid
    assert empty == none
    assert empty.major is None

    foo = Version("foo")
    assert str(foo) == "foo"
    assert not foo.is_valid
    assert not foo.components
    assert not foo.prerelease
    assert foo.major is None

    bogus = Version("1.2.3.4.5")
    assert str(bogus) == "1.2.3.4.5"
    assert not bogus.is_valid
    assert not bogus.components
    assert not bogus.prerelease

    v1 = Version("1")
    assert v1.components == (1, 0, 0, 0, 0)
    assert str(v1) == "1"
    assert empty < v1
    assert v1 > empty
    assert v1 != empty

    v1foo = Version("1foo")  # Ignore additional text
    assert v1 == v1foo

    vrc = Version("1.0rc4-foo")
    vdev = Version("1.0a4.dev5-foo")
    assert vrc < vdev
    assert str(vrc) == "1.0rc4"
    assert str(vdev) == "1.0a4.dev5"
    assert vrc.major == 1
    assert vrc.minor == 0
    assert vrc.patch == 0
    assert vrc.main == "1.0.0"

    # .from_text() can be used to filter out invalid versions as None
    assert Version.from_text("foo") is None
    assert Version.from_text("1.0rc4") == vrc

    # Version() can be used in sets/dicts
    s = set()
    s.add(vrc)
    assert vrc in s

    v11 = Version("1.1.2.3")
    v12 = Version("1.2.3")
    v12p = Version("1.2.3.post4")
    v20 = Version("2.0")
    v20d = Version("2.0.dev1")
    v3 = Version("3.0.1.2")
    assert v12 > v11
    assert v12p > v11
    assert v20 > v11
    assert v20d > v11
    assert v3 > v11
    assert v12p > v12
    assert v20 > v12
    assert v20d > v12
    assert v3 > v12
    assert v20 > v12p
    assert v20d > v12p
    assert v3 > v12p
    assert v20d > v20
    assert v3 > v20
    assert v3 > v20d
