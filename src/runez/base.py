"""
Base functionality used by other parts of `runez`.

This class should not import any other `runez` class, to avoid circular deps.
"""

import threading


try:
    string_type = basestring  # noqa
    PY2 = True

except NameError:
    string_type = str
    unicode = str
    PY2 = False


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


def simplified_class_name(cls, root):
    """By default, root ancestor is ignored, common prefix/suffix is removed, and name is lowercase-d"""
    if cls is not root:
        name = cls.__name__
        root = getattr(root, "__name__", root)
        if name.startswith(root):
            name = name[len(root):]
        elif name.endswith(root):
            name = name[:len(root) + 1]
        return name.lower()


def class_descendants(ancestor, adjust=simplified_class_name, root=None):
    """
    Args:
        ancestor (type): Class to track descendants of
        root (type | str | None): Root ancestor, or ancestor name (defaults to `ancestor`), passed through to `adjust`
        adjust (callable): Function that can adapt each descendant, and return an optionally massaged name to represent it
                           If function returns None for a given descendant, that descendant is ignored in the returned map

    Returns:
        (dict): Map of all descendants, by optionally adjusted name
    """
    result = {}
    if root is None:
        root = ancestor
    name = adjust(ancestor, root)
    if name is not None:
        result[name] = ancestor
    _walk_descendants(result, ancestor, adjust, root)
    return result


def decode(value, strip=False):
    """Python 2/3 friendly decoding of output.

    Args:
        value (str | unicode | bytes | None): The value to decode.
        strip (bool): If True, `strip()` the returned string. (Default value = False)

    Returns:
        str: Decoded value, if applicable.
    """
    if value is None:
        return None
    if isinstance(value, bytes) and not isinstance(value, unicode):
        value = value.decode("utf-8")
    if strip:
        return stringified(value).strip()
    return stringified(value)


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
            name (str | unicode): Name of slot to set.
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


def stringified(value, converter=None):
    """
    Args:
        value: Any object to turn into a string
        converter (callable | None): Optional converter to use for non-string objects

    Returns:
        (str): Ensure `text` is a string if necessary (this is to avoid transforming string types in py2 as much as possible)
    """
    if isinstance(value, string_type):
        return value

    if converter is not None:
        converted = converter(value)
        if isinstance(converted, string_type):
            return converted

        if converted is not None:
            value = converted

    return "%s" % value


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

    def enable(self, on):
        """Enable contextual logging"""
        with self._lock:
            if on:
                if self.filter is None:
                    self.filter = self._filter_type(self)
            else:
                self.filter = None

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
            name (str | unicode): Remove entry with `name` from current thread's context
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
            name (str | unicode): Remove entry with `name` from global context
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

    def _ensure_global(self, values=None):
        """
        Args:
            values (dict): Ensure internal global tracking dict is created, seed it with `values` when provided (Default value = None)
        """
        if self._gpayload is None:
            self._gpayload = values or {}


def _walk_descendants(result, ancestor, adjust, root):
    for m in ancestor.__subclasses__():
        name = adjust(m, root)
        if name is not None:
            result[name] = m
        _walk_descendants(result, m, adjust, root)
