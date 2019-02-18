import re

import pytest


def stringify(*args):
    return " ".join(args)


def crash(*args):
    raise Exception("crashed: %s" % args)


def test_success(cli):
    cli.main = stringify
    cli.run("--dryrun hello")
    assert cli.succeeded
    assert cli.match("hello")
    assert not cli.match("foo")

    cli.expect_success("hello", "hello", "el+", regex=True)

    cli.run("hello")
    m = cli.match("hello")
    assert m
    assert str(m) == "hello"
    m = cli.match("el+", regex=True)
    assert m
    assert m.match == "ell"

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
        cli.run("hello")

    cli.main = crash
    cli.run(["hello"])
    assert cli.failed
    assert cli.match("crashed...hello")
    assert cli.match("Exited with stacktrace:", log=True)

    cli.expect_failure("hello", "crashed...hello", "Exited with stacktrace:", "!this message shouldn't appear", log=True)

    with pytest.raises(AssertionError):
        # No captures specified
        assert cli.match("crashed...hello", stdout=False, stderr=False, log=False)

    with pytest.raises(AssertionError):
        # Expect success failed
        cli.expect_success("hello")

    with pytest.raises(AssertionError):
        # Unexpected message seen in output
        cli.expect_failure("hello", "!crashed...hello")

    with pytest.raises(AssertionError):
        # Expected message not seen in output
        cli.expect_failure("hello", "this message shouldn't appear")
