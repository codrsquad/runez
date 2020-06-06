"""
Base functionality used by other parts of `runez`.

This class should not import any other `runez` class, to avoid circular deps.
"""

import logging
import os
import re
import sys
import threading


try:
    string_type = basestring  # noqa

    import StringIO
    StringIO = StringIO.StringIO
    PY2 = True

except NameError:
    string_type = str

    from io import StringIO
    PY2 = False


LOG = logging.getLogger("runez")
SYMBOLIC_TMP = "<tmp>"
WINDOWS = sys.platform.startswith("win")
RE_FORMAT_MARKERS = re.compile(r"{([^}]*?)}")
RE_SPACES = re.compile(r"[\s\n]+", re.MULTILINE)


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


def abort(message, code=1, exc_info=None, return_value=None, fatal=True, logger=UNSET):
    """General wrapper for optionally fatal calls

    >>> from runez import abort
    >>> abort("foo")  # Raises AbortException
    foo
    runez.system.AbortException: 1
    >>> abort("foo", fatal=True) # Raises AbortException
    foo
    runez.system.AbortException: 1
    >>> # Not fatal, but will log/print message:
    >>> abort("foo", fatal=False)  # Returns False
    foo
    False
    >>> abort("foo", fatal=False)  # Returns None
    foo
    >>> abort("foo", return_value=-1, fatal=False)  # Returns -1
    foo
    -1
    >>> # Not fatal, will not log/print any message:
    >>> abort("foo", fatal=None)  # Returns None
    >>> abort("foo", return_value=-1, fatal=None)  # Returns -1
    -1

    Args:
        message (str): Message explaining why we're aborting
        code (int): Exit code used when runez.system.AbortException is set to SystemExit
        exc_info (Exception): Exception info to pass on to logger
        return_value (Any): Value to return when `fatal` is not True
        fatal (bool | None): True: abort execution, False: don't abort but log, None: don't abort, don't log
        logger (callable | None): Logger to use, or None to disable log chatter

    Returns:
        Given `return_value`
    """
    if exc_info is not None:
        message = "%s: %s" % (message, exc_info)

    if logger is not None and fatal is not None:
        _show_abort_message(message, exc_info, fatal, logger)

    if fatal:
        exception = _R.abort_exception(override=fatal)
        if exception is not None:
            if logger is None and exception is SystemExit:
                _show_abort_message(message, exc_info, fatal, logger)  # Must show message if we're about to raise SystemExit

            _raise(exception, code)  # Raise from dedicated function to reduce stack trace shown in tests

    return return_value


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

    if isinstance(value, bytes):
        value = value.decode("utf-8")

    if strip:
        value = value.strip()

    return value


def expanded(text, *args, **kwargs):
    """Generically expanded 'text': '{...}' placeholders are resolved from given objects / keyword arguments

    >>> expanded("{foo}", foo="bar")
    'bar'
    >>> expanded("{foo} {age}", {"age": 5}, foo="bar")
    'bar 5'

    Args:
        text (str): Text to format
        *args: Objects to extract values from (as attributes)
        **kwargs: Optional values provided as named args

    Returns:
        (str): '{...}' placeholders expanded from given `args` object's properties/fields, or as `kwargs`
    """
    if not text or "{" not in text:
        return text

    strict = kwargs.pop("strict", True)
    max_depth = kwargs.pop("max_depth", 3)
    objects = list(args) + [kwargs] if kwargs else args[0] if len(args) == 1 else args
    if not objects:
        return text

    definitions = {}
    markers = RE_FORMAT_MARKERS.findall(text)
    while markers:
        key = markers.pop()
        if key in definitions:
            continue

        val = _find_value(key, objects)
        if strict and val is None:
            return None

        val = stringified(val) if val is not None else "{%s}" % key
        markers.extend(m for m in RE_FORMAT_MARKERS.findall(val) if m not in definitions)
        definitions[key] = val

    if not max_depth or not isinstance(max_depth, int) or max_depth <= 0:
        return text

    result = dict((k, _rformat(k, v, definitions, max_depth)) for k, v in definitions.items())
    return text.format(**result)


def find_caller_frame(validator=None, depth=2, maximum=1000):
    """
    Args:
        validator (callable): Function that will decide whether a frame is suitable, and return value of interest from it
        depth (int): Depth from top of stack where to start
        maximum (int | None): Maximum depth to scan

    Returns:
        (frame): First frame found
    """
    if hasattr(sys, "_getframe"):
        if validator is None:
            validator = _is_actual_caller_frame

        while not maximum or depth <= maximum:
            try:
                f = sys._getframe(depth)
                value = validator(f)
                if value is not None:
                    return value

                depth = depth + 1

            except ValueError:
                return None


def first_line(text, keep_empty=False, strip=True, default=None):
    """First line in 'data', if any

    Args:
        text (str | list | None): Text to examine
        keep_empty (bool): If False, skip empty lines
        strip (bool): If True, strip lines from leading/trailing spaces/newlines
        default (str | None): Default to return if there was no first line

    Returns:
        (str | None): First line, if any
    """
    if text is None:
        return default

    if hasattr(text, "splitlines"):
        text = text.splitlines()

    for line in text:
        if strip:
            line = line.strip()

        if keep_empty or line:
            return line

    return default


def flattened(value, split=None, sanitized=False, shellify=False, unique=False):
    """
    Args:
        value: Possibly nested arguments (sequence of lists, nested lists, ...)
        split (str | None): If provided, split strings by given character
        sanitized (bool): If True, filter out None values
        shellify (bool): If True, filter out sequences of the form ["-f", None] (handy for simplified cmd line specification)
        unique (bool): If True, ensure every value appears only once

    Returns:
        (list): Flattened list from 'value'
    """
    result = []
    _flatten(result, value, split, sanitized, shellify, unique)
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


def is_tty():
    """
    Returns:
        (bool): True if current stdout is a tty
    """
    return (sys.stdout.isatty() or "PYCHARM_HOSTED" in os.environ) and not _R.current_test()


def quoted(items, delimiter=" ", adapter=UNSET, keep_empty=True):
    """Quoted `items`, for those that contain whitespaces

    >>> quoted("foo")
    'foo'
    >>> quoted("foo bar")
    '"foo bar"'
    >>> quoted(["foo", "foo bar"])
    'foo "foo bar"'

    Args:
        items (str | list | tuple | None): Text, or list of text to optionally quote
        delimiter (str): Delimiter to use to join args back
        adapter (callable | None): Called for every item if provided, it should return a string
        keep_empty (bool): If False, skip empty items

    Returns:
        (str): Quoted if 'text' contains spaces
    """
    if items is None or isinstance(items, string_type):
        items = [items]

    result = []
    for text in items:
        if adapter is UNSET:
            text = Anchored.short(stringified(text))

        elif adapter is not None:
            text = adapter(text)

        if text and " " in text:
            sep = "'" if '"' in text else '"'
            text = "%s%s%s" % (sep, text, sep)

        if keep_empty or text:
            result.append(text)

    return delimiter.join(result)


def resolved_path(path, base=None):
    """
    Args:
        path (str | None): Path to resolve
        base (str | None): Base path to use to resolve relative paths (default: current working dir)

    Returns:
        (str): Absolute path
    """
    if not path or path.startswith(SYMBOLIC_TMP):
        return path

    path = os.path.expanduser(path)
    if base and not os.path.isabs(path):
        return os.path.join(resolved_path(base), path)

    return os.path.abspath(path)


def short(value, size=1024, none="None"):
    """
    Args:
        value: Value to textually represent in a shortened form
        size (int | None): Max chars
        none (str): String to use to represent `None`

    Returns:
        (str): Leading part of text, with at most 'size' chars (when specified)
    """
    text = stringified(value, converter=_prettified, none=none).strip()
    text = RE_SPACES.sub(" ", text)
    text = Anchored.short(text)
    if size and len(text) > size:
        return "%s..." % text[:size - 3]

    return text


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

    if isinstance(value, bytes):
        return value.decode("utf-8")

    if converter is not None:
        converted = converter(value)
        if isinstance(converted, string_type):
            return converted

        if converted is not None:
            value = converted

    if value is None:
        return none

    return "{}".format(value)


class AbortException(Exception):
    """Raised when calls fail, in runez functions with argument `fatal=True`.

    You can replace this with your preferred exception, for example:

    >>> import runez
    >>> runez.system.AbortException = SystemExit
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


class Anchored(object):
    """
    An "anchor" is a known path that we don't wish to show in full when printing/logging
    This allows to conveniently shorten paths, and show more readable relative paths
    """

    _home = None
    _paths = []  # Currently stacked anchored folders that can be simplified away, via short()

    def __init__(self, folder):
        self.folder = resolved_path(folder)

    def __enter__(self):
        Anchored.add(self.folder)

    def __exit__(self, *_):
        Anchored.pop(self.folder)

    @classmethod
    def set(cls, *anchors):
        """
        Args:
            *anchors (str | list): Optional paths to use as anchors for short()
        """
        cls._paths = sorted(flattened(anchors, sanitized=True, unique=True), reverse=True)

    @classmethod
    def add(cls, anchors):
        """
        Args:
            anchors (str | list): Optional paths to use as anchors for short()
        """
        cls.set(cls._paths, anchors)

    @classmethod
    def pop(cls, anchors):
        """
        Args:
            anchors (str | list): Optional paths to use as anchors for short()
        """
        for anchor in flattened(anchors, sanitized=True, unique=True):
            if anchor in cls._paths:
                cls._paths.remove(anchor)

    @classmethod
    def short(cls, text):
        """
        Args:
            text (str): Text where to shorten paths

        Returns:
            (str): Short form, using '~' if applicable
        """
        if cls._home is None:
            cls._home = os.path.expanduser("~")

        if cls._paths:
            for p in cls._paths:
                if p:
                    text = text.replace(p + os.path.sep, "")

        return text.replace(cls._home, "~")


class CapturedStream(object):
    """Capture output to a stream by hijacking temporarily its write() function"""

    def __init__(self, name, target):
        self.name = name
        self.target = target
        self.buffer = StringIO()
        target_class = stringified(self.target.__class__).lower()
        self.capture_write = "_pytest" in target_class or "wrapper" in target_class
        if self.capture_write and self.target.write.__name__ == self.captured_write.__name__:
            self.capture_write = False

    def __repr__(self):
        return self.contents()

    def __contains__(self, item):
        return item is not None and item in self.contents()

    def __len__(self):
        return len(self.contents())

    def captured_write(self, message):
        self.buffer.write(message)

    def contents(self):
        """str: Contents of this capture"""
        return self.buffer.getvalue()

    def _start_capture(self):
        if self.capture_write:
            # setting sys.stdout doesn't survive with cross module fixtures, so we hijack its write the 1st time we see it
            self.original = self.target.write
            self.target.write = self.captured_write

        else:
            self.original = getattr(sys, self.name)
            setattr(sys, self.name, self.buffer)

    def _stop_capture(self):
        if self.capture_write:
            self.target.write = self.original

        else:
            setattr(sys, self.name, self.original)

    def assert_printed(self, expected):
        """Assert that 'expected' matches current output exactly (modulo trailing spaces/newlines), and clear current capture"""
        content = self.pop()
        assert content == expected

    def pop(self):
        """Current content popped, useful for testing"""
        r = self.contents()
        self.clear()
        return r.strip()

    def clear(self):
        """Clear captured content"""
        self.buffer.seek(0)
        self.buffer.truncate(0)


class CaptureOutput(object):
    """Output is captured and made available only for the duration of the context.

    Sample usage:

    >>> with CaptureOutput() as logged:
    >>>     print("foo bar")
    >>>     # output has been captured in `logged`, see `logged.stdout` etc
    >>>     assert "foo" in logged
    >>>     assert "bar" in logged.stdout
    """

    _capture_stack = []  # Shared across all objects, tracks possibly nested CaptureOutput buffers

    def __init__(self, stdout=True, stderr=True, anchors=None, dryrun=UNSET, seed_logging=False):
        """Context manager allowing to temporarily grab stdout/stderr/log output.

        Args:
            stdout (bool): Capture stdout?
            stderr (bool): Capture stderr?
            anchors (str | list | None): Optional paths to use as anchors for `runez.short()`
            dryrun (bool): Optionally override current dryrun setting
            seed_logging (bool): If True, ensure there is at least one logging handler configured
        """
        self.stdout = stdout
        self.stderr = stderr
        self.anchors = anchors
        self.dryrun = dryrun
        self.seed_logging = seed_logging
        self.handler = None

    @classmethod
    def current_capture_buffer(cls):
        if cls._capture_stack:
            return cls._capture_stack[-1].buffer

    def _has_stream_handler(self):
        for h in logging.root.handlers:
            if isinstance(h, logging.StreamHandler) or getattr(h, "isolation", None) == 0:
                return True

    def __enter__(self):
        """
        Returns:
            (TrackedOutput): Object holding captured stdout/stderr/log output
        """
        self.dryrun = _R.set_dryrun(self.dryrun)
        self.tracked = TrackedOutput(
            CapturedStream("stdout", sys.stdout) if self.stdout else None,
            CapturedStream("stderr", sys.stderr) if self.stderr else None,
        )

        for c in self.tracked.captured:
            c._start_capture()

        if self.tracked.captured:
            self._capture_stack.append(self.tracked.captured[-1])

        if self.anchors:
            Anchored.add(self.anchors)

        if self.seed_logging and not self._has_stream_handler():
            # Define a logging handler, IsolatedLogSetup cleared them all
            self.handler = logging.StreamHandler(stream=self.tracked.captured[-1].buffer)
            self.handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
            self.handler.setLevel(logging.DEBUG)
            logging.root.addHandler(self.handler)

        return self.tracked

    def __exit__(self, *args):
        _R.set_dryrun(self.dryrun)
        if self.tracked.captured:
            self._capture_stack.pop()

        for c in self.tracked.captured:
            c._stop_capture()

        if self.handler:
            logging.root.handlers.remove(self.handler)

        if self.anchors:
            Anchored.pop(self.anchors)


class CurrentFolder(object):
    """Context manager for changing the current working directory"""

    def __init__(self, destination, anchor=False):
        self.anchor = anchor
        self.destination = resolved_path(destination)

    def __enter__(self):
        self.current_folder = os.getcwd()
        os.chdir(self.destination)
        if self.anchor:
            Anchored.add(self.destination)

    def __exit__(self, *_):
        os.chdir(self.current_folder)
        if self.anchor:
            Anchored.pop(self.destination)


class TrackedOutput(object):
    """Track captured output"""

    def __init__(self, stdout, stderr):
        """
        Args:
            stdout (CapturedStream | None): Captured stdout
            stderr (CapturedStream | None): Captured stderr
        """
        self.stdout = stdout
        self.stderr = stderr
        self.captured = [c for c in (self.stdout, self.stderr) if c is not None]

    def __repr__(self):
        return "\n".join("%s: %s" % (s.name, s) for s in self.captured)

    def __contains__(self, item):
        return any(item in s for s in self.captured)

    def __len__(self):
        return sum(len(s) for s in self.captured)

    def contents(self):
        return "".join(s.contents() for s in self.captured)

    def assert_printed(self, expected):
        """Assert that 'expected' matches current stdout exactly (modulo trailing spaces/newlines), and clear current capture"""
        self.stdout.assert_printed(expected)
        if self.stderr is not None:
            self.stderr.clear()

    def pop(self):
        """Current content popped, useful for testing"""
        r = self.contents()
        self.clear()
        return r.strip()

    def clear(self):
        """Clear captured content"""
        for s in self.captured:
            s.clear()


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

    def represented_values(self, delimiter=", ", operator="=", include_none=True, name_formatter=None):
        """
        Args:
            delimiter (str): Delimiter used to separate field representation
            operator (str): Operator to represent assignment (equal sign '=' by default)
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

                result.append("%s%s%s" % (name, operator, stringified(value)))

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


class TempArgv(object):
    """Context manager for changing the current sys.argv"""

    def __init__(self, args, exe=sys.executable):
        self.args = args
        self.exe = exe
        self.old_argv = sys.argv

    def __enter__(self):
        sys.argv = [self.exe] + self.args

    def __exit__(self, *_):
        sys.argv = self.old_argv


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


class _R:
    """
    Internal class to provide a late import of runez (after __init__ imported everything), and also holds some common stuff.
    The name is intentionally short to avoid verbose/long lines calling it.
    _R stands for "runez, internal class"

    This internal class allows to make global settings such as runez.DRYRUN usable internally:
    - without having to `import runez` internally (can't do that due to circular import)
    - respecting any external modifications clients may have done (like: runez.DRYRUN = foo)
    """
    _runez = None
    _schema = None

    @classmethod
    def _runez_module(cls):
        """Late-imported runez module"""
        if cls._runez is None:
            import runez

            cls._runez = runez

        return cls._runez

    @classmethod
    def abort_exception(cls, override=None):
        """AbortException can be modified from client"""
        if isinstance(override, type) and issubclass(override, BaseException):
            return override

        return cls._runez_module().system.AbortException

    @classmethod
    def current_test(cls):
        return cls._runez_module().log.current_test()

    @classmethod
    def expanded_message(cls, message):
        if callable(message):
            message = message()  # Allow message to be late-called function

        return message

    @classmethod
    def hdef(cls, default, message, e=None):
        """Handle IO default

        Args:
            default (Any): The default value to return, if it is not UNSET
            message (str): Message explaining failure
            e (Exception): Exception, if this comes from a try/except block

        Returns:
            'default', if it is not UNSET
        """
        if default is UNSET:
            abort(cls.expanded_message(message), exc_info=e)

        return default

    @classmethod
    def hdry(cls, dryrun, logger, message):
        """Handle dryrun

        Args:
            logger (callable | None): Logger to use, or None to disable log chatter
            dryrun (bool): Optionally override current dryrun setting
            message (str | callable): Message to log

        Returns:
            (bool): True if we were indeed in dryrun mode, and we logged the message
        """
        if dryrun is UNSET:
            dryrun = cls.is_dryrun()

        if dryrun:
            if logger is not None and logger is not False:  # Accept UNSET
                message = "Would %s" % cls.expanded_message(message)
                if callable(logger):
                    logger(message)

                else:
                    print(message)

            return True

    @classmethod
    def hlog(cls, logger, message):
        """Handle optional logging calls via 'logger=' for IO-related non-returning-content functions, making them consistent.
        This allows to have less repeated code out there, find all places where we do this,
        and ensure they all respect the same convention.

        Args:
            logger (callable | None): Logger to use, or None to disable log chatter
            message (str | callable): Message to log
        """
        if logger is not None and logger is not False:  # Accept UNSET
            message = cls.expanded_message(message)
            if callable(logger):
                logger(message)

            else:
                LOG.debug(message)

    @classmethod
    def is_dryrun(cls):
        """
        Returns:
            (bool): Same as runez.DRYRUN, but as a function (and with late import)
        """
        return cls._runez_module().DRYRUN

    @classmethod
    def schema(cls):
        """Late-imported schema"""
        if cls._schema is None:
            import runez.schema

            cls._schema = runez.schema

        return cls._schema

    @classmethod
    def serializable(cls):
        """Late-imported Serializable class"""
        return cls._runez_module().Serializable

    @classmethod
    def set_dryrun(cls, dryrun):
        """Set runez.DRYRUN, and return its previous value (useful for context managers)

        Args:
            dryrun (bool | UNSET): New value for runez.DRYRUN

        Returns:
            (bool): Old values for dryrun
        """
        r = cls._runez_module()
        old_dryrun = r.DRYRUN
        if dryrun is not UNSET:
            r.DRYRUN = bool(dryrun)

        return old_dryrun


def _find_value(key, *args):
    """Find a value for 'key' in any of the objects given as 'args'"""
    for arg in args:
        v = _get_value(arg, key)
        if v is not None:
            return v


def _flatten(result, value, split, sanitized, shellify, unique):
    if value is None or value is UNSET:
        if shellify:
            # Convenience: allow to filter out ["--switch", None] easily
            if result and result[-1].startswith("-"):
                result.pop(-1)

            return

        if sanitized:
            return

    elif isinstance(value, (list, tuple, set)):
        for item in value:
            _flatten(result, item, split, sanitized, shellify, unique)

        return

    elif split and isinstance(value, string_type) and split in value:
        _flatten(result, value.split(split), split, sanitized, shellify, unique)
        return

    if shellify:
        value = "%s" % value  # coerce to str() for py2

    if not unique or value not in result:
        result.append(value)


def _get_value(obj, key):
    """Get a value for 'key' from 'obj', if possible"""
    if obj is not None:
        if isinstance(obj, (list, tuple)):
            for item in obj:
                v = _find_value(key, item)
                if v is not None:
                    return v

            return None

        if hasattr(obj, "get"):
            return obj.get(key)

        return getattr(obj, key, None)


def _is_actual_caller_frame(f):
    """Return `f` if it's a frame that looks like coming from actual caller (not runez itself, or an internal library package)"""
    name = f.f_globals.get("__name__")
    if name and "__main__" in name:
        return f

    package = f.f_globals.get("__package__")
    if package and not package.startswith("_") and package.partition(".")[0] not in ("importlib", "pluggy", "runez"):
        return f


def _prettified(value):
    if isinstance(value, list):
        return "[%s]" % ", ".join(stringified(s, converter=_prettified) for s in value)

    if isinstance(value, tuple):
        return "(%s)" % ", ".join(stringified(s, converter=_prettified) for s in value)

    if isinstance(value, dict):
        keys = sorted(value, key=lambda x: "%s" % x)
        pairs = ("%s: %s" % (stringified(k, converter=_prettified), stringified(value[k], converter=_prettified)) for k in keys)
        return "{%s}" % ", ".join(pairs)

    if isinstance(value, set):
        return "{%s}" % ", ".join(stringified(s, converter=_prettified) for s in sorted(value, key=lambda x: "%s" % x))

    if isinstance(value, type):
        return "class %s.%s" % (value.__module__, value.__name__)

    if callable(value):
        return "function '%s'" % value.__name__


def _raise(exception, code):
    if isinstance(exception, type) and issubclass(exception, BaseException):
        raise exception(code)


def _rformat(key, value, definitions, max_depth):
    if max_depth > 1 and value and "{" in value:
        value = value.format(**definitions)
        return _rformat(key, value, definitions, max_depth=max_depth - 1)

    return value


def _show_abort_message(message, exc_info, fatal, logger):
    if not fatal and callable(logger):
        logger(message, exc_info=exc_info)
        return

    if logging.root.handlers:
        LOG.error(message, exc_info=exc_info)

    else:
        sys.stderr.write("%s\n" % message)
