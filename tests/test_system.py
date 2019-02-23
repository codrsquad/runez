import time

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


def test_timezone():
    assert runez.get_timezone() == time.tzname[0]
    with patch("runez.system.time") as runez_time:
        runez_time.tzname = []
        assert runez.get_timezone() == ""


def test_version():
    v1 = runez.get_version(runez)
    v2 = runez.get_version(runez.__name__)
    assert v1 == v2


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
