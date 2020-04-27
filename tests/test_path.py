import os

import pytest

import runez


def test_basename():
    assert runez.basename(None) == ""
    assert runez.basename("/some-folder/bar") == "bar"
    assert runez.basename("/some-folder/.bar") == ".bar"
    assert runez.basename("/some-folder/.bar.py") == ".bar"
    assert runez.basename("/some-folder/.bar.baz.py") == ".bar.baz"
    assert runez.basename("some-folder/bar.py") == "bar"
    assert runez.basename("some-folder/bar.baz.pyc") == "bar.baz"

    assert runez.basename("some-folder/bar.py", extension_marker=None) == "bar.py"


def test_ensure_folder(temp_folder):
    assert runez.ensure_folder(None) == 0
    assert runez.ensure_folder("") == 0

    assert runez.ensure_folder("some-folder") == 0  # 'some-folder' would be in temp_folder, which already exists

    with runez.CaptureOutput():
        assert runez.touch("sample") == 1
        assert "Can't create folder" in runez.verify_abort(runez.ensure_folder, "sample", folder=True)
        custom = runez.verify_abort(runez.ensure_folder, "sample", folder=True, fatal=SystemExit, expected_exception=SystemExit)
        assert "Can't create folder" in custom
        with pytest.raises(AssertionError):
            assert runez.verify_abort(runez.ensure_folder, None)

        assert runez.delete("sample") == 1
        assert os.getcwd() == temp_folder


def test_parent_folder():
    cwd = os.getcwd()

    assert runez.parent_folder(None) is None
    assert runez.parent_folder("././some-file") == cwd

    if not runez.WINDOWS:
        parent = runez.parent_folder("/logs/foo")
        assert parent == "/logs"
        assert runez.parent_folder(parent) == "/"
        assert runez.parent_folder("/") == "/"
