# -*- coding: utf-8 -*-

import runez


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


def test_decode():
    assert runez.decode(None) is None

    assert runez.decode(" something ") == " something "
    assert runez.decode(" something ", strip=True) == "something"

    # len() depends on whether python was built with UCS-2 or UCS-4, we don't care here, just want to check decode() works OK with unicode
    assert len(runez.decode(" lucky leaf ☘ is lucky 😀 ")) in (25, 26)
    assert len(runez.decode(" lucky leaf ☘ is lucky 😀 ", strip=True)) in (23, 24)

    assert runez.decode(b" something ") == " something "
    assert runez.decode(b" something ", strip=True) == "something"


def test_undefined():
    assert str(runez.UNSET) == "UNSET"

    # Verify that runez.UNSET evaluates to falsy
    assert not runez.UNSET
    assert bool(runez.UNSET) is False


class Slotted1(runez.Slotted):
    _default = runez.UNSET
    __slots__ = ["a1", "b1"]


class Slotted2(runez.Slotted):
    __slots__ = ["name", "other"]


def test_slotted():
    s1a = Slotted1()
    assert s1a.a1 is runez.UNSET

    s1a = Slotted1(a1="a1", b1="b1")
    s1b = Slotted1(s1a)
    assert s1a.a1 == "a1"
    assert s1a.b1 == "b1"
    assert s1a == s1b

    s2 = Slotted2(other=s1a)
    assert s2.name is None
    assert s2.other.a1 == "a1"
    s1a.a1 = "changed-a1"
    assert s2.other.a1 == "a1"

    s2.set(other=s1a)
    assert s2.other is not s1a
    assert s2.other == s1a
    assert s2.other.a1 == "changed-a1"

    s2.set(other="other")
    assert s2.other == "other"

    s2.set(other=s1a)
    assert s2.other == s1a


def test_stringified():
    # Edge cases with test_stringified()
    assert runez.stringified(5, converter=lambda x: None) == "5"
    assert runez.stringified(5, converter=lambda x: x) == "5"
