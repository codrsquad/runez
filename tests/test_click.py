"""
Test click related methods
"""

from __future__ import print_function

import os

import click
from mock import patch

import runez


@runez.click.group()
@runez.click.version(message="%(prog)s, version %(version)s")
@runez.click.color()
@runez.click.config("-c", prefix="g.")
@runez.click.debug(expose_value=False)
@runez.click.dryrun()
@runez.click.log(expose_value=False)
def my_group():
    # By default, --config value is NOT exposed, the global runez.config.CONFIG is altered
    config = runez.config.CONFIG
    assert len(config.providers) == 1
    assert "--config: " in config.overview()
    assert config.provider_by_name("--config") is not None


@my_group.command()
@click.argument("text", nargs=-1)
def echo(text):
    """Repeat provided text"""
    text = " ".join(text)
    msg = "%s, color: %s, %s values, g.a=%s" % (text, runez.color.is_coloring(), len(runez.config.CONFIG), runez.config.get("g.a"))
    msg += ", debug: %s, dryrun: %s, log: %s" % (runez.log.debug, runez.DRYRUN, runez.log.spec.file_location)
    print(msg)


@runez.click.command()
@runez.click.version(version="1.2.3")
@runez.click.border("-b")
@runez.click.color("-x", expose_value=True)
@runez.click.config("-c", expose_value=True, default="a=b,c=d", split=",", env="MY_PROG", propsfs=True)
@runez.click.debug()
@runez.click.dryrun()
@runez.click.log()
def say_hello(border, color, config, debug, log):
    """Say hello"""
    # When --config is exposed, global config is NOT modified
    assert not runez.config.CONFIG.providers
    assert runez.log.spec.file_location is None
    # Intentionally set global runez.config.CONFIG to verify it has been restored at the end of the test command run
    runez.config.CONFIG = config
    assert len(config.providers) == 4
    assert "propsfs" in config.overview()
    msg = "border: %s, color: %s, a=%s c=%s, debug: %s, dryrun: %s, log: %s" % (
        border, color, config.get("a"), config.get("c"), debug, runez.DRYRUN, log
    )
    print(msg)


def test_settings():
    s = runez.click.settings(foo="bar", epilog="some epilog")
    assert len(s) == 3
    assert s["epilog"] == "some epilog"
    assert s["foo"] == "bar"
    assert s["context_settings"] == dict(help_option_names=["-h", "--help"], max_content_width=140)

    s = runez.click.settings(help="-h --help --explain")
    assert s["context_settings"]["help_option_names"] == ["-h", "--help", "--explain"]


def test_group(cli):
    cli.main = my_group
    cli.expect_success("--version", "my-group, version ")
    cli.expect_success(["--help"], "--color / --no-color", "--log PATH", "Repeat provided text")

    cli.run("--color echo hello")
    assert cli.succeeded
    cli.assert_printed("hello, color: True, 0 values, g.a=None, debug: False, dryrun: False, log: None")

    cli.run("--no-color --dryrun -ca=b --config c=d --log foo echo hello")
    assert cli.succeeded
    cli.assert_printed("hello, color: False, 2 values, g.a=b, debug: False, dryrun: True, log: foo")


def test_command(cli):
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

    with patch.dict(os.environ, {"MY_PROG_A": "some-value"}, clear=True):
        cli.run("")
        assert cli.succeeded
        cli.assert_printed("border: reddit, color: None, a=some-value c=d, debug: None, dryrun: False, log: None")


def sample_config(**attrs):
    attrs.setdefault("tracer", print)
    c = runez.click._ConfigOption(attrs)
    return c


def test_config(logged):
    with patch.dict(os.environ, {}, clear=True):
        # sys.argv is used as env var prefix when env=True is used
        config = sample_config(env=True)(None, None, "")
        assert str(config) == "--config, PYTEST_* env vars"
        assert "Adding config provider PYTEST_*" in logged.pop()

    with patch.dict(os.environ, {"MY_PROG_A": "via env"}, clear=True):
        propsfs = runez.log.tests_path("sample")
        config = sample_config(env="MY_PROG", default="x=y", propsfs=propsfs, split=",")
        c1 = config(None, None, "")
        assert str(c1) == "--config, MY_PROG_* env vars, propsfs, --config default"
        assert logged.pop()
        assert c1.get("x") == "y"
        logged.assert_printed("Using x='y' from --config default")
        assert c1.get_int("some-int") == 123
        logged.assert_printed("Using some-int='123' from propsfs")

        # 'some-int' from propsfs sample is overridden
        c2 = config(None, None, "x=overridden,some-int=12,twenty-k=20kb,five-one-g=5.1g")
        assert logged.pop()
        assert c1.get_str("key") is None
        assert not logged
        assert c2.get("x") == "overridden"
        logged.assert_printed("Using x='overridden' from --config")
        assert c2.get_int("some-int") == 12
        logged.assert_printed("Using some-int='12' from --config")

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
        logged.assert_printed("Replacing config provider --config at index 0")

        c2.add(runez.config.DictProvider({}, name="foo1"), front=True)
        logged.assert_printed("Adding config provider foo1 to front")
