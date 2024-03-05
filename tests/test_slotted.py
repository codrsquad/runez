import pytest

import runez


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
    with pytest.raises(ValueError, match="invalid literal for int"):  # but anything other than None must be an int
        s1a.prop1c = "foo"
    assert s1a.prop1c is None

    with pytest.raises(TypeError, match="not 'NoneType'"):
        s1a.prop1d = None  # prop1d uses type=int, and int() does not accept None

    # prop3 and prop4 insist on ints
    s1a.prop3 = "30"
    s1a.prop4 = 40
    assert s1a.prop3 == 30
    assert s1a.prop4 == 40

    with pytest.raises(ValueError, match="invalid literal for int"):
        s1a.prop3 = "foo"

    # Verify properties stay bound to their object
    s1b = Slotted1(s1a)
    assert s1b.prop1a == "1a"
    assert s1b.prop1b == "1b"
    assert s1b.prop2 == "p2"
    assert s1b.prop3 is None
    assert s1b.prop4 == 4

    s1b.set({"prop1a": "foo"})
    assert s1b.prop1a == "foo"


def test_insights():
    class Foo:
        name = "testing"
        age = 10

    with pytest.raises(TypeError, match="should be instance"):
        runez.Slotted.fill_attributes(Foo, {})

    foo = Foo()
    assert foo.name == "testing"
    assert foo.age == 10
    runez.Slotted.fill_attributes(foo, {"name": "my-name"})
    assert foo.name == "my-name"
    runez.Slotted.fill_attributes(foo, {"name": runez.UNSET})
    assert foo.name == "testing"  # back to class default

    with pytest.raises(AttributeError, match="Unknown Foo key 'bar'"):
        runez.Slotted.fill_attributes(foo, {"bar": 5})


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
