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


def test_capture(temp_folder):
    with runez.CaptureOutput():
        chatter = runez.resolved_path("chatter")
        assert runez.write(chatter, CHATTER.strip(), fatal=False) == 1
        assert runez.make_executable(chatter, fatal=False) == 1

        assert runez.run(chatter, fatal=False) == "chatter"

        r = runez.run(chatter, include_error=True, fatal=False)
        assert r.startswith("chatter")
        assert "No such file" in r


def test_executable(temp_folder):
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


def test_program():
    program_path = runez.get_program_path()
    assert runez.basename(program_path) == "pytest"


def test_which():
    assert runez.which(None) is None
    assert runez.which("/dev/null") is None
    assert runez.which("dev/null") is None
    assert runez.which("ls")


def test_pids():
    assert runez.check_pid(0)
    assert runez.check_pid(os.getpid())
    assert not runez.check_pid(1)


def test_run(temp_folder):
    assert runez.program.added_env_paths(None) is None

    with runez.CaptureOutput(dryrun=True) as logged:
        assert "Would run: /dev/null" in runez.run("/dev/null", fatal=False)
        assert "Would run: /dev/null" in logged.pop()

        assert "Would run:" in runez.run("ls")
        assert "Would run:" in logged.pop()

    with runez.CaptureOutput() as logged:
        assert runez.run("/dev/null", fatal=False) is False
        assert "ERROR: /dev/null is not installed" in logged.pop()

        assert runez.touch("sample") == 1
        assert runez.run("ls", ".", path_env={"PATH": ":."}) == "sample"
        assert "Running:" in logged.pop()

        assert runez.run("ls", "foo", fatal=False) is False
        assert "Running: " in logged
        assert "exited with code" in logged
        assert "No such file" in logged.pop()


@patch("subprocess.Popen", side_effect=Exception("testing"))
def test_failed_run(_):
    with runez.CaptureOutput() as logged:
        assert runez.run("ls", fatal=False) is False
        assert "ERROR: ls failed: testing" in logged
