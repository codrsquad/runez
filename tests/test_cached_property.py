import pytest

from runez.system import cached_property


class MyObject:

    _global_counter = 0

    @cached_property
    def foo(self):
        """Some example property"""
        MyObject._global_counter += 1
        return MyObject._global_counter


def test_simple_case():
    MyObject._global_counter = None  # Allows to trigger TypeError exception if property is accessed before expected
    assert isinstance(MyObject.foo, cached_property)
    assert not MyObject.foo.__annotations__  # Can't test annotations yet, until full drop for PY2 support
    assert MyObject.foo.__doc__ == "Some example property"
    assert MyObject.foo.__module__ == "tests.test_cached_property"
    assert MyObject.foo.__name__ == "foo"

    obj1 = MyObject()
    assert "foo" not in obj1.__dict__
    cached_property.reset(obj1)  # no-op, does not trigger computation of property

    with pytest.raises(TypeError):
        _ = obj1.foo

    assert "foo" not in obj1.__dict__
    cached_property.reset(obj1)  # no-op
    MyObject._global_counter = 0  # Ensure counter is at known value initially
    assert "foo" not in obj1.__dict__
    assert obj1.foo == 1  # First call
    assert "foo" in obj1.__dict__

    obj2 = MyObject()
    assert obj2.foo == 2  # Freshly computed in new object
    assert obj1.foo == 1  # Check that obj1 didn't change

    cached_property.reset(obj1)  # Resets .foo
    assert obj1.foo == 3  # Recomputed after reset
    assert obj2.foo == 2  # Other object remained unaffected

    obj1.foo = 42
    assert obj1.foo == 42  # Setting value works
    assert obj2.foo == 2  # And does not affect other object

    del obj1.foo
    assert "foo" not in obj1.__dict__
    assert obj1.foo == 4  # Recomputed again after delete
    assert "foo" in obj1.__dict__
    assert obj2.foo == 2  # Other object remained unaffected
