import inspect

import pytest

import runez.colors
import runez.conftest
import runez.logsetup
import runez.render
from runez.system import Slotted, UNSET


class Sample(Slotted):
    __slots__ = ("a", "b")
    a: object
    b: object


def _descendants(cls):
    for subclass in cls.__subclasses__():
        yield subclass
        yield from _descendants(subclass)


def test_annotations():
    # Each runez Slotted descendant must annotate its slots, so that type checkers know about them
    slotted = [c for c in _descendants(Slotted) if c.__module__.startswith("runez.") and "__slots__" in c.__dict__]
    assert runez.logsetup.LogSpec in slotted
    for cls in slotted:
        assert set(inspect.get_annotations(cls)) == set(cls.__slots__), cls


def test_slotted():
    sample1 = Sample()
    sample2 = Sample()
    assert str(sample1) == "Sample()"
    sample1.a = 10
    assert str(sample1) == "Sample(a=10)"
    assert sample1 != sample2

    # Exercise setting
    sample2.set(a=sample1)
    assert sample1 == sample2.a
    sample2.set(a=sample1)  # 2nd set to exercise replacing value

    sample3 = Sample()
    sample3.set({"a": sample1})
    assert sample2 == sample3

    class Foo:
        name = "testing"
        age = 10

    with pytest.raises(TypeError, match="should be instance"):
        Slotted.fill_attributes(Foo, {})

    foo = Foo()
    assert foo.name == "testing"
    assert foo.age == 10
    Slotted.fill_attributes(foo, {"name": "my-name"})
    assert foo.name == "my-name"
    Slotted.fill_attributes(foo, {"name": UNSET})
    assert foo.name == "testing"  # back to class default

    with pytest.raises(AttributeError, match="Unknown Foo key 'bar'"):
        Slotted.fill_attributes(foo, {"bar": 5})
