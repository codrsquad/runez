import logging
import os

import pytest
from mock import patch

import runez


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


def test_anchored():
    user_path = runez.resolved_path("~/some-folder/bar")
    current_path = runez.resolved_path("./some-folder/bar")

    assert user_path != "~/some-folder/bar"
    assert runez.short(user_path) == os.path.join("~", "some-folder", "bar")
    assert runez.short(current_path) != os.path.join("some-folder", "bar")

    with runez.Anchored(os.getcwd()):
        assert runez.short(current_path) == os.path.join("some-folder", "bar")


def test_basename():
    assert runez.basename(None) == ""
    assert runez.basename("/some-folder/bar") == "bar"
    assert runez.basename("some-folder/bar.py") == "bar"
    assert runez.basename("some-folder/bar.baz.pyc") == "bar.baz"

    assert runez.basename("some-folder/bar.py", extension_marker=None) == "bar.py"


def test_paths(temp_folder):
    assert runez.resolved_path(None) is None
    assert runez.resolved_path("some-file") == os.path.join(temp_folder, "some-file")
    assert runez.resolved_path("some-file", base="bar") == os.path.join(temp_folder, "bar", "some-file")

    assert runez.short(None) is None
    assert runez.short("") == ""
    assert runez.short(os.path.join(temp_folder, "some-file")) == "some-file"

    assert runez.parent_folder(None) is None
    assert runez.parent_folder(os.path.join(temp_folder, "some-file")) == temp_folder

    assert runez.represented_args(["ls", os.path.join(temp_folder, "some-file") + " bar", "-a"]) == 'ls "some-file bar" -a'

    # Don't crash for no-ops
    assert runez.ensure_folder(None) == 0
    assert runez.ensure_folder("") == 0
    assert runez.copy(None, None) == 0
    assert runez.move(None, None) == 0
    assert runez.symlink(None, None) == 0
    assert runez.copy("some-file", "some-file") == 0
    assert runez.move("some-file", "some-file") == 0
    assert runez.symlink("some-file", "some-file") == 0
    assert runez.delete("non-existing") == 0

    assert runez.ensure_folder("some-folder") == 0  # 'some-folder' would be in temp_folder, which already exists

    with runez.CaptureOutput(dryrun=True) as logged:
        assert runez.ensure_folder("some-folder", folder=True, fatal=False) == 1
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

    with runez.CaptureOutput():
        assert runez.touch("sample") == 1
        assert "Can't create folder" in runez.verify_abort(runez.ensure_folder, "sample", folder=True)
        custom = runez.verify_abort(runez.ensure_folder, "sample", folder=True, fatal=SystemExit, expected_exception=SystemExit)
        assert "Can't create folder" in custom
        with pytest.raises(AssertionError):
            assert runez.verify_abort(runez.ensure_folder, None)

        assert runez.delete("sample") == 1
        assert runez.ensure_folder("sample", folder=True) == 1
        assert os.getcwd() == temp_folder

    with runez.CurrentFolder("sample", anchor=False):
        cwd = os.getcwd()
        sample = os.path.join(temp_folder, "sample")
        assert cwd == sample
        assert runez.short(os.path.join(cwd, "some-file")) == os.path.join("sample", "some-file")

    with runez.CurrentFolder("sample", anchor=True):
        cwd = os.getcwd()
        sample = os.path.join(temp_folder, "sample")
        assert cwd == sample
        assert runez.short(os.path.join(cwd, "some-file")) == "some-file"

    assert os.getcwd() == temp_folder

    assert runez.delete("sample") == 1

    with runez.CaptureOutput() as logged:
        sample = os.path.join(os.path.dirname(__file__), "sample.txt")
        content = runez.get_lines(sample)

        assert runez.write("sample", "".join(content), fatal=False, logger=logging.debug) == 1
        assert runez.get_lines("sample") == content
        assert "bytes to sample" in logged.pop()  # Writing 13 bytes on linux... but 14 on windows...

        assert runez.first_line("sample") == "Fred"
        assert runez.is_younger("sample", age=10)
        assert not runez.is_younger("sample", age=-1)

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

    assert runez.touch(None) == 0
    assert not runez.is_younger(None, 1)
    assert not runez.is_younger("/dev/null/not-there", 1)
    assert runez.first_line("/dev/null/not-there") is None

    assert runez.get_lines(None) is None


@patch("io.open", side_effect=Exception)
@patch("os.unlink", side_effect=Exception)
@patch("shutil.copy", side_effect=Exception)
@patch("runez.open", side_effect=Exception)
@patch("os.path.exists", return_value=True)
@patch("os.path.isfile", return_value=True)
@patch("os.path.getsize", return_value=10)
def test_failure(*_):
    with runez.CaptureOutput() as logged:
        assert runez.get_lines("bar", fatal=False) is None
        assert "Can't read" in logged.pop()

        assert runez.write("bar", "some content", fatal=False)
        assert "Can't write" in logged.pop()

        assert runez.delete("some-file", fatal=False) == -1
        assert "Can't delete" in logged

        assert runez.copy("some-file", "bar", fatal=False) == -1
        assert "Can't copy" in logged.pop()

        if not runez.WINDOWS:
            assert runez.make_executable("some-file", fatal=False) == -1
            assert "Can't chmod" in logged.pop()


def test_temp():
    cwd = os.getcwd()

    with runez.CaptureOutput(anchors=[os.path.join("/tmp"), os.path.join("/etc")]) as logged:
        with runez.TempFolder() as tmp:
            assert os.path.isdir(tmp)
            assert tmp != runez.convert.SYMBOLIC_TMP
        assert not os.path.isdir(tmp)
        assert os.getcwd() == cwd

        assert runez.short(os.path.join("/tmp", "some-file")) == "some-file"
        assert runez.short(os.path.join("/etc", "some-file")) == "some-file"

        assert not logged

    symbolic = os.path.join(runez.convert.SYMBOLIC_TMP, "some-file")
    with runez.CaptureOutput(dryrun=True) as logged:
        assert os.getcwd() == cwd
        with runez.TempFolder() as tmp:
            assert tmp == runez.convert.SYMBOLIC_TMP
            assert runez.short(symbolic) == "some-file"

        assert os.getcwd() == cwd
        with runez.TempFolder(anchor=False) as tmp:
            assert tmp == runez.convert.SYMBOLIC_TMP
            assert runez.short(symbolic) == symbolic

        assert not logged

    assert os.getcwd() == cwd


def test_conf():
    assert runez.get_conf(None) is None

    expected = {None: {"root": "some-value"}, "": {"ek": "ev"}, "s1": {"k1": "v1"}, "s2": {"k2": ""}}
    assert runez.get_conf(SAMPLE_CONF.splitlines(), keep_empty=True) == expected

    del expected[None]
    del expected[""]
    del expected["s2"]
    assert runez.get_conf(SAMPLE_CONF.splitlines(), keep_empty=False) == expected
