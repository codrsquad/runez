import pytest

from runez.system import cached_property


class MyObject:
    _global_counter = 0

    @property
    def some_property(self):
        """Example regular (non-cached) property"""
        return "some-value"

    @cached_property
    def foo(self) -> int:
        """Some example property"""
        MyObject._global_counter += 1
        return MyObject._global_counter


def check_props(target):
    # Same outcome regardless whether `target` is an instance (with no cached properties called yet), or a class
    assert sorted(cached_property.properties(target)) == ["foo"]
    assert sorted(cached_property.properties(target, cached_only=False)) == ["foo", "some_property"]
    assert sorted(cached_property.properties(target, cached_only=True)) == ["foo"]


def test_simple_case():
    MyObject._global_counter = None  # Allows to trigger TypeError exception if property is accessed before expected
    cached_property.reset(MyObject)  # No-op when called on a class
    assert isinstance(MyObject.foo, cached_property)
    assert MyObject.foo.__annotations__ == {"return": int}
    assert MyObject.foo.__doc__ == "Some example property"
    assert MyObject.foo.__module__ == "tests.test_cached_property"
    assert MyObject.foo.__name__ == "foo"
    assert cached_property.to_dict(MyObject) is None
    check_props(MyObject)

    obj1 = MyObject()
    check_props(obj1)
    assert cached_property.to_dict(obj1) == {}
    assert "foo" not in obj1.__dict__
    cached_property.reset(obj1)  # no-op, does not trigger computation of property
    assert cached_property.to_dict(obj1, cached_only=False) == {"some_property": "some-value"}

    with pytest.raises(TypeError):
        _ = obj1.foo

    assert "foo" not in obj1.__dict__
    cached_property.reset(obj1)  # no-op
    MyObject._global_counter = 0  # Ensure counter is at known value initially
    assert "foo" not in obj1.__dict__
    assert obj1.foo == 1  # First call
    assert "foo" in obj1.__dict__
    assert cached_property.to_dict(obj1) == {"foo": 1}
    assert cached_property.to_dict(obj1, transform=str) == {"foo": "1"}
    assert cached_property.to_dict(obj1, cached_only=False) == {"foo": 1, "some_property": "some-value"}

    obj2 = MyObject()
    assert cached_property.to_dict(obj2) == {}
    assert cached_property.to_dict(obj2, existing_only=False) == {"foo": 2}  # Freshly computed via existing_only=False
    assert obj2.foo == 2
    assert obj1.foo == 1  # Check that obj1 didn't change
    assert cached_property.to_dict(obj1) == {"foo": 1}

    cached_property.reset(obj1)  # Resets .foo
    assert cached_property.to_dict(obj1) == {}
    assert obj1.foo == 3  # Recomputed after reset
    assert obj2.foo == 2  # Other object remained unaffected
    assert cached_property.to_dict(obj1) == {"foo": 3}

    obj1.foo = 42
    assert obj1.foo == 42  # Setting value works
    assert obj2.foo == 2  # And does not affect other object
    assert cached_property.to_dict(obj1) == {"foo": 42}

    del obj1.foo
    assert "foo" not in obj1.__dict__
    assert cached_property.to_dict(obj1) == {}
    assert obj1.foo == 4  # Recomputed again after delete
    assert "foo" in obj1.__dict__
    assert obj2.foo == 2  # Other object remained unaffected
    assert cached_property.to_dict(obj1) == {"foo": 4}
