"""
Base functionality used by other parts of `runez`.

This class should not import any other `runez` class, to avoid circular deps.
"""

import logging
import os
import sys
import threading


try:
    string_type = basestring  # noqa
    PY2 = True

except NameError:
    string_type = str
    unicode = str
    PY2 = False


LOG = logging.getLogger("runez")
SANITIZED = 1
SHELL = 2
UNIQUE = 4
WINDOWS = sys.platform.startswith("win")


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


def abort(*args, **kwargs):
    """General wrapper for optionally fatal calls

    >>> from runez import abort
    >>> abort("foo")  # Raises AbortException
    foo
    runez.base.AbortException: 1
    >>> abort("foo", fatal=True) # Raises AbortException
    foo
    runez.base.AbortException: 1
    >>> # Not fatal, but will log/print message:
    >>> abort("foo", fatal=False)  # Returns False
    foo
    False
    >>> abort("foo", fatal=(False, None))  # Returns None
    foo
    >>> abort("foo", fatal=(False, -1)) # Returns -1
    foo
    -1
    >>> # Not fatal, will not log/print any message:
    >>> abort("foo", fatal=None)  # Returns None
    >>> abort("foo", fatal=(None, None))  # Returns None
    >>> abort("foo", fatal=(None, -1))  # Returns -1
    -1

    Args:
        *args: Args passed through for error reporting
        **kwargs: Args passed through for error reporting

    Returns:
        kwargs["return_value"] (default: -1) to signify failure to non-fatal callers
    """
    code = kwargs.pop("code", 1)
    logger = kwargs.pop("logger", LOG.error if code else LOG.info)
    fatal = kwargs.pop("fatal", True)
    return_value = fatal

    if isinstance(fatal, tuple) and len(fatal) == 2:
        fatal, return_value = fatal

    if logger and fatal is not None and args:
        if logging.root.handlers:
            logger(*args, **kwargs)

        else:
            sys.stderr.write("%s\n" % _formatted_string(*args))

    if fatal:
        if isinstance(fatal, type) and issubclass(fatal, BaseException):
            raise fatal(code)

        if AbortException is not None:
            if isinstance(AbortException, type) and issubclass(AbortException, BaseException):
                raise AbortException(code)

            return AbortException(code)

    return return_value


def actual_caller_frame(f):
    """Return `f` if it's a frame that looks like coming from actual caller (not runez itself, or an internal library package)"""
    name = f.f_globals.get("__name__")
    if name and "__main__" in name:
        return f

    package = f.f_globals.get("__package__")
    if package and not package.startswith("_") and package.partition(".")[0] not in ("importlib", "pluggy", "runez"):
        return f


def auto_import_siblings(auto_clean="TOX_WORK_DIR", skip=None):
    """Auto-import all sibling submodules from caller.

    This is handy for click command groups for example.
    It allows to avoid having to have a module that simply lists all sub-commands, just to ensure they are added to `main`.

    - ./my_cli.py::

        @click.group()
        def main(...):
            ...

        runez.auto_import_siblings()

    - ./my_sub_command.py::

        from .my_cli import main

        @main.command()  # The auto-import will trigger importing this without further ado
        def foo(...):
            ...

    Args:
        auto_clean (str | bool | None): If provided, auto-clean `.pyc`` files
        skip (list | None): Do not auto-import specified modules

    Returns:
        (list): List of imported modules, if any
    """
    caller = find_caller_frame()
    if not caller:
        raise ImportError("Could not determine caller, can't auto-import")

    if caller.f_globals.get("__name__") == "__main__":
        raise ImportError("Calling auto_import_siblings() from __main__ is not supported: %s" % caller)

    caller_package = caller.f_globals.get("__package__")
    if not caller_package:
        raise ImportError("Could not determine caller's __package__, can't auto-import: %s" % caller)

    caller_path = caller.f_globals.get("__file__")
    if not caller_path:
        raise ImportError("Could not determine caller's __file__, can't auto-import: %s" % caller)

    folder = os.path.dirname(caller_path)
    if not os.path.isdir(folder):
        raise ImportError("Caller's __file__ points to a non-existing directory, can't auto-import: %s" % caller)

    if auto_clean is not None and not isinstance(auto_clean, bool):
        auto_clean = os.environ.get(auto_clean)

    if auto_clean:
        # Clean .pyc files so consecutive tox runs with distinct python2 versions don't get confused
        _clean_files(folder, ".pyc")

    import pkgutil

    imported = []
    for loader, module_name, _ in pkgutil.walk_packages([folder], prefix="%s." % caller_package):
        if _should_auto_import(module_name, skip):
            __import__(module_name)
            imported.append(module_name)

    return imported


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


def current_test():
    """
    Returns:
        (str): Not empty if we're currently running a test (such as via pytest)
               Actual value will be path to test_<name>.py file if user followed usual conventions,
               otherwise path to first found test-framework module
    """
    import re
    regex = re.compile(r"^(.+\.|)(conftest|(test_|_pytest\.|unittest\.).+|.+_test)$")

    def test_frame(f):
        name = f.f_globals.get("__name__").lower()
        if not name.startswith("runez"):
            return regex.match(name) and f.f_globals.get("__file__")

    return find_caller_frame(test_frame)


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


def find_caller_frame(validator=actual_caller_frame, depth=2, maximum=None):
    """
    Args:
        validator (callable): Function that will decide whether a frame is suitable, and return value of interest from it
        depth (int): Depth from top of stack where to start
        maximum (int | None): Maximum depth to scan

    Returns:
        (frame): First frame found
    """
    if hasattr(sys, "_getframe"):
        while not maximum or depth <= maximum:
            try:
                f = sys._getframe(depth)
                value = validator(f)
                if value is not None:
                    return value

                depth = depth + 1

            except ValueError:
                return None


def first_meaningful_line(text, default=None):
    """
    Args:
        text (str | None): Text to examine
        default (str): Default to return if no meaningful line found in `text`

    Returns:
        (str | None): First non-empty line, if any
    """
    if text:
        for line in text.splitlines():
            line = line.strip()
            if line:
                return line

    return default


def find_parent_folder(path, basenames):
    """
    Args:
        path (str): Path to examine, first parent folder with basename in `basenames` is returned (case insensitive)
        basenames (set): List of acceptable basenames (must be lowercase)

    Returns:
        (str | None): Path to first containing folder of `path` with one of the `basenames`
    """
    if not path or len(path) <= 1:
        return None

    dirpath, basename = os.path.split(path)
    if basename and basename.lower() in basenames:
        return path

    return find_parent_folder(dirpath, basenames)


def flattened(value, split=None):
    """
    Args:
        value: Possibly nested arguments (sequence of lists, nested lists)
        split (int | str | unicode | (str | unicode | None, int) | None): How to split values:
            - None: simply flatten, no further processing
            - one char string: split() on specified char
            - SANITIZED: discard all None items
            - UNIQUE: each value will appear only once
            - SHELL:  filter out sequences of the form ["-f", None] (handy for simplified cmd line specification)

    Returns:
        (list): 'value' flattened out (leaves from all involved lists/tuples)
    """
    result = []
    separator = None
    mode = 0
    if isinstance(split, tuple):
        separator, mode = split

    elif isinstance(split, int):
        mode = split

    else:
        separator = split

    _flatten(result, value, separator, mode)
    return result


def get_version(mod, default="0.0.0", logger=LOG.warning):
    """
    Args:
        mod (module | str): Module, or module name to find version for (pass either calling module, or its .__name__)
        default (str): Value to return if version determination fails
        logger (callable | None): Logger to use to report inability to determine version

    Returns:
        (str): Determined version
    """
    name = mod
    if hasattr(mod, "__name__"):
        name = mod.__name__

    if not name:
        return default

    module_name = name
    try:
        import pkg_resources

        module_name = name.partition(".")[0]
        return pkg_resources.get_distribution(module_name).version

    except Exception as e:
        if logger and module_name != "tests":
            logger("Can't determine version for %s: %s", name, e, exc_info=e)

        return default


def is_dryrun():
    """
    Returns:
        (bool): Same as runez.DRYRUN, but as a function (and with late import)
    """
    return _get_runez().DRYRUN


def is_tty():
    """
    Returns:
        (bool): True if current stdout is a tty
    """
    return (sys.stdout.isatty() or "PYCHARM_HOSTED" in os.environ) and not current_test()


def quoted(text):
    """Quoted `text`, if it contains whitespaces

    >>> quoted("foo")
    'foo'
    >>> quoted("foo bar")
    '"foo bar"'

    Args:
        text (str | unicode | None): Text to optionally quote

    Returns:
        (str): Quoted if 'text' contains spaces
    """
    if text and " " in text:
        sep = "'" if '"' in text else '"'
        return "%s%s%s" % (sep, text, sep)

    return text


def set_dryrun(dryrun):
    """Set runez.DRYRUN, and return its previous value (useful for context managers)

    Args:
        dryrun (bool): New value for runez.DRYRUN

    Returns:
        (bool): Old value
    """
    r = _get_runez()
    old = r.DRYRUN
    r.DRYRUN = bool(dryrun)
    return old


def stringified(value, converter=None, none="None"):
    """
    Args:
        value: Any object to turn into a string
        converter (callable | None): Optional converter to use for non-string objects
        none (str): String to use to represent `None`

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

    if value is None:
        return none

    return "%s" % value


class AbortException(Exception):
    """Raised when calls fail, in runez functions with argument `fatal=True`.

    You can replace this with your preferred exception, for example:

    >>> import runez
    >>> runez.base.AbortException = SystemExit
    """

    def __init__(self, code):
        self.code = code


class AdaptedProperty(object):
    """
    This decorator allows to define properties with regular get/set behavior,
    but the body of the decorated function can act as a validator, and can auto-convert given values

    Example usage:
        >>> from runez import AdaptedProperty
        >>> class MyObject:
        ...     age = AdaptedProperty(default=5)  # Anonymous property
        ...
        ...     @AdaptedProperty           # Simple adapted property
        ...     def width(self, value):
        ...         if value is not None:  # Implementation of this function acts as validator and adapter
        ...             return int(value)  # Here we turn value into an int (will raise exception if not possible)
        ...
        >>> my_object = MyObject()
        >>> assert my_object.age == 5  # Default value
        >>> my_object.width = "10"     # Implementation of decorated function turns this into an int
        >>> assert my_object.width == 10
    """
    __counter = [0]  # Simple counter for anonymous properties

    def __init__(self, validator=None, default=None, doc=None, caster=None, type=None):
        """
        Args:
            validator (callable | str | None): Function to use to validate/adapt passed values, or name of property
            default: Default value
            doc (str): Doctring (applies to anonymous properties only)
            caster (callable): Optional caster called for non-None values only (applies to anonymous properties only)
            type (type): Optional type, must have initializer with one argument if provided
        """
        self.default = default
        self.caster = caster
        self.type = type
        assert caster is None or type is None, "Can't accept both 'caster' and 'type' for AdaptedProperty, pick one"
        if callable(validator):
            # 'validator' is available when used as decorator of the form: @AdaptedProperty
            assert caster is None and type is None, "'caster' and 'type' are not applicable to AdaptedProperty decorator"
            self.validator = validator
            self.__doc__ = validator.__doc__
            self.key = "__%s" % validator.__name__

        else:
            # 'validator' is NOT available when decorator of this form is used: @AdaptedProperty(default=...)
            # or as an anonymous property form: my_prop = AdaptedProperty()
            self.validator = None
            self.__doc__ = doc
            if validator is None:
                i = self.__counter[0] = self.__counter[0] + 1
                validator = "anon_prop_%s" % i

            self.key = "__%s" % validator

    def __call__(self, validator):
        """Called when used as decorator of the form: @AdaptedProperty(default=...)"""
        assert self.caster is None and self.type is None, "'caster' and 'type' are not applicable to decorated properties"
        self.validator = validator
        self.__doc__ = validator.__doc__
        self.key = "__%s" % validator.__name__
        return self

    def __get__(self, obj, cls):
        if obj is None:
            return self  # We're being called by class

        return getattr(obj, self.key, self.default)

    def __set__(self, obj, value):
        if self.validator is not None:
            value = self.validator(obj, value)

        elif self.type is not None:
            if not isinstance(value, self.type):
                value = self.type(value)

        elif value is not None and self.caster is not None:
            value = self.caster(value)

        setattr(obj, self.key, value)


class Slotted(object):
    """This class allows to easily initialize/set a descendant using named arguments"""

    def __init__(self,  *positionals, **kwargs):
        """
        Args:
            *positionals: Optionally provide positional objects to extract values from, when possible
            **kwargs: Override one or more of this classes' fields (keys must refer to valid slots)
        """
        self._seed()
        self.set(*positionals, **kwargs)

    def __repr__(self):
        return "%s(%s)" % (self.__class__.__name__, self.represented_values())

    @classmethod
    def cast(cls, obj):
        """Cast `obj` to instance of this type, via positional setter"""
        if isinstance(obj, cls):
            return obj

        return cls(obj)

    def represented_values(self, delimiter=", ", separator="=", include_none=True, name_formatter=None):
        """
        Args:
            delimiter (str): Delimiter used to separate field representation
            separator (str): Separator for field=value pairs
            include_none (bool): Included `None` values?
            name_formatter (callable | None): If provided, called to transform 'field' for each field=value pair

        Returns:
            (str): Textual representation of the form field=value
        """
        result = []
        for name in self.__slots__:
            value = getattr(self, name, UNSET)
            if value is not UNSET and (include_none or value is not None):
                if name_formatter is not None:
                    name = name_formatter(name)

                result.append("%s%s%s" % (name, separator, stringified(value)))

        return delimiter.join(result)

    def get(self, key, default=None):
        """This makes Slotted objects able to mimic dict's get() function

        Args:
            key (str | None): Field name (on defined in __slots__)
            default: Default value to return if field is currently undefined (or UNSET)

        Returns:
            Value of field with 'key'
        """
        if key is not None:
            value = getattr(self, key, default)
            if value is not UNSET:
                return value

        return default

    def set(self, *positionals, **kwargs):
        """Conveniently set one or more fields at a time.

        Args:
            *positionals: Optionally set from other objects, available fields from the passed object are used in order
            **kwargs: Set from given key/value pairs (only names defined in __slots__ are used)
        """
        for positional in positionals:
            if positional is not UNSET:
                values = self._values_from_positional(positional)
                if values:
                    for k, v in values.items():
                        if v is not UNSET and kwargs.get(k) in (None, UNSET):
                            # Positionals take precedence over None and UNSET only
                            kwargs[k] = v

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
        """dict: Key/value pairs of defined fields"""
        result = {}
        for name in self.__slots__:
            val = getattr(self, name, UNSET)
            if val is not UNSET:
                result[name] = val

        return result

    def __iter__(self):
        """Iterate over all defined values in this object"""
        for name in self.__slots__:
            val = getattr(self, name, UNSET)
            if val is not UNSET:
                yield val

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            for name in self.__slots__:
                if getattr(self, name, None) != getattr(other, name, None):
                    return False

            return True

    if PY2:
        def __cmp__(self, other):  # Applicable only for py2
            if isinstance(other, self.__class__):
                for name in self.__slots__:
                    i = cmp(getattr(self, name, None), getattr(other, name, None))  # noqa
                    if i != 0:
                        return i

                return 0

    def _seed(self):
        """Seed initial fields"""
        defaults = self._get_defaults()
        if not isinstance(defaults, dict):
            defaults = dict((k, defaults) for k in self.__slots__)

        for name in self.__slots__:
            value = getattr(self, name, defaults.get(name))
            setattr(self, name, value)

    def _set_field(self, name, value):
        setattr(self, name, value)

    def _get_defaults(self):
        """dict|Undefined|None: Optional defaults"""

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

            setter = getattr(self, "set_%s" % name, None)
            if setter is not None:
                setter(value)

            else:
                self._set_field(name, value)

    def _values_from_positional(self, positional):
        """dict: Key/value pairs from a given position to set()"""
        if isinstance(positional, string_type):
            return self._values_from_string(positional)

        if isinstance(positional, dict):
            return positional

        if isinstance(positional, Slotted):
            return positional.to_dict()

        return self._values_from_object(positional)

    def _values_from_string(self, text):
        """dict: Optional hook to allow descendants to extract key/value pairs from a string"""

    def _values_from_object(self, obj):
        """dict: Optional hook to allow descendants to extract key/value pairs from an object"""
        if obj is not None:
            return dict((k, getattr(obj, k, UNSET)) for k in self.__slots__)


class ThreadGlobalContext(object):
    """Thread-local + global context, composed of key/value pairs.

    Thread-local context is a dict per thread (stored in a threading.local()).
    Global context is a simple dict (applies to all threads).
    """

    def __init__(self, filter_type):
        """
        Args:
            filter_type (type): Class to instantiate as filter
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
        """dict: Combined global and thread-specific logging context"""
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


# We have to import 'runez' late when running in runez itself (because runez.__init__ imports everything to expose it)
_runez_module = None


def _clean_files(folder, extension):
    """Clean all files with `extension` from `folder`"""
    for root, dirs, files in os.walk(folder):
        for fname in files:
            if fname.endswith(extension):  # pragma: no cover, only applicable for local development
                try:
                    os.unlink(os.path.join(root, fname))

                except OSError:
                    pass  # Delete is only needed in tox run, no need to fail if delete is not possible


def _flatten(result, value, separator, mode):
    """
    Args:
        result (list): Will hold all flattened values
        value: Possibly nested arguments (sequence of lists, nested lists)
        separator (str | unicode | None): Split values with `separator` if specified
        mode (int): Describes how keep flattenened values

    Returns:
        list: 'value' flattened out (leaves from all involved lists/tuples)
    """
    if value is None or value is UNSET:
        if mode & SHELL:
            # Convenience: allow to filter out ["--switch", None] easily
            if result and result[-1].startswith("-"):
                result.pop(-1)

            return

        if mode & SANITIZED:
            return

    if value is not None:
        if isinstance(value, (list, tuple, set)):
            for item in value:
                _flatten(result, item, separator, mode)

            return

        if separator and hasattr(value, "split") and separator in value:
            _flatten(result, value.split(separator), separator, mode)
            return

        if mode & SHELL:
            value = "%s" % value

    if (mode & UNIQUE == 0) or value not in result:
        result.append(value)


def _formatted_string(*args):
    if not args:
        return ""

    message = args[0]
    if len(args) == 1:
        return message

    try:
        return message % args[1:]

    except TypeError:
        return message


def _get_runez():
    global _runez_module
    if _runez_module is None:
        import runez

        _runez_module = runez

    return _runez_module


def _should_auto_import(module_name, skip):
    """
    Args:
        module_name (str): Module being auto-imported
        skip (list | None): Modules to NOT auto-import

    Returns:
        (bool): True if we should auto-import `module_name`
    """
    if not module_name.endswith("_"):
        if skip and any(module_name.startswith(x) for x in skip):
            return False

        return True


def _walk_descendants(result, ancestor, adjust, root):
    for m in ancestor.__subclasses__():
        name = adjust(m, root)
        if name is not None:
            result[name] = m
        _walk_descendants(result, m, adjust, root)
