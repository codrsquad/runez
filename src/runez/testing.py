"""
Convenience for click CLI testing.

Example usage:

from runez.testing import expect_success

def test_help():
    expect_success(my_main, "--help", "Usage:")
"""

import runez


try:
    from click.testing import CliRunner

except ImportError:
    # Mock click-like behavior
    class Result:
        def __init__(self, output, exit_code=0):
            self.output = output
            self.exit_code = exit_code

    class CliRunner:
        def invoke(self, main, args):
            try:
                return Result(main(args))

            except Exception as e:
                return Result(str(e), exit_code=1)


def click_run(main, args, **kwargs):
    """
    :param main: click entry point
    :param str|list args: Command line args
    :return click.testing.Result:
    """
    runner = CliRunner()
    if not isinstance(args, list):
        # Convenience: accept strings
        args = args.split()

    if kwargs:
        for i, arg in enumerate(args):
            args[i] = arg.format(**kwargs)

    result = runner.invoke(main, args=args)
    if args and args[0] == "--dryrun":
        # Restore default non-dryrun state after a --dryrun test
        runez.State.dryrun = False

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
            assert message in output


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
