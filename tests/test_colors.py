import runez


def test_colors():
    runez.activate_colors(True)
    assert runez.red(None) == "\x1b[91mNone\x1b[0m"
    assert runez.blue("") == ""
    assert runez.plain("hello") == "hello"
    assert runez.yellow("hello") == "\x1b[93mhello\x1b[0m"
    assert runez.yellow("hello", shorten=4) == "\x1b[93mh...\x1b[0m"
    assert runez.bold(1) == "\x1b[1m1\x1b[0m"

    runez.activate_colors(False)
    assert runez.red(None) == "None"
    assert runez.blue("hello") == "hello"
    assert runez.plain("hello") == "hello"
    assert runez.yellow("hello") == "hello"
    assert runez.bold(1) == "1"


def test_uncolored():
    runez.activate_colors(True)
    assert runez.uncolored(None) == ""
    assert runez.uncolored(" ") == " "
    assert runez.uncolored("foo") == "foo"
    assert runez.uncolored(runez.red("foo")) == "foo"
    assert runez.uncolored("%s - %s" % (runez.red("foo"), runez.yellow("bar"))) == "foo - bar"

    assert runez.color_adjusted_size("foo", 5) == 5
    assert runez.color_adjusted_size(runez.red("foo"), 5) == 14
    runez.activate_colors(False)
