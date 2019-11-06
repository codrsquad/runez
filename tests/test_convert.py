import datetime
import math

import runez


def test_capped():
    assert runez.capped(123, minimum=200) == 200
    assert runez.capped(123, maximum=100) == 100
    assert runez.capped(123, minimum=100, maximum=200) == 123
    assert runez.capped(123, minimum=100, maximum=110) == 110


def test_shortened():
    assert runez.shortened(None) == "None"
    assert runez.shortened("") == ""
    assert runez.shortened(5) == "5"
    assert runez.shortened(" some text ") == "some text"
    assert runez.shortened(" \n  some \n  long text", size=9) == "some l..."
    assert runez.shortened(" \n  some \n  long text", size=8) == "some ..."
    assert runez.shortened(" a \n\n  \n  b ") == "a b"

    assert runez.shortened([1, "b"]) == "[1, b]"
    assert runez.shortened((1, {"b": ["c", {"d", "e"}]})) == "(1, {b: [c, {d, e}]})"

    complex = {"a \n b": [1, None, "foo \n ,", {"a2": runez.abort, "c": runez.Anchored}], None: datetime.date(2019, 1, 1)}
    assert runez.shortened(complex) == "{None: 2019-01-01, a b: [1, None, foo ,, {a2: function 'abort', c: class runez.convert.Anchored}]}"
    assert runez.shortened(complex, size=32) == "{None: 2019-01-01, a b: [1, N..."


def test_flattened():
    assert runez.flattened(None) == [None]
    assert runez.flattened([None]) == [None]
    assert runez.flattened(None, split=runez.SANITIZED) == []
    assert runez.flattened(None, split=runez.SHELL) == []
    assert runez.flattened(None, split=runez.UNIQUE) == [None]

    assert runez.flattened(["-a", [None, "b", runez.UNSET], runez.UNSET]) == ["-a", None, "b", runez.UNSET, runez.UNSET]
    assert runez.flattened(["-a", [None, "b", runez.UNSET], runez.UNSET], split=runez.UNIQUE) == ["-a", None, "b", runez.UNSET]
    assert runez.flattened(["-a", [None, "b", runez.UNSET], runez.UNSET], split=runez.SANITIZED) == ["-a", "b"]
    assert runez.flattened(["-a", [None, "b", runez.UNSET], runez.UNSET], split=runez.SHELL) == ["b"]
    assert runez.flattened(["-a", [runez.UNSET, "b", runez.UNSET], runez.UNSET], split=runez.SHELL) == ["b"]

    assert runez.flattened(["a b"]) == ["a b"]
    assert runez.flattened([["a b"]]) == ["a b"]

    assert runez.flattened(["-r", None, "foo"]) == ["-r", None, "foo"]
    assert runez.flattened(["-r", None, "foo"], split=runez.SANITIZED) == ["-r", "foo"]
    assert runez.flattened(["-r", None, "foo"], split=runez.SHELL) == ["foo"]
    assert runez.flattened(["-r", None, "foo"], split=runez.UNIQUE) == ["-r", None, "foo"]
    assert runez.flattened(["-r", None, "foo"], split=runez.SANITIZED | runez.UNIQUE) == ["-r", "foo"]

    # Sanitized
    assert runez.flattened(("a", None, ["b", None]), split=runez.UNIQUE) == ["a", None, "b"]
    assert runez.flattened(("a", None, ["b", None]), split=runez.SANITIZED | runez.UNIQUE) == ["a", "b"]

    # Shell cases
    assert runez.flattened([None, "a", "-f", "b", "c", None], split=runez.SHELL) == ["a", "-f", "b", "c"]
    assert runez.flattened(["a", "-f", "b", "c"], split=runez.SHELL) == ["a", "-f", "b", "c"]
    assert runez.flattened([None, "-f", "b", None], split=runez.SHELL) == ["-f", "b"]
    assert runez.flattened(["a", "-f", None, "c"], split=runez.SHELL) == ["a", "c"]

    # Splitting on separator
    assert runez.flattened("a b b") == ["a b b"]
    assert runez.flattened("a b b", split=" ") == ["a", "b", "b"]
    assert runez.flattened("a b b", split=(" ", runez.UNIQUE)) == ["a", "b"]
    assert runez.flattened("a b b", split=(None, runez.UNIQUE)) == ["a b b"]
    assert runez.flattened("a b b", split=("", runez.UNIQUE)) == ["a b b"]
    assert runez.flattened("a b b", split=("+", runez.UNIQUE)) == ["a b b"]

    # Unique
    assert runez.flattened(["a", ["a", ["b", ["b", "c"]]]]) == ["a", "a", "b", "b", "c"]
    assert runez.flattened(["a", ["a", ["b", ["b", "c"]]]], split=runez.UNIQUE) == ["a", "b", "c"]

    assert runez.flattened(["a b", None, ["a b c"], "a"], split=runez.UNIQUE) == ["a b", None, "a b c", "a"]
    assert runez.flattened(["a b", None, ["a b c"], "a"], split=(" ", runez.UNIQUE)) == ["a", "b", None, "c"]
    assert runez.flattened(["a b", None, ["a b c"], "a"], split=(" ", runez.SANITIZED | runez.UNIQUE)) == ["a", "b", "c"]


def test_representation():
    assert runez.represented_args(None) == ""
    assert runez.represented_args([]) == ""
    assert runez.represented_args([0, 1, 2], separator="+") == "0+1+2"
    assert runez.represented_args(["foo", {}, 0, [1, 2], {3: 4}, 5]) == 'foo {} 0 "[1, 2]" "{3: 4}" 5'

    assert runez.represented_bytesize(20) == "20 B"
    assert runez.represented_bytesize(20, unit="") == "20"
    assert runez.represented_bytesize(9000) == "8.8 KB"
    assert runez.represented_bytesize(20000) == "20 KB"
    assert runez.represented_bytesize(20000, unit="") == "20 K"
    assert runez.represented_bytesize(20000000) == "19 MB"
    assert runez.represented_bytesize(20000000000) == "19 GB"
    assert runez.represented_bytesize(20000000000000) == "18 TB"
    assert runez.represented_bytesize(20000000000000000) == "18 PB"
    assert runez.represented_bytesize(20000000000000000000) == "17764 PB"


def test_formatted():
    class Record(object):
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


def test_to_float():
    assert runez.to_float(None) is None
    assert runez.to_float("foo") is None
    assert runez.to_float("-.if") is None
    assert runez.to_float(["foo"], lenient=True) is None

    assert runez.to_float("0") == 0.0
    assert runez.to_float("-5") == -5.0
    assert runez.to_float("15") == 15.0
    assert runez.to_float("+135.057E+4") == 1350570.0
    assert runez.to_float("-135000.5e-3") == -135.0005

    assert math.isnan(runez.to_float("nan"))
    assert math.isinf(runez.to_float("inf"))
    assert math.isinf(runez.to_float(".inf"))
    assert math.isinf(runez.to_float("-.inf"))

    assert isinstance(runez.to_float("15"), float)
    assert isinstance(runez.to_float("15", lenient=True), int)


def test_to_int():
    assert runez.to_int(None) is None
    assert runez.to_int("foo") is None
    assert runez.to_int(["foo"]) is None
    assert runez.to_int("5.0") is None
    assert runez.to_int("_5_") is None
    assert runez.to_int("_5") is None
    assert runez.to_int("5_") is None
    assert runez.to_int("1__5") is None
    assert runez.to_int("1_ 5") is None

    assert runez.to_int("0") == 0
    assert runez.to_int("-5") == -5
    assert runez.to_int("15") == 15

    assert runez.to_int("0o10") == 8
    assert runez.to_int("0x10") == 16
    assert runez.to_int("0o1_0") == 8
    assert runez.to_int("0x1_0") == 16

    assert runez.to_int(" 1_500 ") == 1500
    assert runez.to_int("1_5 ") == 15
    assert runez.to_int("1_500_001 ") == 1500001


def test_wordification():
    assert runez.get_words(None) == []
    assert runez.get_words("a") == ["a"]
    assert runez.get_words("hi_There-you", normalize=str.lower) == ["hi", "there", "you"]

    assert runez.wordified(None) is None
    assert runez.wordified("Hello_There", separator="-") == "Hello-There"

    assert runez.snakified("my-key") == "MY_KEY"
    assert runez.camel_cased("my-key") == "MyKey"
    assert runez.entitled("my-key") == "My key"

    assert runez.affixed(None) is None
    assert runez.affixed("") == ""
    assert runez.affixed("", prefix="my-") == "my-"

    assert runez.affixed("my-key") == "my-key"
    assert runez.affixed("my-key", prefix="my-") == "my-key"
    assert runez.affixed("key", prefix="my-") == "my-key"
    assert runez.affixed("my-key", prefix="X_", normalize=runez.snakified) == "X_MY_KEY"
