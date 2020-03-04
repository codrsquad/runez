from mock import patch

import runez


def failed_function(*args):
    with patch("runez.system.logging.root") as root:
        root.handlers = None
        runez.abort(*args)


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


def test_current_test():
    assert "test_system.py" in runez.current_test()


def test_failed_version(logged):
    with patch("pkg_resources.get_distribution", side_effect=Exception("testing")):
        assert runez.get_version(runez) == "0.0.0"
    assert "Can't determine version for runez" in logged


def test_formatted_string():
    assert runez.system.formatted_string() == ""

    assert runez.system.formatted_string("test") == "test"
    assert runez.system.formatted_string("test", "bar") == "test"
    assert runez.system.formatted_string("test %s", "bar") == "test bar"
    assert runez.system.formatted_string("test %s %s", "bar") == "test %s %s"

    assert runez.system.formatted_string(None) is None
    assert runez.system.formatted_string(None, "bar") is None

    assert runez.system.formatted_string("test", None) == "test"


def test_platform():
    assert runez.get_platform()


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
