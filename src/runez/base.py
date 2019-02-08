"""
Base functionality used by other parts of runez

We track here whether we're running in dryrun mode, convenience logging etc
"""

import logging
import os
import sys

try:
    string_type = basestring  # noqa

except NameError:
    string_type = str
    unicode = str


LOG = logging.getLogger(__name__)
HOME = os.path.expanduser("~")


class State:
    """Helps track state without importing/dealing with globals"""

    dryrun = False
    anchors = []  # Folder paths that can be used to shorten paths, via short()

    output = True  # print() warning/error messages (can be turned off when/if we have a logger to console for example)
    testing = False  # print all messages instead of logging (useful when running tests)
    logging = False  # Set to True if logging was setup


def debug(message, *args, **kwargs):
    """
    Same as logging.debug(), but more convenient when testing (prints as well, on top of logging)
    """
    if State.logging:
        LOG.debug(message, *args, **kwargs)

    if State.testing:
        print(message % args)


def info(message, *args, **kwargs):
    """
    Often, an info() message should be logged, but also shown to user (in the even where logging is not done to console)

    Example:
        info("...") => Will log if we're logging, but also print() if State.output is currently set
        info("...", output=False) => Will only log, never print
        info("...", output=True) => Will log if we're logging, and print
    """
    output = kwargs.pop("output", State.output)
    if State.logging:
        LOG.info(message, *args, **kwargs)
    if output or State.testing:
        print(message % args)


def warning(message, *args, **kwargs):
    """Same as logging.warning(), but more convenient when testing, similar to info()"""
    if State.logging:
        LOG.warning(message, *args, **kwargs)
    if State.output or State.testing:
        print("WARNING: %s" % (message % args))


def error(message, *args, **kwargs):
    """Same as logging.error(), but more convenient when testing, similar to info()"""
    if State.logging:
        LOG.error(message, *args, **kwargs)
    if State.output or State.testing:
        print("ERROR: %s" % (message % args))


def abort(*args, **kwargs):
    """
    Usage:
        return abort("...") => will sys.exit() by default
        return abort("...", fatal=True) => Will sys.exit()

        # Not fatal, but will log/print message:
        return abort("...", fatal=False) => Will return False
        return abort("...", fatal=(False, None)) => Will return None
        return abort("...", fatal=(False, -1)) => Will return -1

        # Not fatal, will not log/print any message:
        return abort("...", fatal=None) => Will return None
        return abort("...", fatal=(None, None)) => Will return None
        return abort("...", fatal=(None, -1)) => Will return -1

    :param args: Args passed through for error reporting
    :param kwargs: Args passed through for error reporting
    :return: kwargs["return_value"] (default: -1) to signify failure to non-fatal callers
    """
    code = kwargs.pop("code", 1)
    logger = kwargs.pop("logger", error if code else info)
    fatal = kwargs.pop("fatal", True)
    return_value = fatal
    if isinstance(fatal, tuple) and len(fatal) == 2:
        fatal, return_value = fatal
    if logger and fatal is not None and args:
        logger(*args, **kwargs)
    if fatal:
        sys.exit(code)
    return return_value


try:
    from inspect import signature

    def _function_arguments(func):
        return signature(func).parameters

except ImportError:
    from inspect import getargspec

    def _function_arguments(func):
        return getargspec(func).args


class prop(object):
    """
    Decorator for settable cached properties.
    This comes in handy for properties you'd like to avoid computing multiple times,
    yet be able to arbitrarily change them as well, and be able to know when they get changed.

    This is a good fit for convenience setting classes, for example: runez.log.Settings
    It's not a good fit if what you're looking for is speed.
    """

    def __init__(self, func=None, tget=None, tset=None):
        """
        :param callable|None: Wrapped function, provided when decorator is used without arguments
        :param callable|None tget: Optional 'get' tracker, called when 'get' is performed
        :param callable|None tset: Optional 'set' tracker, called when 'set' is performed
        """
        self.function = None
        self.name = None
        self.tget = tget
        self.tset = tset
        if func:
            self._set_function(func)

    def __repr__(self):
        return self.name

    def __call__(self, func):
        self._set_function(func)
        return self

    def _set_function(self, func):
        self.function = func
        self.name = func.__name__
        self.field_name = "__%s" % self.name
        self.__doc__ = func.__doc__

    def _notify(self, instance, operation):
        if operation:
            func = operation.__func__ if isinstance(operation, classmethod) else operation
            sig = _function_arguments(func)
            args = []
            kwargs = {}
            if "instance" in sig:
                kwargs["instance"] = instance
            if "prop" in sig:
                kwargs["prop"] = self
            if "self" in sig:
                args.append(instance)
            elif "cls" in sig:
                args.append(instance.__class__)
            func(*args, **kwargs)

    def __get__(self, instance, cls=None):
        cached = getattr(instance, self.field_name, None)
        if cached is None:
            cached = self.function(instance)
            setattr(instance, self.field_name, cached)
            self._notify(instance, self.tget)
        return cached

    def __set__(self, instance, value):
        setattr(instance, self.field_name, value)
        self._notify(instance, self.tset)


def decode(value):
    """Python 2/3 friendly decoding of output"""
    if isinstance(value, bytes) and not isinstance(value, str):
        return value.decode("utf-8")
    return unicode(value)


def flattened(value, separator=None, unique=True):
    """
    :param value: Possibly nested arguments (sequence of lists, nested lists)
    :param str|None separator: Split values with 'separator' if specified
    :param bool unique: If True, return unique values only
    :return list: 'value' flattened out (leaves from all involved lists/tuples)
    """
    result = []
    _flatten(result, value, separator=separator, unique=unique)
    return result


def get_version(mod, default="0.0.0"):
    """
    :param module|str mod: Module, or module name to find version for (pass either calling module, or its .__name__)
    :param str default: Value to return if version determination fails
    :return str: Determined version
    """
    name = mod
    if hasattr(mod, "__name__"):
        name = mod.__name__

    try:
        import pkg_resources
        return pkg_resources.get_distribution(name).version

    except Exception as e:
        import logging
        logging.warning("Can't determine version for %s: %s", name, e, exc_info=e)
        return default


def quoted(text):
    """
    :param str|None text: Text to optionally quote
    :return str: Quoted if 'text' contains spaces
    """
    if text and " " in text:
        sep = "'" if '"' in text else '"'
        return "%s%s%s" % (sep, text, sep)
    return text


def represented_args(args, separator=" "):
    """
    :param list|tuple|None args: Arguments to represent
    :param str separator: Separator to use
    :return str: Quoted as needed textual representation
    """
    result = []
    if args:
        for text in args:
            result.append(quoted(short(text)))
    return separator.join(result)


def shortened(text, size=120):
    """
    :param str text: Text to shorten
    :param int size: Max chars
    :return str: Leading part of 'text' with at most 'size' chars
    """
    if text:
        text = text.strip()
        if len(text) > size:
            return "%s..." % text[:size - 3].strip()
    return text


def short(path):
    """
    Example:
        short("examined /Users/joe/foo") => "examined ~/foo"

    :param path: Path to represent in its short form
    :return str: Short form, using '~' if applicable
    """
    if not path:
        return path

    path = str(path)
    if State.anchors:
        for p in State.anchors:
            if p:
                path = path.replace(p + "/", "")

    path = path.replace(HOME, "~")
    return path


def to_int(text, default=None):
    """
    :param text: Value to convert
    :param int|None default: Default to use if 'text' can't be parsed
    :return int:
    """
    try:
        return int(text)

    except (TypeError, ValueError):
        return default


def _flatten(result, value, separator=None, unique=True):
    """
    :param list result: Will hold all flattened values
    :param value: Possibly nested arguments (sequence of lists, nested lists)
    :param str|None separator: Split values with 'separator' if specified
    :param bool unique: If True, return unique values only
    """
    if not value:
        # Convenience: allow to filter out --foo None easily
        if value is None and not unique and result and result[-1].startswith("-"):
            result.pop(-1)
        return

    if isinstance(value, (list, tuple, set)):
        for item in value:
            _flatten(result, item, separator=separator, unique=unique)
        return

    if separator is not None and hasattr(value, "split") and separator in value:
        _flatten(result, value.split(separator), separator=separator, unique=unique)
        return

    if not unique or value not in result:
        result.append(value)
