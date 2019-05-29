"""
Convenience methods for (de)serializing objects
"""

import io
import json
import logging
import os

from runez.base import string_type
from runez.convert import resolved_path, short
from runez.path import ensure_folder
from runez.system import abort, is_dryrun

LOG = logging.getLogger(__name__)


def type_name(value):
    """
    :param value: Some object, or None
    :return str: Class name implementing 'value'
    """
    if value is None:
        return "None"

    if isinstance(value, string_type):
        return "str"

    return value.__class__.__name__


def same_type(t1, t2):
    """
    :return bool: True if 't1' and 't2' are of equivalent types
    """
    if isinstance(t1, string_type) and isinstance(t2, string_type):
        return True

    return type(t1) == type(t2)


class Serializable(object):
    """
    Serializable object
    """

    def __repr__(self):
        return getattr(self, "_source", "no source")

    @classmethod
    def from_json(cls, path, fatal=True, logger=None):
        """
        :param str path: Path to json file
        :param bool|None fatal: Abort execution on failure if True
        :param callable|None logger: Logger to use
        :return: Deserialized object
        """
        result = cls()
        result.load(path, fatal=fatal, logger=logger)
        return result

    def set_from_dict(self, data, source=None):
        """
        :param dict data: Set this object from deserialized 'dict'
        :param source: Source where 'data' came from (optional)
        """
        if source:
            self._source = source

        if not data:
            return

        for key, value in data.items():
            key = key.replace("-", "_")
            if not hasattr(self, key):
                LOG.debug("%s is not an attribute of %s", key, self.__class__.__name__)
                continue

            attr = getattr(self, key)
            if attr is not None and not same_type(value, attr):
                source = getattr(self, "_source", None)
                origin = " in %s" % source if source else ""
                LOG.debug("Wrong type '%s' for %s.%s%s, expecting '%s'", type_name(value), type_name(self), key, origin, type_name(attr))
                continue

            setattr(self, key, value)

    def reset(self):
        """
        Reset all fields of this object to class defaults
        """
        for name in self.__dict__:
            if name.startswith("_"):
                continue

            attr = getattr(self, name)
            setattr(self, name, attr and attr.__class__())

    def to_dict(self):
        """
        :return dict: This object serialized to a dict
        """
        result = {}
        for name in self.__dict__:
            if name.startswith("_"):
                continue

            key = name.replace("_", "-")
            attr = getattr(self, name)
            result[key] = attr.to_dict() if hasattr(attr, "to_dict") else attr

        return result

    def load(self, path=None, fatal=True, logger=None):
        """
        :param str|None path: Load this object from file with 'path' (default: self._path)
        :param bool|None fatal: Abort execution on failure if True
        :param callable|None logger: Logger to use
        """
        self.reset()
        if path:
            self._path = path
            self._source = short(path)

        else:
            path = getattr(self, "_path", None)

        if path:
            self.set_from_dict(read_json(path, default={}, fatal=fatal, logger=logger))

    def save(self, path=None, fatal=True, logger=None, sort_keys=True, indent=2):
        """
        :param str|None path: Save this serializable to file with 'path' (default: self._path)
        :param bool|None fatal: Abort execution on failure if True
        :param callable|None logger: Logger to use
        :param bool sort_keys: Sort keys
        :param int indent: Indentation to use
        """
        path = path or getattr(self, "_path", None)
        if path:
            return save_json(self.to_dict(), path, fatal=fatal, logger=logger, sort_keys=sort_keys, indent=indent)


def read_json(path, default=None, fatal=True, logger=None):
    """
    :param str|None path: Path to file to deserialize
    :param dict|list|None default: Default if file is not present, or if it's not json
    :param bool|None fatal: Abort execution on failure if True
    :param callable|None logger: Logger to use
    :return dict|list: Deserialized data from file
    """
    path = resolved_path(path)
    if not path or not os.path.exists(path):
        if default is None:
            return abort("No file %s", short(path), fatal=(fatal, default))
        return default

    try:
        with io.open(path, "rt") as fh:
            data = json.load(fh)
            if default is not None and type(data) != type(default):
                return abort("Wrong type %s for %s, expecting %s", type(data), short(path), type(default), fatal=(fatal, default))

            if logger:
                logger("Read %s", short(path))

            return data

    except Exception as e:
        return abort("Couldn't read %s: %s", short(path), e, fatal=(fatal, default))


def save_json(data, path, fatal=True, logger=None, sort_keys=True, indent=2, **kwargs):
    """
    Args:
        data (object | None): Data to serialize and save
        path (str | None): Path to file where to save
        fatal (bool | None): Abort execution on failure if True
        logger (callable | None): Logger to use
        sort_keys (bool): Save json with sorted keys
        indent (int): Indentation to use
        **kwargs: Passed through to `json.dump()`

    Returns:
        (int): 1 if saved, -1 if failed (when `fatal` is False)
    """
    if data is None or not path:
        return abort("No file %s", short(path), fatal=fatal)

    try:
        path = resolved_path(path)
        ensure_folder(path, fatal=fatal, logger=None)
        if is_dryrun():
            LOG.info("Would save %s", short(path))
            return 1

        if hasattr(data, "to_dict"):
            data = data.to_dict()

        if indent:
            kwargs.setdefault("separators", (",", ": "))

        with open(path, "wt") as fh:
            json.dump(data, fh, sort_keys=sort_keys, indent=indent, **kwargs)
            fh.write("\n")

        if logger:
            logger("Saved %s", short(path))

        return 1

    except Exception as e:
        return abort("Couldn't save %s: %s", short(path), e, fatal=(fatal, -1))
