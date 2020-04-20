import logging
import os

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


def test_ini_to_dict():
    assert runez.ini_to_dict(None) is None
    assert runez.ini_to_dict("/dev/null/no-such-file") is None

    expected = {None: {"root": "some-value"}, "": {"ek": "ev"}, "s1": {"k1": "v1"}, "s2": {"k2": ""}}
    actual = runez.ini_to_dict(SAMPLE_CONF.splitlines(), keep_empty=True)
    assert actual == expected

    with runez.TempFolder():
        runez.write("test.ini", SAMPLE_CONF)
        actual = runez.ini_to_dict("test.ini", keep_empty=True)
        assert actual == expected

        with open("test.ini") as fh:
            actual = runez.ini_to_dict(fh, keep_empty=True)
            assert actual == expected

    del expected[None]
    del expected[""]
    del expected["s2"]
    actual = runez.ini_to_dict(SAMPLE_CONF.splitlines(), keep_empty=False)
    assert actual == expected


@patch("io.open", side_effect=Exception)
@patch("os.unlink", side_effect=Exception)
@patch("shutil.copy", side_effect=Exception)
@patch("runez.open", side_effect=Exception)
@patch("os.path.exists", return_value=True)
@patch("os.path.isfile", return_value=True)
@patch("os.path.getsize", return_value=10)
def test_failure(*_):
    with runez.CaptureOutput() as logged:
        assert runez.readlines("bar") is None
        assert not logged

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


def test_file_operations(temp_folder):
    # Don't crash for no-ops
    assert runez.copy(None, None) == 0
    assert runez.move(None, None) == 0
    assert runez.symlink(None, None) == 0
    assert runez.copy("some-file", "some-file") == 0
    assert runez.move("some-file", "some-file") == 0
    assert runez.symlink("some-file", "some-file") == 0
    assert runez.delete("non-existing") == 0

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

    assert runez.ensure_folder("sample", folder=True) == 1
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
        content = runez.readlines(sample)

        assert runez.write("sample", "".join(content), fatal=False, logger=logging.debug) == 1
        assert runez.readlines("sample") == content
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
    assert not runez.is_younger("", 1)
    assert not runez.is_younger("/dev/null/not-there", 1)
    assert runez.first_line("/dev/null/not-there") is None

    assert runez.readlines(None) is None


def test_terminal_width():
    with patch.dict(os.environ, {"COLUMNS": ""}, clear=True):
        tw = runez.terminal_width()
        if runez.PY2:
            assert tw is None

        else:
            assert tw is not None

        with patch("runez.file._tw_shutil", return_value=None):
            assert runez.terminal_width() is None
            assert runez.terminal_width(default=5) == 5

        with patch("runez.file._tw_shutil", return_value=10):
            assert runez.terminal_width() == 10
            assert runez.terminal_width(default=5) == 10

    with patch.dict(os.environ, {"COLUMNS": "25"}, clear=True):
        assert runez.terminal_width() == 25
