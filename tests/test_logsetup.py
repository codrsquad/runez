import logging
import os
import sys
import time
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from unittest.mock import patch

import pytest

import runez
from runez.ascii import AsciiAnimation, AsciiFrames
from runez.conftest import WrappedHandler
from runez.logsetup import _formatted_text, formatted, LogSpec

LOG = logging.getLogger(__name__)


def test_allow_root(temp_log, monkeypatch):
    with patch("runez.logsetup.os.geteuid", return_value=0):
        # Default: don't complain about running as root inside docker
        monkeypatch.setattr(runez.SYS_INFO, "is_running_in_docker", True)
        runez.log.setup()
        assert "should not be ran as root" not in temp_log.stderr.pop()

        # Complain if explicitly disallowed
        runez.log.setup(allow_root=False)
        assert "should not be ran as root" in temp_log.stderr.pop()

        # Default: complain about running as root outside of docker
        monkeypatch.setattr(runez.SYS_INFO, "is_running_in_docker", False)
        runez.log.setup()
        assert "====\npytest should not be ran as root" in temp_log.stderr.pop()

        # Abort execution with 'allow_root=None'
        with pytest.raises(runez.system.AbortException):
            runez.log.setup(allow_root=None)
        assert "should not be ran as root" in temp_log.stderr.pop()

        # If message doesn't end with '!', then don't do the multi-line '====...' bar decoration
        prev = runez.log.disallow_root_message
        runez.log.disallow_root_message = "no-root-plz"
        runez.log.setup()
        assert "====" not in temp_log.stderr
        assert "no-root-plz" in temp_log.stderr.pop()
        runez.log.disallow_root_message = prev


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
    assert temp_log.logfile == "pytest.log"
    assert not temp_log.tracked


def test_console(temp_log):
    logger = logging.getLogger("runez")
    old_level = logger.level

    try:
        runez.log.setup(console_level=logging.DEBUG, file_location="", greetings="Logging to: {location}, argv: {argv}")

        assert temp_log.logfile is None
        assert "DEBUG Logging to: file log disabled" in temp_log.stderr
        assert ", argv: " in temp_log.stderr
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
    assert runez.log.spec.dev is None
    assert runez.log.spec.project is None
    runez.log.setup(greetings=None)
    assert runez.log.spec.dev
    assert runez.log.spec.project

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
    assert runez.log.context.has_threadlocal()

    # Remove them one by one
    runez.log.context.remove_threadlocal("a")
    assert runez.log.context.has_threadlocal()
    logging.info("hello")
    assert temp_log.pop() == "UTC [[name=foo,version=1.0,worker=susan]] INFO - hello"

    runez.log.context.remove_global("name")
    logging.info("hello")
    assert temp_log.pop() == "UTC [[version=1.0,worker=susan]] INFO - hello"

    runez.log.context.remove_threadlocal("worker")
    assert not runez.log.context.has_threadlocal()

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

    assert "f:system.py mod:system func:hlog INFO Wrote some-file" in temp_log.stderr
    assert "f:test_logsetup.py mod:test_logsetup func:test_convenience INFO hello" in temp_log.stderr
    assert "f:test_logsetup.py mod:test_logsetup func:test_convenience ERROR oops" in temp_log.stderr
    temp_log.stderr.clear()

    runez.write("some-file", "some content", logger=LOG.info)
    LOG.info("hello")
    LOG.exception("oops")
    assert "f:system.py mod:system func:hlog INFO Wrote some-file" in temp_log.stderr
    assert "f:test_logsetup.py mod:test_logsetup func:test_convenience INFO hello" in temp_log.stderr
    assert "f:test_logsetup.py mod:test_logsetup func:test_convenience ERROR oops" in temp_log.stderr


def test_default(temp_log):
    assert runez.log.resolved_dryrun(True) is True
    assert runez.log.resolved_dryrun(False) is False
    assert runez.log.resolved_dryrun(runez.UNSET) is False

    assert not runez.log.hdry("do something")
    assert not temp_log.pop()

    assert runez.log.hdry("do something", dryrun=True)
    assert temp_log.pop() == "Would do something"

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
    temp_log.expect_logged("INFO hello")
    temp_log.expect_logged("WARNING hello")
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


def test_deprecated():
    # Test coverage for deprecated functions
    assert runez.log.tests_path() == runez.DEV.tests_path()  # deprecated


@pytest.mark.skipif(runez.SYS_INFO.platform_id.is_windows, reason="No /dev/null on Windows")
def test_file_location_not_writable(temp_log):
    runez.log.setup(
        greetings="Logging to: {location}",
        console_level=logging.DEBUG,
        file_location="/dev/null/somewhere.log",
    )
    assert "DEBUG Logging to: given location '/dev/null/somewhere.log' is not usable" in temp_log.stderr
    assert runez.log.file_handler is None


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


def test_formatted_text():
    # Unsupported formats
    assert _formatted_text("", {}) == ""
    assert _formatted_text("{filename}", {}) == "{filename}"
    assert _formatted_text("{filename}", {}, strict=True) is None  # In strict mode, all named refs must be defined
    assert _formatted_text("{filename}", {"filename": "foo"}) == "foo"
    assert _formatted_text("{filename}", {"filename": "foo"}, strict=True) == "foo"
    assert _formatted_text("{foo}/{foo}", {"foo": "bar", "unused": "ok"}) == "bar/bar"
    assert _formatted_text("~/.cache/{foo}", {"foo": "bar"}) == os.path.expanduser("~/.cache/bar")

    # Verify that not all '{...}' text is considered a marker
    props = {"argv": '{a} {"foo": "bar {a}"} {a}', "a": "{b}", "b": "b"}
    assert _formatted_text(":: {argv} {a}", props) == ':: {a} {"foo": "bar {a}"} {a} b'

    deep = {"a": "a", "b": "b", "aa": "{a}", "bb": "{b}", "ab": "{aa}{bb}", "ba": "{bb}{aa}", "abba": "{ab}{ba}", "deep": "{abba}"}
    assert _formatted_text("{deep}", deep, max_depth=-1) == "{deep}"
    assert _formatted_text("{deep}", deep, max_depth=0) == "{deep}"
    assert _formatted_text("{deep}", deep, max_depth=1) == "{abba}"
    assert _formatted_text("{deep}", deep, max_depth=2) == "{ab}{ba}"
    assert _formatted_text("{deep}", deep, max_depth=3) == "{aa}{bb}{bb}{aa}"
    assert _formatted_text("{deep}", deep, max_depth=4) == "{a}{b}{b}{a}"
    assert _formatted_text("{deep}", deep, max_depth=5) == "abba"
    assert _formatted_text("{deep}", deep, max_depth=6) == "abba"

    recursive = {"a": "a{b}", "b": "b{c}", "c": "c{a}"}
    assert _formatted_text("{a}", recursive) == "abc{a}"
    assert _formatted_text("{a}", recursive, max_depth=10) == "abcabcabca{b}"

    cycle = {"a": "{b}", "b": "{a}"}
    assert _formatted_text("{a}", cycle, max_depth=0) == "{a}"
    assert _formatted_text("{a}", cycle, max_depth=1) == "{b}"
    assert _formatted_text("{a}", cycle, max_depth=2) == "{a}"
    assert _formatted_text("{a}", cycle, max_depth=3) == "{b}"


def test_level(temp_log):
    runez.log.setup(file_format=None, level=logging.INFO)

    assert not temp_log
    assert temp_log.logfile is None
    logging.debug("debug msg")
    logging.info("info msg")
    assert "debug msg" not in temp_log.stderr
    assert "info msg" in temp_log.stderr


def test_locations(temp_log):
    runez.log.setup(locations=None)
    assert runez.log.file_handler is None

    # Verify that a non-writeable folder is not used
    runez.ensure_folder("foo/bar", logger=None)
    os.chmod("foo/bar", 0o400)
    runez.log.setup(locations=["foo/bar"])
    os.chmod("foo/bar", 0o700)
    assert runez.log.file_handler is None

    assert not temp_log.logfile

    runez.log.setup(locations=["{dev}/test-location.log"])
    assert runez.log.file_handler
    assert temp_log.logfile.endswith("test-location.log")

    runez.log.setup(locations=["{project}/.venv/test-location.log"])
    assert runez.log.file_handler


def test_log_rotate(temp_folder):
    with pytest.raises(ValueError, match="missing kind"):
        runez.log.setup(rotate="foo", tmp=temp_folder)

    with pytest.raises(ValueError, match="missing kind"):
        runez.logsetup._get_file_handler("test.log", "time", 0)

    with pytest.raises(ValueError, match="unknown time spec"):
        runez.logsetup._get_file_handler("test.log", "time:unclear", 0)

    with pytest.raises(ValueError, match="time range not an int"):
        runez.logsetup._get_file_handler("test.log", "time:h", 0)

    with pytest.raises(ValueError, match="unknown time spec"):
        runez.logsetup._get_file_handler("test.log", "time:1h,something", 0)

    with pytest.raises(ValueError, match="size not a bytesize"):
        runez.logsetup._get_file_handler("test.log", "size:not a number,3", 0)

    with pytest.raises(ValueError, match="unknown type"):
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


def test_logspec():
    s1 = LogSpec(runez.log._default_spec, appname="pytest")
    s2 = LogSpec(runez.log._default_spec, appname="pytest")
    assert s1 == s2
    assert s1.appname == "pytest"
    assert s1.timezone == "UTC"
    assert s1.should_log_to_file

    # No basename -> can't determine a usable location anymore
    s1.basename = None
    assert s1.should_log_to_file
    assert s1.usable_location() is None

    s1.set(basename="testing.log", timezone=None, locations=[s1.tmp])
    assert s1.basename == "testing.log"
    assert s1.timezone is None
    assert s1 != s2

    # Empty string custom location just disables file logging
    s1.file_location = ""
    assert not s1.should_log_to_file
    assert s1.usable_location() is None

    # No basename, and custom location points to folder -> not usable
    s1.basename = None
    s1.file_location = "./foo"
    assert s1.should_log_to_file
    assert s1.usable_location() == "./foo"

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

    if not runez.SYS_INFO.platform_id.is_windows:
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
        runez.log.setup(console_stream=sys.stdout, trace="SOME_ENV_VAR")
        logging.info("hello")
        runez.log.trace("some trace info")
        assert not temp_log.stderr
        assert "some trace info" not in temp_log  # Not tracing because env var not set
        assert "INFO hello" in temp_log.stdout.pop()

        # Change logging level
        runez.log.setup(console_level=logging.WARNING, trace=True)
        logging.info("hello")
        assert not temp_log
        logging.warning("hello")
        runez.log.trace("some trace %s", "info")
        assert ":: some trace info" in temp_log  # Tracing forcibly enabled
        assert "WARNING hello" in temp_log.stdout.pop()
        assert not temp_log.stderr

        # Change format and enable debug + tracing
        monkeypatch.setenv("SOME_ENV_VAR", "1")
        runez.log.setup(debug=True, console_format="%(levelname)s - %(message)s", trace="SOME_ENV_VAR+... ")
        assert runez.log.debug
        assert runez.log.console_handler.level == logging.DEBUG
        logging.debug("hello")
        runez.log.trace("some trace info")
        assert "... some trace info" in temp_log  # We're now tracing (because env var is set)
        assert "DEBUG - hello" in temp_log.stdout.pop()
        assert not temp_log.stderr

        if not runez.SYS_INFO.platform_id.is_windows and runez.logsetup.faulthandler:
            # Available only in python3
            runez.log.enable_faulthandler()
            assert runez.log.faulthandler_signum

        assert runez.log.debug is True
        assert runez.DRYRUN is True

    # Verify dryrun and current folder restored, but debug untouched
    assert runez.log.debug
    assert not runez.DRYRUN
    assert os.getcwd() == cwd


def test_progress_bar():
    p = runez.ProgressBar(range(2))
    assert list(p) == [0, 1]
    assert str(p) == "None/2"
    assert p.rendered() is None

    with runez.ProgressBar(total=3, columns=4) as pb:
        assert pb.n == 0
        assert pb.rendered() == "    0%"
        pb.update()
        assert pb.n == 1
        assert pb.rendered() == "▉▏  33%"
        pb.update()
        assert pb.rendered() == "▉▉▌ 67%"
        pb.update()
        assert pb.rendered() == "▉▉▉▉100%"

    assert pb.n is None
    assert pb.rendered() is None


def test_progress_command(cli, monkeypatch):
    cli.run("progress-bar", "-i10", "-d1", "--sleep", "0.01")
    assert cli.succeeded
    assert "done" in cli.logged.stdout
    assert "CPU usage" in cli.logged.stdout

    monkeypatch.setitem(sys.modules, "psutil", None)
    cli.run("progress-bar", "-i10", "-d1", "--sleep", "0.01")
    assert cli.succeeded
    assert "done" in cli.logged.stdout
    assert "CPU usage" not in cli.logged


def test_progress_frames(monkeypatch):
    foo = AsciiFrames(["a", ["b", ""]], fps=10)
    assert foo.frames == ["a", "b"]
    assert foo.index == 0
    assert foo.next_frame() == "b"
    assert foo.index == 1
    assert foo.next_frame() == "a"
    assert foo.index == 0
    assert foo.next_frame() == "b"

    assert AsciiAnimation.get_frames(None)
    assert AsciiAnimation.get_frames(AsciiAnimation.af_dots)
    f = AsciiFrames(list("ab"))
    assert AsciiAnimation.get_frames(f) is f
    assert AsciiAnimation.from_spec(f) is f

    assert AsciiAnimation.predefined("foo") is None
    assert AsciiAnimation.predefined("random")
    off = AsciiAnimation.predefined("off")
    assert off.frames is None
    assert str(off) == "off"
    names = AsciiAnimation.available_names()
    assert names
    for name in names:
        assert AsciiAnimation.predefined(name)

    monkeypatch.setattr(AsciiAnimation, "env_var", None)
    monkeypatch.setattr(AsciiAnimation, "default", None)
    f = AsciiAnimation.get_frames(None)
    assert not f.frames


def next_progress_line(progress_spinner):
    ts = getattr(progress_spinner, "_test_ts", None)
    if ts is None:
        ts = time.time()

    ts += 1
    text = progress_spinner._state.get_line(ts)
    progress_spinner._test_ts = ts
    return text


def test_progress_grooming():
    # Verify that short messages with newlines get their newline changed to a space
    p = runez.logsetup.ProgressSpinner()
    p._state = runez.logsetup._SpinnerState(p, AsciiFrames(None), 80, None, None, None)
    assert next_progress_line(p) is None
    p.show("\n a \n\n\n b \n")
    assert next_progress_line(p) == " a b"


def test_progress_operation(temp_log):
    assert not runez.log.progress.is_running
    runez.log.progress.start()
    assert not runez.log.progress.is_running  # Does not start in test mode by default

    runez.log.progress.stop()  # no-op, already not running
    assert not runez.log.progress.is_running

    runez.log.setup()
    with patch("runez.system.TerminalInfo.isatty", return_value=True):
        # Simulate progress with alternating foo/bar "spinner", using `str` to cover color code path
        p1 = runez.ProgressBar(total=3)
        p1.start()
        p1.update()
        assert runez.log.progress._progress_bar
        runez.log.progress.start(max_columns=10, message_color=str, spinner_color=str)
        assert runez.log.progress.is_running
        assert runez.log.progress._progress_bar
        logging.error("some error")
        time.sleep(0.1)
        runez.log.progress.show("some progress")
        assert runez.log.progress._progress_bar
        print("hello")
        time.sleep(0.1)
        p2 = runez.ProgressBar(total=3)
        p3 = runez.ProgressBar(total=3)
        p4 = runez.ProgressBar(total=3)
        p1.start()
        p2.start()
        p3.start()
        p4.start()

        assert runez.log.progress._progress_bar is p4
        time.sleep(0.1)

        # Stop progress bar in a different order
        p2.stop()
        assert runez.log.progress._progress_bar is p4
        p4.stop()
        assert runez.log.progress._progress_bar is p3
        p3.stop()
        assert runez.log.progress._progress_bar is p1
        p1.stop()
        assert runez.log.progress._progress_bar is None

        runez.log.progress.stop()
        assert not runez.log.progress.is_running

        assert "hello" in temp_log.stdout
        assert "some error" in temp_log.stderr

        # Simulate progress without spinner
        temp_log.clear()
        runez.log.progress.start(frames=None)
        runez.log.progress.show("some progress")
        time.sleep(0.1)
        assert runez.log.progress.is_running
        runez.log.progress.stop()
        time.sleep(0.1)
        assert not runez.log.progress.is_running
        assert "hello" not in temp_log.stdout
        assert "some progress" in temp_log.stderr


class SampleClass:
    @runez.log.timeit  # Without args
    def instance_func1(self, message, fail=False):
        if fail:
            raise ValueError("oops")

        print("%s: %s" % (self, message))

    @runez.log.timeit()  # With args
    def instance_func2(self, message):
        print("%s: %s" % (self, message))

    @classmethod
    @runez.log.timeit
    def class_func1(cls, message):
        print("%s: %s" % (cls, message))

    @classmethod
    @runez.log.timeit()
    def class_func2(cls, message):
        print("%s: %s" % (cls, message))

    @staticmethod
    @runez.log.timeit()
    def static_func1(message):
        print(message)

    @staticmethod
    @runez.log.timeit()
    def static_func2(message):
        print(message)


@runez.log.timeit
def sample_function1(message):
    print(message)


@runez.log.timeit("sample2", color=True, logger=print)
def sample_function2(message):
    print(message)


def test_timeit(logged):
    sample = SampleClass()
    sample.instance_func1("hello")
    assert "SampleClass.instance_func1() took " in logged.pop()

    with pytest.raises(ValueError, match="oops"):
        sample.instance_func1("hello", fail=True)
    assert "SampleClass.instance_func1() failed: oops" in logged.pop()

    sample.instance_func2("hello")
    assert "SampleClass.instance_func2() took " in logged.pop()

    sample.class_func1("hello")
    assert "SampleClass.class_func1() took " in logged.pop()

    sample.class_func2("hello")
    assert "SampleClass.class_func2() took " in logged.pop()

    sample.static_func1("hello")
    assert "SampleClass.static_func1() took " in logged.pop()

    sample.static_func2("hello")
    assert "SampleClass.static_func2() took " in logged.pop()

    sample_function1("sample1")
    assert "sample_function1() took " in logged.pop()

    sample_function2("sample2")
    assert "sample2 took " in logged.pop()

    with runez.log.timeit():
        print("hello")
    assert "tests.test_logsetup.test_timeit() took " in logged.pop()

    with runez.log.timeit("ad-hoc context"):
        print("hello")
    assert "ad-hoc context took " in logged.pop()
