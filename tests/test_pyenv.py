import json
import os
import sys

import pytest

import runez
from runez.http import RestClient
from runez.pyenv import ArtifactInfo, PypiStd, PythonDepot, PythonSpec, Version

PYPI_CLIENT = RestClient("https://example.com/pypi")


def test_artifact_info():
    info = ArtifactInfo.from_basename("E.S.P.-Hadouken-0.2.1.tar.gz")
    assert str(info) == "e-s-p-hadouken/E.S.P.-Hadouken-0.2.1.tar.gz"
    assert info.category == "sdist"
    assert not info.is_dirty
    assert not info.is_wheel
    assert info.package_name == "E.S.P.-Hadouken"
    assert info.pypi_name == "e-s-p-hadouken"
    assert info.tags is None
    assert info.version == "0.2.1"
    assert info.wheel_build_number is None

    info = ArtifactInfo.from_basename("a_b-1!0.0.1-10-py3-none-any.whl", None)
    assert str(info) == "a-b/a_b-1!0.0.1-10-py3-none-any.whl"
    assert info.category == "wheel"
    assert not info.is_dirty
    assert info.is_wheel
    assert info.package_name == "a_b"
    assert info.pypi_name == "a-b"
    assert info.tags == "py3-none-any"
    assert info.version == "1!0.0.1"
    assert info.wheel_build_number == "10"


def mk_python(basename, executable=True, content=None, machine=None):
    if basename[0].isdigit():
        version = Version(basename)
        folder = runez.to_path(".pyenv/versions") / basename / "bin"

    else:
        version = Version(os.path.basename(basename))
        if basename.startswith("./"):
            folder = runez.to_path(os.path.dirname(basename[2:]))

        else:
            folder = runez.to_path(".pyenv/versions") / os.path.dirname(basename) / "bin"

    path = folder / ("python%s" % version.mm)
    if not content:
        content = {"version": str(version), "machine": machine or runez.SYS_INFO.platform_id.arch}

    if content == "failed":
        content = "echo failed\nexit 1"

    elif content == "invalid-json":
        content = "echo '{foo: bar}'"

    else:
        content = "echo '%s'" % json.dumps(content)

    content = "#!/bin/bash\n%s\n" % content
    runez.write(path, content, logger=None)
    runez.symlink(path, folder / "python", logger=None)
    if executable:
        runez.make_executable(path, logger=None)


def test_depot(temp_folder, logged):
    # Create some pyenv-style python installation mocks (using version 8, so it sorts above any real version...)
    mk_python("8.6.1", machine="x86_64_test")
    mk_python("8.7.2")
    mk_python("miniforge3-22.11.1-4/9.11.2")
    mk_python("pypy-9.8.7/9.8.7")
    mk_python("8.5.4", content="invalid content")
    mk_python("8.5.5", content={"version": "invalid-version"})
    mk_python("8.5.6", content="failed")
    mk_python("8.5.7", content="invalid-json")
    runez.symlink(".pyenv/versions/8.6.1", ".pyenv/versions/8.6", logger=None)
    runez.symlink(".pyenv/versions/8.6.1", ".pyenv/versions/python8.6", logger=None)

    depot = PythonDepot(".pyenv/versions/**")
    text = depot.representation()
    assert text.startswith("4 python installations in .pyenv/versions/**:")
    assert len(depot.available_pythons) == 4

    assert str(depot.find_python("8.5.4")) == "8.5.4 [not available]"
    invalid = depot.find_python(".pyenv/versions/8.5.4")
    assert str(invalid) == ".pyenv/versions/8.5.4 [internal error: _inspect.py returned 'invalid content']"
    bad_version = depot.find_python(".pyenv/versions/8.5.5")
    assert str(bad_version) == ".pyenv/versions/8.5.5 [invalid version 'invalid-version']"
    failed = depot.find_python(".pyenv/versions/8.5.6")
    assert str(failed) == ".pyenv/versions/8.5.6 [failed]"
    invalid_json = depot.find_python(".pyenv/versions/8.5.7")
    assert str(invalid_json).startswith(".pyenv/versions/8.5.7 [internal error: ")
    assert invalid < bad_version < failed

    versions = [p.mm_spec.canonical for p in depot.available_pythons]
    assert versions == ["pypy:9.8", "cpython:8.7", "cpython:8.6", "conda:9.11"]

    # Verify that latest available is found (when under-specified)
    p8 = depot.find_python("8")
    assert repr(p8) == ".pyenv/versions/8.7.2"
    assert str(p8) == ".pyenv/versions/8.7.2"
    assert invalid < p8

    # No auto-determined preferred python for pyenv-style installations
    assert depot.preferred_python is None

    # Verify that preferred python is respected
    depot.set_preferred_python("8.6")
    preferred = depot.preferred_python
    assert str(preferred) == ".pyenv/versions/8.6.1 [x86_64_test]"

    p86 = depot.find_python("8.6")
    assert "preferred" in p86.representation(preferred=preferred)

    assert repr(depot.find_python("8")) == ".pyenv/versions/8.6.1 [x86_64_test]"
    assert p8 is depot.find_python("8.7")
    p8b = depot.find_python(".pyenv/versions/8.7.2")
    assert p8 is not p8b
    assert p8 == p8b
    assert p8 < p8b  # Due to their .executable

    # Verify min spec
    assert str(depot.find_python("conda:9.1+")) == ".pyenv/versions/miniforge3-22.11.1-4 [conda:9.11.2]"

    # There's only one symlink of the form 'python*'
    depot2 = PythonDepot(".pyenv/versions/python*")
    assert len(depot2.available_pythons) == 1
    assert str(depot2.available_pythons[0]) == ".pyenv/versions/python8.6 [8.6.1, x86_64_test]"

    assert not logged


def test_depot_adhoc(temp_folder):
    depot = PythonDepot(".pyenv/versions")
    assert depot.representation() == "No python installations found in '.pyenv/versions'"

    p11 = depot.find_python("11.0.0")
    assert p11.problem == "not available"
    assert str(p11.inspection) == "not available"

    # Only paths are cached
    p11b = depot.find_python("11.0.0")
    assert p11 is not p11b
    assert p11 == p11b
    pfoo = depot.find_python("/foo")
    assert depot.find_python("/foo") == pfoo

    mk_python("./some-path/bin/13.1.2")
    assert str(depot.find_python("some-path/bin/python13.1")) == "some-path/bin/python13.1 [13.1.2]"
    assert str(depot.find_python("./some-path/")) == "some-path [13.1.2]"
    assert str(depot.find_python(runez.to_path("some-path"))) == "some-path [13.1.2]"
    assert str(depot.find_python("some-path/bin/python")) == "some-path/bin/python [13.1.2]"
    assert str(depot.find_python("some-path/bin")) == "some-path/bin [13.1.2]"


def test_depot_folder(temp_folder):
    mk_python("8.5.6")
    mk_python("8.5.7")
    runez.symlink(".pyenv/versions/8.5.6/bin/python", "python8.5", logger=None)
    runez.symlink("python8.5", "python", logger=None)
    depot = PythonDepot(temp_folder)
    assert len(depot.available_pythons) == 1
    python = depot.find_python(None)
    assert str(python) == "python8.5 [8.5.6]"
    assert depot.preferred_python is python
    assert depot.locations[0].preferred_python is python
    assert depot.find_python("8.5") is python
    assert depot.find_python("8.5.6") is python
    assert str(depot.find_python(".pyenv/versions/8.5.6/bin/python8.5")) == "python8.5 [8.5.6]"
    assert str(depot.find_python("8.5.7")) == "8.5.7 [not available]"


def test_depot_path():
    depot = PythonDepot("PATH")
    assert depot.available_pythons
    assert depot.preferred_python is None
    assert depot.find_python(None) is depot.invoker


def test_empty_depot():
    depot = PythonDepot()
    assert depot.representation() == "No PythonDepot locations configured"
    assert not depot.available_pythons
    invoker = runez.SYS_INFO.invoker_python

    p95 = depot.find_python(PythonSpec.from_text("9.5"))
    assert p95.problem
    assert depot.find_python(None) is invoker
    assert depot.find_python("") is invoker
    assert depot.find_python("invoker") is invoker
    assert depot.find_python(invoker) is invoker
    assert depot.find_python(invoker.executable).is_invoker
    assert depot.find_python(str(invoker.executable)).is_invoker
    assert depot.find_python(invoker.real_exe).is_invoker
    assert depot.find_python(PythonSpec("cpython", invoker.mm)) is invoker
    assert depot.find_python("python") is invoker
    assert depot.find_python("py%s" % invoker.mm) is invoker  # eg: py3.10
    assert depot.find_python("py%s" % invoker.mm.text.replace(".", "")) is invoker  # tox style: py310
    assert depot.find_python(invoker.mm) is invoker
    assert depot.find_python(invoker.mm.text) is invoker
    assert depot.find_python("python") is invoker
    assert depot.find_python("python%s" % invoker.mm.major) is invoker

    p = depot.find_python("foo")
    assert str(p) == "foo [not available]"
    assert repr(p) == "foo [not available]"
    assert p.executable == runez.to_path("foo")
    assert p.real_exe == runez.to_path("foo").resolve()
    assert p.full_spec is None
    assert p.full_version is None
    assert not p.is_invoker
    assert p.machine is None
    assert p.mm_spec is None
    assert p.problem == "not available"
    assert p.short_name == "foo"


def test_inspect():
    import runez._inspect

    r = runez.run(sys.executable, runez._inspect.__file__)
    assert r.succeeded
    assert '"version":' in r.output


def test_invoker():
    import runez.pyenv

    invoker = runez.SYS_INFO.invoker_python
    assert invoker.full_spec
    assert invoker.is_invoker
    assert invoker.machine
    assert invoker.problem is None


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
        "2.5.5": [{"filename": "pickley-2.5.5-py2.py3-none-any.whl"}, {"filename": "pickley-2.5.5.tar.gz"}],
    },
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


@PYPI_CLIENT.mock(
    {
        "shell-functools/": P_SHELL_FUNCTOOLS,
        "https://pypi.org/pypi/black/json": P_BLACK,
        "https://pypi.org/pypi/foo/json": {"info": {"version": "1.2.3"}},
        "https://pypi.org/pypi/pickley/json": P_PICKLEY,
        "https://pypi.org/pypi/funky-proj/json": P_FUNKY,
    }
)
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


def test_spec():
    p3 = PythonSpec.from_text("3")
    p3plus = PythonSpec.from_text("3+")
    assert str(p3) == "cpython:3"
    assert str(p3plus) == "cpython:3+"
    assert not p3.is_min_spec
    assert p3plus.is_min_spec

    assert p3 == PythonSpec.from_object(Version("3"))

    p3_rep = p3.represented()
    p3plus_rep = p3plus.represented()
    assert isinstance(p3_rep, str)
    assert isinstance(p3plus_rep, str)
    assert p3_rep == "3"
    assert p3plus_rep == "3+"

    p38 = PythonSpec.from_text("3.8")
    assert p38.satisfies(p3)
    assert p38.satisfies(p3plus)

    p38plus = PythonSpec.from_text("3.8+")
    c38 = PythonSpec.from_text("conda:3.8")
    assert c38 != p38
    assert c38.version == p38.version
    assert p38 == PythonSpec.from_text("py38")
    assert not c38.satisfies(p38)
    assert not p38.satisfies(c38)

    p310 = PythonSpec.from_text("3.10")
    assert p310 == PythonSpec.from_text("py310")
    assert not p38.satisfies(p310)
    assert not p310.satisfies(p38)
    assert p310.satisfies(p38plus)
    assert p310.satisfies(p310)
    assert PythonSpec.from_text("3.10.1").satisfies(p310)
    assert PythonSpec.from_text("3.10.0rc1").satisfies(p310)

    assert p38.represented() == "3.8"
    assert p38.represented(compact=None) == "cpython:3.8"
    assert p38.represented(compact=False) == "cpython:3.8"
    assert p38.represented(compact=True) == "3.8"
    assert p38.represented(compact="cpython") == "3.8"
    assert p38.represented(compact=["cpython", "conda"]) == "3.8"
    assert p38.represented(color=str, compact=None) == "cpython:3.8"

    assert c38.represented() == "conda:3.8"
    assert c38.represented(compact=True) == "3.8"
    assert c38.represented(compact="cpython") == "conda:3.8"
    assert c38.represented(compact=["cpython", "conda"]) == "3.8"
    assert c38.represented(color=str, compact=None) == "conda:3.8"

    rc3 = PythonSpec.from_text("cpython:3.12.0rc3")
    assert rc3.represented(compact=None) == "cpython:3.12.0rc3"
    assert not rc3.is_min_spec

    rc3plus = PythonSpec.from_text("cpython:3.12.0rc3+")
    assert rc3plus.represented(compact=True) == "3.12.0rc3+"
    assert rc3plus.is_min_spec


def test_spec_equivalent():
    def check_equivalent_specs(*text):
        specs = [PythonSpec.from_text(x) for x in text]
        assert len(specs) == len(text)
        assert len(set(specs)) == 1

    check_equivalent_specs("3", "py3", "python3", "cpython:3", "python", "py")
    check_equivalent_specs("3+", "py3+", "python3+", "cpython:3+")
    check_equivalent_specs("3.10", "310", "py3.10", "py310", "python3.10", "python310", "cpython:3.10")
    check_equivalent_specs("3.10+", "310+", "py3.10+", "py310+", "python3.10+", "python310+", "cpython:3.10+")
    check_equivalent_specs("3777", "py3.777", "python3.777", "cpython:3.777")


def test_spec_invalid():
    assert PythonSpec.from_object(None) is None
    assert PythonSpec.from_object([]) is None
    assert PythonSpec.from_object(["foo"]) is None

    def check_spec_invalid(text):
        assert PythonSpec.from_text(text) is None

    check_spec_invalid("foo")
    check_spec_invalid("foo:3")
    check_spec_invalid("cpython")
    check_spec_invalid("cpython:")
    check_spec_invalid("cpython:3 ")
    check_spec_invalid("cpython:3.10.0--rc1")
    check_spec_invalid("cpython:+")
    check_spec_invalid("cpython: 3")
    check_spec_invalid("cpython :3")
    check_spec_invalid("python:3")
    check_spec_invalid("p3.9")
    check_spec_invalid("pY3")
    check_spec_invalid("3.9.9a")
    check_spec_invalid("3.9.9++")


def test_spec_list():
    assert not PythonSpec.to_list("a,b")
    x = PythonSpec.to_list("3.10,py39")
    assert x == [PythonSpec.from_text("3.10"), PythonSpec.from_text("3.9")]

    x = PythonSpec.to_list(["3.10,py36", "foo,py37", 3.8])
    assert x == [PythonSpec.from_text("3.10"), PythonSpec.from_text("3.6"), PythonSpec.from_text("3.7"), PythonSpec.from_text("3.8")]


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
    ],
)
def test_pep_sample(given_version, expected):
    version = Version(given_version)
    assert version.is_valid
    assert version.ignored is None
    assert str(version) == given_version
    actual = version.components
    if version.prerelease:
        actual += version.prerelease

    assert actual == expected


def test_version():
    loose = Version("v1.0.dirty", canonical=None)
    assert loose.is_valid
    assert loose.ignored == ".dirty"
    assert str(loose) == "1.0"
    assert loose.pep_440 == "1.0"

    invalid = Version("v1.0.dirty")
    assert not invalid.is_valid
    assert str(invalid) == "v1.0.dirty"
    assert invalid.ignored == ".dirty"
    assert loose > invalid

    dev101 = Version("0.0.1dev101")
    assert not dev101.is_final
    assert dev101.is_valid
    assert not dev101.is_dirty
    assert dev101.prerelease
    assert str(dev101) == "0.0.1dev101"
    assert dev101.pep_440 == "0.0.1.dev101"
    assert dev101.major == 0
    assert dev101.minor == 0
    assert dev101.patch == 1
    assert dev101.mm == "0.0"

    none = Version(None)
    assert str(none) == ""
    assert not none.is_valid
    assert not none.is_final
    assert none.major is None
    assert none.mm is None

    empty = Version("")
    assert str(empty) == ""
    assert not empty.is_valid
    assert empty == none
    assert empty.major is None

    ep = Version("123!2.1+foo.dirty-bar")
    assert str(ep) == "123!2.1+foo.dirty-bar"
    assert ep.pep_440 == "123!2.1+foo.dirty-bar"
    assert ep.is_valid
    assert ep.is_dirty
    assert ep.epoch == 123
    assert ep.main == "2.1"
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
    assert bogus.mm is None

    v1 = Version("1")
    assert v1.components == (1, 0, 0, 0, 0, 0, "")
    assert str(v1) == "1"
    assert v1.main == "1"
    assert v1.major == 1
    assert v1.minor is None
    assert v1.patch is None
    assert v1.mm is None
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

    v1foo = Version("1foo", canonical=None)  # Ignore additional text
    assert v1 == v1foo

    vrc = Version("1.0rc4-bar", canonical=None)
    vdev = Version("1.0a4.dev5-foo", canonical=None)
    assert vdev.pep_440 == "1.0a4.dev5"
    assert vdev.ignored == "-foo"
    assert vrc.is_valid
    assert not vrc.is_final
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
    assert vrc.patch is None
    assert vrc.main == "1.0"

    incomplete_dev = Version("0.4.34dev")
    assert not incomplete_dev.is_final
    assert incomplete_dev.is_valid
    assert incomplete_dev.main == "0.4.34"
    assert incomplete_dev.prerelease == ("", 0, "", 0, "dev", 0)
    assert incomplete_dev.suffix == "dev"

    # Version() can be used in sets/dicts
    s = set()
    s.add(vrc)
    assert vrc in s


def test_version_extraction():
    x = Version.extracted_from_text("foo, version 1.0a4.dev5\nbar baz")
    assert str(x) == "1.0a4.dev5"

    p38 = Version("Python 3.8.6")
    assert not p38.is_valid

    p38 = Version.extracted_from_text("Python 3.8.6")
    assert str(p38) == "3.8.6"
    assert p38.is_valid


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
    assert v12 > None  # For total ordering
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
    verify_ordering(
        [
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
        ]
    )


def test_version_local_part():
    verify_ordering(
        [
            Version("1.0+foo.a"),
            Version("1.0+foo.a.b"),
            Version("1.0+foo.a.5"),
            Version("1.0+foo.z"),
            Version("1.0+foo.z.8"),
            Version("1.0+foo.5"),
            Version("1.0+foo.7"),
        ]
    )


def test_version_ordering():
    verify_ordering(
        [
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
        ]
    )


def verify_ordering(expected):
    # Jumble the given list of versions a bit, then sort them and verify they sort back to 'expected'
    given = sorted(expected, key=lambda x: x.text)
    mid_item = given.pop(len(given) // 2)
    given.append(mid_item)

    assert given != expected
    assert sorted(given) == expected


def test_version_pep_440():
    vpost = Version("1.2.post")
    assert vpost.is_valid
    assert not vpost.prerelease
    assert str(vpost) == "1.2.post"
    assert vpost.pep_440 == "1.2.post0"

    vrev5 = Version("1.2rev05")
    assert str(vrev5) == "1.2rev05"
    assert vrev5.is_valid
    assert vrev5.pep_440 == "1.2.post5"
    assert vrev5 > vpost

    vrev5_canonical = Version("1.2rev05", canonical=True)
    assert str(vrev5_canonical) == "1.2.post5"
    assert vrev5_canonical.pep_440 == vrev5_canonical.text
    assert vrev5_canonical == vrev5

    vr6 = Version("1.2r6")
    assert str(vr6) == "1.2r6"
    assert vr6.is_valid
    assert vr6.pep_440 == "1.2.post6"
    assert vr6 > vrev5

    vrev5dev3 = Version("1.2rev05.dev3")
    assert vrev5dev3.prerelease
    assert str(vrev5dev3) == "1.2rev05.dev3"
    assert vrev5dev3.pep_440 == "1.2.rev5.dev3.post5"
    assert vpost < vrev5dev3
    assert vrev5 > vrev5dev3
    assert vr6 > vrev5dev3

    vrc1 = Version("v1.39.4-rc.1")
    assert str(vrc1) == "1.39.4-rc.1"
    assert vrc1.pep_440 == "1.39.4rc1"
