import runez


def test_shortened():
    assert runez.shortened("") == ""
    assert runez.shortened(" some text ") == "some text"
    assert runez.shortened("some long text", size=9) == "some l..."
    assert runez.shortened("some long text", size=8) == "some..."


def test_flattened():
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


def test_formatted():
    class Record:
        basename = "my-name"
        filename = "{basename}.txt"

    assert runez.formatted("{filename}", Record) == "my-name.txt"
    assert runez.formatted("{basename}/{filename}", Record) == "my-name/my-name.txt"

    assert runez.formatted("") == ""
    assert runez.formatted("", Record) == ""
    assert runez.formatted("{not_there}", Record) is None
    assert runez.formatted("{not_there}", Record, name="susan") is None
    assert runez.formatted("{not_there}", Record, not_there="psyched!") == "psyched!"
    assert runez.formatted("{not_there}", Record, strict=False) == "{not_there}"

    deep = dict(a="a", b="b", aa="{a}", bb="{b}", ab="{aa}{bb}", ba="{bb}{aa}", abba="{ab}{ba}", deep="{abba}")
    assert runez.formatted("{deep}", deep, max_depth=-1) == "{deep}"
    assert runez.formatted("{deep}", deep, max_depth=0) == "{deep}"
    assert runez.formatted("{deep}", deep, max_depth=1) == "{abba}"
    assert runez.formatted("{deep}", deep, max_depth=2) == "{ab}{ba}"
    assert runez.formatted("{deep}", deep, max_depth=3) == "{aa}{bb}{bb}{aa}"
    assert runez.formatted("{deep}", deep, max_depth=4) == "{a}{b}{b}{a}"
    assert runez.formatted("{deep}", deep, max_depth=5) == "abba"
    assert runez.formatted("{deep}", deep, max_depth=6) == "abba"

    cycle = dict(a="{b}", b="{a}")
    assert runez.formatted("{a}", cycle, max_depth=0) == "{a}"
    assert runez.formatted("{a}", cycle, max_depth=1) == "{b}"
    assert runez.formatted("{a}", cycle, max_depth=2) == "{a}"
    assert runez.formatted("{a}", cycle, max_depth=3) == "{b}"

    assert runez.formatted("{filename}") == "{filename}"


def test_quoted():
    assert runez.quoted(None) is None
    assert runez.quoted("") == ""
    assert runez.quoted(" ") == '" "'
    assert runez.quoted('"') == '"'

    assert runez.quoted("a b") == '"a b"'
    assert runez.quoted('a="b"') == 'a="b"'
    assert runez.quoted('foo a="b"') == """'foo a="b"'"""


def test_to_int():
    # bogus
    assert runez.to_int(None) is None
    assert runez.to_int(None, default=0) == 0
    assert runez.to_int("foo", default=1) == 1
    assert runez.to_int("6.1", default=2) == 2

    # valid
    assert runez.to_int(5, default=3) == 5
    assert runez.to_int("5", default=3) == 5
