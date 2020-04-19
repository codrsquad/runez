import datetime
import math
import os

import runez


def test_anchored(temp_folder):
    assert runez.resolved_path(None) is None
    assert runez.resolved_path("some-file") == os.path.join(temp_folder, "some-file")
    assert runez.resolved_path("some-file", base="bar") == os.path.join(temp_folder, "bar", "some-file")

    assert runez.short(None) is None
    assert runez.short("") == ""
    assert runez.short(os.path.join(temp_folder, "some-file")) == "some-file"

    assert runez.represented_args(["ls", os.path.join(temp_folder, "some-file") + " bar", "-a"]) == 'ls "some-file bar" -a'

    user_path = runez.resolved_path("~/some-folder/bar")
    current_path = runez.resolved_path("./some-folder/bar")

    assert user_path != "~/some-folder/bar"
    assert runez.short(user_path) == "~/some-folder/bar"
    assert runez.short(current_path) == "some-folder/bar"

    with runez.Anchored(os.getcwd()):
        assert runez.short(current_path) == os.path.join("some-folder", "bar")


def test_boolean():
    assert runez.to_boolean(None) is False
    assert runez.to_boolean("") is False
    assert runez.to_boolean("t") is False
    assert runez.to_boolean("0") is False
    assert runez.to_boolean("0.0") is False
    assert runez.to_boolean("1.0.0") is False

    assert runez.to_boolean("True") is True
    assert runez.to_boolean("Y") is True
    assert runez.to_boolean("yes") is True
    assert runez.to_boolean("On") is True
    assert runez.to_boolean("5") is True
    assert runez.to_boolean("0.1") is True
    assert runez.to_boolean("16.1") is True


def test_bytesize():
    assert runez.to_bytesize(10) == 10
    assert runez.to_bytesize(None) is None
    assert runez.to_bytesize("") is None
    assert runez.to_bytesize("1a") is None

    assert runez.to_bytesize("10") == 10
    assert runez.to_bytesize("10.4") == 10
    assert runez.to_bytesize("10.6") == 11
    assert runez.to_bytesize(10, default_unit="k", base=1024) == 10 * 1024
    assert runez.to_bytesize(10, default_unit="k", base=1000) == 10000
    assert runez.to_bytesize("10", default_unit="k", base=1000) == 10000
    assert runez.to_bytesize("10m", default_unit="k", base=1000) == 10000000
    assert runez.to_bytesize("10.m", default_unit="k", base=1000) == 10000000
    assert runez.to_bytesize("10.4m", default_unit="k", base=1000) == 10400000

    assert runez.to_bytesize(10, default_unit="a", base=1000) is None  # Bogus default_unit


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

    assert runez.shortened(" some  text ", size=32) == "some text"
    assert runez.shortened(" some  text ", size=7) == "some..."
    assert runez.shortened(" some  text ", size=0) == "some text"


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


def test_plural():
    assert runez.plural(2, "match") == "2 matches"
    assert runez.plural(0, "dish") == "0 dishes"
    assert runez.plural(5, "goth") == "5 goths"
    assert runez.plural(7, "diff") == "7 diffs"

    assert runez.plural(1, "penny") == "1 penny"
    assert runez.plural(2, "penny") == "2 pennies"

    assert runez.plural([], "record") == "0 records"
    assert runez.plural([""], "record") == "1 record"

    assert runez.plural(1, "person") == "1 person"
    assert runez.plural(2, "person") == "2 people"

    assert runez.plural(2, "man") == "2 men"
    assert runez.plural(2, "woman") == "2 women"
    assert runez.plural(2, "status") == "2 statuses"


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
    assert runez.get_identifiers(None) == []
    assert runez.get_identifiers("") == []
    assert runez.get_identifiers("a_b1") == ["a_b1"]
    assert runez.get_identifiers("hi_There-you") == ["hi_There", "you"]
    assert runez.get_identifiers(["a", ["b_c", None, [1]]]) == ["a", "b_c", "1"]

    assert runez.get_words(None) == []
    assert runez.get_words("") == []
    assert runez.get_words("*") == []
    assert runez.get_words("a") == ["a"]
    assert runez.get_words("a b") == ["a", "b"]
    assert runez.get_words("a,b") == ["a", "b"]
    assert runez.get_words("a,,b") == ["a", "b"]
    assert runez.get_words("a_b1") == ["a", "b1"]
    assert runez.get_words("hi_There-you", normalize=str.lower) == ["hi", "there", "you"]

    assert runez.get_words(["a", "b_c", "a"]) == ["a", "b", "c", "a"]
    assert runez.get_words(["a", None, "b", 1]) == ["a", "b", "1"]
    assert runez.get_words(["a", [None, "b,c"], 1]) == ["a", "b", "c", "1"]

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
