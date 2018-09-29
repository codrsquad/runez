import os

from mock import patch

import runez


def test_paths(temp_base):
    assert runez.resolved_path(None) is None
    assert runez.resolved_path("foo") == os.path.join(temp_base, "foo")
    assert runez.resolved_path("foo", base="bar") == os.path.join(temp_base, "bar", "foo")

    assert runez.short(None) is None
    assert runez.short("") == ""
    assert runez.short(temp_base) == temp_base

    assert runez.short(temp_base + "/foo") == "foo"
    assert runez.short(temp_base + "/foo") == "foo"

    assert runez.parent_folder(None) is None
    assert runez.parent_folder(temp_base + "/foo") == temp_base

    assert runez.represented_args(["ls", temp_base + "/foo bar", "-a"]) == 'ls "foo bar" -a'

    # Don't crash for no-ops
    assert runez.ensure_folder(None) == 0
    assert runez.ensure_folder("") == 0
    assert runez.copy(None, None) == 0
    assert runez.move(None, None) == 0
    assert runez.symlink(None, None) == 0
    assert runez.copy("foo", "foo") == 0
    assert runez.move("foo", "foo") == 0
    assert runez.symlink("foo", "foo") == 0

    assert runez.ensure_folder("foo") == 0  # 'foo' would be in temp_base, which already exists

    with runez.CaptureOutput(dryrun=True) as logged:
        assert runez.ensure_folder("foo", folder=True, fatal=False) == 1
        assert "Would create" in logged.pop()

        assert runez.touch("foo", quiet=False) == 1
        assert "Would touch foo" in logged.pop()

        assert runez.copy("foo", "bar") == 1
        assert "Would copy foo -> bar" in logged.pop()

        assert runez.move("foo", "bar") == 1
        assert "Would move foo -> bar" in logged.pop()

        assert runez.symlink("foo", "bar") == 1
        assert "Would symlink foo -> bar" in logged.pop()

        assert runez.delete(temp_base) == 1
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
    assert os.getcwd() == temp_base
    with runez.CurrentFolder("sample", anchor=False):
        cwd = os.getcwd()
        sample = os.path.join(temp_base, "sample")
        assert cwd == sample
        assert runez.short(os.path.join(cwd, "foo")) == "sample/foo"
    with runez.CurrentFolder("sample", anchor=True):
        cwd = os.getcwd()
        sample = os.path.join(temp_base, "sample")
        assert cwd == sample
        assert runez.short(os.path.join(cwd, "foo")) == "foo"
    assert os.getcwd() == temp_base

    assert runez.delete("sample") == 1

    with runez.CaptureOutput() as logged:
        assert runez.write_contents("sample", "bar\nbaz\n\n", quiet=False)
        assert runez.get_lines("sample") == ["bar\n", "baz\n", "\n"]
        assert "Writing 9 bytes" in logged.pop()

        assert runez.first_line("sample") == "bar"
        assert runez.file_younger("sample", age=10)
        assert not runez.file_younger("sample", age=-1)

        assert runez.copy("bar", "baz", fatal=False) == -1
        assert "does not exist" in logged.pop()

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
    assert not runez.file_younger(None, 1)
    assert not runez.file_younger("/dev/null/foo", 1)
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

        assert runez.write_contents("bar", "foo", fatal=False)
        assert "Can't write" in logged.pop()

        assert runez.copy("foo", "bar", fatal=False) == -1
        assert "Can't delete" in logged
        assert "Can't copy" in logged.pop()

        assert runez.make_executable("foo", fatal=False) == -1
        assert "Can't chmod" in logged.pop()


def test_temp():
    with runez.CaptureOutput(anchors=["/tmp", "/etc"]) as logged:
        with runez.TempFolder() as tmp:
            assert tmp
        assert "Deleting " in logged

        assert runez.short("/tmp/foo") == "foo"
        assert runez.short("/etc/foo") == "foo"

    with runez.CaptureOutput(dryrun=True) as logged:
        with runez.TempFolder() as tmp:
            assert tmp == "<tmp>"
            assert runez.short("<tmp>/foo") == "foo"
        assert "Would delete" in logged.pop()

        with runez.TempFolder(anchor=False) as tmp:
            assert tmp == "<tmp>"
            assert runez.short("<tmp>/foo") == "<tmp>/foo"
        assert "Would delete" in logged.pop()
