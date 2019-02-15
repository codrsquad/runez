import logging

import pytest

import runez


runez.log.Settings.level = logging.DEBUG
runez.log.OriginalLogging.level = logging.DEBUG
logging.root.setLevel(logging.DEBUG)
runez.log.Settings.basename = "pytest"


@pytest.fixture
def temp_folder():
    with runez.TempFolder() as path:
        yield path


@pytest.fixture
def isolated_log_setup():
    """Provide a pristine default log setup, and restore to pristine"""
    with runez.log.OriginalLogging():
        yield


@pytest.fixture
def cli():
    """
    Convenience for click CLI testing.

    Example usage:

        from runez.conftest import click_run

        def test_help(cli):
            cli.run(my_main, "--help")

            assert cli.exit_code == 0
            assert "Usage:" in cli.output

            cli.output_has("Usage:")
    """
    yield ClickRunner()


class ClickWrapper:

    __runner = None

    def __init__(self, output=None, exit_code=None):
        self.output = output
        self.exit_code = exit_code

    def invoke(self, main, args):
        """Mocked click-like behavior"""
        try:
            output = main(args)
            return ClickWrapper(output=output, exit_code=0)

        except Exception as e:
            return ClickWrapper(str(e), exit_code=1)

    @runez.prop
    def runner(cls):
        """
        :return type: CliRunner if available
        """
        try:
            from click.testing import CliRunner
            return CliRunner  # pragma: no cover

        except ImportError:
            return cls


class ClickRunner:

    def __init__(self):
        self.output = None
        self.logged = None
        self.exit_code = None

    def run(self, main, args):
        """
        :param main: click entry point
        :param str|list args: Command line args
        :return click.testing.Result:
        """
        if not isinstance(args, list):
            # Convenience: accept strings
            args = args.split()
        with runez.CaptureOutput(dryrun=runez.State.dryrun) as logged:
            runner = ClickWrapper.runner
            runner = runner()
            result = runner.invoke(main, args=args)
            self.output = result.output
            self.logged = str(logged)
            self.exit_code = result.exit_code

    def _assert_has(self, name, output, expected):
        if not output:
            assert False, "nothing %s, was expecting: %s" % (name, expected)
        if expected not in output:
            output = runez.shortened(output, 256)
            assert False, "'%s' not seen in %s '%s'" % (expected, name, output)

    def assert_output_has(self, expected):
        """
        :param str expected: Verify that expected message is seen in output
        """
        self._assert_has("output", self.output, expected)

    def assert_log_has(self, expected):
        """
        :param str expected: Verify that expected message is seen in output
        """
        self._assert_has("log", self.logged, expected)
