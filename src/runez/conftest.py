"""
Import this only from your test cases

Example:

    from runez.conftest import cli, isolated_log_setup, temp_folder
"""

from __future__ import absolute_import

import logging
import os
import re
import sys
import tempfile

import _pytest.logging
import pytest

from runez.base import Slotted, string_type, stringified, UNSET
from runez.context import CaptureOutput, TempArgv, TrackedOutput
from runez.convert import flattened, formatted, represented_args, SHELL, shortened
from runez.file import TempFolder
from runez.logsetup import LogManager
from runez.program import which
from runez.represent import header
from runez.system import current_test, find_parent_folder, is_dryrun

try:
    from click import BaseCommand as _ClickCommand
    from click.testing import CliRunner as _CliRunner

except ImportError:  # pragma: no cover, click used only if installed
    _ClickCommand = None
    _CliRunner = None


LOG = logging.getLogger(__name__)
TMP = tempfile.gettempdir()

# Set DEBUG logging level when running tests, makes sure LOG.debug() calls get captured (for inspection in tests)
logging.root.setLevel(logging.DEBUG)

if sys.argv and "pycharm" in sys.argv[0].lower():  # pragma: no cover, ignore PyCharm's special wrapper "_jb_pytest_runner"...
    pt = which("pytest")
    if pt:
        sys.argv[0] = pt

# Set logsetup defaults to stable/meaningful for pytest runs
LogManager.override_spec(timezone="UTC", tmp=TMP, locations=[os.path.join("{tmp}", "{basename}")])


def project_folder():
    """
    Returns:
        (str | None): Path to project folder, if we're currently running a test from a tests/ subfolder
    """
    tests = tests_folder()
    if tests:
        return os.path.dirname(tests)


def tests_folder():
    """
    Returns:
        (str | None): Path to project's tests/ folder, if we're currently running a test from there
    """
    return find_parent_folder(current_test(), {"tests"})


def test_resource(*relative_path):
    """
    Args:
        *relative_path: Path relative to project's tests/ folder

    Returns:
        (str | None): Full path, if we're currently running a test from a tests/ subfolder
    """
    tests = tests_folder()
    if tests:
        return os.path.join(tests, *relative_path)


class IsolatedLogSetup(object):
    """Allows to isolate changes to logging setup.

    This should only be useful for testing (as in general, logging setup is a global thing).
    """

    def __init__(self, adjust_tmp=True):
        self.adjust_tmp = adjust_tmp
        self.temp_folder = None

    def __enter__(self, tmp=False):
        """Context manager to save and restore log setup, useful for testing"""
        WrappedHandler.isolation += 1
        self.old_handlers = logging.root.handlers
        logging.root.handlers = []

        if self.adjust_tmp:
            # Adjust log.spec.tmp, and leave logging.root without any predefined handlers
            # intent: underlying wants to perform their own log.setup()
            self.old_spec = LogManager.spec.tmp
            self.temp_folder = TempFolder()
            LogManager.spec.tmp = self.temp_folder.__enter__()
            return LogManager.spec.tmp

        # If we're not adjusting tmp, then make sure we have at least one logging handler defined
        handler = logging.StreamHandler(stream=sys.stderr)
        handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
        handler.setLevel(logging.DEBUG)
        logging.root.addHandler(handler)

    def __exit__(self, *_):
        WrappedHandler.isolation -= 1
        LogManager.reset()
        logging.root.handlers = self.old_handlers
        if self.temp_folder:
            LogManager.spec.tmp = self.old_spec
            self.temp_folder.__exit__(*_)


@pytest.fixture
def cli():
    """Convenience fixture for click CLI testing.

    Example usage:

        from runez.conftest import cli
        from my_cli import main

        cli.default_main = main  # Handy if you have only one main

        def test_help(cli):
            cli.main = main  # Not needed if `cli.default_main` was set
            cli.run("--help")
            assert cli.succeeded
            assert cli.match("Usage:")

            # or more specifically
            assert "Usage:" in cli.logged.stdout
    """
    with cli.context() as context:
        yield ClickRunner(context=context)


# This just allows to get auto-complete to work in PyCharm
cli = cli  # type: ClickRunner

# Comes in handy for click apps with only one main entry point
cli.default_main = None

# Can be customized by users, wraps cli (fixture) runs in given context
cli.context = TempFolder


@pytest.fixture
def isolated_log_setup():
    """Log settings restored"""
    with IsolatedLogSetup():
        yield


@pytest.fixture
def logged():
    with CaptureOutput() as logged:
        yield logged


@pytest.fixture
def temp_folder():
    with TempFolder() as tmp:
        yield tmp


# This just allows to get auto-complete to work in PyCharm
logged = logged  # type: TrackedOutput
temp_folder = temp_folder  # type: str


class WrappedHandler(_pytest.logging.LogCaptureHandler):
    """pytest aggressively imposes its own capture, this allows to impose our capture where applicable"""

    isolation = 0

    def emit(self, record):
        if WrappedHandler.isolation == 0:
            stream = CaptureOutput.current_capture_buffer()
            if stream is not None:
                try:
                    msg = self.format(record)
                    stream.write(msg + "\n")
                    self.flush()

                except Exception:  # pragma: no cover
                    self.handleError(record)

            else:
                super(WrappedHandler, self).emit(record)

    @classmethod
    def find_wrapper(cls):
        """
        Returns:
            (WrappedHandler | None): WrappedHandler is logging.root, if present
        """
        if logging.root.handlers:
            for handler in logging.root.handlers:
                if handler and handler.__class__ is WrappedHandler:
                    return handler


_pytest.logging.LogCaptureHandler = WrappedHandler


class ClickWrapper(object):
    """Wrap click invoke, when click is available, otherwise just call provided function"""

    __runner = None

    def __init__(self, output=None, exit_code=None, exception=None):
        self.output = output
        self.exit_code = exit_code
        self.exception = exception

    def invoke(self, main, args):
        """Mocked click-like behavior"""
        output = None
        exit_code = 0
        exception = None
        try:
            with TempArgv(args, exe=sys.executable):
                output = main()

        except SystemExit as e:
            exit_code = 1
            if isinstance(e.code, int):
                exit_code = e.code

            else:
                output = stringified(e)

        except BaseException as e:
            exit_code = 1
            exception = e
            output = stringified(e)

        return ClickWrapper(output=output, exit_code=exit_code, exception=exception)

    @classmethod
    def new_runner(cls, main):
        """
        Returns:
            (ClickWrapper| click.testing.CliRunner): CliRunner if available
        """
        if _ClickCommand is not None and isinstance(main, _ClickCommand):
            return _CliRunner()

        return cls()


class ClickRunner(object):
    """Allows to provide a test-friendly fixture around testing click entry-points"""

    default_main = None  # This just allows to get auto-complete to work in PyCharm

    def __init__(self, context=None):
        """
        Args:
            context (callable | None): Context (example: temp folder) this click run was invoked under
        """
        self.context = context
        self.main = cli.default_main
        self.args = None  # type: list # Arguments used in last run() invocation
        self.logged = None  # type: TrackedOutput
        self.exit_code = None  # type: int
        self._project_folder = None
        self._tests_folder = None

    @property
    def project_folder(self):
        """
        Returns:
            (str | None): Path to project folder, if we're currently running a test from a tests/ subfolder
        """
        if self._project_folder is None:
            self._project_folder = project_folder()

        return self._project_folder

    @property
    def tests_folder(self):
        """
        Returns:
            (str | None): Path to project's tests/ folder, if we're currently running a test from there
        """
        if self._tests_folder is None:
            self._tests_folder = tests_folder()

        return self._tests_folder

    def test_resource(self, *relative_path):
        """
        Args:
            *relative_path: Path relative to project's tests/ folder

        Returns:
            (str | None): Full path, if we're currently running a test from a tests/ subfolder
        """
        return test_resource(*relative_path)

    def run(self, *args, **kwargs):
        """
        Args:
            *args: Command line args
            **kwargs: If provided, format each arg with given `kwargs`
        """
        main = kwargs.pop("main", None)
        if main is not None:
            self.main = main

        if self.main is None:
            self.main = self.default_main

        assert bool(self.main), "No main provided"
        if kwargs:
            args = [formatted(a, **kwargs) for a in args]

        if len(args) == 1 and hasattr(args[0], "split"):
            # Convenience: allow to provide full command as one string argument
            args = args[0].split()

        self.args = flattened(args, split=SHELL)
        with IsolatedLogSetup(adjust_tmp=False):
            with CaptureOutput(dryrun=is_dryrun()) as logged:
                self.logged = logged
                runner = ClickWrapper.new_runner(self.main)
                result = runner.invoke(self.main, args=self.args)
                if result.output:
                    logged.stdout.buffer.write(result.output)

                if result.exception and not isinstance(result.exception, SystemExit):
                    try:
                        raise result.exception

                    except BaseException:
                        LOG.exception("Exited with stacktrace:")

                self.exit_code = result.exit_code

        if self.logged:
            handler = WrappedHandler.find_wrapper()
            if handler:
                handler.reset()

            title = header("Captured output for: %s" % represented_args(self.args), border="==")
            LOG.info("\n%s\nmain: %s\nexit_code: %s\n%s\n", title, self.main, self.exit_code, self.logged)

    @property
    def succeeded(self):
        return self.exit_code == 0

    @property
    def failed(self):
        return self.exit_code != 0

    def match(self, expected, stdout=None, stderr=None, regex=None):
        """
        Args:
            expected (str | unicode | re.Pattern): Message to find in self.logged
            stdout (bool | None): Look at stdout (default: yes, if captured)
            stderr (bool | None): Look at stderr (default: yes, if captured)
            regex (int | bool | None): Specify whether 'expected' should be a regex

        Returns:
            (Match | None): Match found, if any
        """
        if stdout is None and stderr is None:
            # By default, look at stdout/stderr only
            stdout = stderr = True

        assert expected, "No 'expected' provided"
        assert self.exit_code is not None, "run() was not called yet"

        captures = [stdout and self.logged.stdout, stderr and self.logged.stderr]
        captures = [c for c in captures if c is not None and c is not False]

        assert captures, "No captures specified"
        if not any(c for c in captures):
            # There was no output at all
            return None

        if not isinstance(regex, bool) and isinstance(regex, int):
            flags = regex
            regex = True

        else:
            flags = 0

        if isinstance(expected, string_type) and "..." in expected and not isinstance(regex, bool):
            regex = True
            expected = expected.replace("...", ".+")

        if not isinstance(expected, string_type):
            # Assume regex, no easy way to verify isinstance(expected, re.Pattern) for python < 3.7
            regex = expected

        elif regex:
            regex = re.compile("(.{0,32})(%s)(.{0,32})" % expected, flags=flags)

        for c in captures:
            contents = c.contents()
            if regex:
                m = regex.search(contents)
                if m:
                    if m.groups():
                        return Match(c, m.group(2), pre=m.group(1), post=m.group(3))

                    return Match(c, m.group(0))

            elif expected in contents:
                i = contents.index(expected)
                pre = shortened(contents[:i], 32)
                post = shortened(contents[i + len(expected):], 32)
                return Match(c, expected, pre=pre, post=post)

    def expect_messages(self, *expected, **kwargs):
        for message in expected:
            if message[0] == "!":
                m = self.match(message[1:], **kwargs)
                if m:
                    assert False, "Unexpected match in output: %s" % m

            else:
                m = self.match(message, **kwargs)
                if not m:
                    assert False, "Not seen in output: %s" % message

    def expect_success(self, args, *expected, **kwargs):
        spec = RunSpec()
        spec.pop(kwargs)
        self.run(args, **kwargs)
        assert self.succeeded, "%s failed, was expecting success" % represented_args(self.args)
        self.expect_messages(*expected, **spec.to_dict())

    def expect_failure(self, args, *expected, **kwargs):
        spec = RunSpec()
        spec.pop(kwargs)
        self.run(args, **kwargs)
        assert self.failed, "%s succeeded, was expecting failure" % represented_args(self.args)
        self.expect_messages(*expected, **spec.to_dict())


class RunSpec(Slotted):

    __slots__ = ["stdout", "stderr", "regex"]

    def _get_defaults(self):
        return UNSET


class Match(object):
    def __init__(self, capture, match, pre=None, post=None):
        self.capture = capture
        self.match = match
        self.pre = pre
        self.post = post

    def __repr__(self):
        return self.match
