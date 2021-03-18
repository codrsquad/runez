import os
import sys

import pytest
from mock import patch

import runez
from runez.pyenv import InvokerPython, PythonDepot, PythonFromPath, UnknownPython, Version


def mk_python(basename, prefix=None, base_prefix=None, executable=True, content=None, folder=None, version=None):
    if version is None and basename[0].isdigit():
        version = basename

    if folder is None:
        folder = os.path.join(".pyenv/versions", basename)

    path = runez.resolved_path(folder)
    if not prefix:
        prefix = path

    if not base_prefix:
        base_prefix = prefix

    if basename[0].isdigit():
        basename = "python"

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


def test_depot(temp_folder, monkeypatch):
    depot = PythonDepot(pyenv=None, use_invoker=False, use_path=False)
    depot.rescan(scan_path=True)
    assert not depot.available
    assert not depot.invalid

    # Create some pyenv-style python installation mocks
    mk_python("3.6.1")
    mk_python("3.7.2")
    mk_python("3.8.3", executable=False)
    mk_python("3.9.0")

    # Create some PATH-style python installation mocks
    mk_python("python", folder="foo", version="2.7.1")
    mk_python("python2", folder="foo")  # Invalid: no version
    mk_python("python3", folder="foo", content=["foo"])  # Invalid: mocked _pv.py does not return the right number of lines

    monkeypatch.setenv("PATH", "foo/bin:bar")
    depot = PythonDepot(pyenv=".pyenv:non-existent-folder", use_invoker=False)
    assert len(depot.invalid) == 1
    assert len(depot.available) == 3
    depot.rescan(scan_path=True)  # Scan PATH immediately
    assert len(depot.invalid) == 3
    assert len(depot.available) == 4

    depot = PythonDepot(pyenv=".pyenv:non-existent-folder", use_invoker=False)
    assert len(depot.invalid) == 1
    assert len(depot.available) == 3
    p26 = depot.find_python("2.7.1")  # This triggers an env-var scan because 2.7.1 is only found via $PATH
    assert len(depot.invalid) == 3
    assert len(depot.available) == 4

    assert str(p26) == "foo/bin/python [cpython:2.7.1]"
    check_find_python(depot, "2", "foo/bin/python [cpython:2.7.1]")
    check_find_python(depot, "2.6", "cpython:2.6 [not available]")
    check_find_python(depot, "foo", "?foo [not available]")
    check_find_python(depot, "python:11.0.0", "cpython:11.0.0 [not available]")

    with pytest.raises(runez.system.AbortException):
        depot.find_python("/bar", fatal=True)

    pbar = depot.find_python("/bar")
    assert pbar in depot.invalid
    assert str(pbar) == "/bar [not available]"
    assert pbar.problem
    assert not pbar.satisfies(depot.spec_from_text("python"))
    assert len(depot.invalid) == 4
    assert len(depot.available) == 4

    # Ensure we use cached object for 2nd lookup
    assert pbar is depot.find_python("/bar")
    assert pbar is depot.python_from_path("/bar")

    p3 = depot.find_python("3")
    p38 = depot.find_python("3.8")
    p39 = depot.find_python("3.9")
    assert p3.major == 3
    assert p38.major == 3
    assert str(p3) == ".pyenv/versions/3.9.0/bin/python [cpython:3.9.0]"
    assert str(p38) == "cpython:3.8 [not available]"
    assert str(p3) == p3.representation(include_origin=False)
    assert p3 is p39
    assert p3 == p39
    assert p3 != p38
    assert p3 != pbar
    assert p3.satisfies(depot.spec_from_text("python"))
    assert p3.satisfies(depot.spec_from_text("python3"))
    assert p3.satisfies(depot.spec_from_text("py3.9.0"))
    assert not p3.satisfies(depot.spec_from_text("py3.9.1"))


def test_depot_adhoc(temp_folder, monkeypatch):
    depot = PythonDepot(pyenv=None, use_path=False)
    p11 = depot.find_python("11.0.0")
    assert p11.problem == "not available"
    assert len(depot.invalid) == 0
    assert depot.available == [depot.invoker]

    mk_python("python", folder="some-path", version="11.0.0")
    py_path = os.path.realpath("some-path/bin/python")
    p11 = depot.find_python(py_path)
    assert depot.find_python("./some-path/") is p11
    assert depot.find_python("some-path/bin") is p11
    assert str(p11) == "some-path/bin/python [cpython:11.0.0]"
    assert p11.origin is depot.origin.adhoc
    assert depot.available == [p11, depot.invoker]

    p11b = PythonFromPath(depot, depot.origin.adhoc, py_path)
    assert p11b is not p11
    assert p11b == p11

    # Check caching
    assert depot.find_python(py_path) is p11
    assert depot.find_python("some-path/bin/python") is p11
    assert len(depot.invalid) == 0
    assert depot.available == [p11, depot.invoker]

    # Trigger a deferred find, with one valid one invalid installation
    mk_python("python2", folder="some-path", version="2.6.0")
    mk_python("python3", folder="some-path", content=["; foo"])
    monkeypatch.setenv("PATH", "some-path/bin")
    depot = PythonDepot(pyenv=None, use_path=True)
    p26 = depot.find_python("2.6")
    p11 = depot.find_python(py_path)  # Looking up p11 second so that it does not get found as "adhoc"
    assert p26.major == 2
    assert not p26.problem
    assert depot.available == [depot.invoker, p11, p26]  # Sorts 2nd because deferred
    check_find_python(depot, "2.6", "some-path/bin/python2 [cpython:2.6.0]")
    p3bad = depot.find_python("some-path/bin/python3")
    assert depot.invalid == [p3bad]

    assert depot.find_python("11.0.0") is p11
    assert depot.available == [depot.invoker, p11, p26]


def mocked_invoker(depot, **sysattrs):
    major = sysattrs.pop("major", 3)
    exe_exists = sysattrs.pop("exe_exists", True)
    sysattrs.setdefault("base_prefix", "/usr")
    sysattrs.setdefault("real_prefix", None)
    sysattrs.setdefault("version_info", (major, 7, 1))
    with patch("runez.pyenv.os.path.realpath", side_effect=lambda x: x):
        with patch("runez.pyenv.sys") as mocked:
            for k, v in sysattrs.items():
                setattr(mocked, k, v)

            if isinstance(exe_exists, bool):
                with patch("runez.pyenv.is_executable", return_value=exe_exists):
                    return InvokerPython(depot)

            with patch("runez.pyenv.is_executable", side_effect=exe_exists):
                return InvokerPython(depot)


def test_invoker():
    depot = PythonDepot(pyenv=None, use_invoker=False, use_path=False)
    assert not depot.invalid
    assert not depot.available

    depot = PythonDepot(pyenv=None, use_invoker=True, use_path=False)
    assert not depot.invalid
    assert depot.available == [depot.invoker]
    assert depot.find_python(None) is depot.invoker
    assert depot.find_python("") is depot.invoker
    assert depot.find_python("py") is depot.invoker
    assert depot.find_python("python") is depot.invoker
    assert depot.find_python(depot.invoker.executable) is depot.invoker
    assert depot.find_python("invoker") is depot.invoker
    assert depot.find_python("%s" % sys.version_info[0]) is depot.invoker
    assert "invoker" in depot.invoker.representation()
    assert not depot.invalid
    assert depot.available == [depot.invoker]

    p = depot.python_from_path(sys.executable)
    assert p.is_venv
    assert "[venv]" in str(p)
    assert len(depot.available) == 2

    # Linux case with py3
    p = mocked_invoker(depot)
    assert p.executable == "/usr/bin/python3"
    assert p.major == 3

    # Linux case without py3
    p = mocked_invoker(depot, major=2, real_prefix="/usr/local")
    assert p.executable == "/usr/local/bin/python2"
    assert p.major == 2

    # Linux case without py3 or py2 (but only /usr/bin/python)
    p = mocked_invoker(depot, major=2, exe_exists=lambda x: "python2" not in x)
    assert p.executable == "/usr/bin/python"
    assert p.major == 2

    # Use sys.executable when prefix can't be used to determine invoker
    p = mocked_invoker(depot, major=2, base_prefix=None, executable="/foo", exe_exists=False)
    assert p.executable == "/foo"
    assert p.major == 2

    # OSX py2 case
    p = mocked_invoker(depot, major=2, base_prefix="/System/Library/Frameworks/Python.framework/Versions/2.7")
    assert p.executable == "/usr/bin/python2"
    assert p.major == 2

    # OSX py3 case
    p = mocked_invoker(depot, base_prefix="/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.7")
    assert p.executable == "/usr/bin/python3"
    assert p.major == 3

    # OSX brew
    p = mocked_invoker(depot, base_prefix="/usr/local/Cellar/python@3.7/3.7.1_1/Frameworks/Python.framework/Versions/3.7")
    assert p.executable == "/usr/local/bin/python3"
    assert p.major == 3


def test_sorting(temp_folder):
    mk_python("3.6.1")
    mk_python("3.7.2")
    mk_python("3.8.3")
    mk_python("3.6.0", folder=".pyenv/versions/conda-4.6.1")
    mk_python("3.9.2", folder=".pyenv/versions/miniconda3-4.3.2")
    depot = PythonDepot(pyenv=".pyenv", use_invoker=False, use_path=False)
    assert str(depot.families) == "cpython,pypy,conda"
    assert len(depot.available) == 5
    versions = [p.spec.canonical for p in depot.available]
    assert versions == ["cpython:3.8.3", "cpython:3.7.2", "cpython:3.6.1", "conda:4.6.1", "conda:4.3.2"]


def check_spec(depot, text, canonical):
    d = depot.spec_from_text(text)
    assert d.text == text.strip()
    assert str(d) == canonical


def test_spec():
    depot = PythonDepot(pyenv=None, use_invoker=False, use_path=False)
    p37a = depot.spec_from_text("py37")
    p37b = depot.spec_from_text("python3.7")
    p38 = depot.spec_from_text("3.8")
    p381 = depot.spec_from_text("3.8.1")
    assert p37a == p37b
    assert p37a < p38 < p381
    assert p381 > p37b

    c381 = depot.spec_from_text("conda:381")
    c392 = depot.spec_from_text("conda:3.9.2")
    assert c381 != p381
    assert c381.version == p381.version
    assert c381 < p381
    assert c392 < p381  # because 'family' sorts lower

    # Sorting on non-cpython families first, then by version, cpython family sorts highest
    pp381 = depot.spec_from_text("pypy:3.8.1")
    pp39 = depot.spec_from_text("pypy:39")
    assert sorted([p37a, p38, p381, c381, c392, pp381, pp39]) == [c381, c392, pp381, pp39, p37a, p38, p381]

    check_spec(depot, "", "cpython")
    check_spec(depot, " ", "cpython")
    check_spec(depot, "2", "cpython:2")
    check_spec(depot, "3", "cpython:3")
    check_spec(depot, "P3", "cpython:3")
    check_spec(depot, "py3", "cpython:3")
    check_spec(depot, " pY 3 ", "cpython:3")
    check_spec(depot, "python3", "cpython:3")
    check_spec(depot, " python  3 ", "cpython:3")
    check_spec(depot, " p3.7 ", "cpython:3.7")
    check_spec(depot, " cpython:3.7 ", "cpython:3.7")

    # Various convenience notations
    check_spec(depot, "37", "cpython:3.7")
    check_spec(depot, "3.7", "cpython:3.7")
    check_spec(depot, "py37", "cpython:3.7")  # tox.ini style
    check_spec(depot, "py3.7", "cpython:3.7")
    check_spec(depot, "python37", "cpython:3.7")
    check_spec(depot, "python3.7", "cpython:3.7")

    # One separator OK
    check_spec(depot, ":37", "cpython:3.7")
    check_spec(depot, "-37", "cpython:3.7")
    check_spec(depot, "py:3.7", "cpython:3.7")
    check_spec(depot, "py-3.7", "cpython:3.7")

    # More than one separator not OK
    check_spec(depot, "::37", "?::37")
    check_spec(depot, ":-37", "?:-37")
    check_spec(depot, "--37", "?--37")
    check_spec(depot, "py::3.7", "?py::3.7")
    check_spec(depot, "py:-3.7", "?py:-3.7")
    check_spec(depot, "py--3.7", "?py--3.7")

    # Non-cpython families
    check_spec(depot, "pypy36", "pypy:3.6")
    check_spec(depot, "pypy:37", "pypy:3.7")
    check_spec(depot, "pypy:3.8", "pypy:3.8")
    check_spec(depot, "conda:38", "conda:3.8")
    check_spec(depot, "conda:3.9.1", "conda:3.9.1")
    check_spec(depot, "miniconda-3.18.3", "conda:3.18.3")
    check_spec(depot, "miniconda3-4.7.12", "conda:4.7.12")

    # Up to 3 version components are valid
    check_spec(depot, "391", "cpython:3.9.1")
    check_spec(depot, "3.9.1", "cpython:3.9.1")
    check_spec(depot, "py391", "cpython:3.9.1")

    # Invalid marked with starting '?' for canonical form
    check_spec(depot, "cpython:3.7a", "?cpython:3.7a")
    check_spec(depot, "miniconda3--4.7.1", "?miniconda3--4.7.1")
    check_spec(depot, " : ", "?:")
    check_spec(depot, " - ", "?-")
    check_spec(depot, "foo3.7", "?foo3.7")
    check_spec(depot, "3777", "?3777")  # Too many components
    check_spec(depot, "3.7.7.7", "?3.7.7.7")

    # Full path remains as-is
    check_spec(depot, "/foo/python2.7", "/foo/python2.7")
    check_spec(depot, "/foo/python2.7", "/foo/python2.7")
    check_spec(depot, "~/.pyenv/3.8.1", "~/.pyenv/3.8.1")


def import_pv():
    import runez._pv

    assert runez._pv


def test_venv(logged):
    depot = PythonDepot(pyenv=None, use_invoker=False, use_path=False)
    import sys
    p = PythonFromPath(depot, depot.origin.adhoc, sys.executable)
    assert p.executable == sys.executable
    assert sys.executable in p.equivalent
    assert p.is_venv
    assert not logged

    # Trigger code coverage for private _pv module
    with runez.TempArgv(["dump"]):
        import_pv()
        assert logged


def test_unknown():
    depot = PythonDepot(pyenv=None, use_invoker=False, use_path=False)
    p = UnknownPython(depot, depot.origin.adhoc, "foo")
    assert str(p) == "foo [not available]"
    assert p.executable == "foo"
    assert not p.is_venv
    assert p.major is None
    assert p.problem == "not available"
    assert p.spec.canonical == "?foo"
    assert p.family is depot.families.default_family
    assert p.spec.text == "foo"
    assert p.major is None
    assert p.version is None


def test_version():
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
