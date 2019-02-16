"""
This is module should not import any other runez module, it's the lowest on the import chain
"""

import os


def short(path):
    return Anchored.short(path)


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


class Anchored:
    """
    An "anchor" is a known path that we don't wish to show in full when printing/logging
    This allows to conveniently shorten paths, and show more readable relative paths
    """

    paths = []  # Folder paths that can be used to shorten paths, via short()
    home = os.path.expanduser("~")

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
