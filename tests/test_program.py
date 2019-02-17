import os

from mock import patch

import runez


CHATTER = """
#!/bin/bash

ls
ls some-file
echo
echo
"""


def test_capture(temp_folder, logged):
    chatter = runez.resolved_path("chatter")
    assert runez.write(chatter, CHATTER.strip(), fatal=False) == 1
    assert runez.make_executable(chatter, fatal=False) == 1

    assert runez.run(chatter, fatal=False) == "chatter"

    r = runez.run(chatter, include_error=True, fatal=False)
    assert r.startswith("chatter")
    assert "No such file" in r

    assert "Running: chatter" in logged


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


def test_program():
    assert runez.get_dev_folder("") is None
    assert runez.get_dev_folder("some-path/.venv/bar/baz") == "some-path/.venv"
    assert runez.get_dev_folder("some-path/.tox/bar/baz") == "some-path/.tox"
    assert runez.get_dev_folder("some-path/build/bar/baz") == "some-path/build"

    program_path = runez.get_program_path(path="/some/program")
    assert runez.basename(program_path) == "program"


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
        assert "/dev/null is not installed" in logged.pop()

        assert runez.touch("sample") == 1
        assert runez.run("ls", ".", path_env={"PATH": ":."}) == "sample"
        assert "Running:" in logged.pop()

        assert runez.run("ls", "some-file", fatal=False) is False
        assert "Running: " in logged
        assert "exited with code" in logged
        assert "No such file" in logged.pop()


def test_failed_run(logged):
    with patch("subprocess.Popen", side_effect=Exception("testing")):
        assert runez.run("ls", fatal=False) is False
        assert "ls failed: testing" in logged
