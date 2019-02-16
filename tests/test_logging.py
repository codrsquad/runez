import logging
import os
import sys

import pytest
from mock import patch

import runez


LOG = logging.getLogger(__name__)


def test_settings(isolated_log_setup):
    assert runez.LogSettings.basename == "pytest"
    assert runez.LogSettings.dev

    assert runez.LogSettings.formatted("") == ""
    assert runez.LogSettings.formatted("{not_there}") is None
    assert runez.LogSettings.formatted("{filename}") == "pytest.log"
    assert runez.LogSettings.formatted("{basename}/{filename}") == "pytest/pytest.log"

    assert runez.LogSettings.find_dev("") is None
    assert runez.LogSettings.find_dev("some-path/.venv/bar/baz") == "some-path/.venv"

    fmt = "%(asctime)s %(context)s%(levelname)s - %(message)s"
    assert runez.logging.is_using_format("", fmt) is False
    assert runez.logging.is_using_format("%(lineno)d", fmt) is False
    assert runez.logging.is_using_format("%(context)s", fmt) is True
    assert runez.logging.is_using_format("%(context)s %(lineno)d", fmt) is True
    assert runez.logging.is_using_format("%(context)s", "") is False

    # signum=None is equivalent to disabling faulthandler
    runez.LogContext.enable_faulthandler(signum=None)
    assert runez.LogContext.faulthandler_signum is None
    # We didn't call setup, so enabling faulthandler will do nothing
    runez.LogContext.enable_faulthandler()
    assert runez.LogContext.faulthandler_signum is None

    cwd = os.getcwd()
    assert not runez.State.dryrun
    with runez.TempFolder(dryrun=False) as tmp:
        runez.touch("some-file")
        assert runez.LogSettings.usable_location("") is None
        assert runez.LogSettings.usable_location("./some-name.log") == "./some-name.log"
        assert runez.LogSettings.usable_location("./some-folder/bar.log") == "./some-folder/bar.log"
        with patch("os.mkdir", side_effect=IOError):
            # Can't use a location if subfolder can't be created
            assert runez.LogSettings.usable_location("./some-other-folder/bar.log") is None
        assert runez.LogSettings.usable_location("./too/many/subfolders.log") is None
        assert runez.LogSettings.usable_location("./some-file/bar.log") is None
        assert runez.LogSettings.usable_location("./some-file/subfolder/bar.log") is None

        assert runez.LogSettings.usable_location("some-name.log") == "some-name.log"
        assert runez.LogSettings.usable_location("some-folder/bar.log") == "some-folder/bar.log"

        runez.LogSettings.dev = tmp
        assert runez.LogSettings.resolved_location(".") == "./pytest.log"
        assert runez.LogSettings.resolved_location(None) == os.path.join(tmp, "pytest.log")

        runez.LogContext.setup(dryrun=True)
        with pytest.raises(Exception):
            runez.LogContext.setup()

        runez.LogSettings.locations = None
        assert runez.LogSettings.resolved_location(None) is None

        if runez.logging.faulthandler:
            # Available only in python3
            runez.LogContext.enable_faulthandler()
            assert runez.LogContext.faulthandler_signum

    assert not runez.State.dryrun
    assert os.getcwd() == cwd


def test_default(temp_log):
    runez.LogContext.set_global_context(version="1.0")
    runez.LogContext.add_global_context(worker="mark")
    runez.LogContext.add_thread_context(worker="joe", foo="bar")
    runez.LogContext.set_thread_context(worker="joe")
    runez.LogContext.setup()

    assert temp_log.logfile == "pytest.log"
    logging.info("hello")

    temp_log.expect_logged("UTC [MainThread] [[version=1.0,worker=joe]] INFO - hello")
    assert "INFO hello" in temp_log.stderr


def test_console(temp_log):
    runez.LogContext.setup(location="")
    assert temp_log.logfile is None
    logging.info("hello")
    assert "INFO hello" in temp_log.stderr


def test_no_context(temp_log):
    runez.LogContext.set_global_context(version="1.0")
    runez.LogSettings.timezone = ""
    runez.LogSettings.file_format = "%(asctime)s [%(threadName)s] %(timezone)s %(levelname)s - %(message)s"
    runez.LogContext.setup()
    logging.info("hello")
    temp_log.expect_logged("[MainThread] INFO - hello")


def test_context(temp_log):
    runez.LogSettings.locations = None
    runez.LogSettings.console_stream = sys.stdout
    runez.LogSettings.console_format = "%(name)s %(timezone)s %(context)s%(levelname)s - %(message)s"
    runez.LogContext.setup()

    assert temp_log.logfile is None

    # Edge case: verify adding/removing ends up with empty context
    runez.LogContext.add_global_context(x="y")
    runez.LogContext.remove_global_context("x")
    assert runez.LogContext._gpayload is None

    runez.LogContext.add_thread_context(x="y")
    runez.LogContext.remove_thread_context("x")
    assert runez.LogContext._tpayload is None

    # Add a couple global/thread context values
    runez.LogContext.set_global_context(version="1.0", name="foo")
    runez.LogContext.add_thread_context(worker="susan", a="b")
    logging.info("hello")
    assert temp_log.stdout.pop().strip() == "test_logging UTC [[a=b,name=foo,version=1.0,worker=susan]] INFO - hello"

    # Remove them one by one
    runez.LogContext.remove_thread_context("a")
    logging.info("hello")
    assert temp_log.stdout.pop().strip() == "test_logging UTC [[name=foo,version=1.0,worker=susan]] INFO - hello"

    runez.LogContext.remove_global_context("name")
    logging.info("hello")
    assert temp_log.stdout.pop().strip() == "test_logging UTC [[version=1.0,worker=susan]] INFO - hello"

    runez.LogContext.clear_thread_context()
    logging.info("hello")
    assert temp_log.stdout.pop().strip() == "test_logging UTC [[version=1.0]] INFO - hello"

    runez.LogContext.clear_global_context()
    logging.info("hello")
    assert temp_log.stdout.pop().strip() == "test_logging UTC INFO - hello"

    assert runez.LogContext._gpayload is None
    assert runez.LogContext._tpayload is None


def test_convenience(temp_log):
    fmt = "%(name)s f:%(filename)s mod:%(module)s func:%(funcName)s %(levelname)s %(message)s "
    fmt += " path:%(pathname)s"
    runez.LogSettings.console_format = fmt
    runez.LogSettings.file_format = None
    runez.LogContext.setup()

    assert temp_log.logfile is None
    runez.write("some-file", "some content", logger=logging.info)
    logging.info("hello")
    logging.exception("oops")

    assert "runez.file f:file.py mod:file func:write INFO Writing 12 bytes" in temp_log.stderr
    assert "test_logging f:test_logging.py mod:test_logging func:test_convenience INFO hello" in temp_log.stderr
    assert "test_logging f:test_logging.py mod:test_logging func:test_convenience ERROR oops" in temp_log.stderr
    temp_log.stderr.clear()

    runez.write("some-file", "some content", logger=LOG.info)
    LOG.info("hello")
    LOG.exception("oops")
    assert "test_logging f:file.py mod:file func:write INFO Writing 12 bytes" in temp_log.stderr
    assert "test_logging f:test_logging.py mod:test_logging func:test_convenience INFO hello" in temp_log.stderr
    assert "test_logging f:test_logging.py mod:test_logging func:test_convenience ERROR oops" in temp_log.stderr
