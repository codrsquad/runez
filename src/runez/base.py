"""
Base functionality used by other parts of `runez`.

This class should not import any other `runez` class, to avoid circular deps.
"""

import inspect
import threading


try:
    string_type = basestring  # noqa

except NameError:
    string_type = str
    unicode = str


class Undefined(object):
    """Provides base type for `UNSET` below (representing an undefined value)

    Allows to distinguish between a caller not providing a value, vs providing `None`.
    This is needed in order to track whether a user actually provided a value (including `None`) as named argument.

    Example application is `runez.log.setup()`
    """

    def __repr__(self):
        return "UNSET"

    def __len__(self):
        # Ensures that Undefined instances evaluate as falsy
        return 0


# Internal marker for values that are NOT set
UNSET = Undefined()  # type: Undefined


def decode(value, strip=False):
    """Python 2/3 friendly decoding of output.

    Args:
        value (str | bytes | None): The value to decode.
        strip (bool): If True, `strip()` the returned string. (Default value = False)

    Returns:
        str: Decoded value, if applicable.
    """
    if value is None:
        return None
    if isinstance(value, bytes) and not isinstance(value, str):
        if strip:
            return value.decode("utf-8").strip()
        return value.decode("utf-8")
    if strip:
        return unicode(value).strip()
    return unicode(value)


class prop(object):
    """Decorator for settable cached properties.

    This comes in handy for properties you'd like to avoid computing multiple times,
    yet be able to arbitrarily change them as well, and be able to know when they get changed.
    """

    def __init__(self, func):
        """
        Args:
            func (function): Wrapped function
        """
        self.function = func
        self.name = func.__name__  # type: str
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

    _default = None

    def __init__(self, *args, **kwargs):
        """
        Args:
            *args (Slotted): Optionally provide another instance of same type to initialize from
            **kwargs: Override one or more of this classes' fields (keys must refer to valid slots)
        """
        self._seed()
        self.set(*args, **kwargs)

    def _seed(self):
        """Seed initial fields"""
        for name in self.__slots__:
            value = getattr(self, name, UNSET)
            if value is UNSET:
                setattr(self, name, self.__class__._default)

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            for name in self.__slots__:
                if getattr(self, name, None) != getattr(other, name, None):
                    return False
            return True

    def _set(self, name, value):
        """
        Args:
            name (str): Name of slot to set.
            value: Associated value
        """
        if value is not UNSET:
            if isinstance(value, Slotted):
                current = getattr(self, name, UNSET)
                if current is None or current is UNSET:
                    current = value.__class__()
                    current.set(value)
                    setattr(self, name, current)
                    return
                if isinstance(current, Slotted):
                    current.set(value)
                    return
            setattr(self, name, value)

    def set(self, *args, **kwargs):
        """Conveniently set one or more fields at a time.

        Args:
            *args: Optionally set from other objects, available fields from the passed object are used in order
            **kwargs: Set from given key/value pairs (only names defined in __slots__ are used)
        """
        if args:
            for arg in args:
                if arg is not None:
                    for name in self.__slots__:
                        self._set(name, getattr(arg, name, UNSET))
        for name in kwargs:
            self._set(name, kwargs.get(name, UNSET))

    def pop(self, settings):
        """
        Args:
            settings (dict): Dict to pop applicable fields from
        """
        if settings:
            for name in self.__slots__:
                self._set(name, settings.pop(name, UNSET))

    def to_dict(self):
        result = {}
        for name in self.__slots__:
            val = getattr(self, name, UNSET)
            if val is not UNSET:
                result[name] = val
        return result


class ThreadGlobalContext(object):
    """Thread-local + global context, composed of key/value pairs.

    Thread-local context is a dict per thread (stored in a threading.local()).
    Global context is a simple dict (applies to all threads).
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
        """Set current thread's logging context to specified `values`"""
        with self._lock:
            self._ensure_threadlocal()
            self._tpayload.context = values

    def add_threadlocal(self, **values):
        """Add `values` to current thread's logging context"""
        with self._lock:
            self._ensure_threadlocal()
            self._tpayload.context.update(**values)

    def remove_threadlocal(self, name):
        """
        Args:
            name (str): Remove entry with `name` from current thread's context
        """
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
        """Set global logging context to provided `values`"""
        with self._lock:
            self._ensure_global(values)

    def add_global(self, **values):
        """Add `values` to global logging context"""
        with self._lock:
            self._ensure_global()
            self._gpayload.update(**values)

    def remove_global(self, name):
        """
        Args:
            name (str): Remove entry with `name` from global context
        """
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
        Returns:
            dict: Combined global and thread-specific logging context
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
        """
        Args:
            values (dict): Ensure internal global tracking dict is created, seed it with `values` when provided (Default value = None)
        """
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
    """Find `__on_prop` function to notify on `@prop` change, if any.

    Args:
        frame (types.FrameType): Frame to examine.

    Returns:
        (function | None, bool): __on_prop function if any, boolean indicates whether that function takes 'prop' as argument.
    """
    for name, func in frame.f_locals.items():
        if name.endswith("__on_prop"):
            if isinstance(func, classmethod):
                func = func.__func__
            return func, _has_arg(func, "prop")
    return None, False
