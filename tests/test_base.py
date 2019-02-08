import collections

import runez


COUNTER = 0
TRACKED = collections.defaultdict(int)


def track(operation, prop):
    key = "%s.%s" % (operation, prop)
    TRACKED[key] += 1


def global_track_get(prop, instance=None):
    """Tracker with 'instance' as optional keyword arg"""
    assert isinstance(instance, Foo) or issubclass(instance, Foo)
    track("get", prop)


class Foo(object):

    def track_get(self, prop):
        """Use normal instance method as tracker"""
        track("get", prop)

    @classmethod
    def track_set(cls, prop, instance):
        """Use classmethod as tracker, receive 'instance' as well as positional arg"""
        assert isinstance(instance, Foo)
        track("set", prop)

    @runez.prop(tget=track_get, tset=track_set)
    def nothing(self):
        """Simulates a decorated function returning None, which is interpreted as "nothing cached" by prop"""
        return None

    @runez.prop(tget=global_track_get, tset=track_set)
    def hello(self):
        """All operations tracked"""
        return "hello"

    @runez.prop
    def counter(self):
        """Changes not tracked via notifications"""
        global COUNTER
        COUNTER += 1
        return COUNTER


def test_prop():
    foo = Foo()

    # Verify tracking and operations
    assert TRACKED["get.hello"] == 0
    assert foo.hello == "hello"
    assert TRACKED["get.hello"] == 1
    assert foo.hello == "hello"
    assert foo.hello == "hello"
    assert TRACKED["get.hello"] == 1

    # Same with setting to None
    foo.hello = None
    assert foo.hello == "hello"
    assert TRACKED["get.hello"] == 2
    assert TRACKED["set.hello"] == 1

    # Setting is tracked properly (even if value identical)
    foo.hello = "hello"
    assert foo.hello == "hello"
    assert TRACKED["get.hello"] == 2
    assert TRACKED["set.hello"] == 2

    # Setting to a different value
    foo.hello = "bar"
    assert foo.hello == "bar"
    assert TRACKED["get.hello"] == 2
    assert TRACKED["set.hello"] == 3

    # Test that because we return None, nothing keeps getting called until we actually set it
    assert TRACKED["get.nothing"] == 0
    assert foo.nothing is None
    assert TRACKED["get.nothing"] == 1
    assert foo.nothing is None
    assert TRACKED["get.nothing"] == 2
    assert TRACKED["set.nothing"] == 0

    # Setting it now seeds its cache
    foo.nothing = "bar"
    assert foo.nothing == "bar"
    assert foo.nothing == "bar"
    assert TRACKED["get.nothing"] == 2
    assert TRACKED["set.nothing"] == 1

    # Verify that we call implementation only once when it does return a non-None value
    assert foo.counter == 1
    assert foo.counter == 1

    # Verify that resetting via None works
    foo.counter = None
    assert foo.counter == 2
    assert foo.counter == 2

    # Setting any non-None value does not trigger re-computationr
    foo.counter = 15
    assert foo.counter == 15
