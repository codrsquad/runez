from mock import patch

import runez
from runez.colors import terminal


def test_colors():
    runez.activate_colors(terminal.Ansi16Backend)
    assert terminal.PlainBackend.flavor == "neutral"
    assert runez.is_coloring()
    assert runez.red(None) == "\x1b[31mNone\x1b[39m"
    assert runez.blue("") == ""
    assert runez.plain("hello") == "hello"
    assert runez.yellow("hello") == "\x1b[33mhello\x1b[39m"
    assert runez.yellow("hello", shorten=4) == "\x1b[33mh...\x1b[39m"
    assert runez.bold(1) == "\x1b[1m1\x1b[22m"

    assert runez.dim("") == ""
    assert runez.dim("hello", shorten=4) == "\x1b[2mh...\x1b[22m"

    runez.activate_colors(False)
    assert not runez.is_coloring()
    assert runez.red(None) == "None"
    assert runez.blue("") == ""
    assert runez.plain("hello") == "hello"
    assert runez.blue("hello") == "hello"
    assert runez.yellow("hello") == "hello"
    assert runez.bold(1) == "1"

    assert str(runez.black) == "black"
    assert str(runez.dim) == "dim"


def test_default():
    # Default: not coloring, neutral flavor
    assert not runez.is_coloring()
    assert terminal.BACKEND is terminal.PlainBackend
    assert terminal.PlainBackend.flavor == "neutral"
    assert runez.blue("hello") == "hello"

    with patch("runez.colors.terminal.is_tty", return_value=True):
        # Simulate auto-detection of light flavor, with Ansi16Backend
        runez.activate_colors(None, env={"COLORFGBG": "15;0"})
        assert terminal.PlainBackend.flavor == "light"
        assert terminal.BACKEND is terminal.Ansi16Backend

        # Simulate auto-detection of dark flavor, with Ansi256Backend
        runez.activate_colors(None, env={"COLORFGBG": "15;9", "TERM": "xterm-256color"})
        assert terminal.PlainBackend.flavor == "dark"
        assert terminal.BACKEND is terminal.Ansi256Backend

        # Simulate auto-detection of neutral flavor, with TrueColorBackend
        runez.activate_colors(None, env={"COLORTERM": "truecolor"})
        assert terminal.PlainBackend.flavor == "neutral"
        assert terminal.BACKEND is terminal.TrueColorBackend

    # Restore defaults
    runez.activate_colors(None, flavor="neutral")
    assert not runez.is_coloring()
    assert terminal.BACKEND is terminal.PlainBackend
    assert terminal.PlainBackend.flavor == "neutral"
    assert runez.blue("hello") == "hello"


def test_flavor():
    assert not runez.is_coloring()

    assert terminal.detect_flavor(None) == "neutral"
    assert terminal.detect_flavor("") == "neutral"
    assert terminal.detect_flavor("foo") == "neutral"
    assert terminal.detect_flavor("15") == "neutral"
    assert terminal.detect_flavor("15;5;0") == "neutral"
    assert terminal.detect_flavor("0;15") == "dark"
    assert terminal.detect_flavor("15;5") == "light"
    assert terminal.detect_flavor("15;6") == "light"
    assert terminal.detect_flavor("15;7") == "dark"

    assert terminal.usable_backends({"COLORTERM": "truecolor", "TERM": "xterm-256color"}) == [
        terminal.TrueColorBackend,
        terminal.Ansi256Backend,
        terminal.Ansi16Backend,
        terminal.PlainBackend,
    ]
    assert terminal.usable_backends({"TERM": "xterm-256color"}) == [
        terminal.Ansi256Backend,
        terminal.Ansi16Backend,
        terminal.PlainBackend,
    ]
    assert terminal.usable_backends({"TERM": "xterm"}) == [terminal.Ansi16Backend, terminal.PlainBackend]
    assert terminal.usable_backends({"TERM": "foo"}) == [terminal.Ansi16Backend, terminal.PlainBackend]
    assert terminal.usable_backends({}) == [terminal.PlainBackend]

    assert terminal.detect_backend(True, {"COLORTERM": "truecolor"}) is terminal.TrueColorBackend
    assert terminal.detect_backend(True, {"TERM": "xterm-256color"}) is terminal.Ansi256Backend
    assert terminal.detect_backend(True, {"TERM": "xterm"}) is terminal.Ansi16Backend
    assert terminal.detect_backend(True, {}) is terminal.PlainBackend


def test_uncolored():
    runez.activate_colors(terminal.TrueColorBackend)
    assert runez.uncolored(runez.red("foo")) == "foo"
    assert runez.color_adjusted_size("foo", 5) == 5
    assert runez.color_adjusted_size(runez.red("foo"), 5) == 25

    runez.activate_colors(terminal.Ansi16Backend)
    assert runez.is_coloring()
    assert runez.uncolored(None) == ""
    assert runez.uncolored(" ") == " "
    assert runez.uncolored("foo") == "foo"
    assert runez.uncolored(runez.red("foo")) == "foo"
    assert runez.uncolored("%s - %s" % (runez.red("foo"), runez.yellow("bar"))) == "foo - bar"

    assert runez.color_adjusted_size("foo", 5) == 5
    assert runez.color_adjusted_size(runez.red("foo"), 5) == 15

    runez.activate_colors(False)
    assert not runez.is_coloring()
