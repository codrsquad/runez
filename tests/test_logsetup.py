import logging
import os
import sys
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler

import pytest
from mock import patch

import runez


LOG = logging.getLogger(__name__)


def test_logspec(isolated_log_setup):
    s1 = runez.LogSpec(runez.log._default_spec, appname="pytest")
    s2 = runez.LogSpec(runez.log._default_spec, appname="pytest")
    assert s1 == s2
    assert s1.appname == "pytest"
    assert s1.timezone == "UTC"
    assert s1.should_log_to_file
    assert s1.usable_location() == "/tmp/pytest.log"

    # No basename -> can't determine a usable location anymore
    s1.basename = None
    assert s1.should_log_to_file
    assert s1.usable_location() is None

    s1.set(basename="testing.log", timezone=None, locations=[s1.tmp])
    assert s1.basename == "testing.log"
    assert s1.timezone is None
    assert s1.usable_location() == "/tmp/testing.log"
    assert s1 != s2

    # Empty string custom location just disables file logging
    s1.file_location = ""
    assert not s1.should_log_to_file
    assert s1.usable_location() is None

    # No basename, and custom location points to folder -> not usable
    s1.basename = None
    s1.file_location = "/tmp"
    assert s1.should_log_to_file
    assert s1.usable_location() is None

    # Restore from other spec
    s1.set(s2)
    assert s1 == s2

    s1.set(s2, timezone="hello")
    assert s1 != s2
    assert s1.timezone == "hello"

    s1.set(s2, timezone=runez.UNSET)
    assert s1 == s2

    # No-ops, because targets don't have any meaningful values
    s1.set(not_valid="this is not a field of LogSpec")
    assert s1 == s2

    s1.set("hello")
    assert s1 == s2

    s1.set(s2, "hello")
    assert s1 == s2


def test_setup(temp_log):
    fmt = "%(asctime)s %(context)s%(levelname)s - %(message)s"
    assert runez.log.is_using_format("", fmt) is False
    assert runez.log.is_using_format("%(lineno)d", fmt) is False
    assert runez.log.is_using_format("%(context)s", fmt) is True
    assert runez.log.is_using_format("%(context)s %(lineno)d", fmt) is True
    assert runez.log.is_using_format("%(context)s", "") is False

    # signum=None is equivalent to disabling faulthandler
    runez.log.enable_faulthandler(signum=None)
    assert runez.log.faulthandler_signum is None
    # We didn't call setup, so enabling faulthandler will do nothing
    runez.log.enable_faulthandler()
    assert runez.log.faulthandler_signum is None

    cwd = os.getcwd()
    assert not runez.DRYRUN
    with runez.TempFolder(dryrun=False):
        assert not runez.log.debug

        # Auto-debug on dryrun
        runez.log.setup(dryrun=True, level=logging.INFO)
        assert runez.log.debug
        logging.debug("hello")
        assert runez.log.debug
        assert not temp_log.stdout
        assert "DEBUG hello" in temp_log.stderr.pop()

        # Second call without any customization is a no-op
        runez.log.setup()
        assert runez.log.debug
        logging.debug("hello")
        assert not temp_log.stdout
        assert "DEBUG hello" in temp_log.stderr.pop()

        # Change stream
        runez.log.setup(console_stream=sys.stdout)
        logging.debug("hello")
        assert "DEBUG hello" in temp_log.stdout.pop()
        assert not temp_log.stderr

        # Change logging level
        runez.log.setup(debug=False, console_level=logging.INFO)
        assert not runez.log.debug
        logging.debug("hello")
        assert not temp_log.stdout
        assert not temp_log.stderr
        logging.info("hello")
        assert "INFO hello" in temp_log.stdout.pop()
        assert not temp_log.stderr

        # Change format
        runez.log.setup(console_format="%(levelname)s - %(message)s")
        assert not runez.log.debug
        logging.info("hello")
        assert "INFO - hello" in temp_log.stdout.pop()
        assert not temp_log.stderr

        if runez.logsetup.faulthandler:
            # Available only in python3
            runez.log.enable_faulthandler()
            assert runez.log.faulthandler_signum

    assert not runez.DRYRUN
    assert os.getcwd() == cwd


def test_default(temp_log):
    runez.log.context.set_global(version="1.0")
    runez.log.context.add_global(worker="mark")
    runez.log.context.add_threadlocal(worker="joe", foo="bar")
    runez.log.context.set_threadlocal(worker="joe")
    runez.log.setup(greetings="Logging to: {location}, pid {pid}")

    assert temp_log.logfile == "pytest.log"
    temp_log.expect_logged("Logging to: ")
    temp_log.expect_logged("pytest.log, pid %s" % os.getpid())

    logging.info("hello")
    logging.warning("hello")
    temp_log.expect_logged("UTC [[version=1.0,worker=joe]] INFO - hello")
    temp_log.expect_logged("UTC [[version=1.0,worker=joe]] WARNING - hello")
    assert "INFO hello" not in temp_log.stderr
    assert "WARNING hello" in temp_log.stderr

    # Now stop logging context
    runez.log.setup(file_format="%(asctime)s %(timezone)s %(levelname)s - %(message)s")
    logging.info("hello")
    logging.warning("hello")
    temp_log.expect_logged("UTC INFO - hello")
    temp_log.expect_logged("UTC WARNING - hello")


def test_level(temp_log):
    runez.log.setup(file_format=None, level=logging.INFO)

    assert not temp_log
    assert temp_log.logfile is None
    logging.debug("debug msg")
    logging.info("info msg")
    assert "debug msg" not in temp_log.stderr
    assert "info msg" in temp_log.stderr


def test_console(temp_log):
    logger = logging.getLogger("runez")
    old_level = logger.level

    try:
        runez.log.setup(console_level=logging.DEBUG, file_location="", greetings=["Logging to: {location}", ":: argv: {argv}"])

        assert temp_log.logfile is None
        assert "DEBUG Logging to: file log disabled" in temp_log.stderr
        assert ":: argv: " in temp_log.stderr
        logger.info("hello")
        assert "INFO hello" in temp_log.stderr

        temp_log.clear()
        runez.log.silence(runez)
        logger.info("hello")
        assert not temp_log

    finally:
        logger.setLevel(old_level)


def test_no_context(temp_log):
    runez.log.context.set_global(version="1.0")
    runez.log.spec.set(timezone="", file_format="%(asctime)s [%(threadName)s] %(timezone)s %(levelname)s - %(message)s")
    runez.log.setup()
    logging.info("hello")
    temp_log.expect_logged("[MainThread] INFO - hello")


def test_context(temp_log):
    runez.log.spec.locations = None
    runez.log.spec.console_stream = sys.stdout
    runez.log.spec.console_format = "%(timezone)s %(context)s%(levelname)s - %(message)s"
    runez.log.spec.console_level = logging.DEBUG
    runez.log.setup(greetings=None)

    assert temp_log.logfile is None

    # Edge case: verify adding/removing ends up with empty context
    runez.log.context.add_global(x="y")
    runez.log.context.remove_global("x")
    assert not runez.log.context.has_global()

    runez.log.context.add_threadlocal(x="y")
    runez.log.context.remove_threadlocal("x")
    assert not runez.log.context.has_threadlocal()

    # Add a couple global/thread context values
    runez.log.context.set_global(version="1.0", name="foo")
    runez.log.context.add_threadlocal(worker="susan", a="b")
    logging.info("hello")
    assert temp_log.stdout.pop(strip=True) == "UTC [[a=b,name=foo,version=1.0,worker=susan]] INFO - hello"

    # Remove them one by one
    runez.log.context.remove_threadlocal("a")
    logging.info("hello")
    assert temp_log.stdout.pop(strip=True) == "UTC [[name=foo,version=1.0,worker=susan]] INFO - hello"

    runez.log.context.remove_global("name")
    logging.info("hello")
    assert temp_log.stdout.pop(strip=True) == "UTC [[version=1.0,worker=susan]] INFO - hello"

    runez.log.context.clear_threadlocal()
    logging.info("hello")
    assert temp_log.stdout.pop(strip=True) == "UTC [[version=1.0]] INFO - hello"

    runez.log.context.clear_global()
    logging.info("hello")
    assert temp_log.stdout.pop(strip=True) == "UTC INFO - hello"

    assert not runez.log.context.has_global()
    assert not runez.log.context.has_threadlocal()


def test_convenience(temp_log):
    fmt = "f:%(filename)s mod:%(module)s func:%(funcName)s %(levelname)s %(message)s "
    fmt += " path:%(pathname)s"
    runez.log.setup(console_format=fmt, console_level=logging.DEBUG, file_format=None)

    assert temp_log.logfile is None
    runez.write("some-file", "some content", logger=logging.info)
    logging.info("hello")
    logging.exception("oops")

    assert "f:file.py mod:file func:write INFO Writing 12 bytes" in temp_log.stderr
    assert "f:test_logsetup.py mod:test_logsetup func:test_convenience INFO hello" in temp_log.stderr
    assert "f:test_logsetup.py mod:test_logsetup func:test_convenience ERROR oops" in temp_log.stderr
    temp_log.stderr.clear()

    runez.write("some-file", "some content", logger=LOG.info)
    LOG.info("hello")
    LOG.exception("oops")
    assert "f:file.py mod:file func:write INFO Writing 12 bytes" in temp_log.stderr
    assert "f:test_logsetup.py mod:test_logsetup func:test_convenience INFO hello" in temp_log.stderr
    assert "f:test_logsetup.py mod:test_logsetup func:test_convenience ERROR oops" in temp_log.stderr


def test_auto_location_not_writable(temp_log):
    with patch("runez.path.os.access", return_value=False):
        runez.log.setup(
            greetings="Logging to: {location}",
            console_format="%(name)s f:%(filename)s mod:%(module)s func:%(funcName)s %(levelname)s - %(message)s",
            console_level=logging.DEBUG,
        )

        assert "runez.logsetup f:logsetup.py mod:logsetup func:greet DEBUG" in temp_log.stderr
        assert "Logging to: no usable locations" in temp_log.stderr

        assert runez.log.file_handler is None


def test_file_location_not_writable(temp_log):
    runez.log.setup(
        greetings="Logging to: {location}",
        console_level=logging.DEBUG,
        file_location="/dev/null/somewhere.log",
    )

    assert "DEBUG Can't create folder /dev/null" in temp_log.stderr
    assert "DEBUG Logging to: /dev/null/somewhere.log is not usable" in temp_log.stderr

    assert runez.log.file_handler is None


def test_bad_rotate(temp_log):
    with pytest.raises(ValueError):
        runez.log.setup(rotate="foo")


def test_log_rotate(temp_folder):
    with pytest.raises(ValueError):
        assert runez.logsetup._get_file_handler("test.log", "time", 0) is None

    with pytest.raises(ValueError):
        assert runez.logsetup._get_file_handler("test.log", "time:unclear", 0) is None

    with pytest.raises(ValueError):
        assert runez.logsetup._get_file_handler("test.log", "time:h", 0) is None

    with pytest.raises(ValueError):
        assert runez.logsetup._get_file_handler("test.log", "time:1h,something", 0) is None

    with pytest.raises(ValueError):
        assert runez.logsetup._get_file_handler("test.log", "size:not a number,3", 0) is None

    with pytest.raises(ValueError):
        assert runez.logsetup._get_file_handler("test.log", "unknown:something", 0) is None

    assert runez.logsetup._get_file_handler("test.log", None, 0).__class__ is logging.FileHandler
    assert runez.logsetup._get_file_handler("test.log", "", 0).__class__ is logging.FileHandler

    h = runez.logsetup._get_file_handler("test.log", "time:1h", 0)
    assert isinstance(h, TimedRotatingFileHandler)
    assert h.backupCount == 0
    assert h.interval == 3600
    assert h.when == "H"

    h = runez.logsetup._get_file_handler("test.log", "time:midnight", 7)
    assert isinstance(h, TimedRotatingFileHandler)
    assert h.backupCount == 7
    assert h.when == "MIDNIGHT"

    h = runez.logsetup._get_file_handler("test.log", "size:10k", 3)
    assert isinstance(h, RotatingFileHandler)
    assert h.backupCount == 3
    assert h.maxBytes == 10240


def test_clean_handlers(temp_log):
    # Initially, only pytest logger is here
    assert len(logging.root.handlers) == 1

    # Default setup adds a console + file log
    runez.log.setup()
    assert len(logging.root.handlers) == 3

    # Clean up all non-runez handlers: removes pytest's handler
    runez.log.setup(clean_handlers=True)
    assert len(logging.root.handlers) == 2

    # Cancel file log
    runez.log.setup(file_format=None)
    assert len(logging.root.handlers) == 1
