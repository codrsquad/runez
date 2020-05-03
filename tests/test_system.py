import os

import pytest
from mock import MagicMock, patch

import runez


def failed_function(*args):
    with patch("runez.system.logging.root") as root:
        root.handlers = None
        runez.abort(*args)


def mock_package(package, **kwargs):
    globs = {"__package__": package}
    for key, value in kwargs.items():
        globs["__%s__" % key] = value

    return MagicMock(f_globals=globs)


def test_abort(logged):
    assert runez.abort("aborted", fatal=(False, "some-return")) == "some-return"
    assert "aborted" in logged.pop()

    assert runez.abort("aborted", fatal=(False, "some-return"), code=0) == "some-return"
    assert "aborted" in logged
    assert "ERROR" not in logged.pop()

    assert runez.abort("aborted", fatal=(None, "some-return")) == "some-return"
    assert not logged
    assert "stderr: oops" in runez.verify_abort(failed_function, "oops")

    with patch("runez.system.AbortException", side_effect=str):
        assert runez.abort("oops", logger=None) == "1"


def test_auto_import_siblings():
    # Check that none of these invocations raise an exception
    assert not runez.system.actual_caller_frame(mock_package(None))
    assert not runez.system.actual_caller_frame(mock_package(""))
    assert not runez.system.actual_caller_frame(mock_package("_pydevd"))
    assert not runez.system.actual_caller_frame(mock_package("_pytest.foo"))
    assert not runez.system.actual_caller_frame(mock_package("pluggy.hooks"))
    assert not runez.system.actual_caller_frame(mock_package("runez"))
    assert not runez.system.actual_caller_frame(mock_package("runez.system"))

    assert runez.system.actual_caller_frame(mock_package("foo"))
    assert runez.system.actual_caller_frame(mock_package("runez.system", name="__main__"))

    with pytest.raises(ImportError):
        with patch("runez.system.find_caller_frame", return_value=None):
            runez.auto_import_siblings()

    with pytest.raises(ImportError):
        with patch("runez.system.find_caller_frame", return_value=mock_package("foo", name="__main__")):
            runez.auto_import_siblings()

    with pytest.raises(ImportError):
        with patch("runez.system.find_caller_frame", return_value=mock_package(None)):
            runez.auto_import_siblings()

    with pytest.raises(ImportError):
        with patch("runez.system.find_caller_frame", return_value=mock_package("foo")):
            runez.auto_import_siblings()

    with pytest.raises(ImportError):
        with patch("runez.system.find_caller_frame", return_value=mock_package("foo", file="/dev/null/foo")):
            runez.auto_import_siblings()

    with patch.dict(os.environ, {"TOX_WORK_DIR": "some-value"}, clear=True):
        imported = runez.auto_import_siblings(skip=["tests.test_base", "tests.test_system"])
        assert len(imported) == 20

        assert "tests.conftest" in imported
        assert "tests.secondary" in imported
        assert "tests.secondary.test_import" in imported
        assert "tests.test_base" not in imported
        assert "tests.test_click" in imported
        assert "tests.test_system" not in imported

    imported = runez.auto_import_siblings(skip=["tests.secondary"])
    assert len(imported) == 20
    assert "tests.conftest" in imported
    assert "tests.secondary" not in imported
    assert "tests.secondary.test_import" not in imported
    assert "tests.test_base" in imported


def test_current_test():
    assert runez.system.find_parent_folder("", {"foo"}) is None
    assert runez.system.find_parent_folder("/a/b//", {""}) is None
    assert runez.system.find_parent_folder("/a/b", {"a"}) == "/a"
    assert runez.system.find_parent_folder("/a/b//", {"a"}) == "/a"
    assert runez.system.find_parent_folder("//a/b//", {"a"}) == "//a"
    assert runez.system.find_parent_folder("/a/b", {"b"}) == "/a/b"
    assert runez.system.find_parent_folder("/a/B", {"a", "b"}) == "/a/B"  # case insensitive
    assert runez.system.find_parent_folder("/a/b", {"c"}) is None
    assert runez.system.find_parent_folder("/dev/null", {"foo"}) is None
    assert "test_system.py" in runez.current_test()


def test_failed_version(logged):
    with patch("pkg_resources.get_distribution", side_effect=Exception("testing")):
        assert runez.get_version(runez) == "0.0.0"
    assert "Can't determine version for runez" in logged


def test_formatted_string():
    assert runez.system._formatted_string() == ""

    assert runez.system._formatted_string("test") == "test"
    assert runez.system._formatted_string("test", "bar") == "test"
    assert runez.system._formatted_string("test %s", "bar") == "test bar"
    assert runez.system._formatted_string("test %s %s", "bar") == "test %s %s"

    assert runez.system._formatted_string(None) is None
    assert runez.system._formatted_string(None, "bar") is None

    assert runez.system._formatted_string("test", None) == "test"


def test_version():
    with runez.CaptureOutput() as logged:
        expected = runez.get_version(runez)
        assert expected
        assert expected != "0.0.0"
        assert expected == runez.get_version(runez.__name__)
        assert expected == runez.get_version("runez")
        assert expected == runez.get_version("runez.base")
        assert not logged

    with runez.CaptureOutput() as logged:
        assert runez.get_version(None) == "0.0.0"
        assert not logged

        assert runez.get_version(["foo"]) == "0.0.0"
        assert "Can't determine version" in logged.pop()
