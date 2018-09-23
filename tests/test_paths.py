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

    assert runez.short(temp_base + "/foo", anchors=temp_base) == "foo"
    assert runez.short(temp_base + "/foo", anchors=[temp_base]) == "foo"

    assert runez.parent_folder(None) is None
    assert runez.parent_folder(temp_base + "/foo") == temp_base

    assert runez.represented_args(["ls", temp_base + "/foo", "-a"], anchors=temp_base) == "ls foo -a"

    # Don't crash for no-ops
    assert runez.ensure_folder(None) == 0
    assert runez.ensure_folder("") == 0
    assert runez.copy_file(None, None) == 0
    assert runez.copy_file("foo", "foo") == 0
    assert runez.move_file(None, None) == 0
    assert runez.move_file("foo", "foo") == 0

    assert runez.ensure_folder("foo") == 0  # 'foo' would be in temp_base, which already exists

    with runez.CaptureOutput(dryrun=True) as logged:
        assert runez.ensure_folder("foo", folder=True, fatal=False) == 1
        assert "Would create" in logged

        assert runez.touch("foo") == 1
        assert "Would touch foo" in logged

        assert runez.copy_file("foo", "bar") == 1
        assert "Would copy" in logged

        assert runez.delete_file(temp_base) == 1
        assert "Would delete" in logged

    assert runez.touch("foo") == 1
    assert "Can't create folder" in runez.verify_abort(runez.ensure_folder, "foo", folder=True)
    assert runez.verify_abort(runez.ensure_folder, None) is None

    assert runez.delete_file("foo") == 1
    assert runez.ensure_folder("foo", folder=True) == 1
    assert os.getcwd() == temp_base
    with runez.CurrentFolder("foo"):
        assert os.getcwd() == os.path.join(temp_base, "foo")
    assert os.getcwd() == temp_base

    assert runez.delete_file("foo") == 1

    with runez.CaptureOutput() as logged:
        assert runez.write_contents("foo", "bar\nbaz\n\n", verbose=True)
        assert runez.get_lines("foo") == ["bar\n", "baz\n", "\n"]
        assert "Writing 9 bytes" in logged

        assert runez.first_line("foo") == "bar"
        assert runez.file_younger("foo", age=10)
        assert not runez.file_younger("foo", age=-1)

        assert runez.copy_file("bar", "baz", fatal=False) == -1
        assert "does not exist" in logged

    assert runez.copy_file("foo", "bar") == 1
    assert runez.move_file("foo", "baz") == 1

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
        assert "Can't read" in logged

        assert runez.write_contents("bar", "foo", fatal=False)
        assert "Can't write" in logged

        assert runez.copy_file("foo", "bar", fatal=False) == -1
        assert "Can't delete" in logged
        assert "Can't copy" in logged
