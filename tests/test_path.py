import logging
import os

from mock import patch

import runez


SAMPLE_CONF = """
# Sample .conf (or .ini file)
root = foo # Definition without section

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


def test_anchor():
    user_path = runez.resolved_path("~/foo/bar")
    current_path = runez.resolved_path("./foo/bar")

    assert user_path != "~/foo/bar"
    assert runez.short(user_path) == "~/foo/bar"
    assert runez.short(current_path) != "foo/bar"

    with runez.Anchored(os.getcwd()):
        assert runez.short(current_path) == "foo/bar"


def test_basename():
    assert runez.basename(None) == ""
    assert runez.basename("/foo/bar") == "bar"
    assert runez.basename("foo/bar.py") == "bar"
    assert runez.basename("foo/bar.baz.pyc") == "bar.baz"

    assert runez.basename("foo/bar.py", extension_marker=None) == "bar.py"


def test_paths(temp_folder):
    assert runez.resolved_path(None) is None
    assert runez.resolved_path("foo") == os.path.join(temp_folder, "foo")
    assert runez.resolved_path("foo", base="bar") == os.path.join(temp_folder, "bar", "foo")

    assert runez.short(None) is None
    assert runez.short("") == ""
    assert runez.short(temp_folder) == temp_folder

    assert runez.short(temp_folder + "/foo") == "foo"
    assert runez.short(temp_folder + "/foo") == "foo"

    assert runez.parent_folder(None) is None
    assert runez.parent_folder(temp_folder + "/foo") == temp_folder

    assert runez.represented_args(["ls", temp_folder + "/foo bar", "-a"]) == 'ls "foo bar" -a'

    # Don't crash for no-ops
    assert runez.ensure_folder(None) == 0
    assert runez.ensure_folder("") == 0
    assert runez.copy(None, None) == 0
    assert runez.move(None, None) == 0
    assert runez.symlink(None, None) == 0
    assert runez.copy("foo", "foo") == 0
    assert runez.move("foo", "foo") == 0
    assert runez.symlink("foo", "foo") == 0

    assert runez.ensure_folder("foo") == 0  # 'foo' would be in temp_folder, which already exists

    with runez.CaptureOutput(dryrun=True) as logged:
        assert runez.ensure_folder("foo", folder=True, fatal=False) == 1
        assert "Would create" in logged.pop()

        assert runez.touch("foo", logger=logging.debug) == 1
        assert "Would touch foo" in logged.pop()

        assert runez.copy("foo", "bar") == 1
        assert "Would copy foo -> bar" in logged.pop()

        assert runez.move("foo", "bar") == 1
        assert "Would move foo -> bar" in logged.pop()

        assert runez.symlink("foo", "bar") == 1
        assert "Would symlink foo <- bar" in logged.pop()

        assert runez.delete(temp_folder) == 1
        assert "Would delete" in logged.pop()

        assert runez.copy("foo/bar/baz", "foo", fatal=False) == -1
        assert "source contained in destination" in logged.pop()

        assert runez.move("foo/bar/baz", "foo", fatal=False) == -1
        assert "source contained in destination" in logged.pop()

        assert runez.symlink("foo/bar/baz", "foo", fatal=False) == -1
        assert "source contained in destination" in logged.pop()

    assert runez.touch("sample") == 1
    assert "Can't create folder" in runez.verify_abort(runez.ensure_folder, "sample", folder=True)
    assert runez.verify_abort(runez.ensure_folder, None) is None

    assert runez.delete("sample") == 1
    assert runez.ensure_folder("sample", folder=True) == 1
    assert os.getcwd() == temp_folder
    with runez.CurrentFolder("sample", anchor=False):
        cwd = os.getcwd()
        sample = os.path.join(temp_folder, "sample")
        assert cwd == sample
        assert runez.short(os.path.join(cwd, "foo")) == "sample/foo"
    with runez.CurrentFolder("sample", anchor=True):
        cwd = os.getcwd()
        sample = os.path.join(temp_folder, "sample")
        assert cwd == sample
        assert runez.short(os.path.join(cwd, "foo")) == "foo"
    assert os.getcwd() == temp_folder

    assert runez.delete("sample") == 1

    with runez.CaptureOutput() as logged:
        sample = os.path.join(os.path.dirname(__file__), "sample.txt")
        content = runez.get_lines(sample)

        assert runez.write("sample", "".join(content), fatal=False, logger=logging.debug) == 1
        assert runez.get_lines("sample") == content
        assert "Writing 13 bytes" in logged.pop()

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

        assert runez.copy("x/y", "x/z") == 1
        assert os.path.exists("x/z/sample")
        assert os.path.exists("x/z/sample2")
        assert os.path.exists("x/z/sample3")
        assert os.path.islink("x/z/sample3")

    assert runez.touch(None) == 0
    assert not runez.is_younger(None, 1)
    assert not runez.is_younger("/dev/null/foo", 1)
    assert runez.first_line("/dev/null/foo") is None

    assert runez.get_lines(None) is None


@patch("io.open", side_effect=Exception)
@patch("os.unlink", side_effect=Exception)
@patch("shutil.copy", side_effect=Exception)
@patch("runez.open", side_effect=Exception)
@patch("os.path.exists", return_value=True)
@patch("os.path.isfile", return_value=True)
@patch("os.path.getsize", return_value=10)
def test_failed_read(*_):
    with runez.CaptureOutput() as logged:
        assert runez.get_lines("bar", fatal=False) is None
        assert "Can't read" in logged.pop()

        assert runez.write("bar", "foo", fatal=False)
        assert "Can't write" in logged.pop()

        assert runez.copy("foo", "bar", fatal=False) == -1
        assert "Can't delete" in logged
        assert "Can't copy" in logged.pop()

        assert runez.make_executable("foo", fatal=False) == -1
        assert "Can't chmod" in logged.pop()


def test_temp():
    with runez.CaptureOutput(anchors=["/tmp", "/etc"]) as logged:
        with runez.TempFolder() as tmp:
            assert os.path.isdir(tmp)
            assert tmp != "<tmp>"
        assert not os.path.isdir(tmp)

        assert runez.short("/tmp/foo") == "foo"
        assert runez.short("/etc/foo") == "foo"

        assert not logged

    with runez.CaptureOutput(dryrun=True) as logged:
        with runez.TempFolder() as tmp:
            assert tmp == "<tmp>"
            assert runez.short("<tmp>/foo") == "foo"

        with runez.TempFolder(anchor=False) as tmp:
            assert tmp == "<tmp>"
            assert runez.short("<tmp>/foo") == "<tmp>/foo"

        assert not logged


def test_conf():
    assert runez.get_conf(None) is None

    expected = {None: {"root": "foo"}, "": {"ek": "ev"}, "s1": {"k1": "v1"}, "s2": {"k2": ""}}
    assert runez.get_conf(SAMPLE_CONF.splitlines(), keep_empty=True) == expected

    del expected[None]
    del expected[""]
    del expected["s2"]
    assert runez.get_conf(SAMPLE_CONF.splitlines(), keep_empty=False) == expected
