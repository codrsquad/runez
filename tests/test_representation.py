from mock import patch

import runez


def test_shortening():
    assert runez.shortened("") == ""
    assert runez.shortened(" some text ") == "some text"
    assert runez.shortened("some long text", size=9) == "some l..."
    assert runez.shortened("some long text", size=8) == "some..."


def test_flattening():
    assert runez.flattened(None) == []
    assert runez.flattened("") == []

    assert runez.flattened(["-r", None, "foo"]) == ["-r", "foo"]
    assert runez.flattened(["-r", None, "foo"], unique=False) == ["foo"]

    assert runez.flattened(["foo", "--something", (None, "bar")], unique=False) == ["foo", "bar"]

    assert runez.flattened("a b") == ["a b"]
    assert runez.flattened("a b", separator=" ") == ["a", "b"]

    assert runez.flattened(["a b"]) == ["a b"]
    assert runez.flattened([["a b"]]) == ["a b"]

    assert runez.flattened(["a", ["a", "b"]]) == ["a", "b"]
    assert runez.flattened(["a", ["a", "b"]], unique=False) == ["a", "a", "b"]

    assert runez.flattened(["a b", ["a b c"]]) == ["a b", "a b c"]
    assert runez.flattened(["a b", ["a b c"]], separator=" ") == ["a", "b", "c"]
    assert runez.flattened(["a b", ["a b c"], "a"], separator=" ", unique=False) == ["a", "b", "a", "b", "c", "a"]

    assert runez.flattened(["a b", [None, "-i", None]]) == ["a b", "-i"]
    assert runez.flattened(["a b", [None, "-i", None]], unique=False) == ["a b"]

    assert runez.represented_args(None) == ""
    assert runez.represented_args([]) == ""
    assert runez.represented_args([1, 2], separator="+") == "1+2"


def test_quoting():
    assert runez.quoted(None) is None
    assert runez.quoted("") == ""
    assert runez.quoted(" ") == '" "'
    assert runez.quoted('"') == '"'

    assert runez.quoted("a b") == '"a b"'
    assert runez.quoted('a="b"') == 'a="b"'
    assert runez.quoted('foo a="b"') == """'foo a="b"'"""


def test_conversion():
    # bogus
    assert runez.to_int(None) is None
    assert runez.to_int(None, default=0) == 0
    assert runez.to_int("foo", default=1) == 1
    assert runez.to_int("6.1", default=2) == 2

    # valid
    assert runez.to_int(5, default=3) == 5
    assert runez.to_int("5", default=3) == 5


def test_version():
    v1 = runez.get_version(runez)
    v2 = runez.get_version(runez.__name__)
    assert v1 == v2


def test_failed_version(logged):
    with patch("pkg_resources.get_distribution", side_effect=Exception("testing")):
        assert runez.get_version(runez) == "0.0.0"
    assert "Can't determine version for runez" in logged
