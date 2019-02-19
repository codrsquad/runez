"""
Base functionality used by other parts of runez

We track here whether we're running in dryrun mode, convenience logging etc
"""

import inspect
import threading


try:
    string_type = basestring  # noqa

except NameError:
    string_type = str
    unicode = str


# Internal marker for values that are NOT set
# This allows to distinguish between an argument being given as `None`, vs not mentioned by caller
UNSET = object()


def decode(value):
    """Python 2/3 friendly decoding of output"""
    if isinstance(value, bytes) and not isinstance(value, str):
        return value.decode("utf-8")
    return unicode(value)


class prop(object):
    """
    Decorator for settable cached properties.
    This comes in handy for properties you'd like to avoid computing multiple times,
    yet be able to arbitrarily change them as well, and be able to know when they get changed.
    """

    def __init__(self, func):
        """
        :param callable: Wrapped function
        """
        self.function = func
        self.name = func.__name__
        self.field_name = "__%s" % self.name
        self.on_prop, self.prop_arg = _find_on_prop(inspect.currentframe().f_back)
        self.__doc__ = func.__doc__

    def __repr__(self):
        return self.name

    def __get__(self, instance, cls=None):
        if instance is None:
            instance = cls
        cached = getattr(instance, self.field_name, UNSET)
        if cached is UNSET:
            cached = self.function(instance)
            setattr(instance, self.field_name, cached)
        return cached

    def __set__(self, instance, value):
        setattr(instance, self.field_name, value)
        if self.on_prop:
            if self.prop_arg:
                self.on_prop(instance, prop=self)
            else:
                self.on_prop(instance)


class Slotted(object):
    """This class allows to easily initialize/set a descendant using named arguments"""

    def __init__(self, *args, **kwargs):
        """
        :param args: Optionally provide another instance of same type to initialize from
        :param kwargs: Override one or more of this classes' fields listed above
        """
        self._seed()
        self.set(*args, **kwargs)

    def _seed(self):
        """Seed initial fields"""
        for name in self.__slots__:
            setattr(self, name, None)

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            for name in self.__slots__:
                if getattr(self, name, None) != getattr(other, name, None):
                    return False
            return True

    def _set(self, name, value):
        setattr(self, name, value)

    def set(self, *args, **kwargs):
        """Conveniently set one or more fields at a time"""
        if args:
            if kwargs:
                raise ValueError("Provide either one positional, or field values as named arguments, but not both")
            if len(args) > 1:
                raise ValueError("Provide only one other %s as positional argument" % self.__class__.__name__)
            other = args[0]
            if isinstance(other, self.__class__):
                for name in self.__slots__:
                    self._set(name, getattr(other, name))
                return
            raise ValueError("Argument is not of type %s: %s" % (self.__class__.__name__, args[0]))
        for name in kwargs:
            if not hasattr(self, name):
                raise ValueError("Unknown %s field '%s'" % (self.__class__.__name__, name))
            self._set(name, kwargs[name])


class ThreadGlobalContext:
    """
    Thread-local + global context, composed of key/value pairs
    Thread-local context is a dict per thread (stored in a threading.local())
    Global context is a simple dict (applies to all threads)
    """

    def __init__(self, filter_type):
        """
        :param type filter_type: Class to instantiate as filter
        """
        self._filter_type = filter_type
        self._lock = threading.RLock()
        self._tpayload = None
        self._gpayload = None
        self.filter = None

    def reset(self):
        with self._lock:
            self.filter = None
            self._tpayload = None
            self._gpayload = None

    def enable(self):
        """Enable contextual logging"""
        with self._lock:
            if self.filter is None:
                self.filter = self._filter_type(self)

    def has_threadlocal(self):
        with self._lock:
            return bool(self._tpayload)

    def has_global(self):
        with self._lock:
            return bool(self._gpayload)

    def set_threadlocal(self, **values):
        """Set current thread's logging context to 'values'"""
        with self._lock:
            self._ensure_threadlocal()
            self._tpayload.context = values

    def add_threadlocal(self, **values):
        """Add 'values' to current thread's logging context"""
        with self._lock:
            self._ensure_threadlocal()
            self._tpayload.context.update(**values)

    def remove_threadlocal(self, name):
        """Remove entry with 'name' from current thread's context"""
        with self._lock:
            if self._tpayload is not None:
                if name in self._tpayload.context:
                    del self._tpayload.context[name]
                if not self._tpayload.context:
                    self._tpayload = None

    def clear_threadlocal(self):
        """Clear current thread's context"""
        with self._lock:
            self._tpayload = None

    def set_global(self, **values):
        """Set global logging context to 'values'"""
        with self._lock:
            self._ensure_global(values)

    def add_global(self, **values):
        """Add 'values' to global logging context"""
        with self._lock:
            self._ensure_global()
            self._gpayload.update(**values)

    def remove_global(self, name):
        """Remove entry with 'name' from global context"""
        with self._lock:
            if self._gpayload is not None:
                if name in self._gpayload:
                    del self._gpayload[name]
                if not self._gpayload:
                    self._gpayload = None

    def clear_global(self):
        """Clear global context"""
        with self._lock:
            if self._gpayload is not None:
                self._gpayload = None

    def to_dict(self):
        """
        :return dict: Combined global and thread-specific logging context
        """
        with self._lock:
            result = {}
            if self._gpayload:
                result.update(self._gpayload)
            if self._tpayload:
                result.update(getattr(self._tpayload, "context", {}))
            return result

    def _ensure_threadlocal(self):
        if self._tpayload is None:
            self._tpayload = threading.local()
            self._tpayload.context = {}
        self.enable()

    def _ensure_global(self, values=None):
        if self._gpayload is None:
            self._gpayload = values or {}
        self.enable()


if hasattr(inspect, "signature"):
    # python3
    def _has_arg(func, arg_name):
        return arg_name in inspect.signature(func).parameters

else:
    # python2
    def _has_arg(func, arg_name):
        return arg_name in inspect.getargspec(func).args


def _find_on_prop(frame):
    """
    :param frame frame: Frame to examine
    :return function|None, bool: __on_prop function if any, boolean indicates whether that function takes 'prop' as argument
    """
    for name, func in frame.f_locals.items():
        if name.endswith("__on_prop"):
            if isinstance(func, classmethod):
                func = func.__func__
            return func, _has_arg(func, "prop")
    return None, False
