# -*- coding: utf-8 -*-

"""
Test click related methods
"""

import click

import runez


@runez.click.group()
@runez.click.version()
@runez.click.color()
@runez.click.config("-c", expose_value=False)
@runez.click.debug(expose_value=False)
@runez.click.dryrun(expose_value=False)
@runez.click.log(expose_value=False)
def my_group():
    config = runez.config.CONFIG.overview()
    print("color: %s, %s" % (runez.colors.is_coloring(), config))
    print("debug: %s, dryrun: %s, log: %s" % (runez.DRYRUN, runez.log.debug, runez.log.spec.file_location))


@my_group.command()
@click.argument("text", nargs=-1)
def echo(text):
    """Repeat provided text"""
    text = " ".join(text)
    print(text)


@runez.click.command()
@runez.click.version()
@runez.click.color("-x", expose_value=True)
@runez.click.config("-c")
@runez.click.debug()
@runez.click.dryrun()
@runez.click.log()
def say_hello(color, config, debug, dryrun, log):
    """Say hello"""
    print("color: %s, config: %s" % (color, config))
    print("debug: %s, dryrun: %s, log: %s" % (debug, dryrun, log))


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

    cli.expect_success(["--color", "echo", "hello"], "color: True, --config: 0 values", "hello")
    cli.expect_success(["--no-color", "-c", "a=b", "echo", "hello"], "color: False, --config: 1 values")
    cli.expect_success(["--config", "a=b", "-cc=d", "echo", "hello"], "--config: 2 values")
    p = runez.config.CONFIG.provider_by_name("--config")
    assert p
    assert p.values["a"] == "b"
    assert runez.log.spec.file_location is None

    cli.expect_success(["--log", "foo", "echo", "hi"], "log: foo")
    assert runez.log.spec.file_location == "foo"

    cli.expect_success(["--dryrun", "echo", "hi"], "--config: 0 values", "debug: True, dryrun: True")
    assert runez.log.spec.file_location is None

    runez.config.clear()


def test_command(cli):
    cli.main = say_hello
    cli.expect_success("--version", "say-hello, version ")
    cli.expect_success(["--help"], "-x, --color / --no-color", "--log PATH", "Say hello")

    cli.expect_success([], "color: None, config: ()", "debug: None, dryrun: None, log: None")
    cli.expect_success(["-x"], "color: True")
    cli.expect_success(["--color", "--config=a=b", "-c", "c=d"], "color: True", "a=b", "c=d")
    cli.expect_success(["--no-color", "--debug", "--log=foo"], "color: False", "debug: True, dryrun: None, log: foo")
    assert runez.log.spec.file_location is None


def test_edge_cases():
    # Ensure we stop once callstack is exhausted
    assert runez.click.find_caller_frame(lambda d, f: None, maximum=1000) is None
