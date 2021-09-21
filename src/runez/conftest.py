"""
Import this only from your test cases

Example:

    from runez.conftest import cli, isolated_log_setup, temp_folder
"""

import logging
import os
import re
import sys
import tempfile

import _pytest.logging
import pytest

import runez.config
import runez.system
from runez.colors import ActivateColors
from runez.file import TempFolder
from runez.logsetup import LogManager
from runez.render import Header
from runez.system import _R, CaptureOutput, DEV, Slotted, TempArgv, TrackedOutput
from runez.system import flattened, LOG, quoted, short, stringified, UNSET

try:
    from click import BaseCommand as _ClickCommand
    from click.testing import CliRunner as _CliRunner

except ImportError:  # pragma: no cover, click used only if installed
    _ClickCommand = None
    _CliRunner = None


TMP = tempfile.gettempdir()

# Set DEBUG logging level when running tests, makes sure LOG.debug() calls get captured (for inspection in tests)
logging.root.setLevel(logging.DEBUG)

if sys.argv and "pycharm" in sys.argv[0].lower():  # pragma: no cover, ignore PyCharm's special wrapper "_jb_pytest_runner"...
    from runez.program import which

    pt = which("pytest")
    if pt:
        sys.argv[0] = pt

# Set logsetup defaults to stable/meaningful for pytest runs
LogManager.override_spec(timezone="UTC", tmp=TMP, locations=[os.path.join("{tmp}", "{basename}")])


def exception_raiser(exc=Exception):
    """
    Convenience wrapper for monkeypatch
    Example usage:
        monkeypatch.setattr(io, "open", runez.conftest.exception_raiser(KeyboardInterrupt))
        monkeypatch.setattr(os, "unlink", runez.conftest.exception_raiser("oops, unlink failed"))
        monkeypatch.setattr(mymodule.MyClass, "myfunction", runez.conftest.exception_raiser(MyException("some message")))

    Args:
        exc (BaseException | type | str): Exception to raise

    Returns:
        (callable): Function that will raise given exception
    """
    def _raise(*_, **__):
        if isinstance(exc, str):
            raise Exception(exc)

        if isinstance(exc, type) and issubclass(exc, BaseException):
            raise exc()

        raise exc

    return _raise


def patch_env(monkeypatch, clear=True, uppercase=True, **values):
    """
    Args:
        monkeypatch (pytest.MonkeyPatch): Monkeypatch object (obtained from pytest fixture)
        clear (bool): If True, clear all env vars (other than the ones given in 'values')
        uppercase (bool): If True, uppercase all keys in 'values'
        **values: Env vars to mock
    """
    if uppercase:
        values = {k.upper(): v for k, v in values.items()}

    if clear:
        for k in os.environ.keys():
            if k not in values:
                monkeypatch.delenv(k)

    for k, v in values.items():
        if v:
            monkeypatch.setenv(k, v)

        else:
            monkeypatch.delenv(k, raising=False)


class IsolatedLogSetup:
    """Allows to isolate changes to logging setup.

    This should only be useful for testing (as in general, logging setup is a global thing).
    """

    def __init__(self, adjust_tmp=True):
        """
        Args:
            adjust_tmp (bool): If True, create a temp folder and cd to it while in context
        """
        self.adjust_tmp = adjust_tmp
        self.temp_folder = None
        self.abort_exception = None
        self.old_cwd = None

    def __enter__(self):
        WrappedHandler.isolation += 1
        self.color_context = ActivateColors(enable=False, flavor="neutral")
        self.color_context.__enter__()
        self.prev_config = runez.config.CONFIG
        self.old_spec = LogManager.spec
        self.old_handlers = logging.root.handlers
        logging.root.handlers = []
        LogManager.reset()
        if self.adjust_tmp:
            self.temp_folder = TempFolder()
            LogManager.spec.tmp = self.temp_folder.__enter__()

        else:
            self.abort_exception = runez.system.AbortException
            self.old_cwd = os.getcwd()

        return self.temp_folder and self.temp_folder.tmp_folder

    def __exit__(self, *_):
        self.color_context.__exit__()
        runez.config.CONFIG = self.prev_config
        LogManager.spec = self.old_spec
        logging.root.handlers = self.old_handlers
        WrappedHandler.isolation -= 1
        LogManager.reset()
        if self.temp_folder:
            self.temp_folder.__exit__()

        else:
            runez.system.AbortException = self.abort_exception
            if self.old_cwd and self.old_cwd != os.getcwd():
                os.chdir(self.old_cwd)


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
    with IsolatedLogSetup() as tmp:
        yield tmp


@pytest.fixture
def logged():
    with CaptureOutput(seed_logging=True) as logged:
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

    _current_instance = None
    isolation = 0

    def __new__(cls, *_):
        if cls._current_instance is not None:
            return cls._current_instance

        cls._current_instance = super().__new__(cls)
        return cls._current_instance

    @classmethod
    def count_non_wrapped_handlers(cls):
        return len([h for h in logging.root.handlers if not isinstance(h, cls)])

    def emit(self, record):
        if self.__class__.isolation == 0:
            stream = CaptureOutput.current_capture_buffer()
            if stream is not None:
                try:
                    msg = self.format(record)
                    stream.write(msg + "\n")
                    self.flush()

                except Exception:  # pragma: no cover
                    self.handleError(record)

            else:
                super().emit(record)

    @classmethod
    def clean_accumulated_logs(cls):
        """Reset pytest log accumulator"""
        cls._current_instance.reset()


_pytest.logging.LogCaptureHandler = WrappedHandler


class ClickWrapper:
    """Wrap click invoke, when click is available, otherwise just call provided function"""

    def __init__(self, stdout, stderr, exit_code, exception):
        self.stdout = stdout
        self.stderr = stderr
        self.exit_code = exit_code
        self.exception = exception


class ClickRunner:
    """Allows to provide a test-friendly fixture around testing click entry-points"""

    args: list = None  # Arguments used in last run()
    exit_code: int = None  # Exit code of last run()
    logged: TrackedOutput = None  # Captured log from last run()
    main: callable = None  # Optional, override default_main for this runner instance
    trace: bool = None  # Optional, enable trace logging for this runner instance

    def __init__(self, context=None):
        """
        Args:
            context (callable | None): Context (example: temp folder) this click run was invoked under
        """
        self.context = context

    @classmethod
    def project_path(cls, *relative_path) -> str:
        """Convenience shortcut to DEV.project_path()"""
        return DEV.project_path(*relative_path)

    @classmethod
    def tests_path(cls, *relative_path) -> str:
        """Convenience shortcut to DEV.tests_path()"""
        return DEV.tests_path(*relative_path)

    @property
    def project_folder(self) -> str:
        """Convenience shortcut to DEV.project_folder"""
        return DEV.project_folder

    @property
    def tests_folder(self) -> str:
        """Convenience shortcut to DEV.tests_folder"""
        return DEV.tests_folder

    def assert_printed(self, expected):
        self.logged.assert_printed(expected)

    def exercise_main(self, *entry_points):
        """Run --help on given entry point scripts, for code coverage.

        This allows to avoid copy-pasting code around just to exercise `if __name__ == "__main__"` sections of code
        Example usage:
            def test_my_cli(cli):
                cli.exercise_main("-mmy_cli", "src/my_cli/cli.py")

        Args:
            *entry_points (str): Relative path to scripts to exercise (or "-mNAME" for a `python --module NAME` form of invocation)
        """
        with runez.CurrentFolder(self.project_folder):  # Change cwd to project otherwise code coverage does NOT correctly detect
            for entry_point in entry_points:
                script = self._resolved_script(entry_point)
                r = runez.run(sys.executable, script, "--help", fatal=False)
                if r.failed:
                    msg = "%s --help failed" % runez.short(script)
                    logging.error("%s\n%s", msg, r.full_output)
                    assert False, msg

    def run(self, *args, exe=None, main=UNSET, trace=UNSET):
        """
        Args:
            *args: Command line args
            exe (str | None): Optional, override sys.argv[0] just for this run
            main (callable | None): Optional, override current self.main just for this run
            trace (bool): If True, enable trace logging
        """
        main = _R.rdefault(main, self.main or cli.default_main)
        if len(args) == 1 and hasattr(args[0], "split"):
            # Convenience: allow to provide full command as one string argument
            args = args[0].split()

        self.args = flattened(args, shellify=True)
        with IsolatedLogSetup(adjust_tmp=False):
            with CaptureOutput(dryrun=_R.is_dryrun(), seed_logging=True, trace=_R.rdefault(trace, self.trace)) as logged:
                self.logged = logged
                with TempArgv(self.args, exe=exe):
                    result = self._run_main(main, self.args)
                    if isinstance(result.exception, AssertionError):
                        raise result.exception

                    if result.stdout:
                        logged.stdout.buffer.write(result.stdout)

                    if result.stderr:
                        logged.stderr.buffer.write(result.stderr)

                    if result.exception and not isinstance(result.exception, SystemExit):
                        try:
                            raise result.exception

                        except Exception:
                            LOG.exception("Exited with stacktrace:")

                    self.exit_code = result.exit_code

        if self.logged:
            WrappedHandler.clean_accumulated_logs()
            title = Header.aerated("Captured output for: %s" % quoted(self.args), border="==")
            LOG.info("\n%s\nmain: %s\nexit_code: %s\n%s\n", title, main, self.exit_code, self.logged)

    @property
    def succeeded(self):
        return self.exit_code == 0

    @property
    def failed(self):
        return self.exit_code != 0

    def match(self, expected, stdout=None, stderr=None, regex=None):
        """
        Args:
            expected (str | re.Pattern): Message to find in self.logged
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

        if isinstance(expected, str) and "..." in expected and not isinstance(regex, bool):
            regex = True
            expected = expected.replace("...", ".+")

        if not isinstance(expected, str):
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
                pre = short(contents[:i], size=32)
                post = short(contents[i + len(expected):], size=32)
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
        assert self.succeeded, "%s failed, was expecting success" % quoted(self.args)
        self.expect_messages(*expected, **spec.to_dict())

    def expect_failure(self, args, *expected, **kwargs):
        spec = RunSpec()
        spec.pop(kwargs)
        self.run(args, **kwargs)
        assert self.failed, "%s succeeded, was expecting failure" % quoted(self.args)
        self.expect_messages(*expected, **spec.to_dict())

    def _resolved_script(self, script):
        if script.startswith("-") or os.path.exists(script):
            return script

        path = self.project_path(script)
        if os.path.exists(path):
            return path

        path = self.tests_path(script)
        if os.path.exists(path):
            return path

    def _run_main(self, main, args):
        if _ClickCommand is not None and isinstance(main, _ClickCommand):
            if "LANG" not in os.environ:
                # Avoid click complaining about unicode for tests that mock env vars
                os.environ["LANG"] = "en_US.UTF-8"

            runner = _CliRunner()
            r = runner.invoke(main, args=args)
            return ClickWrapper(r.output, None, r.exit_code, r.exception)

        if callable(main):
            result = ClickWrapper(None, None, None, None)
            try:
                result.stdout = main()
                result.exit_code = 0

            except AssertionError:
                raise

            except SystemExit as e:
                if isinstance(e.code, int):
                    result.exit_code = e.code

                else:
                    result.exit_code = 1
                    result.stderr = stringified(e)

            except BaseException as e:
                result.exit_code = 1
                result.exception = e
                result.stderr = stringified(e)

            return result

        if isinstance(main, str):
            script = self._resolved_script(main)
            if not script:
                assert False, "Can't find script '%s', invalid main" % script

            r = runez.run(sys.executable, script, *args, fatal=False)
            return ClickWrapper(r.output, r.error, r.exit_code, r.exc_info)

        assert False, "Can't invoke invalid main: %s" % main


class RunSpec(Slotted):

    __slots__ = ["stdout", "stderr", "regex"]

    def _get_defaults(self):
        return UNSET


class Match:
    def __init__(self, capture, match, pre=None, post=None):
        self.capture = capture
        self.match = match
        self.pre = pre
        self.post = post

    def __repr__(self):
        return self.match
