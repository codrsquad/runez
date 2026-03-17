import pytest

from runez.system import Slotted, UNSET


class Sample(Slotted):
    __slots__ = ("a", "b")


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
