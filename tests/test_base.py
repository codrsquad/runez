# -*- coding: utf-8 -*-

import sys
import time

import pytest

import runez


def test_base():
    assert runez.decode(None) is None
    assert runez.decode(" something ") == " something "
    assert runez.decode(" something ", strip=True) == "something"

    # len() depends on whether python was built with UCS-2 or UCS-4, we don't care here, just want to check decode() works OK with unicode
    assert len(runez.decode(" lucky leaf ☘ is lucky 😀 ")) in (25, 26)
    assert len(runez.decode(" lucky leaf ☘ is lucky 😀 ", strip=True)) in (23, 24)

    assert runez.decode(b" something ") == " something "
    assert runez.decode(b" something ", strip=True) == "something"

    assert runez.first_meaningful_line("") is None
    assert runez.first_meaningful_line("\n  \n\n") is None
    assert runez.first_meaningful_line("\n\n\n  foo  \n\bar") == "foo"

    # Verify that UNSET behaves as expected: evaluates to falsy, has correct representation
    assert not runez.UNSET
    assert bool(runez.UNSET) is False
    assert str(runez.UNSET) == "UNSET"

    assert runez.quoted(None) is None
    assert runez.quoted("") == ""
    assert runez.quoted(" ") == '" "'
    assert runez.quoted('"') == '"'
    assert runez.quoted("a b") == '"a b"'
    assert runez.quoted('a="b"') == 'a="b"'
    assert runez.quoted('foo a="b"') == """'foo a="b"'"""

    # Edge cases with test_stringified()
    assert runez.stringified(5, converter=lambda x: None) == "5"
    assert runez.stringified(5, converter=lambda x: x) == "5"


def test_descendants():
    class Cat(object):
        _foo = None

    class FastCat(Cat):
        pass

    class LittleCatKitty(Cat):
        pass

    class CatMeow(FastCat):
        pass

    # By default, root ancestor is skipped, common prefix/suffix is removed, and name is lowercase-d
    d = runez.class_descendants(Cat)
    assert len(d) == 3
    assert d["fast"] is FastCat
    assert d["littlecatkitty"] is LittleCatKitty
    assert d["meow"] is CatMeow

    # Keep names as-is, including root ancestor
    d = runez.class_descendants(Cat, adjust=lambda x, r: x.__name__)
    assert len(d) == 4
    assert d["Cat"] is Cat
    assert d["FastCat"] is FastCat
    assert d["LittleCatKitty"] is LittleCatKitty
    assert d["CatMeow"] is CatMeow

    assert FastCat._foo is None

    # The 'adjust' function can also be used to simply modify descendants (but not track them)
    def adjust(cls, root):
        cls._foo = cls.__name__.lower()

    d = runez.class_descendants(Cat, adjust=adjust)
    assert len(d) == 0
    assert FastCat._foo == "fastcat"


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


@pytest.mark.skipif(sys.version_info[:2] < (3, 7), reason="Available in 3.7+")
def test_importtime():
    """Verify that importing runez remains fast"""
    check_importtime_within(4, "os", "runez")
    check_importtime_within(4, "sys", "runez")


def get_importtime(module):
    output = runez.run(sys.executable, "-Ximporttime", "-c", "import %s" % module, fatal=False, include_error=True)
    assert output
    total = 0
    cumulative = None
    for line in output.splitlines():
        stime, cumulative, mod_name = line.split("|")
        mod_name = mod_name.strip()
        if module in mod_name:
            value = runez.to_int(stime.partition(":")[2])
            assert value is not None, line
            total += value

    cumulative = runez.to_int(cumulative)
    assert cumulative is not None
    return total, cumulative


def average_importtime(module, count):
    cumulative = 0
    started = time.time()
    for _ in range(count):
        s, c = get_importtime(module)
        cumulative += c

    return cumulative / count, time.time() - started


def check_importtime_within(factor, mod1, mod2, count=5):
    """Check that importtime of 'mod1' is less than 'factor' times slower than 'mod2' on average"""
    c1, e1 = average_importtime(mod1, count)
    c2, e2 = average_importtime(mod2, count)
    assert c2 < factor * c1
    assert e2 < factor * e1
