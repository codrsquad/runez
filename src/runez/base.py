"""
Base functionality used by other parts of runez

We track here whether we're running in dryrun mode, convenience logging etc
"""

import os

try:
    string_type = basestring  # noqa

except NameError:
    string_type = str
    unicode = str


HOME = os.path.expanduser("~")


class State:
    """Helps track state without importing/dealing with globals"""

    dryrun = False
    anchors = []  # Folder paths that can be used to shorten paths, via short()

    output = True  # print() warning/error messages (can be turned off when/if we have a logger to console for example)
    testing = False  # print all messages instead of logging (useful when running tests)
    logging = False  # Set to True if logging was setup


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
