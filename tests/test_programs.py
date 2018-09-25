import os

from mock import patch

import runez


CHATTER = """
#!/bin/bash

ls
ls foo
echo
echo
"""


def test_capture(temp_base):
    with runez.CaptureOutput():
        chatter = runez.resolved_path("chatter")
        runez.write_contents(chatter, CHATTER.strip())
        runez.make_executable(chatter)

        assert runez.run_program(chatter, fatal=False) == "chatter"

        r = runez.run_program(chatter, include_error=True, fatal=False)
        assert r.startswith("chatter")
        assert "No such file" in r


def test_executable(temp_base):
    with runez.CaptureOutput(dryrun=True) as logged:
        assert runez.make_executable("foo") == 1
        assert "Would make foo executable" in logged

    assert runez.touch("foo") == 1
    assert runez.make_executable("foo") == 1
    assert runez.is_executable("foo")
    assert runez.make_executable("foo") == 0

    assert runez.delete("foo") == 1
    assert not runez.is_executable("foo")

    with runez.CaptureOutput() as logged:
        assert runez.make_executable("/dev/null/foo", fatal=False) == -1
        assert "does not exist, can't make it executable" in logged


def test_which():
    assert runez.which(None) is None
    assert runez.which("/dev/null") is None
    assert runez.which("dev/null") is None
    assert runez.which("ls")


def test_pids():
    assert runez.check_pid(0)
    assert runez.check_pid(os.getpid())
    assert not runez.check_pid(1)


def test_run(temp_base):
    assert runez.added_env_paths(None) is None

    with runez.CaptureOutput(dryrun=True) as logged:
        assert "Would run: /dev/null" in runez.run_program("/dev/null", fatal=False)
        assert "Would run: /dev/null" in logged.pop()

        assert "Would run:" in runez.run_program("ls")
        assert "Would run:" in logged.pop()

    with runez.CaptureOutput() as logged:
        assert runez.run_program("/dev/null", fatal=False) is None
        assert "ERROR: /dev/null is not installed" in logged.pop()

        assert runez.touch("sample") == 1
        assert runez.run_program("ls", ".", path_env={"PATH": ":."}) == "sample"
        assert "Running:" in logged.pop()

        assert runez.run_program("ls", "foo", fatal=False) is None
        assert "Running: " in logged
        assert "exited with code" in logged
        assert "No such file" in logged.pop()


@patch("subprocess.Popen", side_effect=Exception("testing"))
def test_failed_run(_):
    with runez.CaptureOutput() as logged:
        assert runez.run_program("ls", fatal=False) is None
        assert "ERROR: ls failed: testing" in logged
