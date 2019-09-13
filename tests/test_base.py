# -*- coding: utf-8 -*-

import runez


def test_descendants():
    class A(object):
        _foo = None

    class B(A):
        pass

    class C(B):
        pass

    d = runez.class_descendants(A)
    assert len(d) == 2
    assert d["B"] is B
    assert d["C"] is C

    d = runez.class_descendants(A, include_ancestor=True)
    assert len(d) == 3
    assert d["A"] is A

    d = runez.class_descendants(A, adjust=lambda x: x.__name__.lower())
    assert len(d) == 2
    assert d["b"] is B
    assert d["c"] is C

    assert B._foo is None

    def adjust(some_type):
        some_type._foo = some_type.__name__.lower()

    d = runez.class_descendants(A, adjust=adjust)
    assert len(d) == 2
    assert d["B"] is B
    assert d["C"] is C

    assert B._foo == "b"


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
