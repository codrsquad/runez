import collections

import pytest

import runez


COUNTER = 0
TRACKED = collections.defaultdict(int)


def track(operation, prop):
    key = "%s.%s" % (operation, prop)
    TRACKED[key] += 1


class SimpleCallback(object):
    """__on_prop callback as instance method, receiving 'prop' as argument"""

    def __on_prop(self, prop):
        track("set", prop)

    @runez.prop
    def nothing(self):
        """Simulates a decorated function returning None, which is interpreted as "nothing cached" by prop"""
        track("get", "nothing")
        return None


class ClassmethodCallback(object):
    """__on_prop callback as class method, receiving 'prop' as argument"""

    @classmethod
    def __on_prop(self, prop):
        track("set", prop)

    @runez.prop
    def hello(self):
        """All operations tracked"""
        track("get", "hello")
        return "hello"


class GenericCallback(object):
    """__on_prop callback as instance method, no arguments"""

    def __on_prop(self):
        track("set", "counter")

    @runez.prop
    def counter(self):
        """Changes not tracked via notifications"""
        global COUNTER
        COUNTER += 1
        track("get", "counter")
        return COUNTER


class NoCallback(object):
    """No __on_prop callback"""

    @runez.prop
    def welcome(self):
        return "welcome"


@pytest.fixture
def tracked():
    global COUNTER
    global TRACKED
    COUNTER = 0
    TRACKED = collections.defaultdict(int)
    yield TRACKED


def test_simple(tracked):
    sample = SimpleCallback()

    # Test that because we return None, nothing keeps getting called until we actually set it
    assert tracked["get.nothing"] == 0
    assert sample.nothing is None
    assert tracked["get.nothing"] == 1
    assert sample.nothing is None
    assert tracked["get.nothing"] == 2
    assert tracked["set.nothing"] == 0

    # Setting it now seeds its cache
    sample.nothing = "bar"
    assert sample.nothing == "bar"
    assert sample.nothing == "bar"
    assert tracked["get.nothing"] == 2
    assert tracked["set.nothing"] == 1


def test_classmethod(tracked):
    sample = ClassmethodCallback()

    # Verify tracking and operations
    assert tracked["get.hello"] == 0
    assert sample.hello == "hello"
    assert tracked["get.hello"] == 1
    assert sample.hello == "hello"
    assert sample.hello == "hello"
    assert tracked["get.hello"] == 1

    # Same with setting to None
    sample.hello = None
    assert sample.hello == "hello"
    assert tracked["get.hello"] == 2
    assert tracked["set.hello"] == 1

    # Setting is tracked properly (even if value identical)
    sample.hello = "hello"
    assert sample.hello == "hello"
    assert tracked["get.hello"] == 2
    assert tracked["set.hello"] == 2

    # Setting to a different value
    sample.hello = "bar"
    assert sample.hello == "bar"
    assert tracked["get.hello"] == 2
    assert tracked["set.hello"] == 3


def test_generic(tracked):
    sample = GenericCallback()

    # Verify that we call implementation only once when it does return a non-None value
    assert sample.counter == 1
    assert sample.counter == 1
    assert tracked["get.counter"] == 1

    # Verify that resetting via None works
    sample.counter = None
    assert sample.counter == 2
    assert sample.counter == 2
    assert tracked["get.counter"] == 2
    assert tracked["set.counter"] == 1

    # Setting any non-None value does not trigger re-computationr
    sample.counter = 15
    assert sample.counter == 15
    assert tracked["get.counter"] == 2
    assert tracked["set.counter"] == 2


def test_no_callback():
    sample = NoCallback()

    assert sample.welcome == "welcome"
    sample.welcome = "hi"
    assert sample.welcome == "hi"
    sample.welcome = None
    assert sample.welcome == "welcome"


def test_class_prop(tracked):
    """
    Verify that using props on class directly also works (but won't work for setting those props...)
    """
    assert SimpleCallback.nothing is None
    assert ClassmethodCallback.hello == "hello"
    assert GenericCallback.counter == 1

    assert SimpleCallback.nothing is None
    assert ClassmethodCallback.hello == "hello"
    assert GenericCallback.counter == 1

    assert NoCallback.welcome == "welcome"

    assert tracked["get.nothing"] == 2
    assert tracked["get.hello"] == 1
    assert tracked["get.counter"] == 1
