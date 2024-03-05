import sys
from unittest.mock import patch

import pytest

import runez
from runez.colors import terminal
from runez.conftest import patch_env


def test_colors():
    dim = runez.color.style.dim
    assert runez.color.cast_style(dim) is dim
    assert runez.color.cast_style(runez.dim) is runez.dim
    assert runez.color.cast_style("dim") is dim
    assert runez.color.cast_color(dim) is dim
    assert runez.color.cast_color("dim") is dim
    assert runez.color.cast_color("blue") is runez.color.fg.blue

    msg1 = dim("hi")
    msg2 = runez.colored("hi", "dim")
    assert msg1 == msg2

    with pytest.raises(ValueError, match="Unknown color"):
        runez.color.cast_style("foo")

    assert not runez.color.is_coloring()
    with runez.ActivateColors(terminal.Ansi16Backend):
        # Check that backend can be passed as class (flavor auto-determined in that case)
        assert runez.color.is_coloring()
        assert "ansi16" in runez.color.backend.name

        msg1 = runez.dim("hi")
        msg2 = runez.colored("hi", "dim")
        assert msg1 == msg2

    assert not runez.color.is_coloring()
    with runez.ActivateColors(terminal.Ansi16Backend(flavor="neutral")):
        assert runez.color.is_coloring()
        assert runez.red(None) == "\x1b[31mNone\x1b[39m"
        assert runez.blue("") == ""
        assert runez.plain("hello") == "hello"
        assert runez.yellow("hello") == "\x1b[33mhello\x1b[39m"
        assert runez.yellow("hello", size=4) == "\x1b[33mh...\x1b[39m"
        assert runez.bold(1) == "\x1b[1m1\x1b[22m"

        assert runez.color.bg.get(None) is None
        assert runez.color.bg.get("blue") is runez.color.bg.blue

        assert runez.dim("") == ""
        assert runez.dim("hello", size=4) == "\x1b[2mh...\x1b[22m"

        # Verify unicode char 'μ' from represented_duration() works
        assert "foo: %s" % runez.dim(runez.represented_duration(0.010049)) == "foo: \x1b[2m10 ms 49 μs\x1b[22m"
        assert "foo: %s" % runez.blue(runez.represented_duration(0.010049)) == "foo: \x1b[34m10 ms 49 μs\x1b[39m"

    assert not runez.color.is_coloring()
    assert runez.black("") == ""
    assert runez.blue("") == ""
    assert runez.brown("") == ""
    assert runez.gray("") == ""
    assert runez.green("") == ""
    assert runez.orange("") == ""
    assert runez.plain("hello") == "hello"
    assert runez.purple("") == ""
    assert runez.red(None) == "None"
    assert runez.teal("") == ""
    assert runez.white("") == ""
    assert runez.yellow("hello") == "hello"
    assert runez.blink("hello") == "hello"
    assert runez.bold(1) == "1"
    assert runez.dim("") == ""
    assert runez.invert("") == ""
    assert runez.italic("") == ""
    assert runez.strikethrough("") == ""
    assert runez.underline("") == ""

    assert str(runez.color.fg.black) == "black"


def check_flavor(monkeypatch, expected, term=None, colorfgbg=None):
    # Verify defaults
    assert not runez.color.is_coloring()
    assert runez.color.backend.name == "plain"

    patch_env(monkeypatch, term=term, colorfgbg=colorfgbg)
    assert not runez.color.is_coloring()
    with runez.ActivateColors():
        assert runez.color.is_coloring()
        assert runez.color.backend.name == expected


def test_default(monkeypatch):
    # Default: not coloring, neutral flavor
    assert not runez.color.is_coloring()
    assert runez.color.backend.name == "plain"
    assert runez.blue("hello") == "hello"

    with patch("runez.DEV.current_test", return_value=None):  # simulate not running in test
        check_flavor(monkeypatch, "ansi16 neutral")
        check_flavor(monkeypatch, "ansi16 light", colorfgbg="15;0")
        check_flavor(monkeypatch, "ansi16 dark", colorfgbg="15;9")

        check_flavor(monkeypatch, "ansi256 neutral", term="xterm-256color")
        check_flavor(monkeypatch, "ansi256 light", term="xterm-256color", colorfgbg="15;0")
        check_flavor(monkeypatch, "ansi256 dark", term="xterm-256color", colorfgbg="15;9")

        check_flavor(monkeypatch, "truecolor neutral", term="truecolor")
        check_flavor(monkeypatch, "truecolor light", term="truecolor", colorfgbg="15;0")
        check_flavor(monkeypatch, "truecolor dark", term="truecolor", colorfgbg="15;9")


def check_usable(monkeypatch, names, colorterm=None, term=None):
    patch_env(monkeypatch, colorterm=colorterm, term=term)
    usable = terminal.usable_backends()
    usable_names = ", ".join(x.name for x in usable)
    assert names == usable_names


def test_flavor(monkeypatch):
    assert terminal.detect_flavor(None) == "neutral"
    assert terminal.detect_flavor("") == "neutral"
    assert terminal.detect_flavor("foo") == "neutral"
    assert terminal.detect_flavor("15") == "neutral"
    assert terminal.detect_flavor("15;5;0") == "neutral"
    assert terminal.detect_flavor("0;15") == "dark"
    assert terminal.detect_flavor("15;5") == "light"
    assert terminal.detect_flavor("15;6") == "light"
    assert terminal.detect_flavor("15;7") == "dark"

    check_usable(monkeypatch, "truecolor neutral, ansi256 neutral, ansi16 neutral", colorterm="truecolor", term="xterm-256color")
    check_usable(monkeypatch, "ansi256 neutral, ansi16 neutral", term="xterm-256color")
    check_usable(monkeypatch, "ansi16 neutral", term="xterm")
    check_usable(monkeypatch, "ansi16 neutral", term="foo")
    check_usable(monkeypatch, "ansi16 neutral")


def test_no_color():
    r = runez.run(sys.executable, "-mrunez", "colors", "--no-color", fatal=False)
    assert r.succeeded
    assert "Backend: plain" in r.output
    assert r.error == ""


def test_show_colors(cli):
    cli.run("colors")
    assert cli.succeeded
    assert "Backend: plain" in cli.logged.stdout

    cli.run("colors --color --bg foo,yellow --flavor light")
    assert cli.succeeded
    assert "Backend: ansi16 light" in cli.logged.stdout
    assert "Unknown bg color 'foo'" in cli.logged.stdout


def test_uncolored():
    # Verify incomplete codes are removed too
    assert runez.uncolored("foo-\x1b[0m z") == "foo- z"
    assert runez.uncolored("foo-\x1b") == "foo-"
    assert runez.uncolored("foo-\x1b[") == "foo-"

    with runez.ActivateColors(terminal.TrueColorBackend(flavor="neutral")):
        assert runez.uncolored(runez.red("foo")) == "foo"
        assert runez.color.adjusted_size("foo", 5) == 5
        assert runez.color.adjusted_size(runez.red("foo"), 5) == 25

    with runez.ActivateColors(terminal.Ansi16Backend(flavor="neutral")):
        assert runez.uncolored(None) == "None"
        assert runez.uncolored(" ") == " "
        assert runez.uncolored("foo") == "foo"
        assert runez.uncolored(runez.red("foo")) == "foo"
        assert runez.uncolored("%s - %s" % (runez.red("foo"), runez.yellow("bar"))) == "foo - bar"

        assert runez.color.adjusted_size("foo", 5) == 5
        assert runez.color.adjusted_size(runez.red("foo"), 5) == 15
