import os
import re
import sys
from unittest.mock import patch

import pytest

import runez
from runez.http import RestClient
from runez.pyenv import PypiStd, PythonDepot, PythonInstallation, PythonInstallationScanner, PythonSpec, Version


RE_VERSION = re.compile(r"^(.*)(\d+\.\d+.\d+)$")
PYPI_CLIENT = RestClient("https://example.com/pypi")


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
    runez.write(path, content, logger=None)
    if executable:
        runez.make_executable(path, logger=None)


def check_find_python(depot, spec, expected):
    p = depot.find_python(spec)
    assert str(p) == expected


def test_depot(temp_folder, monkeypatch, logged):
    # Create some pyenv-style python installation mocks (using version 8 so it sorts above any real version...)
    mk_python("8.6.1")
    mk_python("8.7.2")
    runez.symlink("8.6.1", ".pyenv/versions/8.6", must_exist=False, logger=None)

    # Verify that if invoker is one of the pyenv-installations, it is properly detected
    depot = mocked_invoker(pyenv=".pyenv", base_prefix=".pyenv/versions/8.6.1", version_info=(8, 6, 1))
    p8 = depot.find_python("8")
    p86 = depot.find_python("8.6")
    assert str(p8) == ".pyenv/versions/8.7.2 [cpython:8.7.2]"  # Latest version 8 (invoker doesn't take precedence)
    assert p8.folder == runez.to_path(".pyenv/versions/8.7.2/bin").absolute()
    assert p86 is depot.invoker
    assert str(depot) == "2 scanned"
    assert depot.scanned == [p8, p86]
    assert depot.from_path == []
    assert not logged

    mk_python("8.8.3", executable=False)
    mk_python("8.9.0")
    mk_python("miniconda3-4.7.12")

    # Create some PATH-style python installation mocks (using version 9 so it sorts higher than pyenv ones)
    mk_python("python", folder="path1", version="9.5.1")
    mk_python("python3", folder="path1", content=["foo"])  # Invalid: mocked _pv.py does not return the right number of lines
    mk_python("python", folder="path2", content=["foo; bar"])  # --version fails
    mk_python("some-other-python-exe-name", folder="path3", version="8.5.0")
    mk_python("python3", folder="path3")  # Invalid version
    with runez.CurrentFolder("path3/bin"):
        runez.symlink("some-other-python-exe-name", "python", logger=None)

    monkeypatch.setenv("PATH", "bar:path1/bin:path2/bin:path3/bin")
    scanner = PythonInstallationScanner(".pyenv")
    assert str(scanner) == "portable python [.pyenv]"
    depot = PythonDepot(scanner=scanner, use_path=True)
    assert str(depot) == "4 scanned, 2 from PATH"
    r = depot.representation()
    assert "Installed portable python:" in r
    assert "Available pythons from PATH:" in r

    depot.find_preferred_python("8.7.2,8.9.0", "8.7", "8.10")
    assert depot.preferred_python.version == "8.7.2"

    depot.find_preferred_python("8.7.2,8.9.0", "8.7", "8.8")
    assert depot.preferred_python.version == "8.9.0"
    assert depot.find_python(None) is depot.preferred_python
    assert depot.find_python("8") is depot.preferred_python

    depot.find_preferred_python("8.7.2,8.9.0", "10.7", "10.8")
    assert depot.preferred_python is None

    depot.find_preferred_python("")
    assert depot.preferred_python is None

    assert len(depot.from_path) == 2
    assert len(depot.scanned) == 4
    assert depot.scan_path_env_var() is None  # Already scanned to try and find invoker
    p95 = depot.find_python("9.5.1")
    assert str(p95) == "path1/bin/python [cpython:9.5.1]"

    check_find_python(depot, "9", "path1/bin/python [cpython:9.5.1]")
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

    # Edge case: comparison still works even when there is no spec, arbitrarily sort no spec lower...
    pfoo.spec = None
    assert pfoo < p11

    mk_python("python", folder="some-path", version="11.0.0")
    py_path = os.path.realpath("some-path/bin/python")
    p11 = depot.find_python(py_path)
    assert depot.find_python("./some-path/") == p11
    assert depot.find_python("some-path/bin") == p11
    assert str(p11) == "some-path/bin/python [cpython:11.0.0]"


def test_empty_depot():
    depot = PythonDepot(use_path=False)
    assert str(depot) == "0 scanned"
    assert depot.from_path == []
    assert depot.scanned == []

    assert depot.find_python(depot.invoker) is depot.invoker
    assert depot.find_python(PythonSpec(depot.invoker.executable)) is depot.invoker
    assert depot.find_python(PythonSpec("invoker")) is depot.invoker
    assert depot.find_python("invoker") is depot.invoker
    assert depot.find_python(depot.invoker.spec.family) is depot.invoker
    assert depot.representation() == ""

    p = depot.find_python("foo")
    assert str(p) == "foo [not available]"
    assert repr(p) == "foo [not available]"
    assert p.problem == "not available"
    assert str(depot) == "0 scanned"


def mocked_invoker(**sysattrs):
    major = sysattrs.pop("major", 3)
    pyenv = sysattrs.pop("pyenv", None)
    use_path = sysattrs.pop("use_path", False)
    exe_exists = sysattrs.pop("exe_exists", True)
    sysattrs.setdefault("base_prefix", "/usr")
    sysattrs.setdefault("prefix", sysattrs["base_prefix"])
    sysattrs["base_prefix"] = runez.resolved_path(sysattrs["base_prefix"])
    sysattrs["prefix"] = runez.resolved_path(sysattrs["prefix"])
    sysattrs.setdefault("executable", "%s/bin/python" % sysattrs["base_prefix"])
    sysattrs.setdefault("version_info", (major, 7, 1))
    sysattrs.setdefault("version", ".".join(str(s) for s in sysattrs["version_info"]))
    scanner = None if not pyenv else PythonInstallationScanner(pyenv)
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
    assert str(depot.invoker) == repr(depot.invoker)  # Identical when coloring is off

    # Linux case with py3
    depot = mocked_invoker()
    assert depot.invoker.executable == "/usr/bin/python3.7"
    assert depot.invoker.folder == runez.to_path("/usr/bin")
    assert depot.invoker.major == 3

    # Linux case without py3
    depot = mocked_invoker(major=2, base_prefix="/usr/local")
    assert depot.invoker.executable == "/usr/local/bin/python2.7"
    assert depot.invoker.major == 2

    # Linux case with only /usr/bin/python
    depot = mocked_invoker(major=2, exe_exists=lambda x: "python2" not in x and "python3" not in x)
    assert depot.invoker.executable == "/usr/bin/python"
    assert depot.invoker.major == 2

    # Use sys.executable when prefix can't be used to determine invoker
    depot = mocked_invoker(major=2, base_prefix=None, executable="/foo", exe_exists=False)
    assert depot.invoker.executable == "/foo"
    assert depot.invoker.major == 2

    # macos silly path choices
    depot = mocked_invoker(major=2, base_prefix="/System/Library/Frameworks/Python.framework/Versions/2.7")
    assert depot.invoker.executable == "/usr/bin/python2"
    assert depot.invoker.major == 2

    depot = mocked_invoker(base_prefix="/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.7")
    assert depot.invoker.executable == "/usr/bin/python3"
    assert depot.invoker.major == 3

    depot = mocked_invoker(base_prefix="/usr/local/Cellar/python@3.7/3.7.1_1/Frameworks/Python.framework/Versions/3.7")
    assert depot.invoker.executable == "/usr/local/bin/python3"
    assert depot.invoker.major == 3


def test_pypi_standardized_naming():
    assert not PypiStd.is_acceptable(None)
    assert not PypiStd.is_acceptable(1)
    assert not PypiStd.is_acceptable("")
    assert not PypiStd.is_acceptable("a")  # Don't bother with one letter packages
    assert not PypiStd.is_acceptable("1a")  # Don't bother with anything that does start with a letter
    assert not PypiStd.is_acceptable("-a")
    assert not PypiStd.is_acceptable(".a")
    assert not PypiStd.is_acceptable("a.")  # Must end with a letter or number
    assert not PypiStd.is_acceptable("a b")  # No spaces plz

    assert PypiStd.is_acceptable("a1")
    assert PypiStd.is_acceptable("aB")
    assert PypiStd.is_acceptable("foo")
    assert PypiStd.is_acceptable("Foo_1.0")

    assert PypiStd.std_package_name(None) is None
    assert PypiStd.std_package_name(5) is None
    assert PypiStd.std_package_name("") is None
    assert PypiStd.std_package_name("-a-") is None
    assert PypiStd.std_package_name("a") is None
    assert PypiStd.std_package_name("foo") == "foo"
    assert PypiStd.std_package_name("Foo") == "foo"
    assert PypiStd.std_package_name("A__b-c_1.0") == "a-b-c-1-0"
    assert PypiStd.std_package_name("some_-Test") == "some-test"
    assert PypiStd.std_package_name("a_-_-.-_.--b") == "a-b"

    assert PypiStd.std_wheel_basename(None) is None
    assert PypiStd.std_package_name(10.1) is None
    assert PypiStd.std_wheel_basename("") is None
    assert PypiStd.std_wheel_basename("a.b_-_1.5--c") == "a.b_1.5_c"
    assert PypiStd.std_wheel_basename("a.b_-___1.5--c") == "a.b_1.5_c"


P_BLACK = """
<html><head><title>Simple Index</title><meta name="api-version" value="2" /></head><body>
<a href="/pypi/packages/pypi-public/black/black-18.3a0-py3-none-any.whl#sha256=..."</a><br/>
<a href="/pypi/packages/pypi-public/black/black-18.3a0.tar.gz#sha256=...">black-18.3a0.tar.gz</a><br/>
<a href="/pypi/packages/pypi-public/black/black-18.3a1-py3-none-any.whl#sha256=..."
"""

P_FUNKY = """
href="funky-proj/funky.proj-1.3.0+dirty_custom-py3-none-any.whl#sha256=..."
href="funky-proj/funky.proj-1.3.0_custom.tar.gz#sha256=..."
"""

P_PICKLEY = {
  "info": {"version": "2.5.6.dev1"},
  "releases": {
    "2.5.3": [{"filename": "pickley-2.5.3-py2.py3-none-any.whl", "yanked": True}, {"filename": "oops-bad-filename"}],
    "2.5.4": [{"filename": "pickley-2.5.4-py2.py3-none-any.whl", "upload_time": "2012-01-22T05:08:17"}],
    "2.5.5": [{"filename": "pickley-2.5.5-py2.py3-none-any.whl"}, {"filename": "pickley-2.5.5.tar.gz"}]
  }
}

P_SHELL_FUNCTOOLS = """
<html><head><title>Simple Index</title><meta name="api-version" value="2" /></head><body>

# 1.8.1 intentionally malformed
<a href="/pypi/shell-functools/shell_functools-1.8.1!1-py2.py3-none-any.whl9#">shell_functools-1.8.1-py2.py3-none-any.whl</a><br/>
<a href="/pypi/shell-functools/shell-functools-1.8.1!1.tar.gz#">shell-functools-1.8.1.tar.gz</a><br/>

<a href="/pypi/shell-functools/shell_functools-1.9.9+local-py2.py3-none-any.whl#sha...">shell_functools-1.9.9-py2.py3-none-any.whl</a><br/>
<a href="/pypi/shell-functools/shell-functools-1.9.9+local.tar.gz#sha256=ff...">shell-functools-1.9.9.tar.gz</a><br/>
<a href="/pypi/shell-functools/shell_functools-1.9.11-py2.py3-none-any.whl#sha256=...">shell_functools-1.9.11-py2.py3-none-any.whl</a><br/>
<a href="/pypi/shell-functools/shell-functools-1.9.11.tar.gz#sha256=ca...">shell-functools-1.9.11.tar.gz</a><br/>
</body></html>
"""


@PYPI_CLIENT.mock({
    "shell-functools/": P_SHELL_FUNCTOOLS,
    "https://pypi.org/pypi/black/json": P_BLACK,
    "https://pypi.org/pypi/foo/json": {"info": {"version": "1.2.3"}},
    "https://pypi.org/pypi/pickley/json": P_PICKLEY,
    "https://pypi.org/pypi/funky-proj/json": P_FUNKY,
})
def test_pypi_parsing():
    assert PypiStd.pypi_response("-invalid-") is None
    assert PypiStd.latest_pypi_version("shell_functools", index=PYPI_CLIENT.base_url) == Version("1.9.11")
    assert PypiStd.latest_pypi_version("foo") == Version("1.2.3")  # Vanilla case
    assert PypiStd.latest_pypi_version("pickley") == Version("2.5.5")  # Pre-release ignored
    assert PypiStd.latest_pypi_version("pickley", include_prerelease=True) == Version("2.5.6.dev1")

    assert sorted(PypiStd.ls_pypi("foo")) == []

    sample = sorted(PypiStd.ls_pypi("shell-functools", client=PYPI_CLIENT, source="s1"))
    assert len(sample) == 5
    assert str(sample[0]) == "shell-functools/shell-functools-1.8.1!1.tar.gz"
    assert sample[0].version == Version("1.8.1")
    assert not sample[0].is_dirty
    assert sample[0].category == "sdist"

    pickley = sorted(PypiStd.ls_pypi("pickley", source="s1"))
    assert len(pickley) == 3
    assert pickley[0] < sample[0]  # Alphabetical sort for same-source artifacts
    assert pickley[0].last_modified.year == 2012

    assert sample[3].version == Version("1.9.11")
    assert not sample[3].is_wheel
    assert sample[4].version == Version("1.9.11")
    assert sample[4].category == "wheel"
    assert sample[4].is_wheel
    assert sample[4].tags == "py2.py3-none-any"
    assert sample[3] < sample[4]  # Source distribution before wheel
    assert sample[3] != sample[4]

    with pytest.raises(TypeError):
        _ = sample[3] < "foo"

    black = sorted(PypiStd.ls_pypi("black"))  # All versions are pre-releases
    assert len(black) == 3
    assert black[0].version.prerelease

    funky = sorted(PypiStd.ls_pypi("funky-proj", source=None))
    assert len(funky) == 2
    assert funky[0].package_name == "funky.proj"
    assert funky[0].pypi_name == "funky-proj"
    assert funky[1].is_dirty
    assert black[0] < funky[0]  # Alphabetical sort when both have no source
    assert funky[0] < sample[4]  # Arbitrary: no-source sorts lowest...


def test_sorting(temp_folder):
    mk_python("3.6.1")
    mk_python("3.7.2")
    mk_python("3.8.3")
    mk_python("conda-4.6.1")
    mk_python("miniconda3-4.3.2")
    depot = PythonDepot(scanner=PythonInstallationScanner(".pyenv"), use_path=False)
    assert str(depot) == "5 scanned"
    versions = [p.spec.canonical for p in depot.scanned]
    assert versions == ["conda:4.6.1", "conda:4.3.2", "cpython:3.8.3", "cpython:3.7.2", "cpython:3.6.1"]


def check_spec(text, canonical):
    d = PythonSpec(text)
    assert d.text == runez.stringified(text).strip()
    assert str(d) == canonical


def test_spec():
    invoker = PythonSpec("invoker")
    assert invoker.family
    assert invoker.version
    assert str(invoker) == "invoker"
    assert PythonSpec.speccified(None) == []
    assert PythonSpec.speccified([]) == []
    assert PythonSpec.speccified([None, "", None]) == []
    assert PythonSpec.speccified([""]) == []
    assert PythonSpec.speccified(["", "foo"]) == [PythonSpec("foo")]
    assert PythonSpec.speccified(["", "foo"], strict=True) == []
    assert PythonSpec.speccified(["", "foo", "3.7"], strict=True) == [PythonSpec("3.7")]
    assert PythonSpec.speccified([2.7, 3.9]) == [PythonSpec("2.7"), PythonSpec("3.9")]
    assert PythonSpec.speccified("27") == [PythonSpec("2.7")]
    assert PythonSpec.speccified("39,2.7") == [PythonSpec("3.9"), PythonSpec("2.7")]
    assert PythonSpec.speccified("2.7.7a", strict=True) == []

    pnone = PythonSpec(None)
    assert pnone == invoker
    assert PythonSpec.to_spec(None) == invoker
    assert PythonSpec.to_spec(pnone) is pnone
    p32a = PythonSpec("py32")
    p32b = PythonSpec("python3.2")
    assert p32a == p32b
    assert pnone != p32a
    assert pnone > p32a
    assert not (pnone < p32a)
    assert len({p32a, p32b}) == 1
    assert len({p32a, p32b, pnone}) == 2

    assert not p32a.satisfies(pnone)
    assert not pnone.satisfies(p32a)

    invoker = PythonSpec("invoker")
    assert str(invoker) == "invoker"
    assert invoker.version.major == sys.version_info[0]

    p38plus = PythonSpec("3.8+")
    assert not p32a.satisfies(p38plus)
    assert not p32b.satisfies(p38plus)

    p38 = PythonSpec("3.8")
    c38a = PythonSpec("conda:38")
    c38b = PythonSpec("conda:3.8")
    assert p38.satisfies(p38plus)
    assert c38a != p38
    assert c38a.version == p38.version
    assert c38a == c38b

    p310 = PythonSpec("3.10.0")
    p310rc = PythonSpec("3.10.0rc1")
    assert p310rc < p310
    assert p310 > p310rc

    p39 = PythonSpec("3.9")
    p395 = PythonSpec("3.9.5")
    assert p39.satisfies(p38plus)
    assert p395.satisfies(p38plus)

    assert p38.represented() == "3.8"
    assert p38.represented(compact=None) == "cpython:3.8"
    assert p38.represented(compact=False) == "cpython:3.8"
    assert p38.represented(compact=True) == "3.8"
    assert p38.represented(compact="cpython") == "3.8"
    assert p38.represented(compact=["cpython", "conda"]) == "3.8"
    assert p38.represented(color=str, compact=None) == "cpython:3.8"

    assert c38a.represented() == "conda:3.8"
    assert c38a.represented(compact=True) == "3.8"
    assert c38a.represented(compact="cpython") == "conda:3.8"
    assert c38a.represented(compact=["cpython", "conda"]) == "3.8"
    assert c38a.represented(color=str, compact=None) == "conda:3.8"

    check_spec("", "invoker")
    check_spec(" ", "invoker")
    check_spec(" : ", "?:")
    check_spec(" - ", "?-")
    check_spec(" pY 3 ", "?pY 3")
    check_spec(2, "cpython:2")
    check_spec("2", "cpython:2")
    check_spec("3", "cpython:3")
    check_spec("3+", "cpython:3+")
    check_spec("P3", "cpython:3")
    check_spec("py3", "cpython:3")
    check_spec("cpython:", "cpython:")
    check_spec("cpython-", "cpython:")
    check_spec("cpython3", "cpython:3")
    check_spec("python3", "cpython:3")
    check_spec(3.7, "cpython:3.7")
    check_spec(" p3.7 ", "cpython:3.7")
    check_spec(" cpython:3.7 ", "cpython:3.7")
    check_spec(" p3.7+ ", "cpython:3.7+")
    check_spec(" p3.7++ ", "?p3.7++")

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
    check_spec("pypy:", "pypy:")
    check_spec("pypy:+", "?pypy:+")  # Need actual version for '+' marker to count
    check_spec("pypy36", "pypy:3.6")
    check_spec("pypy36+", "pypy:3.6+")
    check_spec("pypy:37", "pypy:3.7")
    check_spec("pypy:3.8", "pypy:3.8")
    check_spec("conda:", "conda:")
    check_spec("conda:38", "conda:3.8")
    check_spec("conda:3.9.1", "conda:3.9.1")
    check_spec("miniconda-3.18.3", "miniconda:3.18.3")
    check_spec("miniconda3-4.7.12", "miniconda3:4.7.12")

    # Up to 3 version components are valid
    check_spec("391", "cpython:3.91")
    check_spec("3.9.1", "cpython:3.9.1")
    check_spec("py391", "cpython:3.91")
    check_spec("3777", "cpython:3.777")
    check_spec("3.7.7.7", "cpython:3.7.7.7")

    # Invalid marked with starting '?' for canonical form
    check_spec(" + ", "?+")
    check_spec(" cpython+ ", "?cpython+")
    check_spec(" python+ ", "?python+")
    check_spec("cpython:3.7a", "?cpython:3.7a")
    check_spec("miniconda3--4.7.1", "?miniconda3--4.7.1")
    check_spec("foo3.7", "foo:3.7")
    check_spec("python3:", "python3:")  # Separator is in the wrong place, consider 'python3' to be the family name...

    # Paths remain as-is
    check_spec("foo/python2.7", runez.short(runez.resolved_path("foo/python2.7")))
    check_spec("/foo/python2.7", "/foo/python2.7")
    check_spec("~/.pyenv/3.8.1", "~/.pyenv/3.8.1")


class CustomScanner(PythonInstallationScanner):
    def unknown_python(self, spec):
        # Pretend an auto-installation for example
        return PythonInstallation(runez.resolved_path(self.location / spec.text / "bin" / "python"), spec)


def test_venv(temp_folder, logged):
    depot = PythonDepot(use_path=False)
    import sys
    p = depot.find_python(sys.executable)
    assert p is depot.invoker

    # Simulate an explicit reference to a venv python
    mk_python("8.6.1")
    mk_python("8.6.1", prefix="foo", base_prefix=".pyenv/versions/8.6.1", folder=".venv")
    assert str(depot) == "0 scanned"
    pvenv = depot.find_python(".venv/bin/python")
    assert str(depot) == "0 scanned"
    assert depot.find_python(".venv") == pvenv
    assert str(pvenv) == ".pyenv/versions/8.6.1 [cpython:8.6.1]"

    # Edge case: version is found via .pyenv first
    depot = PythonDepot(scanner=CustomScanner(".pyenv"), use_path=False)
    assert str(depot) == "1 scanned"
    pvenv = depot.find_python(".venv/bin/python")
    assert str(pvenv) == ".pyenv/versions/8.6.1 [cpython:8.6.1]"
    assert depot.scanned == [pvenv]

    p95 = depot.find_python("9.5.1")
    assert p95.problem is None
    assert str(depot) == "2 scanned"
    assert depot.scanned == [p95, pvenv]
    assert not logged


def test_unknown():
    depot = PythonDepot(use_path=False)
    p = depot.find_python("foo")
    assert str(p) == "foo [not available]"
    assert p.executable == "foo"
    assert p.folder is None
    assert p.major is None
    assert p.problem == "not available"
    assert p.spec.canonical == "foo:"
    assert p.spec.text == "foo"
    assert p.major is None
    assert p.version is None


@pytest.mark.parametrize(
    ("given_version", "expected"),
    [
        ("1.2", (1, 2, 0, 0, 0, 0, "")),
        ("1.2rev5", (1, 2, 0, 0, 0, 5, "rev")),
        ("1.2r5.dev3", (1, 2, 0, 0, 0, 5, "r", "", 0, "r", 5, "dev", 3)),
        ("1.dev0", (1, 0, 0, 0, 0, 0, "", "", 0, "", 0, "dev", 0)),
        ("1.0.dev456", (1, 0, 0, 0, 0, 0, "", "", 0, "", 0, "dev", 456)),
        ("1.0a12", (1, 0, 0, 0, 0, 0, "", "a", 12, "", 0, "z", 0)),
        ("1.2.3rc12", (1, 2, 3, 0, 0, 0, "", "rc", 12, "", 0, "z", 0)),
        ("1.0a2.dev456", (1, 0, 0, 0, 0, 0, "", "a", 2, "", 0, "dev", 456)),
        ("1.0b2.post345", (1, 0, 0, 0, 0, 0, "", "b", 2, "post", 345, "z", 0)),
        ("1.0b2.post345.dev456", (1, 0, 0, 0, 0, 0, "", "b", 2, "post", 345, "dev", 456)),
        ("1.0rc1.dev456", (1, 0, 0, 0, 0, 0, "", "rc", 1, "", 0, "dev", 456)),
        ("1.0.post456.dev34", (1, 0, 0, 0, 0, 456, "post", "", 0, "post", 456, "dev", 34)),
    ]
)
def test_pep_sample(given_version, expected):
    version = Version(given_version, strict=True)
    assert version.is_valid
    assert str(version) == given_version
    actual = version.components
    if version.prerelease:
        actual += version.prerelease

    assert actual == expected


def test_version():
    loose = Version("v1.0.dirty", strict=False)
    assert loose.is_valid
    assert loose.ignored == ".dirty"
    assert str(loose) == "1.0"

    invalid = Version("v1.0.dirty", strict=True)
    assert not invalid.is_valid
    assert str(invalid) == "v1.0.dirty"
    assert invalid.ignored == ".dirty"
    assert loose > invalid

    dev101 = Version("0.0.1.dev101")
    assert not dev101.is_final
    assert dev101.is_valid
    assert dev101.prerelease

    none = Version(None)
    assert str(none) == ""
    assert not none.is_valid
    assert not none.is_final
    assert none.mm is None

    empty = Version("")
    assert str(empty) == ""
    assert not empty.is_valid
    assert empty == none
    assert empty.major is None

    ep = Version("123!2.1+foo.dirty-bar")
    assert ep.is_valid
    assert ep.epoch == 123
    assert ep.main == "2.1.0"
    assert ep.local_part == "foo.dirty-bar"
    assert ep.mm == "2.1"

    foo = Version("foo")
    assert str(foo) == "foo"
    assert not foo.is_valid
    assert not foo.components
    assert not foo.prerelease
    assert foo.major is None

    bogus = Version("1.2.3.4.5.6")
    assert str(bogus) == "1.2.3.4.5.6"
    assert not bogus.is_valid
    assert not bogus.components
    assert not bogus.prerelease

    v1 = Version("1")
    assert v1.components == (1, 0, 0, 0, 0, 0, "")
    assert str(v1) == "1"
    assert v1.mm == "1.0"
    assert empty < v1
    assert v1 > empty
    assert v1 != empty
    assert v1 < 2
    assert v1 < 1.1
    assert v1 < "1.1"
    assert v1 < [5]
    assert v1 > 0
    assert v1 > 0.5
    assert v1 > "0"

    # All versions are bigger than anything not parsing to a valid version
    assert v1 > ""
    assert v1 > []
    assert v1 > [5, 2, 3, 4, 5, 6]

    v1foo = Version("1foo")  # Ignore additional text
    assert v1 == v1foo

    vrc = Version("1.0rc4-foo")
    vrc_strict = Version("1.0rc4-foo", strict=True)
    vdev = Version("1.0a4.dev5-foo")
    assert vrc.is_valid
    assert not vrc.is_final
    assert not vrc_strict.is_valid
    assert not vdev.is_final
    assert vdev.prerelease == ("a", 4, "", 0, "dev", 5)
    assert vrc.suffix == "rc"
    assert vdev.suffix == "a.dev"  # Try and convey the fact that we have .a.dev version

    assert vdev < vrc
    assert str(vrc) == "1.0rc4"
    assert str(vdev) == "1.0a4.dev5"
    assert vdev.suffix == "a.dev"
    assert vdev.prerelease == ("a", 4, "", 0, "dev", 5)
    assert vrc.major == 1
    assert vrc.minor == 0
    assert vrc.patch == 0
    assert vrc.main == "1.0.0"
    assert Version.from_text("foo, version 1.0a4.dev5\nbar baz") == vdev

    incomplete_dev = Version("0.4.34dev")
    assert not incomplete_dev.is_final
    assert incomplete_dev.is_valid
    assert incomplete_dev.main == "0.4.34"
    assert incomplete_dev.prerelease == ("", 0, "", 0, "dev", 0)
    assert incomplete_dev.suffix == "dev"

    # .from_text() can be used to filter out invalid versions as None
    assert Version.from_text("Python 3.8.6", strict=True) is None
    assert Version.from_text("Python 3.8.6") == Version("3.8.6")
    assert Version.from_text("foo") is None
    assert Version.from_text("1.0rc4") == vrc

    # Version() can be used in sets/dicts
    s = set()
    s.add(vrc)
    assert vrc in s


def test_version_comparison():
    v10rc5 = Version("1.0rc5")
    assert v10rc5 > "0.9"
    assert v10rc5 > "1.0rc2"
    assert v10rc5 > "1.0rc2.dev10"
    assert v10rc5 > "1.0a5"
    assert v10rc5 < "1.0rc15"
    assert v10rc5 < "1.0"
    assert v10rc5 < "1.1"
    assert v10rc5 < "1.1rc2"

    v = "2.11.1.dev2+b 2.11.0 2.11.1.dev11+a.dirty 1!1.0 2.11.1.dev1 2.11.1"
    v = runez.flattened(v, split=" ", transform=Version)
    assert all(x.is_valid for x in v)
    v = sorted(v)
    v = runez.joined(v)
    assert v == "2.11.0 2.11.1.dev1 2.11.1.dev2+b 2.11.1.dev11+a.dirty 2.11.1 1!1.0"

    v = "1.2rc1 1.2rc2.dev05 1.2rc2.dev4 1.2a1.dev1"
    v = runez.flattened(v, split=" ", transform=Version)
    assert all(x.is_valid for x in v)
    v = sorted(v)
    v = runez.joined(v)
    assert v == "1.2a1.dev1 1.2rc1 1.2rc2.dev4 1.2rc2.dev05"

    v11 = Version("1.1.2.3")
    v12 = Version("1.2.3")
    v12p = Version("1.2.3.post4")
    v2 = Version("2")
    v20 = Version("2.0")
    v20d = Version("2.0.dev1")
    v21d = Version("2.1.dev1")
    v3 = Version("3.0.1.2")
    assert v11.is_final
    assert v12p.is_final
    assert v11.suffix is None
    assert v12p.suffix == "post"
    assert v20d.suffix == "dev"

    # Verify that numerical comparison takes place (not alphanumeric)
    assert None < v12  # For total ordering
    assert v12 > None
    assert v12 == "1.2.3"
    assert v12 == [1, 2, 3]
    assert v12 == (1, 2, 3)
    assert v12 <= (1, 2, 3)
    assert v12 < 1.19
    assert v12 != 1.19
    assert v12 != 1
    assert v12 != (1, 2)
    assert v12 < "1.19"
    assert v12 < "1.19"
    assert v12 != "1.19"
    assert v12 <= "1.19"
    assert v12 <= "1.2.3"
    assert v12 > "1.2"
    assert v12 >= "1.2"
    assert v12 >= "1.2.3"
    assert v12 > 1
    assert v12 == "1.2.3"
    assert v12 < 2
    assert v12 <= 2
    assert v20 == 2
    assert v20 == 2.0
    assert v20 != 2.1

    assert v2 == v20
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
    assert v21d > v20
    assert v20d < v20
    assert v3 > v20
    assert v3 > v20d


def test_version_crazy():
    verify_ordering([
        Version("1.2.3.7"),
        Version("1.2.3.40dev7"),
        Version("1.2.3.40a6"),
        Version("1.2.3.40rc5.dev0"),
        Version("1.2.3.40c5.dev7"),  # PEP-440 says 'c' should be sorted as 'rc'
        Version("1.2.3.40rc5"),
        Version("1.2.3.40rc5.post6.dev7"),
        Version("1.2.3.40rc5.post6.dev8"),
        Version("1.2.3.40rc5.post6"),
        Version("1.2.3.40rc6.dev7"),
        Version("1.2.3.40rc6"),
        Version("1.2.3.40rc6.post15"),
        Version("1.2.3.40rc20.post6.dev7"),
        Version("1.2.3.40rc20.post17.dev8"),
        Version("1.2.3.40"),
        Version("1.2.3.40post6.dev7"),
        Version("1.2.3.40post6"),
    ])


def test_version_local_part():
    verify_ordering([
        Version("1.0+foo.a"),
        Version("1.0+foo.a.b"),
        Version("1.0+foo.a.5"),
        Version("1.0+foo.z"),
        Version("1.0+foo.z.8"),
        Version("1.0+foo.5"),
        Version("1.0+foo.7"),
    ])


def test_version_pep_440():
    verify_ordering([
        Version("1.dev0"),
        Version("1.0.dev456"),
        Version("1.0a1"),
        Version("1.0a2.dev456"),
        Version("1.0a12.dev456"),
        Version("1.0a12"),
        Version("1.0b1.dev456"),
        Version("1.0b2"),
        Version("1.0b2.post345.dev456"),
        Version("1.0b2.post345"),
        Version("1.0rc1.dev456"),
        Version("1.0rc1"),
        Version("1.0"),
        Version("1.0+abc.5"),
        Version("1.0+abc.7"),
        Version("1.0+5"),
        Version("1.0.post456.dev34"),
        Version("1.0.post456"),
        Version("1.0.15"),
        Version("1.1.dev1"),
    ])


def verify_ordering(expected):
    # Jumble the given list of versions a bit, then sort them and verify they sort back to 'expected'
    given = sorted(expected, key=lambda x: x.text)
    x = given.pop(len(given) // 2)
    given.append(x)

    assert given != expected
    assert sorted(given) == expected
