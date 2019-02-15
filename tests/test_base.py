import collections
import time

import pytest
from mock import patch

import runez


def test_abort(logged):
    assert runez.abort("aborted", fatal=(False, "foo")) == "foo"
    assert "aborted" in logged.pop()

    assert runez.abort("aborted", fatal=(False, "foo"), code=0) == "foo"
    assert "aborted" in logged
    assert "ERROR" not in logged.pop()

    assert runez.abort("aborted", fatal=(None, "foo")) == "foo"
    assert not logged


def test_timezone():
    assert runez.get_timezone() == time.tzname[0]
    with patch("runez.base.time") as runez_time:
        runez_time.tzname = []
        assert runez.get_timezone() == ""


class TracedCalls(object):
    """Track calls, to verify that runez.prop invokes implementations as expected"""

    _called_ops = collections.defaultdict(int)

    @classmethod
    def _track(cls, operation, prop):
        cls._called_ops["%s.%s" % (operation, prop)] += 1

    @classmethod
    def call_count(cls, operation, prop):
        return cls._called_ops["%s.%s" % (operation, prop)]


class SimpleCallback(TracedCalls):
    """__on_prop callback as instance method, receiving 'prop' as argument"""

    def __on_prop(self, prop):
        self._track("set", prop)

    @runez.prop
    def nothing(self):
        """
        Simulate a decorated function returning None, which is interpreted as "nothing cached" by prop
        This function should thus be called every time we look at it
        """
        self._track("get", "nothing")
        return None


class ClassmethodCallback(TracedCalls):
    """__on_prop callback as class method, receiving 'prop' as argument"""

    @classmethod
    def __on_prop(self, prop):
        self._track("set", prop)

    @runez.prop
    def hello(self):
        """Returns a value, which should be cached by runez.prop"""
        self._track("get", "hello")
        return "hello"


class GenericCallback(TracedCalls):
    """__on_prop callback as instance method, no arguments"""

    def __on_prop(self):
        self._track("set", "some_int")

    @runez.prop
    def some_int(self):
        """
        Return a value, incrementing each time runez.prop calls its implementation
        This
        """
        self._track("get", "some_int")
        return 123


class NoCallback(object):
    """No __on_prop callback"""

    @runez.prop
    def welcome(self):
        return "welcome"


@pytest.fixture
def tracked():
    TracedCalls._called_ops = collections.defaultdict(int)
    yield TracedCalls.call_count


def test_simple(tracked):
    sample = SimpleCallback()

    # Test that because we return None, nothing keeps getting called until we actually set it
    assert tracked("get", "nothing") == 0
    assert sample.nothing is None
    assert tracked("get", "nothing") == 1
    assert sample.nothing is None
    assert tracked("get", "nothing") == 2
    assert tracked("set", "nothing") == 0

    # Setting it now seeds its cache
    sample.nothing = "bar"
    assert sample.nothing == "bar"
    assert sample.nothing == "bar"
    assert tracked("get", "nothing") == 2
    assert tracked("set", "nothing") == 1


def test_classmethod(tracked):
    sample = ClassmethodCallback()

    # Verify tracking and operations
    assert tracked("get", "hello") == 0
    assert sample.hello == "hello"
    assert tracked("get", "hello") == 1
    assert sample.hello == "hello"
    assert sample.hello == "hello"
    assert tracked("get", "hello") == 1

    # Same with setting to None
    sample.hello = None
    assert sample.hello == "hello"
    assert tracked("get", "hello") == 2
    assert tracked("set", "hello") == 1

    # Setting is tracked properly (even if value identical)
    sample.hello = "hello"
    assert sample.hello == "hello"
    assert tracked("get", "hello") == 2
    assert tracked("set", "hello") == 2

    # Setting to a different value
    sample.hello = "bar"
    assert sample.hello == "bar"
    assert tracked("get", "hello") == 2
    assert tracked("set", "hello") == 3


def test_generic(tracked):
    sample = GenericCallback()

    # Verify that we call implementation only once when it does return a non-None value
    assert sample.some_int == 123
    assert sample.some_int == 123
    assert tracked("get", "some_int") == 1
    assert tracked("set", "some_int") == 0

    # Verify that resetting via None works
    sample.some_int = None
    assert sample.some_int == 123
    assert sample.some_int == 123
    assert tracked("get", "some_int") == 2
    assert tracked("set", "some_int") == 1

    # Setting any non-None value does not trigger re-computationr
    sample.some_int = 15
    assert sample.some_int == 15
    assert tracked("get", "some_int") == 2
    assert tracked("set", "some_int") == 2


def test_no_callback(tracked):
    sample = NoCallback()

    assert sample.welcome == "welcome"
    sample.welcome = "hi"
    assert sample.welcome == "hi"
    sample.welcome = None
    assert sample.welcome == "welcome"
    assert tracked("get", "welcome") == 0
    assert tracked("set", "welcome") == 0


def test_class_prop(tracked):
    """
    Verify that using props on class directly also works (but won't work for setting those props...)
    """
    assert SimpleCallback.nothing is None
    assert ClassmethodCallback.hello == "hello"
    assert GenericCallback.some_int == 123

    assert SimpleCallback.nothing is None
    assert ClassmethodCallback.hello == "hello"
    assert GenericCallback.some_int == 123

    assert NoCallback.welcome == "welcome"

    assert tracked("get", "nothing") == 2
    assert tracked("get", "hello") == 1
    assert tracked("get", "some_int") == 1
    assert tracked("get", "welcome") == 0


def test_listify():
    assert runez.listify(None) is None
    assert runez.listify("") == [""]
    assert runez.listify("foo,bar") == ["foo,bar"]
    assert runez.listify("foo,bar", separator=",") == ["foo", "bar"]

    assert runez.listify(1) == [1]
    assert runez.listify((1, 2, 3)) == [1, 2, 3]
