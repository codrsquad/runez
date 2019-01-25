"""
Convenience for click CLI testing.

Example usage:

from runez.testing import expect_success

def test_help():
    expect_success(my_main, "--help", "Usage:")
"""

import runez


class ClickResult:
    def __init__(self, output, exit_code=0):
        self.output = output
        self.exit_code = exit_code


try:
    from click.testing import CliRunner

except ImportError:
    class CliRunner:
        # Mock click-like behavior
        def invoke(self, main, args):
            try:
                return ClickResult(main(args))

            except Exception as e:
                return ClickResult(str(e), exit_code=1)


def click_run(main, args, **kwargs):
    """
    :param main: click entry point
    :param str|list args: Command line args
    :return click.testing.Result:
    """
    old_dryrun = runez.State.dryrun
    runner = CliRunner()
    if not isinstance(args, list):
        # Convenience: accept strings
        args = args.split()

    if kwargs:
        for i, arg in enumerate(args):
            args[i] = arg.format(**kwargs)

    with runez.CaptureOutput() as logged:
        result = runner.invoke(main, args=args)
        result = ClickResult("%s\n%s" % (result.output, logged), exit_code=result.exit_code)

    runez.State.dryrun = old_dryrun
    return result


def expect_messages(output, *expected):
    """
    :param str output: Output received from command execution
    :param list(str) expected: Expected messages (start with '!' to negate)
    """
    for message in expected:
        if message[0] == '!':
            assert message[1:] not in output

        else:
            output = runez.shortened(output, 256)
            assert message in output, "'%s' not seen in '%s'" % (message, output)


def expect_success(main, args, *expected, **kwargs):
    """
    Run CLI with 'args' and verify it exits with code 0

    :param list(str) args: Args to invoke CLI with
    :param list(str) expected: Expected messages in output
    """
    result = click_run(main, args, **kwargs)
    assert result.exit_code == 0
    expect_messages(result.output, *expected)


def expect_failure(main, args, *expected, **kwargs):
    """
    Run CLI with 'args' and verify it exits with code != 0

    :param list(str) args: Args to invoke CLI with
    :param list(str) expected: Expected messages in output
    """
    result = click_run(main, args, **kwargs)
    assert result.exit_code != 0
    expect_messages(result.output, *expected)
