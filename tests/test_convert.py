#  -*- encoding: utf-8 -*-

import datetime

from freezegun import freeze_time

import runez
from runez.convert import SECONDS_IN_ONE_DAY, SECONDS_IN_ONE_HOUR


def test_shortened():
    assert runez.shortened("") == ""
    assert runez.shortened(" some text ") == "some text"
    assert runez.shortened("some long text", size=9) == "some l..."
    assert runez.shortened("some long text", size=8) == "some..."


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

    assert runez.represented_args(None) == ""
    assert runez.represented_args([]) == ""
    assert runez.represented_args([0, 1, 2], separator="+") == "0+1+2"
    assert runez.represented_args(["foo", {}, 0, [1, 2], {3: 4}, 5]) == 'foo {} 0 "[1, 2]" "{3: 4}" 5'


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


REF_TIME1 = datetime.datetime(2019, 9, 2, microsecond=100)
REF_TIME2 = datetime.datetime(2019, 9, 2, microsecond=200)


@freeze_time("2019-09-01")
def test_represented_duration():
    assert runez.represented_duration(None) == ""
    assert runez.represented_duration("foo") == "foo"

    assert runez.represented_duration(datetime.date.today()) == "0 seconds"
    assert runez.represented_duration(REF_TIME1) == "1 day"
    assert runez.represented_duration(REF_TIME2 - REF_TIME1) == "100 μs"
    assert runez.represented_duration(REF_TIME1 - REF_TIME2) == "100 μs"

    assert runez.represented_duration(None) == ""
    assert runez.represented_duration("foo") == "foo"

    assert runez.represented_duration(0) == "0 seconds"
    assert runez.represented_duration(1) == "1 second"
    assert runez.represented_duration(-1.00001) == "1 second 10 μs"
    assert runez.represented_duration(-180.00001) == "3 minutes"
    assert runez.represented_duration(-180.00001, span=None) == "3 minutes 10 μs"
    assert runez.represented_duration(5.1) == "5 seconds 100 ms"
    assert runez.represented_duration(180.1) == "3 minutes"

    assert runez.represented_duration(65) == "1 minute 5 seconds"
    assert runez.represented_duration(65, span=-2) == "1m 5s"
    assert runez.represented_duration(3667, span=-2) == "1h 1m"
    assert runez.represented_duration(3667, span=None) == "1 hour 1 minute 7 seconds"

    h2 = 2 * SECONDS_IN_ONE_HOUR
    d8 = 8 * SECONDS_IN_ONE_DAY
    a_week_plus = d8 + h2 + 13 + 0.00001
    assert runez.represented_duration(a_week_plus, span=None) == "1 week 1 day 2 hours 13 seconds 10 μs"
    assert runez.represented_duration(a_week_plus, span=-2, separator="+") == "1w+1d"
    assert runez.represented_duration(a_week_plus, span=3) == "1 week 1 day 2 hours"
    assert runez.represented_duration(a_week_plus, span=0) == "1w 1d 2h 13s 10μs"

    five_weeks_plus = (5 * 7 + 3) * SECONDS_IN_ONE_DAY + SECONDS_IN_ONE_HOUR + 5 + 0.0002
    assert runez.represented_duration(five_weeks_plus, span=-2, separator=", ") == "5w, 3d"
    assert runez.represented_duration(five_weeks_plus, span=0, separator=", ") == "5w, 3d, 1h, 5s, 200μs"

    assert runez.represented_duration(752 * SECONDS_IN_ONE_DAY, span=3) == "2 years 3 weeks 1 day"


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
