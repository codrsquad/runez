import logging
import os
import sys
import time
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler

import pytest
from mock import patch

import runez
from runez.conftest import TMP, WrappedHandler
from runez.logsetup import _find_parent_folder, AsciiAnimation, AsciiFrames, expanded, formatted, LogSpec


LOG = logging.getLogger(__name__)


def test_auto_location_not_writable(temp_log):
    with patch("runez.file.os.access", return_value=False):
        runez.log.setup(
            greetings="Logging to: {location}",
            console_format="%(name)s f:%(filename)s mod:%(module)s func:%(funcName)s %(levelname)s - %(message)s",
            console_level=logging.DEBUG,
        )
        logging.info("hello")
        assert "runez f:logsetup.py mod:logsetup func:greet DEBUG" in temp_log.stderr
        assert "INFO - hello" in temp_log.stderr
        assert "Logging to: no usable locations" in temp_log.stderr
        assert runez.log.file_handler is None


def test_clean_handlers(temp_log):
    # Initially, only pytest logger is here
    assert WrappedHandler.count_non_wrapped_handlers() == 0
    existing = len(logging.root.handlers)

    # Default setup adds a console + file log
    runez.log.setup()
    assert WrappedHandler.count_non_wrapped_handlers() == 2
    assert len(logging.root.handlers) == existing + 2

    # Clean up all non-runez handlers: removes pytest's handler
    runez.log.setup(clean_handlers=True)
    assert WrappedHandler.count_non_wrapped_handlers() == 2
    assert len(logging.root.handlers) == 2

    # Cancel file log
    runez.log.setup(file_format=None)
    assert WrappedHandler.count_non_wrapped_handlers() == 1
    assert len(logging.root.handlers) == 1


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
    assert temp_log.pop() == "UTC [[a=b,name=foo,version=1.0,worker=susan]] INFO - hello"

    # Remove them one by one
    runez.log.context.remove_threadlocal("a")
    logging.info("hello")
    assert temp_log.pop() == "UTC [[name=foo,version=1.0,worker=susan]] INFO - hello"

    runez.log.context.remove_global("name")
    logging.info("hello")
    assert temp_log.pop() == "UTC [[version=1.0,worker=susan]] INFO - hello"

    runez.log.context.clear_threadlocal()
    logging.info("hello")
    assert temp_log.pop() == "UTC [[version=1.0]] INFO - hello"

    runez.log.context.clear_global()
    logging.info("hello")
    assert temp_log.pop() == "UTC INFO - hello"

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

    assert "f:system.py mod:system func:hlog INFO Wrote 12 bytes" in temp_log.stderr
    assert "f:test_logsetup.py mod:test_logsetup func:test_convenience INFO hello" in temp_log.stderr
    assert "f:test_logsetup.py mod:test_logsetup func:test_convenience ERROR oops" in temp_log.stderr
    temp_log.stderr.clear()

    runez.write("some-file", "some content", logger=LOG.info)
    LOG.info("hello")
    LOG.exception("oops")
    assert "f:system.py mod:system func:hlog INFO Wrote 12 bytes" in temp_log.stderr
    assert "f:test_logsetup.py mod:test_logsetup func:test_convenience INFO hello" in temp_log.stderr
    assert "f:test_logsetup.py mod:test_logsetup func:test_convenience ERROR oops" in temp_log.stderr


def test_default(temp_log):
    assert runez.log.spec.console_level == logging.WARNING
    runez.log.context.set_global(version="1.0")
    runez.log.context.add_global(worker="mark")
    runez.log.context.add_threadlocal(worker="joe", foo="bar")
    runez.log.context.set_threadlocal(worker="joe")
    runez.log.setup(greetings="Logging to: {location}, pid {pid}")

    assert os.path.basename(temp_log.logfile) == "pytest.log"
    temp_log.expect_logged("Logging to: ")
    temp_log.expect_logged("pytest.log, pid %s" % os.getpid())

    logging.info("hello")
    logging.warning("hello")
    temp_log.expect_logged("UTC [MainThread] [[version=1.0,worker=joe]] INFO - hello")
    temp_log.expect_logged("UTC [MainThread] [[version=1.0,worker=joe]] WARNING - hello")
    assert "INFO hello" not in temp_log.stderr
    assert "WARNING hello" in temp_log.stderr.pop()

    # Now stop logging context
    runez.log.setup(
        console_format="%(funcName)s %(module)s %(levelname)s %(message)s",
        file_format="%(asctime)s %(timezone)s %(levelname)s %(message)s",
    )
    logging.info("hello")
    logging.warning("hello")
    temp_log.expect_logged("UTC INFO hello")
    temp_log.expect_logged("UTC WARNING hello")
    assert temp_log.pop() == "test_default test_logsetup WARNING hello"


def test_expanded():
    class Record(object):
        basename = "my-name"
        filename = "{basename}.txt"

    # Unsupported formats
    with pytest.raises(IndexError):
        expanded("{}", "foo", a="b")

    with pytest.raises(IndexError):
        expanded("{0}", "foo", a="b")

    assert expanded("{filename}", Record, "foo") == "my-name.txt"
    assert expanded("{filename}", [Record]) == "my-name.txt"  # Value found even in nested list
    assert expanded("{filename}", filename="foo.yml") == "foo.yml"
    assert expanded("{filename}", "unused positional", filename="bar.yml", unused="x") == "bar.yml"
    assert expanded("{basename}/~/{filename}", Record) == "my-name/~/my-name.txt"
    assert expanded("~/{basename}/{filename}", Record) == os.path.expanduser("~/my-name/my-name.txt")

    assert expanded("") == ""
    assert expanded("", Record) == ""
    assert expanded("{not_there} {0}", "foo", strict=True) is None  # In strict mode, all named refs must be defined
    assert expanded("{not_there}", Record, name="susan", strict=True) is None
    assert expanded("{not_there}", Record, not_there="psyched!") == "psyched!"
    assert expanded("{not_there}", Record) == "{not_there}"

    deep = dict(a="a", b="b", aa="{a}", bb="{b}", ab="{aa}{bb}", ba="{bb}{aa}", abba="{ab}{ba}", deep="{abba}")
    assert expanded("{deep}", deep, max_depth=-1) == "{deep}"
    assert expanded("{deep}", deep, max_depth=0) == "{deep}"
    assert expanded("{deep}", deep, max_depth=1) == "{abba}"
    assert expanded("{deep}", deep, max_depth=2) == "{ab}{ba}"
    assert expanded("{deep}", deep, max_depth=3) == "{aa}{bb}{bb}{aa}"
    assert expanded("{deep}", deep, max_depth=4) == "{a}{b}{b}{a}"
    assert expanded("{deep}", deep, max_depth=5) == "abba"
    assert expanded("{deep}", deep, max_depth=6) == "abba"

    recursive = dict(a="a{b}", b="b{c}", c="c{a}")
    assert expanded("{a}", recursive) == "abc{a}"
    assert expanded("{a}", recursive, max_depth=10) == "abcabcabca{b}"

    cycle = dict(a="{b}", b="{a}")
    assert expanded("{a}", cycle, max_depth=0) == "{a}"
    assert expanded("{a}", cycle, max_depth=1) == "{b}"
    assert expanded("{a}", cycle, max_depth=2) == "{a}"
    assert expanded("{a}", cycle, max_depth=3) == "{b}"

    assert expanded("{filename}") == "{filename}"


@pytest.mark.skipif(runez.WINDOWS, reason="No /dev/null on Windows")
def test_file_location_not_writable(temp_log):
    runez.log.setup(
        greetings="Logging to: {location}",
        console_level=logging.DEBUG,
        file_location="/dev/null/somewhere.log",
    )
    assert "DEBUG Logging to: given location '/dev/null/somewhere.log' is not usable" in temp_log.stderr
    assert runez.log.file_handler is None


def test_find_parent_folder():
    assert "test_logsetup.py" in runez.log.current_test()
    assert _find_parent_folder("", {"foo"}) is None
    assert _find_parent_folder("/a/b//", {""}) is None
    assert _find_parent_folder("/a/b", {"a"}) == "/a"
    assert _find_parent_folder("/a/b//", {"a"}) == "/a"
    assert _find_parent_folder("//a/b//", {"a"}) == "//a"
    assert _find_parent_folder("/a/b", {"b"}) == "/a/b"
    assert _find_parent_folder("/a/B", {"a", "b"}) == "/a/B"  # case insensitive
    assert _find_parent_folder("/a/b", {"c"}) is None
    assert _find_parent_folder("/dev/null", {"foo"}) is None

    assert runez.log.dev_folder()
    assert runez.log.dev_folder("foo")


def test_formatted():
    assert formatted("foo") == "foo"
    assert formatted("foo", "bar") == "foo"  # Ignoring extra positionals

    assert formatted("foo %s", "bar") == "foo bar"
    assert formatted("foo {0}", "bar") == "foo bar"
    assert formatted("foo %s {0}", "bar") == "foo bar {0}"  # '%s' format used first

    assert formatted("foo %s {a}", "bar", a="val_a") == "foo %s val_a"  # '%s' does not apply when there are kwargs

    # Bogus formats
    assert formatted("foo %s %s {0}", "bar") == "foo %s %s bar"  # bogus '%s' format
    assert formatted("foo %s %s {0} {1}", "bar") == "foo %s %s {0} {1}"  # bogus '%s' and {positional} format
    assert formatted("{a} {b}", a="val_a") == "{a} {b}"  # Incomplete


def test_level(temp_log):
    runez.log.setup(file_format=None, level=logging.INFO)

    assert not temp_log
    assert temp_log.logfile is None
    logging.debug("debug msg")
    logging.info("info msg")
    assert "debug msg" not in temp_log.stderr
    assert "info msg" in temp_log.stderr


def test_log_rotate(temp_folder):
    with pytest.raises(ValueError):
        runez.log.setup(rotate="foo")

    with pytest.raises(ValueError):
        runez.logsetup._get_file_handler("test.log", "time", 0)

    with pytest.raises(ValueError):
        runez.logsetup._get_file_handler("test.log", "time:unclear", 0)

    with pytest.raises(ValueError):
        runez.logsetup._get_file_handler("test.log", "time:h", 0)

    with pytest.raises(ValueError):
        runez.logsetup._get_file_handler("test.log", "time:1h,something", 0)

    with pytest.raises(ValueError):
        runez.logsetup._get_file_handler("test.log", "size:not a number,3", 0)

    with pytest.raises(ValueError):
        runez.logsetup._get_file_handler("test.log", "unknown:something", 0)

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


def test_logspec(isolated_log_setup):
    s1 = LogSpec(runez.log._default_spec, appname="pytest")
    s2 = LogSpec(runez.log._default_spec, appname="pytest")
    assert s1 == s2
    assert s1.appname == "pytest"
    assert s1.timezone == "UTC"
    assert s1.should_log_to_file
    assert s1.usable_location() == os.path.join(TMP, "pytest.log")

    # No basename -> can't determine a usable location anymore
    s1.basename = None
    assert s1.should_log_to_file
    assert s1.usable_location() is None

    s1.set(basename="testing.log", timezone=None, locations=[s1.tmp])
    assert s1.basename == "testing.log"
    assert s1.timezone is None
    assert s1.usable_location() == os.path.join(TMP, "testing.log")
    assert s1 != s2

    # Empty string custom location just disables file logging
    s1.file_location = ""
    assert not s1.should_log_to_file
    assert s1.usable_location() is None

    # No basename, and custom location points to folder -> not usable
    s1.basename = None
    s1.file_location = TMP
    assert s1.should_log_to_file
    assert s1.usable_location() is None

    # Location referring to env var
    s1.set(file_location=None, locations=[os.path.join(".", "{FOO}", "bar")])
    with patch.dict(os.environ, {"FOO": "foo"}, clear=True):
        assert s1.usable_location() == os.path.join(".", "foo", "bar")

    with patch.dict(os.environ, {}, clear=True):
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


def test_no_context(temp_log):
    runez.log.context.set_global(version="1.0")
    runez.log.spec.set(timezone="", file_format="%(asctime)s [%(threadName)s] %(timezone)s %(levelname)s - %(message)s")
    runez.log.setup()
    logging.info("hello")
    temp_log.expect_logged("[MainThread] INFO - hello")


def test_setup(temp_log, monkeypatch):
    fmt = "%(asctime)s %(context)s%(levelname)s - %(message)s"
    assert runez.log.is_using_format("", fmt) is False
    assert runez.log.is_using_format("%(lineno)", fmt) is False
    assert runez.log.is_using_format("%(context)", fmt) is True
    assert runez.log.is_using_format("%(context) %(lineno)", fmt) is True
    assert runez.log.is_using_format("%(context)", "") is False

    if not runez.WINDOWS:
        # signum=None is equivalent to disabling faulthandler
        runez.log.enable_faulthandler(signum=None)
        assert runez.log.faulthandler_signum is None
        # We didn't call setup, so enabling faulthandler will do nothing
        runez.log.enable_faulthandler()
        assert runez.log.faulthandler_signum is None

    cwd = os.getcwd()
    assert not runez.DRYRUN
    assert not runez.log.debug
    with runez.TempFolder(dryrun=False):
        assert not runez.log.debug

        # No auto-debug on dryrun
        runez.log.setup(dryrun=True, level=logging.INFO)
        runez.log.enable_trace(None)
        assert not runez.log.debug
        assert runez.DRYRUN
        logging.info("info")
        logging.debug("hello")
        runez.log.trace("some trace info")
        assert not temp_log.stdout
        assert "hello" not in temp_log
        assert "some trace info" not in temp_log  # Tracing not enabled
        assert "info" in temp_log.stderr.pop()

        # Second call without any customization is a no-op
        runez.log.setup()
        runez.log.enable_trace(False)
        assert not runez.log.debug
        assert runez.DRYRUN
        logging.debug("hello")
        runez.log.trace("some trace info")
        assert "some trace info" not in temp_log  # Tracing not enabled
        assert not temp_log

        # Change stream
        runez.log.setup(console_stream=sys.stdout)
        runez.log.enable_trace("SOME_ENV_VAR")
        logging.info("hello")
        runez.log.trace("some trace info")
        assert not temp_log.stderr
        assert "some trace info" not in temp_log  # Not tracing because env var not set
        assert "INFO hello" in temp_log.stdout.pop()

        # Change logging level
        runez.log.setup(console_level=logging.WARNING)
        runez.log.enable_trace(True)
        logging.info("hello")
        assert not temp_log
        logging.warning("hello")
        runez.log.trace("some trace %s", "info")
        assert ":: some trace info" in temp_log  # Tracing forcibly enabled
        assert "WARNING hello" in temp_log.stdout.pop()
        assert not temp_log.stderr

        # Change format and enable debug + tracing
        monkeypatch.setenv("SOME_ENV_VAR", "1")
        runez.log.setup(debug=True, console_format="%(levelname)s - %(message)s")
        runez.log.enable_trace("SOME_ENV_VAR")
        runez.log.tracer.prefix = "..."
        assert runez.log.debug
        assert runez.log.console_handler.level == logging.DEBUG
        logging.debug("hello")
        runez.log.trace("some trace info")
        assert "...some trace info" in temp_log  # We're now tracing (because env var is set)
        assert "DEBUG - hello" in temp_log.stdout.pop()
        assert not temp_log.stderr

        if not runez.WINDOWS and runez.logsetup.faulthandler:
            # Available only in python3
            runez.log.enable_faulthandler()
            assert runez.log.faulthandler_signum

        assert runez.log.debug is True
        assert runez.DRYRUN is True

    # Verify dryrun and current folder restored, but debug untouched
    assert runez.log.debug
    assert not runez.DRYRUN
    assert os.getcwd() == cwd


def test_progress_command(cli):
    cli.run("progress-bar", "-i2", "-d1")
    assert cli.succeeded
    assert "done" in cli.logged.stdout

    assert AsciiAnimation.predefined("foo") is None
    off = AsciiAnimation.predefined("off")
    assert off.frames is None
    assert str(off) == "off"
    names = AsciiAnimation.available_names()
    assert names
    for name in names:
        assert AsciiAnimation.predefined(name)


def test_progress_frames():
    foo = AsciiFrames(["a", ["b", ""]], fps=10)
    assert foo.animate_every == 1
    assert foo.frames == ["a", "b"]
    assert foo.index == 0
    assert foo.next_frame() == "b"
    assert foo.index == 1
    assert foo.next_frame() == "a"
    assert foo.index == 0
    assert foo.next_frame() == "b"

    foo.set_parent_fps(100)
    assert foo.animate_every == 10

    foo.set_parent_fps(20)
    assert foo.animate_every == 2
    assert foo.next_frame() == "a"
    assert foo.next_frame() == "a"
    assert foo.next_frame() == "b"
    assert foo.next_frame() == "b"
    assert foo.next_frame() == "a"


def test_progress_operation(isolated_log_setup, logged):
    assert not runez.log.progress.is_running
    runez.log.progress.start()
    assert not runez.log.progress.is_running  # Does not start in test mode by default

    runez.log.progress.stop()  # no-op, already not running
    assert not runez.log.progress.is_running

    runez.log.setup()
    logged.clear()
    with patch("runez.system.TerminalInfo.isatty", return_value=True):
        # Simulate progress with alternating foo/bar "spinner"
        runez.log.progress.start(frames=AsciiFrames(["foo", "bar"], fps=100))
        runez.log.progress.show("some progress")
        assert runez.log.progress.is_running
        time.sleep(0.1)
        print("hello")
        logging.error("some error")
        logging.debug("some debug %s", "message")
        time.sleep(0.1)

        runez.log.progress.stop()
        time.sleep(0.1)
        assert not runez.log.progress.is_running

        assert "[?25l" in logged.stderr
        assert "hello" in logged.stdout
        assert "ERROR some error" in logged.stderr
        assert "[Kfoo" in logged.stderr
        assert "[Kbar" in logged.stderr
        assert "some progress" in logged.stderr
        assert "[?25h" in logged.stderr

        # Simulate progress without spinner
        logged.clear()
        runez.log.progress.start(frames=None, fps=100)
        runez.log.progress.show("some progress")
        time.sleep(0.1)
        assert runez.log.progress.is_running
        runez.log.progress.stop()
        time.sleep(0.1)
        assert "some progress" in logged.stderr
        assert not runez.log.progress.is_running
