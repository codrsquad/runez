from runez.system import cached_property


class MyObject:

    _global_counter = 1

    @cached_property
    def foo(self):
        """Some example property"""
        MyObject._global_counter += 1
        return MyObject._global_counter


def test_simple_case():
    MyObject._global_counter = 1  # This reset is needed only if we add more test cases some day (using same `_global_counter`)
    assert isinstance(MyObject.foo, cached_property)
    assert MyObject.foo.__doc__ == "Some example property"

    obj1 = MyObject()
    assert obj1.foo == 2  # First calls

    obj2 = MyObject()
    assert obj1.foo == 2  # Check that obj1 didn't change
    assert obj2.foo == 3  # Freshly computed in new object

    del obj1.foo
    assert obj1.foo == 4  # Recomputed after delete
    assert obj2.foo == 3  # Other object remained unaffected

    obj1.foo = 42
    assert obj1.foo == 42  # Setting value works
    assert obj2.foo == 3  # And does not affect other object

    del obj1.foo
    assert obj1.foo == 5  # Recomputed again after delete
