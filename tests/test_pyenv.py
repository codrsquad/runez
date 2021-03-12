import os
import sys

import pytest
from mock import patch

import runez
from runez.pyenv import InvokerPython, PythonDepot, PythonFromPath, PythonSpec, Version


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

    return PythonFromPath(path)


def check_find_python(depot, spec, expected):
    p = depot.find_python(spec)
    assert str(p) == expected


def test_depot(temp_folder, monkeypatch):
    depot = PythonDepot()
    assert depot.find_python(None) is depot.invoker
    assert depot.find_python("") is depot.invoker
    assert depot.find_python("py") is depot.invoker
    assert depot.find_python("python") is depot.invoker
    assert depot.find_python(depot.invoker.executable) is depot.invoker
    assert not depot.invalid
    assert depot.available == [depot.invoker]
    assert depot.invoker.spec.given_name == "invoker"
    assert depot.find_python("invoker") is depot.invoker
    assert depot.find_python("%s" % sys.version_info[0]) is depot.invoker
    assert "invoker" in depot.invoker.colored_representation()

    depot.reset()
    assert not depot.invalid
    assert not depot.available

    # Create some pyenv-style python installation mocks
    mk_python("3.6.1")
    mk_python("3.7.2")
    mk_python("3.8.3", executable=False)
    mk_python("3.9.0")

    # Create some PATH-style python installation mocks
    mk_python("python", folder="foo", version="2.7.1")
    mk_python("python2", folder="foo")  # Invalid: no version
    mk_python("python3", folder="foo", content=["foo"])  # Invalid: mocked _pv.py does not return the right number of lines

    depot.scan_pyenv(".pyenv:non-existent-folder")
    assert len(depot.invalid) == 1
    assert len(depot.available) == 3

    depot.register_deferred("no-such-python", "")
    assert depot.deferred == depot.DEFAULT_DEFERRED + ["no-such-python"]
    depot.deferred = ["", "$PATH", "no-such-python"]

    monkeypatch.setenv("PATH", "foo/bin:bar")
    scanned = depot.scan_deferred()
    assert len(scanned) == 1
    from_path = depot.scan_path()
    assert not from_path  # We already scanned $PATH via deferred
    assert len(depot.invalid) == 3
    assert len(depot.available) == 4

    check_find_python(depot, "2", "foo/bin/python [cpython:2.7.1]")
    check_find_python(depot, "2.6", "2.6 [not available]")
    check_find_python(depot, "foo", "foo [not available]")
    check_find_python(depot, "python:3.0.0", "python:3.0.0 [not available]")

    with pytest.raises(runez.system.AbortException):
        depot.find_python("/bar", fatal=True)

    pbar = depot.find_python("/bar")
    assert str(pbar) == "/bar [can't be introspected: /bar is not installed]"
    assert pbar.problem
    assert not pbar.satisfies(PythonSpec("python"))

    p3 = depot.find_python("3")
    p38 = depot.find_python("3.8")
    p39 = depot.find_python("3.9")
    assert str(p3) == ".pyenv/versions/3.9.0/bin/python [cpython:3.9.0]"
    assert str(p38) == "3.8 [not available]"
    assert str(p3) == p3.colored_representation()
    assert p3 is p39
    assert p3 == p39
    assert p3 != p38
    assert p3 != pbar
    assert p3.satisfies(PythonSpec("python"))
    assert p3.satisfies(PythonSpec("python3"))
    assert p3.satisfies(PythonSpec("py3.9.0"))
    assert not p3.satisfies(PythonSpec("py3.9.1"))

    mk_python("python", folder="extra", version="3.0.0")
    extra_path = os.path.realpath("extra/bin/python")
    pextra1 = depot.find_python(extra_path)
    pextra2 = PythonFromPath(extra_path)
    assert str(pextra1) == "extra/bin/python [cpython:3.0.0]"
    assert pextra2 != p3
    assert pextra2 is not pextra1
    assert pextra2 == pextra1
    assert pextra1.satisfies(PythonSpec(pextra1.executable))
    pextra3 = depot.find_python("./extra/")
    assert pextra3 == pextra1

    # Trigger a deferred find
    assert len(depot.invalid) == 3
    assert len(depot.available) == 5
    mk_python("python2", folder="extra", version="2.6.0")
    monkeypatch.setenv("PATH", "extra/bin")
    depot.deferred = ["$PATH"]
    p26 = depot.find_python("2.6")
    assert not p26.problem
    assert len(depot.available) == 6
    check_find_python(depot, "2.6", "extra/bin/python2 [cpython:2.6.0]")

    # Trigger a deferred find by path
    depot.reset()
    assert not depot.invalid
    assert not depot.available
    depot.deferred = []
    pextra = depot.find_python("3.0.0")
    assert pextra.problem == "not available"
    depot.deferred = [extra_path]
    pextra = depot.find_python("3.0.0")
    assert not pextra.problem
    assert pextra == pextra1
    assert len(depot.available) == 2  # Invoker is auto-added


def mocked_invoker(**sysattrs):
    major = sysattrs.pop("major", 3)
    exe_exists = sysattrs.pop("exe_exists", True)
    sysattrs.setdefault("implementation", None)
    sysattrs.setdefault("base_prefix", "/usr")
    sysattrs.setdefault("real_prefix", None)
    sysattrs.setdefault("version_info", (major, 7, 1))
    with patch("runez.pyenv.sys") as mocked:
        for k, v in sysattrs.items():
            setattr(mocked, k, v)

        if isinstance(exe_exists, bool):
            with patch("runez.pyenv.is_executable", return_value=exe_exists):
                return InvokerPython()

        with patch("runez.pyenv.is_executable", side_effect=exe_exists):
            return InvokerPython()


def test_invoker():
    # Linux case with py3
    p = mocked_invoker()
    assert p.executable == "/usr/bin/python3"
    assert p.spec.version.major == 3

    # Linux case without py3
    p = mocked_invoker(major=2, real_prefix="/usr/local")
    assert p.executable == "/usr/local/bin/python2"
    assert p.spec.version.major == 2

    # Linux case without py3 or py2 (but only /usr/bin/python)
    p = mocked_invoker(major=2, exe_exists=lambda x: "python2" not in x)
    assert p.executable == "/usr/bin/python"
    assert p.spec.version.major == 2

    # Use sys.executable when prefix can't be used to determine invoker
    p = mocked_invoker(major=2, base_prefix=None, executable="/foo", exe_exists=False)
    assert p.executable == "/foo"
    assert p.spec.version.major == 2

    # OSX py2 case
    p = mocked_invoker(major=2, base_prefix="/System/Library/Frameworks/Python.framework/Versions/2.7")
    assert p.executable == "/usr/bin/python2"
    assert p.spec.version.major == 2

    # OSX py3 case
    p = mocked_invoker(base_prefix="/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.7")
    assert p.executable == "/usr/bin/python3"
    assert p.spec.version.major == 3


def check_spec(text, canonical, family="cpython"):
    d = PythonSpec(text)
    assert d.text == (text.strip() if text else "")
    assert str(d) == canonical
    assert d.family == family


def test_spec():
    p37a = PythonSpec("py37")
    p37b = PythonSpec("python3.7")
    p38 = PythonSpec("3.8")
    p381 = PythonSpec("3.8.1")
    assert p37a == p37b
    assert p37a < p38 < p381
    assert p381 > p37b

    c381 = PythonSpec("conda:381")
    c392 = PythonSpec("conda:3.9.2")
    assert c381 != p381
    assert c381.version == p381.version
    assert c381 < p381
    assert c392 < p381  # because 'family' sorts lower

    # Sorting on non-cpython families first, then by version, cpython family sorts highest
    pp381 = PythonSpec("pypy:3.8.1")
    pp39 = PythonSpec("pypy:39")
    assert sorted([p37a, p38, p381, c381, c392, pp381, pp39]) == [c381, c392, pp381, pp39, p37a, p38, p381]

    check_spec(None, "cpython")
    check_spec("", "cpython")
    check_spec(" ", "cpython")
    check_spec("2", "cpython:2")
    check_spec("3", "cpython:3")
    check_spec("P3", "cpython:3")
    check_spec("py3", "cpython:3")
    check_spec(" pY 3 ", "cpython:3")
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
    check_spec("pypy36", "pypy:3.6", "pypy")
    check_spec("pypy:37", "pypy:3.7", "pypy")
    check_spec("pypy:3.8", "pypy:3.8", "pypy")
    check_spec("conda:38", "conda:3.8", "conda")
    check_spec("conda:3.9.1", "conda:3.9.1", "conda")
    check_spec("miniconda-3.18.3", "conda:3.18.3", "conda")
    check_spec("miniconda3-4.7.12", "conda:4.7.12", "conda")

    # Up to 3 version components are valid
    check_spec("391", "cpython:3.9.1")
    check_spec("3.9.1", "cpython:3.9.1")
    check_spec("py391", "cpython:3.9.1")

    # Invalid marked with starting '?' for canonical form
    check_spec("cpython:3.7a", "?cpython:3.7a")
    check_spec("miniconda3--4.7.1", "?miniconda3--4.7.1", "conda")
    check_spec(" : ", "?:")
    check_spec(" - ", "?-")
    check_spec("foo3.7", "?foo3.7")
    check_spec("3777", "?3777")  # Too many components
    check_spec("3.7.7.7", "?3.7.7.7")

    # Full path remains as-is
    check_spec("/foo/python2.7", "/foo/python2.7")
    check_spec("/foo/python2.7", "/foo/python2.7")
    check_spec("~/.pyenv/3.8.1", "~/.pyenv/3.8.1")


def test_venv(logged):
    import sys
    p = PythonFromPath(sys.executable)
    assert p.executable == sys.executable
    assert sys.executable in p.equivalent
    assert p.is_venv
    assert not logged

    import runez._pv  # noqa

    assert logged
    lines = logged.stdout.contents().splitlines()
    assert lines[0].startswith("%s " % ".".join(str(c) for c in sys.version_info[:3]))
    assert sys.prefix == lines[1]
    assert sys.base_prefix == lines[2]


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
