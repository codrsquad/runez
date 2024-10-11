"""
Test click related methods
"""

import errno
import logging
import os
import sys

import click
import pytest

import runez
from runez.conftest import exception_raiser


def my_formatter(text):
    return text.format(placeholder="epilog")


@runez.click.group()
@runez.click.version(message="%(prog)s, version %(version)s")
@runez.click.color()
@runez.click.config("-c", prefix="g.")
@runez.click.debug()
@runez.click.dryrun()
@runez.click.log(expose_value=False)
def my_group(debug):
    # By default, --config value is NOT exposed, the global runez.config.CONFIG is altered
    runez.system.AbortException = SystemExit
    runez.log.setup(
        debug=debug,
        console_format="%(levelname)s %(message)s",
        console_level=logging.INFO,
        locations=None,
        greetings=":: {argv}",
    )
    config = runez.config.CONFIG
    cd = config.get("g.cd")
    if cd:
        logging.info("Changed folder to %s", runez.short(cd))
        runez.ensure_folder(cd)
        os.chdir(cd)

    assert len(config.providers) == 1
    assert "--config: " in config.overview()
    assert config.provider_by_name("--config") is not None


@my_group.command()
@click.argument("text", nargs=-1)
def echo(text):
    """
    Repeat provided text

    This part will be an {placeholder}
    """
    text = " ".join(text)
    assert text != "AssertionError", "oops"
    msg = "%s, color: %s, %s values, g.a=%s" % (text, runez.color.is_coloring(), len(runez.config.CONFIG), runez.config.get("g.a"))
    msg += ", debug: %s, dryrun: %s, log: %s" % (runez.log.debug, runez.DRYRUN, runez.log.spec.file_location)
    print(msg)


@my_group.command()
@click.argument("env_vars", required=False)
def setenv(env_vars):
    for kv in runez.flattened(env_vars, split=","):
        k, _, v = kv.partition("=")
        if v:
            logging.info("Setting env var %s=%s", k, v)
            os.environ[k] = v

        else:
            logging.info("Deleting env var %s", k)
            del os.environ[k]


@runez.click.command()
@runez.click.version(version="1.2.3")
@runez.click.border("-b")
@runez.click.color("-x", expose_value=True)
@runez.click.config("-c", expose_value=True, default="a=b,c=d", split=",", env="MY_PROG", propsfs=True)
@runez.click.debug()
@runez.click.dryrun()
@runez.click.log()
@click.option("--use-stderr", is_flag=True, help="Print on stderr")
def say_hello(border, color, config, debug, log, use_stderr):
    """Say hello"""
    # When --config is exposed, global config is NOT modified
    assert not runez.config.CONFIG.providers
    assert runez.log.spec.file_location is None
    # Intentionally set global runez.config.CONFIG to verify it has been restored at the end of the test command run
    runez.config.CONFIG = config
    assert len(config.providers) == 4
    assert "propsfs" in config.overview()
    msg = "border: %s, color: %s, a=%s c=%s, debug: %s, dryrun: %s, log: %s" % (
        border,
        color,
        config.get("a"),
        config.get("c"),
        debug,
        runez.DRYRUN,
        log,
    )
    if use_stderr:
        sys.stderr.write("%s\n" % msg)

    else:
        print(msg)


def test_command(cli, monkeypatch):
    cli.main = say_hello
    cli.run("--help")
    assert cli.succeeded
    assert "--border" in cli.logged
    assert "--color" in cli.logged
    assert "--no-color" in cli.logged

    cli.expect_success("--version", "1.2.3")
    cli.expect_success(["--help"], "-x, --color / --no-color", "--log PATH", "Say hello")

    cli.run("--no-color")
    assert cli.succeeded
    cli.assert_printed("border: reddit, color: False, a=b c=d, debug: None, dryrun: False, log: None")

    cli.run("-x")
    assert cli.succeeded
    assert "color: True" in cli.logged.stdout

    cli.run("--border github --color --debug --config=a=x -c c=y --log=foo")
    assert cli.succeeded
    cli.assert_printed("border: github, color: True, a=x c=y, debug: True, dryrun: False, log: foo")

    monkeypatch.setenv("MY_PROG_A", "some-value")
    monkeypatch.delenv("LANG", raising=False)
    cli.run("")
    assert cli.succeeded
    cli.assert_printed("border: reddit, color: None, a=some-value c=d, debug: None, dryrun: False, log: None")


def test_command_with_stderr(cli):
    cli.main = say_hello
    cli.run("")
    assert cli.succeeded
    assert "border:" in cli.logged

    cli.main = say_hello
    cli.run("--use-stderr")
    assert cli.succeeded
    assert "border:" in cli.logged


def sample_config(**attrs):
    attrs.setdefault("tracer", print)
    return runez.click._ConfigOption(attrs)


def test_config(logged, monkeypatch):
    # sys.argv is used as env var prefix when env=True is used
    runez.log.enable_trace(True)
    config = sample_config(env=True)(None, None, "")
    assert str(config) == "--config, PYTEST_* env vars"
    assert "Adding config provider PYTEST_*" in logged.pop()

    monkeypatch.setenv("MY_PROG_A", "via env")
    propsfs = runez.DEV.tests_path("sample")
    config = sample_config(env="MY_PROG", default="x=y", propsfs=propsfs, split=",")
    c1 = config(None, None, "")
    assert str(c1) == "--config, MY_PROG_* env vars, propsfs, --config default"
    assert logged.pop()
    assert c1.get("x") == "y"
    assert "Using x='y' from --config default" in logged.stderr.pop()
    assert c1.get_int("some-int") == 123
    assert "Using some-int='123' from propsfs" in logged.stderr.pop()

    # 'some-int' from propsfs sample is overridden
    c2 = config(None, None, "x=overridden,some-int=12,twenty-k=20kb,five-one-g=5.1g")
    assert logged.pop()
    assert c1.get_str("key") is None
    assert not logged
    assert c2.get("x") == "overridden"
    assert "Using x='overridden' from --config" in logged.stderr.pop()
    assert c2.get_int("some-int") == 12
    assert "Using some-int='12' from --config" in logged.stderr.pop()

    # Test bytesize
    assert c2.get_bytesize("some-int") == 12
    assert c2.get_bytesize("some-int", default_unit="k") == 12 * 1024
    assert c2.get_bytesize("some-int", default_unit="m") == 12 * 1024 * 1024

    assert c2.get_bytesize("twenty-k") == 20 * 1024
    assert c2.get_bytesize("five-one-g") == int(5.1 * 1024 * 1024 * 1024)

    assert c2.get_bytesize("twenty-k", minimum=5, maximum=100) == 100

    # Invalid default unit affects only ints without unit
    assert c2.get_bytesize("some-int", default_unit="a") is None
    assert c2.get_bytesize("twenty-k", default_unit="a") == 20 * 1024

    assert c2.get_bytesize("some-string") is None
    assert c2.get_bytesize("some-string", default=5) == 5
    assert c2.get_bytesize("some-string", default="5k") == 5 * 1024
    assert c2.get_bytesize("some-string", default=5, default_unit="k") == 5 * 1024
    assert c2.get_bytesize("some-string", default="5m", default_unit="k") == 5 * 1024 * 1024
    logged.pop()

    # Shuffle things around
    c2.add(c2.providers[0])
    assert "Replacing config provider --config at index 0" in logged.stderr.pop()

    c2.add(runez.config.DictProvider({}, name="foo1"), front=True)
    assert "Adding config provider foo1 to front" in logged.stderr.pop()


def test_group(cli, monkeypatch):
    assert runez.system.AbortException is not SystemExit
    cli.main = my_group
    runez.click.prettify_epilogs(my_group, formatter=my_formatter)
    runez.click.prettify_epilogs(my_group, formatter=my_formatter)  # Calling this multiple times is a no-op
    cli.expect_success("--version", "my-group, version ")

    cli.run("--help")
    assert cli.succeeded
    assert "--color / --no-color" in cli.logged
    assert "--log PATH" in cli.logged
    assert "Repeat provided text" in cli.logged
    assert "This part will be" not in cli.logged

    assert cli.context == os.getcwd()
    cli.run("-ccd=foo", "echo", "--help")
    assert cli.succeeded
    assert "Repeat provided text" in cli.logged
    assert "This part will be an epilog" in cli.logged
    assert "Changed folder to foo" in cli.logged

    # Test env var restoration
    assert os.environ.get("TT_A") is None
    cli.run("setenv", "TT_A=foo")
    assert cli.succeeded
    assert "Setting env var TT_A=foo" in cli.logged
    assert os.environ.get("TT_A") is None

    monkeypatch.setenv("TT_A", "bar")
    cli.run("setenv", "TT_A=foo")
    assert cli.succeeded
    assert "Setting env var TT_A=foo" in cli.logged
    assert os.environ.get("TT_A") == "bar"

    cli.run("setenv", "TT_A=")
    assert cli.succeeded
    assert "Deleting env var TT_A" in cli.logged
    assert os.environ.get("TT_A") == "bar"

    # Verify that current folder was restored
    assert cli.context == os.getcwd()
    assert runez.system.AbortException is not SystemExit

    cli.run("--color echo hello")
    assert cli.succeeded
    cli.assert_printed("hello, color: True, 0 values, g.a=None, debug: False, dryrun: False, log: None")

    cli.run("--no-color --dryrun -ca=b --config c=d --log foo echo hello")
    assert cli.succeeded
    cli.assert_printed("hello, color: False, 2 values, g.a=b, debug: False, dryrun: True, log: foo")

    with pytest.raises(AssertionError):
        cli.run("echo", "AssertionError")


def check_protected_main(exit_code, exception, *messages, **kwargs):
    with runez.CaptureOutput() as logged:
        with pytest.raises(SystemExit) as x:
            runez.click.protected_main(exception_raiser(exception), **kwargs)
        assert x.value.code == exit_code
        for message in messages:
            assert message in logged

        return logged


def test_protected_main():
    # Exercise protected_main()
    check_protected_main(1, KeyboardInterrupt, "Aborted")
    check_protected_main(1, NotImplementedError, "Not implemented yet")
    check_protected_main(1, Exception("oops"), "Exception: oops", "Traceback")

    # No stack trace with debug_stacktrace=True
    logged = check_protected_main(1, Exception("oops"), "oops", debug_stacktrace=True)
    assert "Traceback" not in logged

    check_protected_main(1, TypeError("oops"), "TypeError", "Traceback", no_stacktrace=[ValueError])
    logged = check_protected_main(1, ValueError("oops"), "oops", no_stacktrace=[ValueError])
    assert "ValueError" not in logged  # Exception is stringified and shown as ERROR
    assert "Traceback" not in logged

    exc = IOError()
    exc.errno = errno.EPIPE
    logged = check_protected_main(0, exc)
    assert not logged


def test_settings():
    s = runez.click.settings(foo="bar", epilog="some epilog")
    assert len(s) == 3
    assert s["epilog"] == "some epilog"
    assert s["foo"] == "bar"
    assert s["context_settings"] == {"help_option_names": ["-h", "--help"], "max_content_width": 140}

    s = runez.click.settings(help="-h --help --explain")
    assert s["context_settings"]["help_option_names"] == ["-h", "--help", "--explain"]
