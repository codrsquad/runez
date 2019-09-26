"""
Convenience methods for (de)serializing objects
"""

import datetime
import inspect
import io
import json
import logging
import os

from runez.base import decode, string_type
from runez.convert import resolved_path, short
from runez.path import ensure_folder
from runez.system import abort, is_dryrun

LOG = logging.getLogger(__name__)


def json_sanitized(value, stringify=decode, dt=str, keep_none=False):
    """
    Args:
        value: Value to sanitize
        stringify (callable | None): Function to use to stringify non-builtin types
        dt (callable | None): Function to use to stringify dates
        keep_none (bool): If False, don't include None values

    Returns:
        An object that should be json serializable
    """
    if value is None or isinstance(value, (int, float, string_type)):
        return value
    if hasattr(value, "to_dict"):
        value = value.to_dict()
    if isinstance(value, set):
        return [json_sanitized(v, stringify=stringify, dt=dt) for v in sorted(value) if keep_none or v is not None]
    if isinstance(value, (tuple, list)):
        return [json_sanitized(v, stringify=stringify, dt=dt) for v in value if keep_none or v is not None]
    if isinstance(value, dict):
        return dict((stringify(k), json_sanitized(v, stringify=stringify, dt=dt)) for k, v in value.items() if keep_none or v is not None)
    if isinstance(value, datetime.date):
        if dt is None:
            return value
        return dt(value)
    if stringify is None:
        return value
    return stringify(value)


def same_type(t1, t2):
    """
    :return bool: True if 't1' and 't2' are of equivalent types
    """
    if t1 is None or t2 is None:
        return t1 is t2

    if t1.__class__ is not type:
        t1 = t1.__class__

    if t2.__class__ is not type:
        t2 = t2.__class__

    if issubclass(t1, string_type) and issubclass(t2, string_type):
        return True

    return t1 == t2


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


class ClassDescription(object):
    """Info on class attributes and properties"""

    def __init__(self, cls, dct=None):
        self.cls = cls
        self.attributes = {}
        self.properties = []
        if dct is None:
            dct = cls.__dict__

        for key, value in dct.items():
            if not key.startswith("_"):
                if value is None:
                    self.attributes[key] = None

                elif value.__class__ is type:
                    self.attributes[key] = value

                elif "property" in value.__class__.__name__:
                    self.properties.append(key)

                elif not inspect.isroutine(value):
                    self.attributes[key] = value.__class__


def with_metaclass(meta, *bases):
    """Create a base class with a metaclass (taken from https://pypi.org/project/six/)"""
    class metaclass(type):

        def __new__(cls, name, this_bases, dct):
            return meta(name, bases, dct)

        @classmethod
        def __prepare__(cls, name, this_bases):
            return meta.__prepare__(name, bases)

    return type.__new__(metaclass, "temporary_class", (), {})


def with_meta_injector(meta_type):
    """A metaclass that injects a `._meta` class attribute using given `meta_type` class"""
    class simple_injector(type):
        def __init__(cls, name, bases, dct):
            super(simple_injector, cls).__init__(name, bases, dct)
            cls._meta = meta_type(cls, dct)

    return with_metaclass(simple_injector)


class Serializable(with_meta_injector(ClassDescription)):
    """Serializable object"""

    _meta = None  # type: ClassDescription  # This describes fields and properties of descendant classes, populated via metaclass

    def __repr__(self):
        return getattr(self, "_source", "no source")

    def __eq__(self, other):
        if other is not None and other.__class__ is self.__class__:
            for name in self._meta.attributes:
                if not hasattr(other, name) or getattr(self, name) != getattr(other, name):
                    return False

            return True

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

    @classmethod
    def from_dict(cls, data):
        """
        Args:
            data (dict):

        Returns:
            Deserialized object
        """
        result = cls()
        result.set_from_dict(data)
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

        attrs = self._meta.attributes
        for key, value in data.items():
            if key not in attrs:
                LOG.debug("%s is not an attribute of %s", key, self.__class__.__name__)
                continue

            vtype = attrs[key]
            if vtype is not None and value is not None and not same_type(value.__class__, vtype):
                source = getattr(self, "_source", None)
                origin = " in %s" % source if source else ""
                LOG.debug("Wrong type '%s' for %s.%s%s, expecting '%s'", type_name(value), type_name(self), key, origin, vtype.__name__)
                continue

            setter = getattr(self, "set_%s" % key, None)
            if setter is not None and value is not None:
                setter(value)
            else:
                setattr(self, key, value)

    def reset(self):
        """
        Reset all fields of this object to class defaults
        """
        for name, vtype in self._meta.attributes.items():
            setattr(self, name, vtype and vtype())

    def to_dict(self, keep_none=False):
        """
        :param (bool) keep_none: If False, don't include None values
        :return dict: This object serialized to a dict
        """
        return json_sanitized(dict((name, getattr(self, name)) for name in self._meta.attributes), keep_none=keep_none)

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
    Args:
        path (str | None): Path to file to deserialize
        default (dict | list | str | None): Default if file is not present, or if it's not json
        fatal (bool | None): Abort execution on failure if True
        logger (callable | None): Logger to use

    Returns:
        (dict | list | str): Deserialized data from file
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


def represented_json(data, sort_keys=True, indent=2, keep_none=False, **kwargs):
    """
    Args:
        data (object | None): Data to serialize
        sort_keys (bool): Whether keys should be sorted
        indent (int | None): Indentation to use
        keep_none (bool): If False, don't include None values
        **kwargs: Passed through to `json.dumps()`

    Returns:
        (dict | list | str): Serialized `data`, with defaults that are usually desirable for a nice and clean looking json
    """
    data = json_sanitized(data, keep_none=keep_none)
    return "%s\n" % json.dumps(data, sort_keys=sort_keys, indent=indent, **kwargs)


def save_json(data, path, fatal=True, logger=None, sort_keys=True, indent=2, keep_none=False, **kwargs):
    """
    Args:
        data (object | None): Data to serialize and save
        path (str | None): Path to file where to save
        fatal (bool | None): Abort execution on failure if True
        logger (callable | None): Logger to use
        sort_keys (bool): Save json with sorted keys
        indent (int | None): Indentation to use
        keep_none (bool): If False, don't include None values
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

        data = json_sanitized(data, keep_none=keep_none)
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
