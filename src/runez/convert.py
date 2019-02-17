"""
This is module should not import any other runez module, it's the lowest on the import chain
"""

import os
import re


SYMBOLIC_TMP = "<tmp>"
RE_FORMAT_MARKERS = re.compile(r"{([^}]*?)}")


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


def formatted(text, *args, **kwargs):
    """
    :param str text: Text to format
    :param args: Objects to extract values from (as attributes)
    :param kwargs: Optional values provided as named args
    :return str: Attributes from this class are expanded if mentioned
    """
    objects = list(args) + [kwargs] if kwargs else args[0] if len(args) == 1 else args
    if not text or not objects:
        return text
    values = {}
    markers = RE_FORMAT_MARKERS.findall(text)
    while markers:
        key = markers.pop()
        if key in values:
            continue
        val = _find_value(key, objects)
        if val is None:
            return None
        markers.extend(m for m in RE_FORMAT_MARKERS.findall(val) if m not in values)
        values[key] = val
    for key, val in values.items():
        if '{' in val:
            values[key] = values[key].format(**values)
    return text.format(**values)


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


def resolved_path(path, base=None):
    """
    :param str|None path: Path to resolve
    :param str|None base: Base path to use to resolve relative paths (default: current working dir)
    :return str: Absolute path
    """
    if not path or path.startswith(SYMBOLIC_TMP):
        return path

    path = os.path.expanduser(path)
    if base and not os.path.isabs(path):
        return os.path.join(resolved_path(base), path)

    return os.path.abspath(path)


def short(path):
    return Anchored.short(path)


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


class Anchored:
    """
    An "anchor" is a known path that we don't wish to show in full when printing/logging
    This allows to conveniently shorten paths, and show more readable relative paths
    """

    paths = []  # Folder paths that can be used to shorten paths, via short()
    home = os.path.expanduser("~")

    def __init__(self, folder):
        self.folder = resolved_path(folder)

    def __enter__(self):
        Anchored.add(self.folder)

    def __exit__(self, *_):
        Anchored.pop(self.folder)

    @classmethod
    def set(cls, *anchors):
        """
        :param str|list anchors: Optional paths to use as anchors for short()
        """
        cls.paths = sorted(flattened(anchors, unique=True), reverse=True)

    @classmethod
    def add(cls, anchors):
        """
        :param str|list anchors: Optional paths to use as anchors for short()
        """
        cls.set(cls.paths, anchors)

    @classmethod
    def pop(cls, anchors):
        """
        :param str|list anchors: Optional paths to use as anchors for short()
        """
        for anchor in flattened(anchors):
            if anchor in cls.paths:
                cls.paths.remove(anchor)

    @classmethod
    def short(cls, path):
        """
        Example:
            short("examined /Users/joe/foo") => "examined ~/foo"

        :param path: Path to represent in its short form
        :return str: Short form, using '~' if applicable
        """
        if not path:
            return path

        path = str(path)
        if cls.paths:
            for p in cls.paths:
                if p:
                    path = path.replace(p + "/", "")

        path = path.replace(cls.home, "~")
        return path


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


def _get_value(obj, key):
    """Get a value for 'key' from 'obj', if possible"""
    if isinstance(obj, (list, tuple)):
        for item in obj:
            v = _find_value(key, item)
            if v is not None:
                return v
        return None
    if isinstance(obj, dict):
        return obj.get(key)
    if obj is not None:
        return getattr(obj, key, None)


def _find_value(key, *args):
    """Find a value for 'key' in any of the objects given as 'args'"""
    for arg in args:
        v = _get_value(arg, key)
        if v is not None:
            return v
