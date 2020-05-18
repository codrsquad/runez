import os
import sys

import pytest
from mock import patch

import runez
from runez.colors import terminal


def test_colors():
    dim = runez.color.style.dim
    assert runez.colors.cast_style(dim) is dim
    assert runez.colors.cast_style(runez.dim) is dim
    assert runez.colors.cast_style("dim") is dim

    with pytest.raises(ValueError):
        runez.colors.cast_style("foo")

    assert not runez.is_coloring()
    with runez.ActivateColors(terminal.Ansi16Backend):
        # Check that backend can be passed as class (flavor auto-determined in that case)
        assert runez.is_coloring()
        assert "ansi16" in runez.color.backend.name

    assert not runez.is_coloring()
    with runez.ActivateColors(terminal.Ansi16Backend(flavor="neutral")):
        assert runez.is_coloring()
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

    assert not runez.is_coloring()
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


def check_flavor(expected, term=None, fgbg=None):
    env = {}
    if term:
        env["TERM"] = term

    if fgbg:
        env["COLORFGBG"] = fgbg

    assert not runez.is_coloring()
    with patch.dict(os.environ, env, clear=True):
        with runez.ActivateColors():
            assert runez.is_coloring()
            assert runez.color.backend.name == expected

    # Verify testing defaults were restored
    assert not runez.is_coloring()
    assert runez.color.backend.name == "plain"


@patch("runez.colors.current_test", return_value=None)
def test_default(*_):
    # Default: not coloring, neutral flavor
    assert not runez.is_coloring()
    assert runez.color.backend.name == "plain"
    assert runez.blue("hello") == "hello"

    check_flavor("ansi16 neutral")
    check_flavor("ansi16 light", fgbg="15;0")
    check_flavor("ansi16 dark", fgbg="15;9")

    check_flavor("ansi256 neutral", term="xterm-256color")
    check_flavor("ansi256 light", term="xterm-256color", fgbg="15;0")
    check_flavor("ansi256 dark", term="xterm-256color", fgbg="15;9")

    check_flavor("truecolor neutral", term="truecolor")
    check_flavor("truecolor light", term="truecolor", fgbg="15;0")
    check_flavor("truecolor dark", term="truecolor", fgbg="15;9")


def check_usable(names, env):
    with patch.dict(os.environ, env, clear=True):
        usable = terminal.usable_backends()
        usable_names = ", ".join(x.name for x in usable)
        assert names == usable_names


def test_flavor():
    assert terminal.detect_flavor(None) == "neutral"
    assert terminal.detect_flavor("") == "neutral"
    assert terminal.detect_flavor("foo") == "neutral"
    assert terminal.detect_flavor("15") == "neutral"
    assert terminal.detect_flavor("15;5;0") == "neutral"
    assert terminal.detect_flavor("0;15") == "dark"
    assert terminal.detect_flavor("15;5") == "light"
    assert terminal.detect_flavor("15;6") == "light"
    assert terminal.detect_flavor("15;7") == "dark"

    check_usable("truecolor neutral, ansi256 neutral, ansi16 neutral", {"COLORTERM": "truecolor", "TERM": "xterm-256color"})
    check_usable("ansi256 neutral, ansi16 neutral", {"TERM": "xterm-256color"})
    check_usable("ansi16 neutral", {"TERM": "xterm"})
    check_usable("ansi16 neutral", {"TERM": "foo"})
    check_usable("ansi16 neutral", {})


def test_show_colors(cli):
    cli.run("colors")
    assert cli.succeeded
    assert "Backend: plain" in cli.logged.stdout

    cli.run("colors --color --bg foo,yellow --flavor light")
    assert cli.succeeded
    assert "Backend: ansi16 light" in cli.logged.stdout
    assert "Unknown bg color 'foo'" in cli.logged.stdout


def test_no_color():
    output = runez.run(sys.executable, "-mrunez", "colors", "--no-color")
    assert "Backend: plain" in output


def test_uncolored():
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
