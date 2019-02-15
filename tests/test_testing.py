import pytest


def stringify(args):
    return str(args)


def crash(args):
    raise Exception("crashed: %s" % args)


def test_success(cli):
    cli.main = stringify
    cli.run("--dryrun hello")
    cli.assert_output_has("hello")
    assert "foo" not in cli.output

    cli.run("hello")
    cli.assert_output_has("hello")


def test_crash(cli):
    with pytest.raises(AssertionError):
        # Nothing ran yet, no output
        cli.assert_output_has("foo")

    with pytest.raises(AssertionError):
        # No main provided
        cli.run("hello")

    cli.main = crash
    cli.run(["hello"])
    assert cli.exit_code != 0
    assert "crashed" in cli.output
    cli.assert_output_has("hello")

    with pytest.raises(AssertionError):
        cli.assert_log_has("hello")

    with pytest.raises(AssertionError):
        cli.assert_output_has("foo")
