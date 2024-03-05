import os
import re
import sys

import pytest

import runez
import runez.conftest


def sample_main():
    args = sys.argv[1:]
    runez.log.trace("Running main() with: %s" % args)
    if args:
        args = runez.flattened(args, shellify=True)
        if args[0] == "TypeError":
            # Raise a TypeError
            len(42)

        exit_code = runez.to_int(args[0])
        if exit_code is not None:
            # When first arg is a number, call sys.exit() with that number
            if len(args) > 1:
                print(" ".join(args[1:]))

            sys.exit(exit_code)

        if args[0] == "Exception":
            # Raise a generic exception
            raise RuntimeError("crashed: %s" % args[1:])

        assert args[0] != "AssertionError", "oops, something went wrong"
        if args[0] == "exit":
            # exit without explicit code
            sys.exit(" ".join(args[1:]))

        if args[0] == "quiet":
            # Don't output anything
            sys.exit(0)

    # Simulate some output
    return "%s %s" % (os.path.basename(sys.argv[0]), " ".join(args))


def test_cli_uninitialized(cli, monkeypatch):
    from runez.conftest import cli as cli_fixture

    monkeypatch.setattr(cli_fixture, "default_main", None)
    with pytest.raises(AssertionError):
        # No main provided
        cli.run("hello no main")


def test_crash(cli):
    cli.main = sample_main
    cli.run(["Exception", "hello with main"])
    assert cli.failed
    assert cli.match("crashed...hello")
    assert cli.match("Exited with stacktrace:")

    with pytest.raises(AssertionError):
        cli.run(["AssertionError"])

    cli.run("TypeError")
    assert cli.failed
    assert cli.match("TypeError: ... has no len")

    cli.run("exit", "some message")
    assert cli.failed
    cli.expect_messages("some message", "!stacktrace")

    cli.expect_failure("Exception hello", "crashed...hello", "Exited with stacktrace:", "!this message shouldn't appear")

    cli.run(["successful hello"])
    assert cli.succeeded
    assert cli.match("successful hello")

    cli.run(["Exception", "hello again"])
    assert cli.failed
    assert not cli.match("hello with main")
    assert not cli.match("successful hello")
    assert cli.match("hello again")

    cli.run(1, "hello")
    assert cli.failed
    assert "hello" in cli.logged.stdout
    assert "Exited with stacktrace" not in cli.logged

    cli.run(2)
    assert cli.failed
    assert cli.exit_code == 2
    assert not cli.logged

    with pytest.raises(AssertionError):
        # No captures specified
        assert cli.match("crashed...hello", stdout=False, stderr=False)

    with pytest.raises(AssertionError):
        # Expect success failed
        cli.expect_success("Exception", "hello")

    with pytest.raises(AssertionError):
        # Unexpected message seen in output
        cli.expect_failure(["Exception", "hello"], "!crashed...hello")

    with pytest.raises(AssertionError):
        # Expected message not seen in output
        cli.expect_failure(["Exception", "hello"], "this message shouldn't appear")


def test_edge_cases(temp_folder):
    # Exercise dev folder determination code
    info = runez.system.DevInfo()
    info.tests_folder = "./bar/baz"
    info.venv_folder = "./foo"
    assert info.project_path() is None

    runez.touch("setup.py", logger=None)
    del info.project_folder
    p = info.project_path()
    assert p == "."


def test_invalid_main(cli):
    cli.run("hello", main="-mno_such_module")
    assert cli.failed
    assert "No module named no_such_module" in cli.logged.stderr

    with pytest.raises(AssertionError):
        cli.run("hello", main="no_such_script.foo")

    with pytest.raises(AssertionError):
        cli.run("foo", main=["invalid"])


def test_script_invocations(cli):
    # This unfortunately does is not enough to detect code coverage (due to cwd being a temp folder I think)
    cli.run("--help", main="-mrunez")
    assert cli.succeeded
    assert "usage: python -mrunez [-h]" in cli.logged
    assert "Set of sample commands" in cli.logged

    cli.run("--help", main="src/runez/__main__.py")
    assert cli.succeeded
    assert "/runez [-h]" in cli.logged
    assert "Set of sample commands" in cli.logged

    # Below will properly make test coverage detect properly that we did execute code in __main__.py
    cli.exercise_main("-mrunez", "src/runez/__main__.py")
    cli.exercise_main("extra-validations")  # Checks also that script is found even in tests/ subfolder

    with pytest.raises(AssertionError):
        cli.exercise_main("failed-help")


def test_success(cli):
    cli.main = sample_main

    # Verify that project folder works properly
    tests = os.path.dirname(__file__)
    project_folder = os.path.abspath(os.path.join(tests, ".."))

    assert cli.project_folder == project_folder
    assert runez.DEV.project_folder == project_folder
    assert cli.tests_folder == tests
    assert cli.tests_path("foo.txt") == os.path.join(tests, "foo.txt")
    assert cli.project_path() == project_folder
    assert cli.project_path("foo") == os.path.join(project_folder, "foo")

    cli.run("quiet")
    assert cli.succeeded
    assert not cli.logged
    assert cli.match(".*", regex=True) is None

    cli.run("quiet", trace=True)
    assert cli.succeeded
    assert ":: Running main() with: ['quiet']" in cli.logged

    cli.run("--dryrun hello", exe="bar/foo")
    assert cli.succeeded
    assert cli.logged.stdout.contents() == "foo --dryrun hello"
    assert not cli.logged.stderr

    cli.run("--dryrun hello")
    assert cli.succeeded
    assert cli.logged.stdout.contents() == "pytest --dryrun hello"
    assert not cli.logged.stderr
    assert cli.match("el+", regex=True)
    assert not cli.match("EL+", regex=True)
    assert cli.match("EL+", regex=re.IGNORECASE)

    cli.expect_success("hello world", "hello", "el+", regex=True)
    m = cli.match("hello ...l")
    assert str(m) == "hello worl"
    assert cli.match("el+", regex=True).match == "ell"
    assert cli.match(re.compile("hel+o")).match == "hello"
    assert cli.match("h...")
    assert cli.match("h...", regex=True)
    assert not cli.match("h...", regex=False)
    assert not cli.match("Hello")
    assert cli.match("Hello", regex=re.IGNORECASE)

    cli.run([""])
    assert cli.succeeded
    assert cli.logged.stdout.contents().strip() == os.path.basename(sys.argv[0])
    assert not cli.logged.stderr
    assert not cli.match("hello")
