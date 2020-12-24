from runez.system import cached_property, chill_property


class MyObject:

    _global_counter = 1

    @cached_property
    def foo(self):
        """Some example property"""
        MyObject._global_counter += 1
        return MyObject._global_counter

    @chill_property
    def bar(self):
        """First non-empty is returned"""
        yield None
        yield "bar%s" % MyObject._global_counter
        yield None  # Will never be reached


def test_simple_case():
    MyObject._global_counter = 1  # This reset is needed only if we add more test cases some day (using same `_global_counter`)
    assert isinstance(MyObject.foo, cached_property)
    assert MyObject.foo.__doc__ == "Some example property"
    assert isinstance(MyObject.bar, chill_property)
    assert MyObject.bar.__doc__ == "First non-empty is returned"

    obj1 = MyObject()
    assert obj1.foo == 2  # First call
    assert obj1.bar == "bar2"

    obj2 = MyObject()
    assert obj2.foo == 3  # Freshly computed in new object
    assert obj2.bar == "bar3"
    assert obj1.foo == 2  # Check that obj1 didn't change
    assert obj1.bar == "bar2"

    del obj1.foo
    assert obj1.foo == 4  # Recomputed after delete
    assert obj2.foo == 3  # Other object remained unaffected

    obj1.foo = 42
    assert obj1.foo == 42  # Setting value works
    assert obj2.foo == 3  # And does not affect other object

    del obj1.foo
    assert obj1.foo == 5  # Recomputed again after delete
