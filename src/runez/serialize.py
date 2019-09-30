"""
Convenience methods for (de)serializing objects
"""

import datetime
import inspect
import io
import json
import logging
import os

from runez.base import decode, string_type, UNSET
from runez.convert import resolved_path, short, shortened
from runez.path import ensure_folder
from runez.schema import Any, Dict, Integer, List, MetaSerializable, String
from runez.system import abort, is_dryrun


LOG = logging.getLogger(__name__)
TYPE_MAP = {
    dict: Dict,
    int: Integer,
    list: List,
    set: List,
    string_type: String,
    tuple: List,
}


class ValidationException(Exception):
    """
    Thrown when type mismatch found during deserialization (and strict mode enabled)
    """

    def __init__(self, message):
        self.message = message


def with_behavior(strict=UNSET, extras=UNSET, hook=UNSET):
    """
    Args:
        strict (bool | callable): False: don't check, True: raise ValidationException on type mismatch, Exception: raise given exception
        extras (bool | callable | (callable, list)): False: don't notify when there are extra fields in deserialized data
                                                    True: use LOG.debug() to notify
                                                    callable: use callable(str) to notify
                                                    (callable, list): use callable(str) to notify, but not for extras mentioned in list
        hook (callable): Called if provided at the end of ClassMetaDescription initialization

    Returns:
        (type): Internal temp class (compatible with `Serializable` metaclass) indicating how to handle Serializable type checking
    """
    return BaseMetaInjector("_MBehavior", tuple(), {"behavior": DefaultBehavior(strict=strict, extras=extras, hook=hook)})


class DefaultBehavior(object):
    """
    Defines how to handle type mismatches and extra data in `Serializable`

    Can be changed globally at the start of your app, for example:

        runez.serializable.DefaultBehavior.strict = True
    """
    strict = False  # type: callable # Original default: don't strictly enforce type compatibility
    extras = False  # type: callable  # Original default: don't notify
    ignored_extras = None
    hook = None  # type: callable  # Called if provided at the end of ClassMetaDescription initialization

    def __init__(self, strict=UNSET, extras=UNSET, hook=UNSET):
        """
        Args:
            strict (bool | callable): False: don't check, True: raise ValidationException on type mismatch, Exception: raise given exception
            extras (bool | callable | (callable, list)): See `with_behavior()`
            hook (callable): Called if provided at the end of ClassMetaDescription initialization
        """
        if strict is UNSET:
            strict = self.strict

        if extras is UNSET:
            extras = self.extras

        if hook is not UNSET:
            self.hook = hook

        self.strict = self.to_callable(strict, ValidationException)
        if isinstance(extras, tuple) and len(extras) == 2:
            extras, self.ignored_extras = extras
            if hasattr(self.ignored_extras, "split"):
                self.ignored_extras = self.ignored_extras.split()

        else:
            self.ignored_extras = None

        self.extras = self.to_callable(extras, LOG.debug)

    def __repr__(self):
        result = []
        if self.strict:
            result.append("strict: %s" % shortened(self.strict))

        if self.extras:
            result.append("extras: %s" % shortened(self.extras))

        if self.ignored_extras:
            result.append("ignored extras: %s" % shortened(self.ignored_extras))

        if self.hook:
            result.append("hook: %s" % shortened(self.hook))

        if result:
            return ", ".join(result)

        return "lenient"

    @staticmethod
    def get_behavior(bases):
        for base in bases:
            if isinstance(base, type) and base.__name__ == "_MBehavior":
                behavior = getattr(base, "behavior", None)
                if behavior is not None:
                    return behavior
            meta = getattr(base, "_meta", None)
            if isinstance(meta, ClassMetaDescription) and meta.name != "Serializable" and meta.behavior:
                return meta.behavior

        return DefaultBehavior()

    @staticmethod
    def to_callable(value, default):
        if not value:
            return None

        if callable(value):
            return value

        return default

    def handle_mismatch(self, class_name, field_name, problem, source):
        if self.strict:
            msg = " from %s" % source if source else ""
            msg = "Can't deserialize %s.%s%s: %s" % (class_name, field_name, msg, problem)
            if isinstance(self.strict, type) and issubclass(self.strict, Exception):
                raise self.strict(msg)

            self.strict(msg)

    def do_notify(self, message):
        if self.extras:
            if isinstance(self.extras, type) and issubclass(self.extras, Exception):
                raise self.extras(message)

            self.extras(message)

    def handle_extra(self, class_name, field_name):
        self.do_notify("'%s' is not an attribute of %s" % (field_name, class_name))

    def handle_extras(self, class_name, extras):
        if self.extras:
            if self.ignored_extras:
                for x in self.ignored_extras:
                    extras.pop(x, None)

            if extras:
                # We have more stuff in `data` than described in corresponding `._meta`
                self.do_notify("Extra content given for %s: %s" % (class_name, ", ".join(sorted(extras))))


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

    elif isinstance(value, set):
        value = sorted(value)

    if isinstance(value, (tuple, list)):
        return [json_sanitized(v, stringify=stringify, dt=dt, keep_none=keep_none) for v in value if keep_none or v is not None]

    if isinstance(value, dict):
        return dict(
            (
                json_sanitized(k, stringify=stringify, dt=dt, keep_none=keep_none),
                json_sanitized(v, stringify=stringify, dt=dt, keep_none=keep_none),
            )
            for k, v in value.items()
            if keep_none or v is not None
        )

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

    if not isinstance(t1, type):
        t1 = t1.__class__

    if not isinstance(t2, type):
        t2 = t2.__class__

    if issubclass(t1, string_type) and issubclass(t2, string_type):
        return True

    return t1 == t2


def type_name(value):
    """
    Args:
        value: Some object, class, or None

    Returns:
        (str): Class name implementing 'value'
    """
    if value is None:
        return "None"

    if isinstance(value, string_type):
        return "str"

    if isinstance(value, type):
        return value.__name__

    return value.__class__.__name__


def get_descriptor(value):
    """
    Args:
        value: Value given by user (as class attribute to describe their runez.Serializable schema)

    Returns:
        (Any | None): Descriptor if one is applicable
    """
    if value is None:
        return Any()  # Used used None as value, no more info to be had

    if isinstance(value, Any):
        return value  # User specified their schema properly

    if inspect.isroutine(value):
        return None  # Routine, not a descriptor

    if inspect.ismemberdescriptor(value):
        return Any()  # Member descriptor (such as slot), not type as runez.Serializable goes

    if isinstance(value, string_type):
        return String(default=value)  # User gave a string as value, assume they mean string type, and use value as default

    mapped = TYPE_MAP.get(value.__class__)
    if mapped is not None:
        return mapped(default=value)

    if not isinstance(value, type):
        value = value.__class__

    if issubclass(value, string_type):
        return String()

    if issubclass(value, Serializable):
        return MetaSerializable(value._meta)

    if issubclass(value, Any):
        return value()

    mapped = TYPE_MAP.get(value)
    if mapped is not None:
        return mapped()


class ClassMetaDescription(object):
    """Info on class attributes and properties"""

    def __init__(self, cls):
        self.name = type_name(cls)
        self.cls = cls
        self.attributes = {}
        self.properties = []
        self.behavior = DefaultBehavior.get_behavior(cls.__bases__)
        for key, value in cls.__dict__.items():
            if not key.startswith("_"):
                if value is not None and "property" in value.__class__.__name__:
                    self.properties.append(key)
                    continue

                descriptor = get_descriptor(value)
                if descriptor is not None:
                    self.attributes[key] = descriptor
                    setattr(cls, key, descriptor.default)

        if self.behavior.hook:
            self.behavior.hook(self)

    def __repr__(self):
        return "%s (%s attributes, %s properties)" % (type_name(self.cls), len(self.attributes), len(self.properties))

    def from_dict(self, data, source=None):
        """
        Args:
            data (dict): Raw data, coming for example from a json file
            source (str | None): Optional, description of source where 'data' came from

        Returns:
            (cls): Deserialized object
        """
        result = self.cls()
        # Call objects' own set_from_dict() to allow descendants to fine-tune its behavior if needed
        result.set_from_dict(data, source=source)
        return result

    def set_from_dict(self, obj, data, source=None):
        """
        Args:
            obj (Serializable): Object to populate
            data (dict): Raw data, coming for example from a json file
            source (str | None): Optional, description of source where 'data' came from
        """
        if data is None:
            given = {}

        else:
            given = data.copy()

        for name, descriptor in self.attributes.items():
            value = given.pop(name, descriptor.default)
            problem = descriptor.problem(value)
            if problem is None:
                value = descriptor.converted(value)

            else:
                self.behavior.handle_mismatch(self.name, name, problem, source)

            if value is None:
                setattr(obj, name, None)

            else:
                setter = getattr(obj, "set_%s" % name, None)
                if setter is None:
                    setattr(obj, name, value)

                else:
                    setter(value)

        self.behavior.handle_extras(self.name, given)

    def problem(self, value):
        """
        Args:
            value: Value to verify compliance of

        Returns:
            (str | None): Explanation of compliance issue, if there is any
        """
        for name, descriptor in self.attributes.items():
            problem = descriptor.problem(value.get(name))
            if problem is not None:
                return problem

        if self.behavior.extras:
            for key in value:
                if key not in self.attributes:
                    self.behavior.handle_extra(self.name, key)


class BaseMetaInjector(type):
    """Used solely to provide common ancestor for `MetaInjector` and internal types returned by `with_behavior`"""


def add_metaclass(metaclass):
    """Class decorator for creating a class with a metaclass (taken from https://pypi.org/project/six/)."""
    def wrapper(cls):
        orig_vars = cls.__dict__.copy()
        slots = orig_vars.get("__slots__")
        if slots is not None:
            if isinstance(slots, str):
                slots = [slots]
            for slots_var in slots:
                orig_vars.pop(slots_var)
        orig_vars.pop("__dict__", None)
        orig_vars.pop("__weakref__", None)
        if hasattr(cls, "__qualname__"):
            orig_vars["__qualname__"] = cls.__qualname__
        return metaclass(cls.__name__, cls.__bases__, orig_vars)
    return wrapper


def add_meta(meta_type):
    """A simplified metaclass that simply injects a `._meta` field of given type `meta_type`"""
    class MetaInjector(BaseMetaInjector):
        def __init__(cls, name, bases, dct):
            super(MetaInjector, cls).__init__(name, bases, dct)
            cls._meta = meta_type(cls)

    return add_metaclass(MetaInjector)


@add_meta(ClassMetaDescription)
class Serializable(object):
    """Serializable object"""

    _meta = None  # type: ClassMetaDescription  # This describes fields and properties of descendant classes, populated via metaclass

    def __eq__(self, other):
        if other is not None and other.__class__ is self.__class__:
            for name in self._meta.attributes:
                if not hasattr(other, name) or getattr(self, name) != getattr(other, name):
                    return False

            return True

    @classmethod
    def from_json(cls, path, default=None, fatal=True, logger=None):
        """
        Args:
            path (str): Path to json file
            default (dict | None): Default if file is not present, or if it's not json
            fatal (bool | None): Abort execution on failure if True
            logger (callable | None): Logger to use

        Returns:
            (cls): Deserialized object
        """
        result = cls()
        data = read_json(path, default=default, fatal=fatal, logger=logger)
        result.set_from_dict(data, source=short(path))
        return result

    @classmethod
    def from_dict(cls, data, source=None):
        """
        Args:
            data (dict): Raw data, coming for example from a json file
            source (str | None): Optional, description of source where 'data' came from

        Returns:
            (cls): Deserialized object
        """
        return cls._meta.from_dict(data, source=source)

    def set_from_dict(self, data, source=None):
        """
        Args:
            data (dict): Raw data, coming for example from a json file
            source (str | None): Optional, description of source where 'data' came from
        """
        self._meta.set_from_dict(self, data, source=source)

    def reset(self):
        """
        Reset all fields of this object to class defaults
        """
        for name, descriptor in self._meta.attributes.items():
            setattr(self, name, descriptor.default)

    def to_dict(self, keep_none=False):
        """
        :param (bool) keep_none: If False, don't include None values
        :return dict: This object serialized to a dict
        """
        raw = dict((name, getattr(self, name)) for name in self._meta.attributes)
        return json_sanitized(raw, keep_none=keep_none)


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
