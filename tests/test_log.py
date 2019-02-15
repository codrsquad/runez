import logging

import pytest

import runez


def test_default_settings(isolated_log_setup):
    assert runez.log.Settings.basename == "pytest"

    assert runez.log.Settings.formatted("") == ""
    assert runez.log.Settings.find_dev("") is None
    assert runez.log.Settings.find_dev("foo/.venv/bar/baz") == "foo/.venv"
    assert runez.log.Settings.is_using_format("") is False
    assert runez.log.Settings.usable_folder("") is None


def test_double_setup(isolated_log_setup):
    runez.log.SETUP.context = ""
    with pytest.raises(Exception):
        runez.log.setup()


def test_console(temp_log):
    assert temp_log.logged == "stdout: stderr: LogCaptureHandler:"

    runez.log.Settings.console_format = "%(message)s"
    runez.log.setup()
    logging.info("hello")

    assert temp_log.files == ["pytest.log"]
    assert not temp_log.absent("pytest.log", "UTC [MainThread] INFO - hello")

    assert "hello" in temp_log
