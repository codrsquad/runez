import os

import pytest
from mock import patch

import runez
from runez.conftest import test_resource, verify_abort


CHATTER = test_resource("chatter")


@pytest.mark.skipif(runez.WINDOWS, reason="Not supported on windows")
def test_capture():
    with runez.CurrentFolder(os.path.dirname(CHATTER)):
        # Check which finds programs in current folder
        assert runez.which("chatter") == CHATTER

    with runez.CaptureOutput(dryrun=True) as logged:
        r = runez.run(CHATTER, "silent-fail", fatal=None)
        assert r.succeeded
        assert "Would run:" in r.output
        assert r.error == ""
        assert "Would run:" in logged.pop()

        r = runez.run(CHATTER, "silent-fail", stdout=None, stderr=None, fatal=None)
        assert r.succeeded
        assert r.output is None
        assert r.error is None
        assert "Would run:" in logged.pop()

    with runez.CaptureOutput(seed_logging=True) as logged:
        # Test success
        assert runez.run(CHATTER, "hello", fatal=False) == "hello"
        assert runez.run(CHATTER, "hello", fatal=True) == "hello"
        assert "chatter hello" in logged.pop()
        assert runez.run(CHATTER, stdout=None) == 0

        r = runez.run(CHATTER, stdout=None, stderr=None, fatal=None)
        assert str(r) == "RunResult(exit_code=0)"
        assert r.succeeded
        assert r.output is None
        assert r.error is None
        assert r.full_output is None

        r = runez.run(CHATTER, "hello", fatal=None, path_env={"PATH": ":."})
        assert str(r) == "RunResult(exit_code=0)"
        assert r.succeeded
        assert r.output == "hello"
        assert r.error == ""
        assert r.full_output == "hello"

        # Test stderr
        r = runez.run(CHATTER, "complain", fatal=None)
        assert r.succeeded
        assert r.output == ""
        assert r.error == "complaining"
        assert r.full_output == "complaining"

        # Test failure
        r = runez.run(CHATTER, "silent-fail", fatal=None)
        assert str(r) == "RunResult(exit_code=1)"
        assert r.failed
        assert "exited with code" in r.error
        assert r.output == ""
        assert r.full_output == r.error

        r = runez.run(CHATTER, "fail", fatal=None)
        assert r.failed
        assert r.error == "failed"
        assert r.output == ""
        assert r.full_output == "failed"

        assert runez.run("/dev/null", fatal=False) is False
        assert runez.run("/dev/null", fatal=None) == runez.program.RunResult(None, "/dev/null is not installed", 1)
        assert "ERROR" in verify_abort(runez.run, CHATTER, "fail", fatal=True)

        with patch("subprocess.Popen", side_effect=Exception("testing")):
            r = runez.run("python", "--version", fatal=None)
            assert r.failed
            assert r.error == "python failed: testing"
            assert r.output is None
            assert r.full_output == "python failed: testing"

        # Test convenience arg None filtering
        logged.clear()
        assert runez.run(CHATTER, "hello", "-a", 0, "-b", None, 1, 2, None, "foo bar") == "hello -a 0 1 2 foo bar"
        assert 'chatter hello -a 0 1 2 "foo bar"' in logged.pop()


@pytest.mark.skipif(runez.WINDOWS, reason="Not supported on windows")
def test_executable(temp_folder):
    with runez.CaptureOutput(dryrun=True) as logged:
        assert runez.make_executable("some-file") == 1
        assert "Would make some-file executable" in logged

    assert runez.touch("some-file") == 1
    assert runez.make_executable("some-file") == 1
    assert runez.is_executable("some-file")
    assert runez.make_executable("some-file") == 0

    assert runez.delete("some-file") == 1
    assert not runez.is_executable("some-file")

    with runez.CaptureOutput() as logged:
        assert runez.make_executable("/dev/null/some-file", fatal=False) == -1
        assert "does not exist, can't make it executable" in logged


def test_terminal_width():
    with patch.dict(os.environ, {"COLUMNS": ""}, clear=True):
        tw = runez.terminal_width()
        if runez.PY2:
            assert tw is None

        else:
            assert tw is not None

        with patch("runez.program._tw_shutil", return_value=None):
            assert runez.terminal_width() is None
            assert runez.terminal_width(default=5) == 5

        with patch("runez.program._tw_shutil", return_value=10):
            assert runez.terminal_width() == 10
            assert runez.terminal_width(default=5) == 10

    with patch.dict(os.environ, {"COLUMNS": "25"}, clear=True):
        assert runez.terminal_width() == 25


def test_which():
    assert runez.which(None) is None
    assert runez.which("/dev/null") is None
    assert runez.which("dev/null") is None
    assert runez.which("python")


def test_require_installed():
    with patch("runez.program.which", return_value="/bin/foo"):
        assert runez.program.require_installed("foo") is True

    with patch("runez.program.which", return_value=None):
        with runez.CaptureOutput() as logged:
            runez.program.require_installed("foo", fatal=False, platform="darwin")
            assert "foo is not installed, run: `brew install foo`" in logged.pop()

            runez.program.require_installed("foo", instructions="see http:...", fatal=False, platform="darwin")
            assert "foo is not installed, see http:..." in logged.pop()

            runez.program.require_installed("foo", fatal=False, platform="linux")
            assert "foo is not installed, run: `apt install foo`" in logged.pop()

            runez.program.require_installed("foo", instructions={"linux": "see http:..."}, fatal=False, platform="linux")
            assert "foo is not installed, see http:..." in logged.pop()

            runez.program.require_installed("foo", instructions={"linux": "see http:..."}, fatal=False, platform=None)
            assert "foo is not installed, on linux: see http:..." in logged.pop()

            runez.program.require_installed("foo", fatal=False, platform=None)
            message = logged.pop()
            assert "foo is not installed:\n" in message
            assert "- on darwin: run: `brew install foo`" in message
            assert "- on linux: run: `apt install foo`" in message


def test_pids():
    if not runez.WINDOWS:
        assert runez.check_pid(0)

    assert runez.check_pid(os.getpid())
    assert not runez.check_pid(1)


@pytest.mark.skipif(runez.WINDOWS, reason="Not supported on windows")
def test_wrapped_run():
    original = ["python", "-mvenv", "foo"]
    with patch.dict(os.environ, {}, clear=True):
        with runez.program._WrappedArgs(original) as args:
            assert args == original

    with patch.dict(os.environ, {"PYCHARM_HOSTED": "1"}):
        with runez.program._WrappedArgs(original) as args:
            assert args
            assert len(args) == 5
            assert args[0] == "/bin/sh"
            assert os.path.basename(args[1]) == "pydev-wrapper.sh"
