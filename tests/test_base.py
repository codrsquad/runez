# -*- coding: utf-8 -*-

import sys
import time

import pytest

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
    __slots__ = ["a1", "b1"]

    prop1a = runez.AdaptedProperty(default="1a")  # No validation, accepts anything as-is
    prop1b = runez.AdaptedProperty(default="1b", doc="p1b")  # Allows to verify multiple anonymous properties work
    prop1c = runez.AdaptedProperty(caster=int)  # Allows to verify caster approach
    prop1d = runez.AdaptedProperty(type=int, default=123)  # Allows to verify type approach

    @runez.AdaptedProperty(default="p2")
    def prop2(self, value):
        """No validation, accepts anything as-is"""
        return value

    @runez.AdaptedProperty
    def prop3(self, value):
        """Requires something that can be turned into an int"""
        return int(value)

    @runez.AdaptedProperty(default=4)
    def prop4(self, value):
        """Requires something that can be turned into an int"""
        return int(value)

    def _get_defaults(self):
        return runez.UNSET


class Slotted2(runez.Slotted):
    __slots__ = ["name", "other"]


def test_adapted_properties():
    with pytest.raises(AssertionError):
        runez.AdaptedProperty(validator=lambda x: x, caster=int)  # Can't have validator and caster at the same time

    with pytest.raises(AssertionError):
        runez.AdaptedProperty(caster=int, type=int)  # Can't specify both

    s1a = Slotted1()

    # Check class-level properties
    s1ac = s1a.__class__
    assert isinstance(s1ac.prop1a, runez.AdaptedProperty)
    assert s1ac.prop1a.__doc__ is None
    assert s1ac.prop1b.__doc__ == "p1b"
    assert s1ac.prop1c.__doc__ is None
    assert s1ac.prop1d.__doc__ is None
    assert s1ac.prop2.__doc__ == "No validation, accepts anything as-is"
    assert s1ac.prop3.__doc__ == "Requires something that can be turned into an int"

    assert s1a.prop1a == "1a"
    assert s1a.prop1b == "1b"
    assert s1a.prop1c is None
    assert s1a.prop1d == 123
    assert s1a.prop2 == "p2"
    assert s1a.prop3 is None
    assert s1a.prop4 == 4

    # prop1a/b and prop2 have no validators
    s1a.prop2 = 2
    assert s1a.prop2 == 2

    s1a.prop1a = "foo"
    assert s1a.prop1a == "foo"
    assert s1a.prop1b == "1b"  # Verify other anonymous props remain unchanged
    assert s1a.prop1c is None
    assert s1a.prop1d == 123

    s1a.prop1b = 0
    s1a.prop1d = 234
    assert s1a.prop1a == "foo"
    assert s1a.prop1b == 0
    assert s1a.prop1c is None
    assert s1a.prop1d == 234

    s1a.prop1c = "100"  # prop1c has a caster
    assert s1a.prop1a == "foo"
    assert s1a.prop1b == 0
    assert s1a.prop1c == 100

    s1a.prop1c = None  # caster should accept None
    assert s1a.prop1c is None
    with pytest.raises(ValueError):  # but anything other than None must be an int
        s1a.prop1c = "foo"
    assert s1a.prop1c is None

    with pytest.raises(TypeError):
        s1a.prop1d = None  # prop1d uses type=int, and int() does not accept None

    # prop3 and prop4 insist on ints
    s1a.prop3 = "30"
    s1a.prop4 = 40
    assert s1a.prop3 == 30
    assert s1a.prop4 == 40

    with pytest.raises(ValueError):
        s1a.prop3 = "foo"

    # Verify properties stay bound to their object
    s1b = Slotted1(s1a)
    assert s1b.prop1a == "1a"
    assert s1b.prop1b == "1b"
    assert s1b.prop2 == "p2"
    assert s1b.prop3 is None
    assert s1b.prop4 == 4


def test_slotted():
    s1a = Slotted1()
    assert s1a.a1 is runez.UNSET

    s1a = Slotted1(a1="a1", b1="b1")
    s1b = Slotted1(s1a)
    assert str(s1b) == "Slotted1(a1=a1, b1=b1)"
    assert s1a.a1 == "a1"
    assert s1a.b1 == "b1"
    assert s1a == s1b

    # Check properties
    assert s1a.prop4 == 4
    assert s1b.prop4 == 4
    s1a.prop4 = 40
    assert s1a.prop4 == 40
    assert s1b.prop4 == 4  # Clone's property did not get modified

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


@pytest.mark.skipif(sys.version_info[:2] < (3, 7), reason="Available in 3.7+")
def test_importtime():
    """Verify that importing runez remains fast"""
    check_importtime_within(4, "os", "runez")
    check_importtime_within(4, "sys", "runez")
