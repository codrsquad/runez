import logging
import time

import pytest
from mock import patch

import runez

from .conftest import PROJECT


def test_default_settings(temp_settings):
    assert "pytest" in runez.log.Settings.basename
    assert runez.log.Settings.timezone == time.tzname[0]
    assert runez.log.Settings.dev.startswith(PROJECT)
    assert len(runez.log.Settings.uuid) == 32

    assert runez.log.Settings.formatted("") == ""
    assert runez.log.Settings.find_dev("") is None
    assert runez.log.Settings.find_dev("foo/.venv/bar/baz") == "foo/.venv"
    assert runez.log.Settings.is_using_format("") is False
    assert runez.log.Settings.usable_folder("") is None


def test_no_timezone(temp_settings):
    with patch("runez.log.time") as runez_time:
        runez_time.tzname = []
        assert runez.log.Settings.timezone == ""


def test_double_setup(temp_settings):
    runez.log.SETUP.context = ""
    with pytest.raises(Exception):
        runez.log.setup()


def test_console(temp_log):
    runez.log.Settings.console_format = "%(message)s"
    runez.log.setup()
    logging.info("hello")

    assert temp_log.files == ["test.log"]
    assert not temp_log.absent("test.log", "UTC [MainThread] INFO - hello")

    assert "hello" in temp_log
