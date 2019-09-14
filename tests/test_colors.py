import runez


def test_colors():
    runez.activate_colors(True)
    assert runez.red(None) == "\x1b[91mNone\x1b[0m"
    assert runez.blue("") == ""
    assert runez.yellow("hello") == "\x1b[93mhello\x1b[0m"
    assert runez.bold(1) == "\x1b[1m1\x1b[0m"

    runez.activate_colors(False)
    assert runez.red(None) == "None"
    assert runez.blue("hello") == "hello"
    assert runez.yellow("hello") == "hello"
    assert runez.bold(1) == "1"
