import time

from mock import patch

import runez


def test_abort(logged):
    assert runez.abort("aborted", fatal=(False, "some-return")) == "some-return"
    assert "aborted" in logged.pop()

    assert runez.abort("aborted", fatal=(False, "some-return"), code=0) == "some-return"
    assert "aborted" in logged
    assert "ERROR" not in logged.pop()

    assert runez.abort("aborted", fatal=(None, "some-return")) == "some-return"
    assert not logged


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
