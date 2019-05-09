import re
import sys

import pytest


def stringify(*args):
    return " ".join(args)


def crash(*args):
    raise Exception("crashed: %s" % args)


def hard_exit(*args):
    if len(args) == 1 and isinstance(args[0], int):
        sys.exit(args[0])
    sys.exit(" ".join(args))


def test_success(cli):
    cli.main = stringify
    cli.run("--dryrun hello")
    assert cli.succeeded
    assert cli.match("hello")
    assert not cli.match("foo")
    assert cli.match("el+", regex=True)
    assert not cli.match("EL+", regex=True)
    assert cli.match("EL+", regex=re.IGNORECASE)

    cli.expect_success("hello", "hello", "el+", regex=True)

    cli.run("{marker} world", marker="hello")
    m = cli.match("hello world")
    assert m
    assert str(m) == "hello world"
    m = cli.match("el+", regex=True)
    assert m
    assert m.match == "ell"

    assert cli.match("h...")
    assert cli.match("h...", regex=True)
    assert not cli.match("h...", regex=False)
    assert cli.match(re.compile("hel+o"))

    assert not cli.match("Hello")
    assert cli.match("Hello", regex=re.IGNORECASE)

    cli.run([""])
    assert not cli.match("hello")


def test_crash(cli):
    with pytest.raises(AssertionError):
        # Nothing ran yet, no output
        cli.match("foo")

    with pytest.raises(AssertionError):
        # No main provided
        cli.run("hello no main")

    cli.main = crash
    cli.run(["hello with main"])
    assert cli.failed
    assert cli.match("crashed...hello")
    assert cli.match("Exited with stacktrace:")

    cli.expect_failure("hello", "crashed...hello", "Exited with stacktrace:", "!this message shouldn't appear")

    cli.main = stringify
    cli.run(["successful hello"])
    assert cli.succeeded
    assert cli.match("successful hello")

    cli.main = crash
    cli.run(["hello again"])
    assert cli.failed
    assert not cli.match("hello with main")
    assert not cli.match("successful hello")
    assert cli.match("hello again")

    with pytest.raises(AssertionError):
        # No captures specified
        assert cli.match("crashed...hello", stdout=False, stderr=False)

    with pytest.raises(AssertionError):
        # Expect success failed
        cli.expect_success("hello")

    with pytest.raises(AssertionError):
        # Unexpected message seen in output
        cli.expect_failure("hello", "!crashed...hello")

    with pytest.raises(AssertionError):
        # Expected message not seen in output
        cli.expect_failure("hello", "this message shouldn't appear")


def test_hard_exit(cli):
    cli.main = hard_exit
    cli.run("hello")
    assert cli.failed
    assert "hello" in cli.logged.stdout
    assert "Exited with stacktrace" not in cli.logged

    cli.run(2)
    assert cli.failed
    assert cli.exit_code == 2
    assert not cli.logged
