import runez


def test_flattening():
    assert runez.flattened(["-r", None, "foo"]) == ["-r", "foo"]
    assert runez.flattened(["-r", None, "foo"], unique=False) == ["foo"]

    assert runez.flattened(["foo", "--something", (None, "bar")], unique=False) == ["foo", "bar"]

    assert runez.flattened("foo bar") == ["foo bar"]
    assert runez.flattened("foo bar", separator=" ") == ["foo", "bar"]

    assert runez.represented_args(None) == ""
    assert runez.represented_args([]) == ""
    assert runez.represented_args([1, 2], separator="+") == "1+2"


def test_quoting():
    assert runez.quoted(None) is None
    assert runez.quoted("") == ""
    assert runez.quoted(" ") == '" "'
    assert runez.quoted("foo bar") == '"foo bar"'
    assert runez.quoted('a="b"') == 'a="b"'
    assert runez.quoted('foo a="b"') == """'foo a="b"'"""


def test_conversion():
    # bogus
    assert runez.to_int(None) is None
    assert runez.to_int(None, default=0) == 0
    assert runez.to_int("foo", default=1) == 1
    assert runez.to_int("6.1", default=2) == 2

    # valid
    assert runez.to_int("5", default=1) == 5
