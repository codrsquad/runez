import runez


def test_colors():
    runez.colors.terminal.PlainBackend.flavor = "neutral"
    runez.activate_colors(runez.colors.terminal.Ansi16Backend)
    assert runez.red(None) == "\x1b[31mNone\x1b[39m"
    assert runez.blue("") == ""
    assert runez.plain("hello") == "hello"
    assert runez.yellow("hello") == "\x1b[33mhello\x1b[39m"
    assert runez.yellow("hello", shorten=4) == "\x1b[33mh...\x1b[39m"
    assert runez.bold(1) == "\x1b[1m1\x1b[22m"

    assert runez.dim("") == ""
    assert runez.dim("hello", shorten=4) == "\x1b[2mh...\x1b[22m"

    runez.activate_colors(False)
    assert runez.red(None) == "None"
    assert runez.blue("hello") == "hello"
    assert runez.plain("hello") == "hello"
    assert runez.yellow("hello") == "hello"
    assert runez.bold(1) == "1"

    assert str(runez.black) == "black"
    assert str(runez.dim) == "dim"
    assert str(runez.black.ansi16) == "\x1b[90m{}\x1b[39m - \x1b[30m{}\x1b[39m"


def test_flavor():
    assert runez.colors.terminal.detect_flavor("") == "neutral"
    assert runez.colors.terminal.detect_flavor("foo") == "neutral"
    assert runez.colors.terminal.detect_flavor("15") == "dark"
    assert runez.colors.terminal.detect_flavor("5") == "light"
    assert runez.colors.terminal.detect_flavor("0;15") == "dark"
    assert runez.colors.terminal.detect_flavor("15;5") == "light"
    assert runez.colors.terminal.detect_backend(True, {"COLORTERM": "truecolor"}) is runez.colors.terminal.TrueColorBackend
    assert runez.colors.terminal.detect_backend(True, {"TERM": "xterm-256color"}) is runez.colors.terminal.Ansi256Backend
    assert runez.colors.terminal.detect_backend(True, {}) is runez.colors.terminal.Ansi16Backend


def test_uncolored():
    runez.activate_colors(runez.colors.terminal.Ansi16Backend)
    assert runez.uncolored(None) == ""
    assert runez.uncolored(" ") == " "
    assert runez.uncolored("foo") == "foo"
    assert runez.uncolored(runez.red("foo")) == "foo"
    assert runez.uncolored("%s - %s" % (runez.red("foo"), runez.yellow("bar"))) == "foo - bar"

    assert runez.color_adjusted_size("foo", 5) == 5
    assert runez.color_adjusted_size(runez.red("foo"), 5) == 15
    runez.activate_colors(False)
