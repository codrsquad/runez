import errno
import logging
import os
import subprocess
import sys
from unittest.mock import patch

import pytest

import runez
from runez.conftest import exception_raiser
from runez.program import RunAudit, RunResult

CHATTER = runez.DEV.tests_path("chatter")


def simulate_os_error(code):
    e = OSError(code)
    e.errno = code

    def do_raise(*_):
        raise e

    return do_raise


def test_background_run(logged):
    with runez.CurrentFolder(os.path.dirname(CHATTER)):
        r = runez.run(CHATTER, "hello", background=True, dryrun=True, logger=True)
        assert r.succeeded
        assert "chatter hello &" in logged.pop()

        r = runez.run(CHATTER, "hello", background=True, dryrun=False)
        assert r.succeeded
        assert r.pid
        assert r.output is None
        assert r.error is None
        assert "chatter hello &" in logged.pop()


class CrashingWrite:
    """Simulate a file/stream that keeps on crashing"""

    crash_counter = 0

    def write(self, message):
        self.crash_counter += 1
        raise RuntimeError("oops, failed to write %s" % message)


@pytest.mark.skipif(runez.SYS_INFO.platform_id.is_windows, reason="Not supported on windows")
def test_capture(monkeypatch):
    with runez.CurrentFolder(os.path.dirname(CHATTER)):
        # Check which finds programs in current folder
        assert runez.which("chatter") == CHATTER
        assert runez.shell("chatter hello") == "hello"

    with runez.CaptureOutput(dryrun=True) as logged:
        # Dryrun mode doesn't fail (since it doesn't actually run the program)
        r = runez.run(CHATTER, "silent-fail", fatal=True)
        assert r.succeeded
        assert "[dryrun] " in r.output
        assert r.error == ""
        assert "Would run:" in logged.pop()

        r = runez.run(CHATTER, "silent-fail", stdout=None, stderr=None, fatal=True)
        assert r.succeeded
        assert r.output is None
        assert r.error is None
        assert "Would run:" in logged.pop()

    with runez.CaptureOutput(seed_logging=True) as logged:
        # Test success
        assert runez.run(CHATTER, "hello", fatal=False) == RunResult("hello", "", 0)
        assert runez.run(CHATTER, "hello", fatal=True) == RunResult("hello", "", 0)
        assert "chatter hello" in logged.pop()
        assert runez.run(CHATTER, stdout=None) == RunResult(None, "", 0)
        assert "Running:" in logged.pop()

        r = runez.run(CHATTER, "hello", fatal=True, passthrough=True)
        assert r == RunResult("hello", "", 0)

        crasher = CrashingWrite()
        r = runez.run(CHATTER, "hello", fatal=True, passthrough=crasher)
        assert r == RunResult(None, None, 0)
        assert crasher.crash_counter
        assert "hello" in logged.pop()

        # Test no-wait
        r = runez.run(CHATTER, "hello", fatal=None, stdout=None, stderr=None)
        assert r.exit_code is None  # We don't know exit code because we didn't wait
        assert r.pid

        r = runez.run(CHATTER, stdout=None, stderr=None)
        assert r
        assert str(r) == "RunResult(exit_code=0)"
        assert r.succeeded
        assert r.output is None
        assert r.error is None
        assert r.full_output is None

        r = runez.run(CHATTER, "hello", path_env={"PATH": ":.", "CPPFLAGS": " -I/usr/local/opt/openssl/include"})
        assert str(r) == "RunResult(exit_code=0)"
        assert r.succeeded
        assert r.output == "hello"
        assert r.error == ""
        assert r.full_output == "hello"

        # Test stderr
        r = runez.run(CHATTER, "complain")
        assert r.succeeded
        assert r.output == ""
        assert r.error == "complaining"
        assert r.full_output == "complaining"
        logged.pop()

        # Test failure
        with pytest.raises(runez.system.AbortException):
            runez.run(CHATTER, "fail")
        assert "Run failed:" in logged.pop()

        r = runez.run(CHATTER, "silent-fail", fatal=False)
        assert str(r) == "RunResult(exit_code=1)"
        assert r.failed
        assert r.error == ""
        assert r.output == ""
        assert r.full_output == r.error

        if hasattr(subprocess.Popen, "__enter__"):
            # Simulate an EIO
            with patch("runez.program._read_data", side_effect=simulate_os_error(errno.EIO)):
                r = runez.run(CHATTER, "fail", fatal=False, passthrough=True)
                assert r.failed
                assert r.exc_info is None
                assert r.output == ""
                assert r.error == ""

            # Simulate an OSError
            with patch("runez.program._read_data", side_effect=simulate_os_error(errno.EINTR)):
                r = runez.run(CHATTER, "fail", fatal=False, passthrough=True)
                assert r.failed
                assert r.output is None
                assert "failed: OSError(" in r.error

        # Verify "exited with code ..." is mention in passthrough
        logged.clear()
        with pytest.raises(SystemExit):
            runez.run(CHATTER, "fail", fatal=SystemExit, passthrough=True)
        assert "exited with code" in logged.pop()

        with pytest.raises(runez.system.AbortException):
            runez.run(CHATTER, "fail", fatal=True, passthrough=True)
        assert "exited with code" in logged.pop()

        # Verify that silent pass-through gets at least mention of exit code
        with pytest.raises(SystemExit):
            runez.run(CHATTER, "silent-fail", fatal=SystemExit, passthrough=True)
        assert "exited with code" in logged.pop()

        with pytest.raises(runez.system.AbortException):
            runez.run(CHATTER, "silent-fail", fatal=True, passthrough=True)
        assert "exited with code" in logged.pop()

        r = runez.run(CHATTER, "fail", fatal=False, passthrough=True)
        assert r.failed
        assert r.error == "failed"
        assert r.output == "hello there"
        assert r.full_output == "failed\nhello there"

        r = runez.run("foo/bar", fatal=False)
        assert r.exit_code == 1
        assert "foo/bar is not an executable" in r.error

        r = runez.run("foo-bar-no-such-program", fatal=False)
        assert r.exit_code == 1
        assert "is not installed (PATH=" in r.error

        with monkeypatch.context() as m:
            m.setattr(subprocess, "Popen", exception_raiser(OSError("testing")))
            r = runez.run("python", "--version", fatal=False)
            assert not r
            assert r.failed
            assert "python failed: OSError(" in r.error
            assert r.output is None

            with pytest.raises(OSError, match="testing"):
                runez.run("python", "--version")

        # Test convenience arg None filtering
        logged.clear()
        assert runez.run(CHATTER, "hello", "-a", 0, "-b", None, 1, 2, None, "foo bar") == RunResult("hello -a 0 1 2 foo bar", "", 0)
        assert 'chatter hello -a 0 1 2 "foo bar"' in logged.pop()


@patch("runez.program.os.fork", return_value=None)
@patch("runez.program.os.setsid")
@patch("runez.program.os.open")
@patch("runez.program.os.dup2")
@patch("runez.program.os.close")
def test_daemonize(*_):
    # This simply exercises code daemonize() that would otherwise run in a forked process
    assert runez.program.daemonize() is None


@pytest.mark.skipif(runez.SYS_INFO.platform_id.is_windows, reason="Not supported on windows")
def test_executable(temp_folder):
    with runez.CaptureOutput(dryrun=True) as logged:
        assert runez.make_executable("some-file") == 1
        assert "Would make some-file executable" in logged.pop()
        assert runez.make_executable("some-file", logger=False) == 1
        assert not logged

    with runez.CaptureOutput() as logged:
        assert runez.touch("some-file") == 1
        assert "Touched some-file" in logged.pop()
        assert runez.delete("some-file") == 1
        assert "Deleted some-file" in logged.pop()
        assert runez.touch("some-file", logger=logging.debug) == 1
        assert "Touched some-file" in logged.pop()
        assert runez.make_executable("some-file", logger=logging.debug) == 1
        assert "Made 'some-file' executable" in logged.pop()
        assert runez.is_executable("some-file")
        assert runez.make_executable("some-file") == 0
        assert not logged

        assert runez.touch("some-file", logger=False) == 1
        assert runez.delete("some-file", logger=False) == 1
        assert not runez.is_executable("some-file")
        assert not logged

        assert runez.make_executable("/dev/null/some-file", fatal=False) == -1
        assert "does not exist, can't make it executable" in logged.pop()

        assert runez.make_executable("/dev/null/some-file", fatal=False, logger=None) == -1  # Don't log anything
        assert not logged

        assert runez.make_executable("/dev/null/some-file", fatal=False, logger=False) == -1  # Log errors only
        assert "does not exist, can't make it executable" in logged.pop()


def test_pids():
    assert not runez.check_pid(None)
    assert not runez.check_pid(0)
    assert not runez.check_pid("foo")  # garbage given, don't crash

    assert runez.check_pid(os.getpid())
    assert not runez.check_pid(1)  # No privilege to do this (tests shouldn't run as root)


def check_process_tree(pinfo, max_depth=10):
    """Verify that process info .parent does not recurse infinitely"""
    if pinfo:
        assert max_depth > 0
        check_process_tree(pinfo.parent, max_depth=max_depth - 1)


def test_ps():
    assert runez.PsInfo.from_pid(None) is None
    assert runez.PsInfo.from_pid(0) is None

    p = runez.PsInfo()
    check_process_tree(p)
    assert p == runez.PsInfo(0)
    assert p == runez.PsInfo("0")
    assert p == runez.PsInfo(os.getpid())
    assert p == runez.PsInfo("%s" % os.getpid())

    info = p.info
    assert info["PID"] in str(p)
    assert p.cmd
    assert p.cmd_basename
    assert p.ppid == os.getppid()
    assert p.userid != p.uid

    parent = p.parent
    assert parent.pid == p.ppid

    # Verify that both variants (user name or uid number) for UID work
    uid = p.uid
    userid = p.userid
    p = runez.PsInfo()
    if runez.to_int(info["UID"]) is None:
        p.info["UID"] = uid

    else:
        p.info["UID"] = userid

    assert p.uid == uid
    assert p.userid == userid

    # Edge case: verify __eq__ based on pid
    p.pid = 0
    assert p != runez.PsInfo(0)


def simulated_ps_output(pid, ppid, cmd):
    template = "UID   PID  PPID CMD\n  0 {pid:>5} {ppid:>5} {cmd}"
    return RunResult(output=template.format(pid=pid, ppid=ppid, cmd=cmd), code=0)


def simulated_tmux(program, *args, **_):
    if program == "tmux":
        return RunResult(output="3", code=0)

    if program == "id":
        if args[0] == "-un":
            return RunResult(output="root", code=0)

        return RunResult(output="0", code=0)

    assert program == "ps"
    pid = args[1]
    if pid == 1:
        return simulated_ps_output(pid, 0, "/sbin/init")

    if pid == 2:
        return simulated_ps_output(pid, 1, "tmux new-session ...")

    if pid == 3:
        return simulated_ps_output(pid, 1, "tmux attach-session ...")

    if pid == -1:
        return RunResult(code=1)

    return simulated_ps_output(pid, 2, "/dev/null/some-test foo bar")


def test_ps_follow():
    with patch("runez.program.run", side_effect=simulated_tmux):
        assert runez.PsInfo.from_pid(-1) is None
        bad_pid = runez.PsInfo(-1)
        assert str(bad_pid) == "-1 None None"
        assert bad_pid.cmd is None
        assert bad_pid.cmd_basename is None
        assert bad_pid.info is None
        assert bad_pid.followed_parent is None
        assert bad_pid.parent is None
        assert bad_pid.pid == -1
        assert bad_pid.ppid is None
        assert bad_pid.uid is None
        assert bad_pid.userid is None
        assert bad_pid.parent_list(follow=True) == []
        assert bad_pid.parent_list(follow=False) == []

        p = runez.PsInfo()
        assert p.cmd == "/dev/null/some-test foo bar"
        assert p.cmd_basename == "/dev/null/some-test"  # Falls back to using 1st sequence with space as basename
        assert p.uid == 0
        assert p.userid == "root"
        parents = p.parent_list(follow=False)
        followed_parents = p.parent_list(follow=True)

        # Verify that parent_list(follow=True) follows parent processes properly
        assert parents != followed_parents
        assert parents == [p.parent, p.parent.parent]
        assert followed_parents == [p.followed_parent, p.followed_parent.parent]

        with patch("runez.program.is_executable", side_effect=lambda x: x == "/dev/null/some-test foo"):
            # Edge case: verify that `ps` lack of quoting is properly detected
            p = runez.PsInfo()
            assert p.cmd == "/dev/null/some-test foo bar"
            assert p.cmd_basename == "some-test foo"


def test_require_installed(monkeypatch):
    monkeypatch.setattr(runez.program, "which", lambda _: "/bin/foo")
    assert runez.program.require_installed("foo") is None  # Does not raise

    monkeypatch.setattr(runez.program, "which", lambda _: None)
    with pytest.raises(runez.system.AbortException, match="foo is not installed, run: `brew install foo`"):
        runez.program.require_installed("foo", platform="macos")

    with pytest.raises(runez.system.AbortException, match="foo is not installed, run: `apt install foo`"):
        runez.program.require_installed("foo", platform="linux")

    with pytest.raises(runez.system.AbortException, match="foo is not installed, custom instructions"):
        runez.program.require_installed("foo", instructions="custom instructions", platform="macos")

    with pytest.raises(runez.system.AbortException, match="foo is not installed:\n- on "):
        runez.program.require_installed("foo", platform="unknown-platform")


def test_run_description():
    short_py = runez.short(sys.executable)
    audit = RunAudit(sys.executable, ["-mpip", "--help"], {})
    assert str(audit) == "pip --help"
    assert audit.run_description() == "pip --help"
    assert audit.run_description(short_exe=None) == "%s -mpip --help" % short_py
    assert audit.run_description(short_exe=False) == "%s -mpip --help" % short_py
    assert audit.run_description(short_exe=True) == "pip --help"
    assert audit.run_description(short_exe="foo") == "foo -mpip --help"

    audit = RunAudit(sys.executable, ["-m", "pip", "--help"], {})
    assert audit.run_description() == "pip --help"
    assert audit.run_description(short_exe=None) == "%s -m pip --help" % short_py
    assert audit.run_description(short_exe=False) == "%s -m pip --help" % short_py
    assert audit.run_description(short_exe=True) == "pip --help"
    assert audit.run_description(short_exe="foo") == "foo -m pip --help"

    audit = RunAudit(sys.executable, ["bin/pip/__main__.py", "--help"], {})
    assert audit.run_description() == "pip --help"
    assert audit.run_description(short_exe=None) == "%s bin/pip/__main__.py --help" % short_py
    assert audit.run_description(short_exe=False) == "%s bin/pip/__main__.py --help" % short_py
    assert audit.run_description(short_exe=True) == "pip --help"
    assert audit.run_description(short_exe="foo") == "foo bin/pip/__main__.py --help"

    audit = RunAudit("foo/python3", ["-mpip", "--help"], {})
    assert audit.run_description() == "foo/python3 -mpip --help"
    assert audit.run_description(short_exe=None) == "foo/python3 -mpip --help"
    assert audit.run_description(short_exe=False) == "foo/python3 -mpip --help"
    assert audit.run_description(short_exe=True) == "pip --help"
    assert audit.run_description(short_exe="foo") == "foo -mpip --help"

    audit = RunAudit("foo/bar", ["-mpip", "--help"], {})
    assert audit.run_description() == "foo/bar -mpip --help"
    assert audit.run_description(short_exe=None) == "foo/bar -mpip --help"
    assert audit.run_description(short_exe=False) == "foo/bar -mpip --help"
    assert audit.run_description(short_exe=True) == "foo/bar -mpip --help"
    assert audit.run_description(short_exe="foo") == "foo -mpip --help"

    cmd = runez.to_path(runez.SYS_INFO.venv_bin_path("foo"))
    audit = RunAudit(cmd, ["--help"], {})
    assert str(audit) == "foo --help"
    assert audit.run_description() == "foo --help"


def test_which():
    assert runez.which(None) is None
    assert runez.which("/dev/null") is None
    assert runez.which("dev/null") is None
    pp = runez.which(runez.to_path("python"))
    ps = runez.which("python")
    assert pp == ps


@pytest.mark.skipif(runez.SYS_INFO.platform_id.is_windows, reason="Not supported on windows")
def test_wrapped_run(monkeypatch):
    original = ["python", "-mvenv", "foo"]
    monkeypatch.delenv("PYCHARM_HOSTED", raising=False)
    with runez.program._WrappedArgs(original) as args:
        assert args == original

    monkeypatch.setenv("PYCHARM_HOSTED", "1")
    with runez.program._WrappedArgs(original) as args:
        assert args
        assert len(args) == 5
        assert args[0] == "/bin/sh"
        assert os.path.basename(args[1]) == "pydev-wrapper.sh"
