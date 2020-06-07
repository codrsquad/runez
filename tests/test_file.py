import io
import logging
import os

import pytest
from mock import patch

import runez
import runez.conftest

SAMPLE_CONF = """
# Sample .conf (or .ini file)
root = some-value # Definition without section

[malformed section      # Missing closing square bracket
malformed definition    # This line has no '=' sign (outside of this comment...), ignored

[] # Empty section name
ek = ev

[s1] # Some section
k1 = v1

[empty] # Empty section

[s2]
k2 =

[s3]
#k3 = v3                # This one is commented out, shouldn't show up
"""


def test_basename():
    assert runez.basename(None) == ""
    assert runez.basename("/some-folder/bar") == "bar"
    assert runez.basename("/some-folder/.bar") == ".bar"
    assert runez.basename("/some-folder/.bar.py") == ".bar"
    assert runez.basename("/some-folder/.bar.baz.py") == ".bar.baz"
    assert runez.basename("some-folder/bar.py") == "bar"
    assert runez.basename("some-folder/bar.baz.pyc") == "bar.baz"

    assert runez.basename("some-folder/bar.py", extension_marker=None) == "bar.py"


def test_edge_cases():
    assert runez.file.ini_to_dict(None, default=None) is None

    # Don't crash for no-ops
    assert runez.copy(None, None) == 0
    assert runez.move(None, None) == 0
    assert runez.symlink(None, None) == 0
    assert runez.copy("some-file", "some-file") == 0
    assert runez.move("some-file", "some-file") == 0
    assert runez.symlink("some-file", "some-file") == 0
    assert runez.delete("non-existing") == 0

    assert runez.touch(None) == 0
    assert not runez.file.is_younger("", None)
    assert not runez.file.is_younger("", 1)
    assert not runez.file.is_younger("/dev/null/not-there", 1)

    assert runez.readlines(None, default=None) is None
    with pytest.raises(runez.system.AbortException):
        runez.readlines("/dev/null/not-there")


def test_ensure_folder(temp_folder, logged):
    assert runez.ensure_folder(None) == 0
    assert runez.ensure_folder("") == 0
    assert runez.ensure_folder(".") == 0

    assert runez.touch("some-file") == 1
    assert "Can't create folder" in runez.conftest.verify_abort(runez.ensure_folder, "some-file")

    assert runez.ensure_folder("some-dir", dryrun=True) == 1
    assert "Would create some-dir" in logged.pop()
    assert runez.ensure_folder("some-dir") == 1
    assert "Created folder some-dir" in logged.pop()

    assert runez.ensure_folder("some-dir") == 0
    assert not logged

    assert runez.touch("some-dir/a/b") == 1
    assert "Created folder" not in logged
    assert "Touched some-dir/a/b" in logged.pop()
    assert runez.ensure_folder("some-dir", clean=True, dryrun=True) == 1
    assert "Would clean 1 file from some-dir" in logged.pop()

    assert runez.touch("some-dir/b", logger=False) == 1
    assert not logged

    assert runez.ensure_folder("some-dir", clean=True) == 1
    assert "Cleaned 2 files from some-dir" in logged


def test_ini_to_dict(temp_folder, logged):
    foo = runez.file.ini_to_dict("foo", default={})
    assert not logged
    assert foo == {}

    expected = {None: {"root": "some-value"}, "": {"ek": "ev"}, "s1": {"k1": "v1"}, "s2": {"k2": ""}}
    runez.write("test.ini", SAMPLE_CONF)
    logged.pop()

    actual = runez.file.ini_to_dict("test.ini", keep_empty=True)
    assert not logged
    assert actual == expected

    del expected[None]
    del expected[""]
    del expected["s2"]
    actual = runez.file.ini_to_dict("test.ini", keep_empty=False)
    assert not logged
    assert actual == expected


@patch("io.open", side_effect=Exception)
@patch("os.unlink", side_effect=Exception("bad unlink"))
@patch("shutil.copy", side_effect=Exception)
@patch("runez.open", side_effect=Exception)
@patch("os.path.exists", return_value=True)
@patch("os.path.isfile", return_value=True)
@patch("os.path.getsize", return_value=10)
def test_failure(*_):
    with runez.CaptureOutput() as logged:
        assert runez.copy("some-file", "bar", fatal=False) == -1
        assert "Can't copy" in logged.pop()

        assert runez.delete("some-file", fatal=False) == -1
        assert "Can't delete" in logged
        assert "bad unlink" in logged.pop()

        with pytest.raises(runez.system.AbortException):
            runez.file.ini_to_dict("bar")
        assert "Couldn't read ini file" in logged.pop()

        assert runez.write("bar", "some content", fatal=False)
        assert "Can't write" in logged.pop()

        if not runez.WINDOWS:
            assert runez.make_executable("some-file", fatal=False) == -1
            assert "Can't chmod" in logged.pop()


def test_file_operations(temp_folder):
    with runez.CaptureOutput(dryrun=True) as logged:
        assert runez.ensure_folder("some-folder", fatal=False) == 1
        assert "Would create" in logged.pop()

        assert runez.touch("some-file", logger=logging.debug) == 1
        assert "Would touch some-file" in logged.pop()

        assert runez.copy("some-file", "bar") == 1
        assert "Would copy some-file -> bar" in logged.pop()

        assert runez.move("some-file", "bar") == 1
        assert "Would move some-file -> bar" in logged.pop()

        assert runez.symlink("some-file", "bar") == 1
        assert "Would symlink some-file <- bar" in logged.pop()

        assert runez.delete(temp_folder) == 1
        assert "Would delete" in logged.pop()

        assert runez.copy("some-folder/bar/baz", "some-folder", fatal=False) == -1
        assert "source contained in destination" in logged.pop()

        assert runez.move("some-folder/bar/baz", "some-folder", fatal=False) == -1
        assert "source contained in destination" in logged.pop()

        assert runez.symlink("some-folder/bar/baz", "some-folder", fatal=False) == -1
        assert "source contained in destination" in logged.pop()


def test_file_inspection(temp_folder, logged):
    assert runez.touch("sample") == 1
    assert runez.delete("sample") == 1
    assert "Deleted sample" in logged.pop()

    assert runez.ensure_folder("sample") == 1
    assert runez.delete("sample") == 1
    assert "Deleted sample" in logged.pop()

    sample = runez.conftest.resource_path("sample.txt")
    assert len(runez.readlines(sample)) == 4
    assert len(runez.readlines(sample, first=1)) == 1
    assert not logged

    content = runez.readlines(sample)
    cc = "%s\n" % "\n".join(content)
    assert runez.write("sample", cc, fatal=False, logger=logging.debug) == 1
    assert runez.readlines("sample") == content
    assert "bytes to sample" in logged.pop()  # Wrote 13 bytes on linux... but 14 on windows...

    assert runez.readlines("sample", first=2) == ["", "Fred"]
    assert runez.file.is_younger("sample", age=10)
    assert not runez.file.is_younger("sample", age=-1)

    # Verify that readlines() can ignore encoding errors
    with io.open("not-a-text-file", "wb") as fh:
        fh.write(b"\x89 hello\nworld")

    assert runez.readlines("not-a-text-file", first=1, errors="ignore") == [" hello"]
    assert not logged

    assert runez.copy("bar", "baz", fatal=False) == -1
    assert "does not exist" in logged.pop()
    assert runez.move("bar", "baz", fatal=False) == -1
    assert "does not exist" in logged.pop()
    assert runez.symlink("bar", "baz", fatal=False) == -1
    assert "does not exist" in logged.pop()

    # Creating dangling symlinks is possible
    assert runez.symlink("bar", "baz", fatal=False, must_exist=False) == 1
    assert "Symlink bar <- baz" in logged.pop()
    assert os.path.islink("baz")
    assert not os.path.exists("baz")

    assert runez.copy("sample", "x/y/sample") == 1
    assert runez.symlink("sample", "x/y/sample3", fatal=False) == 1

    assert os.path.exists("sample")
    assert runez.move("sample", "x/y/sample2") == 1
    assert not os.path.exists("sample")

    assert runez.copy("x/y", "x/z1") == 1
    assert os.path.exists("x/z1/sample")
    assert os.path.exists("x/z1/sample2")
    assert os.path.exists("x/z1/sample3")
    assert os.path.islink("x/z1/sample3")

    assert runez.copy("x/y", "x/z2", ignore=["sample2"]) == 1
    assert os.path.exists("x/z2/sample")
    assert not os.path.exists("x/z2/sample2")
    assert os.path.exists("x/z2/sample3")
    assert os.path.islink("x/z2/sample3")

    assert runez.copy("x/y", "x/z3", ignore=lambda src, dest: ["sample3"]) == 1
    assert os.path.exists("x/z3/sample")
    assert os.path.exists("x/z3/sample2")
    assert not os.path.exists("x/z3/sample3")

    assert runez.copy("x/y", "x/z2") == 1
    assert os.path.exists("x/z2/sample2")

    # Copy a folder over an existing file
    runez.touch("x2")
    assert not os.path.exists("x2/z2/sample2")
    assert runez.copy("x", "x2") == 1
    assert os.path.exists("x2/z2/sample2")


def test_parent_folder():
    cwd = os.getcwd()

    assert runez.parent_folder(None) is None
    assert runez.parent_folder("././some-file") == cwd

    if not runez.WINDOWS:
        parent = runez.parent_folder("/logs/foo")
        assert parent == "/logs"
        assert runez.parent_folder(parent) == "/"
        assert runez.parent_folder("/") == "/"
