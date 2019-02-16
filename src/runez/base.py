"""
Base functionality used by other parts of runez

We track here whether we're running in dryrun mode, convenience logging etc
"""

from __future__ import absolute_import

import inspect
import logging
import time

from runez.state import short


try:
    string_type = basestring  # noqa

except NameError:
    string_type = str
    unicode = str


LOG = logging.getLogger(__name__)


class State:
    """Helps track state without importing/dealing with globals"""

    dryrun = False


class AbortException(Exception):
    """
    You can replace this with your preferred exception, for example:

        runez.base.AbortException = SystemExit
    """
    def __init__(self, code):
        self.code = code


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
    logger = kwargs.pop("logger", LOG.error if code else LOG.info)
    fatal = kwargs.pop("fatal", True)
    return_value = fatal
    if isinstance(fatal, tuple) and len(fatal) == 2:
        fatal, return_value = fatal
    if logger and fatal is not None and args:
        logger(*args, **kwargs)
    if fatal:
        if isinstance(fatal, type) and issubclass(fatal, BaseException):
            raise fatal(code)
        if AbortException is not None:
            if isinstance(AbortException, type) and issubclass(AbortException, BaseException):
                raise AbortException(code)
            return AbortException(code)
    return return_value


def decode(value):
    """Python 2/3 friendly decoding of output"""
    if isinstance(value, bytes) and not isinstance(value, str):
        return value.decode("utf-8")
    return unicode(value)


def get_timezone():
    try:
        return time.tzname[0]
    except (IndexError, TypeError):
        return ""


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
        LOG.warning("Can't determine version for %s: %s", name, e, exc_info=e)
        return default


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
        cached = getattr(instance, self.field_name, None)
        if cached is None:
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


_get_function_signature = None


def _has_arg(func, arg_name):
    """
    :param function func: Function to examine
    :param str arg_name: Argument name
    :return bool: True if 'func' has an argument called 'prop'
    """
    global _get_function_signature
    if _get_function_signature is None:
        try:
            # python 3
            from inspect import signature

            def _get_function_signature(x):
                return signature(x).parameters

        except ImportError:
            # python 2
            from inspect import getargspec

            def _get_function_signature(x):
                return getargspec(x).args

    sig = _get_function_signature(func)
    return arg_name in sig


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
