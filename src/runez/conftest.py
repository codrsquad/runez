"""
Import this only from your test cases

Example:

    from runez.conftest import cli, isolated_log_setup, temp_folder
"""

import logging
import os
import re

import _pytest.logging
import pytest

import runez
from runez.base import string_type


runez.log.override_root_level(logging.DEBUG)
runez.log.override_spec(appname="pytest", timezone="UTC", locations=["{tmp}/{basename}"], tmp=os.path.join("/", "tmp"))


class IsolatedLogs:
    """
    Allows to isolate changes to logging setup.
    This should only be useful for testing (as in general, logging setup is a global thing)
    """

    def __enter__(self):
        """Context manager to save and restore log setup, useful for testing"""
        return runez.log

    def __exit__(self, *_):
        runez.log._reset()


@pytest.fixture
def cli():
    """
    Convenience for click CLI testing.

    Example usage:

        from runez.conftest import cli
        from my_cli import main

        cli.default_main = main  # Handy if you have only one main

        def test_help(cli):
            cli.main = main  # Not needed if `cli.default_main` was set
            cli.run("--help", main=main)  # 'main' not needed if already set
            assert cli.succeeded
            assert cli.match("Usage:")
            # or more specifically
            assert "Usage:" in cli.logged.stdout

    """
    yield ClickRunner()


# Comes in handy for click apps with only one main entry point
cli.default_main = None


@pytest.fixture
def isolated_log_setup():
    """Log settings restored"""
    with runez.TempFolder(follow=True) as tmp:
        with IsolatedLogs() as isolated:
            isolated.spec.tmp = tmp
            yield isolated


@pytest.fixture
def logged():
    with runez.CaptureOutput() as logged:
        yield logged


@pytest.fixture
def temp_folder():
    with runez.TempFolder() as tmp:
        yield tmp


class WrappedHandler(_pytest.logging.LogCaptureHandler):
    """pytest aggressively imposes its own capture, this allows to capture it in our context managers"""

    _is_capturing = False
    _buffer = runez.context.StringIO()

    def __init__(self):
        super(WrappedHandler, self).__init__()

    def emit(self, record):
        if self._is_capturing:
            msg = self.format(record)
            WrappedHandler._buffer.write(msg)
        else:
            super(WrappedHandler, self).emit(record)


runez.context.CapturedStream._shared = WrappedHandler
_pytest.logging.LogCaptureHandler = WrappedHandler


class ClickWrapper:
    """Wrap click invoke, when click is available, otherwise just call provided function"""

    __runner = None

    def __init__(self, output=None, exit_code=None, exception=None):
        self.output = output
        self.exit_code = exit_code
        self.exception = exception

    def invoke(self, main, args, **kwargs):
        """Mocked click-like behavior"""
        try:
            output = main(*args, **kwargs)
            return ClickWrapper(output=output, exit_code=0)

        except Exception as e:
            return ClickWrapper(str(e), exit_code=1, exception=e)

    @runez.prop
    def runner(cls):
        """
        :return type: CliRunner if available
        """
        try:
            from click.testing import CliRunner

            return CliRunner  # pragma: no cover, click used only if installed

        except ImportError:
            return cls


class ClickRunner:
    """Allows to provide a test-friendly fixture around testing click entry-points"""

    def __init__(self):
        self.main = cli.default_main
        self.logged = None  # type: runez.TrackedOutput
        self.exit_code = None  # type: int

    def run(self, *args, **kwargs):
        """
        :param str|list args: Command line args
        """
        if len(args) == 1 and hasattr(args[0], "split"):
            # Convenience: allow to provide full command as one string argument
            args = args[0].split()
        args = runez.flattened(args, unique=False)
        cmd = kwargs.pop("main", self.main)
        assert bool(cmd), "No main provided"
        with IsolatedLogs():
            with runez.CaptureOutput(dryrun=runez.DRYRUN) as logged:
                runner = ClickWrapper.runner
                runner = runner()
                result = runner.invoke(cmd, args=args, **kwargs)
                if result.output:
                    logged.stdout.write(result.output)
                if result.exception:
                    try:
                        raise result.exception
                    except BaseException:
                        logging.exception("Exited with stacktrace:")
                self.logged = logged.duplicate()
                self.exit_code = result.exit_code

    @property
    def succeeded(self):
        return self.exit_code == 0

    @property
    def failed(self):
        return self.exit_code != 0

    def match(self, expected, stdout=None, stderr=None, log=None, regex=None):
        """
        :param str|re.Pattern expected: Message to find in self.logged
        :param bool|None stdout: Look at stdout (default: yes)
        :param bool|None stderr: Look at stderr (default: yes)
        :param bool|None log: Look at what was logged (default: no)
        :param int|bool|None regex: Specify whether 'expected' should be a regex
        :return Match|None: Match found, if any
        """
        if stdout is None and stderr is None and log is None:
            # By default, look at stdout/stderr only
            stdout = stderr = True
        assert expected, "No 'expected' provided"
        assert self.exit_code is not None, "run() was not called yet"
        captures = [stdout and self.logged.stdout, stderr and self.logged.stderr, log and self.logged.log]
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

        if not isinstance(expected, string_type):
            # Assume regex, no easy way to verify isinstance(expected, re.Pattern) for python < 3.7
            regex = expected

        elif "..." in expected and regex is not False and regex is not True:
            regex = True
            expected = expected.replace("...", ".+")

        if regex is True:
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
                pre = runez.shortened(contents[:i], 32)
                post = runez.shortened(contents[i + len(expected):], 32)
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
        self.run(args)
        assert self.succeeded, "%s failed, was expecting success:\n%s" % (args, self.logged)
        self.expect_messages(*expected, **kwargs)

    def expect_failure(self, args, *expected, **kwargs):
        self.run(args)
        assert self.failed, "%s succeeded, was expecting failure:\n%s" % (args, self.logged)
        self.expect_messages(*expected, **kwargs)


class Match:
    def __init__(self, capture, match, pre=None, post=None):
        self.capture = capture
        self.match = match
        self.pre = pre
        self.post = post

    def __repr__(self):
        return self.match
