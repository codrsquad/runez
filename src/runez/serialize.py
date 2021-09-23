"""
Convenience methods for (de)serializing objects
"""

import collections
import datetime
import io
import json

from runez.file import ensure_folder, parent_folder
from runez.system import _R, abort, is_basetype, is_iterable, LOG, resolved_path, short, stringified, UNSET


K_INDENTED_SEPARATORS = (",", ": ")
K_COMPACT_SEPARATORS = (", ", ": ")


def _to_callable(value, fallback=None):
    if value:
        return value if callable(value) else fallback


def with_behavior(strict=UNSET, extras=UNSET, hook=UNSET):
    """
    Args:
        strict (bool | Exception | callable): False: don't perform any schema validation
                                              True: raise ValidationException when schema is not respected
                                              Exception: raise given exception when schema is not respected
                                              callable: call callable(reason) when schema is not respected

        extras (bool | Exception | callable | (callable, list)):
            False: don't do anything when there are extra fields in deserialized data
            True: call LOG.debug(reason) to report extra (not in schema) fields seen in data
            Exception: raise given Exception(reason) when extra fields are seen in data
            callable: call callable(reason) when extra fields are seen in data
            (callable, list): call callable(reason), except for extras mentioned in list

        hook (callable): If provided, call callable(meta: ClassMetaDescription) at the end of ClassMetaDescription initialization

    Returns:
        (type): Internal temp class (compatible with `Serializable` metaclass) indicating how to handle Serializable type checking
    """
    return BaseMetaInjector("_MBehavior", tuple(), {"behavior": DefaultBehavior(strict=strict, extras=extras, hook=hook)})


def is_serializable_descendant(base):
    """
    Args:
        base (type): Base class to examine

    Returns:
        (bool): True if `base` is a descendant of `Serializable` (but not `Serializable` itself)
    """
    if "Serializable" in globals():  # We're doing a forward reference here, class is defined below
        return base is not Serializable and issubclass(base, Serializable)


def set_default_behavior(strict=UNSET, extras=UNSET):
    """
    Use this to change defaults globally at the start of your app (or in your conftest), for example:
        runez.serializable.set_default_behavior(strict=True)

    Args:
        strict (bool | Exception | callable): False: don't perform any schema validation
                                              True: raise ValidationException when schema is not respected
                                              Exception: raise given exception when schema is not respected
                                              callable: call callable(reason) when schema is not respected

        extras (bool | Exception | callable): False: don't do anything when there are extra fields in deserialized data
                                              True: call LOG.debug(reason) to report extra (not in schema) fields seen in data
                                              Exception: raise given Exception(reason) when extra fields are seen in data
                                              callable: call callable(reason) when extra fields are seen in data
    """
    if strict is not UNSET:
        DefaultBehavior.strict = strict

    if extras is not UNSET:
        DefaultBehavior.extras = extras


class DefaultBehavior:
    """
    Defines how to handle type mismatches and extra data in `Serializable`.
    Default behavior will be used only if no specific with_behavior() is used in Serializable descendant definition.

    Also carries an optional `hook` to call at the end of each Serializable descendant registration
    (global default for that does not make sense).
    """

    strict = False  # type: callable # Original default: don't strictly enforce type compatibility
    extras = False  # type: callable  # Original default: don't report extra fields seen in deserialized data (ie: ignore them)

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

        self.strict = _to_callable(strict, fallback=_R.schema().ValidationException)
        self.hook = _to_callable(hook)  # Called if provided at the end of ClassMetaDescription initialization
        self.ignored_extras = None  # Internal, populated if given `extras` is a `tuple(callable, list)`

        if isinstance(extras, tuple) and len(extras) == 2:
            extras, self.ignored_extras = extras
            if isinstance(self.ignored_extras, str):
                self.ignored_extras = self.ignored_extras.split()

        else:
            self.ignored_extras = None

        self.extras = _to_callable(extras, fallback=LOG.debug)

    def __repr__(self):
        result = []
        if self.strict:
            result.append("strict: %s" % short(self.strict))

        if self.extras:
            result.append("extras: %s" % short(self.extras))

        if self.ignored_extras:
            result.append("ignored extras: %s" % short(self.ignored_extras))

        if self.hook:
            result.append("hook: %s" % short(self.hook))

        if result:
            return ", ".join(result)

        return "lenient"

    @staticmethod
    def behavior_from_bases(cls):
        """Determine behavior from base classes of given `cls`"""
        strict = hook = UNSET
        for base in reversed(cls.__bases__):
            meta = getattr(base, "_meta", None)
            if isinstance(meta, ClassMetaDescription) and meta.behavior is not None and is_serializable_descendant(base):
                # Let `strict` and `hook` be inherited from parent classes (but not `Serializable` itself)
                strict = meta.behavior.strict
                hook = meta.behavior.hook

        return DefaultBehavior(strict=strict, hook=hook)

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


def json_sanitized(value, stringify=stringified, dt=str, none=False):
    """
    Args:
        value: Value to sanitize
        stringify (callable | None): Function to use to stringify non-builtin types
        dt (callable | None): Function to use to stringify dates
        none (str | bool): States how to treat `None` keys/values
                           - string: Replace `None` *keys* with given string (keep `None` *values* as-is)
                           - False (default): Filter out `None` keys/values
                           - True: No filtering, keep `None` keys/values as-is

    Returns:
        An object that should be json serializable
    """
    if value is None or is_basetype(value):
        return value

    if hasattr(value, "to_dict"):
        value = value.to_dict()

    elif isinstance(value, set):
        value = sorted(value)

    if isinstance(value, dict):
        return dict(
            (
                json_sanitized(none if k is None and isinstance(none, str) else k, stringify=stringify, dt=dt, none=none),
                json_sanitized(v, stringify=stringify, dt=dt, none=none),
            )
            for k, v in value.items()
            if none or (k is not None and v is not None)
        )

    if is_iterable(value):
        return [json_sanitized(v, stringify=stringify, dt=dt, none=none) for v in value]

    if isinstance(value, datetime.date):
        return value if dt is None else dt(value)

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

    if issubclass(t1, str) and issubclass(t2, str):
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

    if isinstance(value, str):
        return "str"

    if isinstance(value, type):
        return value.__name__

    return value.__class__.__name__


def applicable_bases(cls):
    yield cls
    for base in cls.__bases__:
        if is_serializable_descendant(base):
            yield base


def scan_attributes(cls):
    for key, value in cls.__dict__.items():
        if not key.startswith("_"):
            yield key, value


def scan_all_attributes(cls):
    seen = set()
    for base in applicable_bases(cls):
        for key, value in scan_attributes(base):
            if key not in seen:
                seen.add(key)
                yield key, value


class SerializableDescendants:
    """Tracks all descendants of Serializable, with at least one attribute defined"""

    by_name = {}  # Tracks by class name only, last imported class wins
    by_qualified_name = {}  # Tracks by full qualified name (won't be any conflicts)

    @classmethod
    def descendant_with_name(cls, name):
        """
        Args:
            name (str): Short name or fully qualified name of Serializable descendant

        Returns:
            (ClassMetaDescription | None): Meta of corresponding Serializable class, if any
        """
        descendant = cls.by_qualified_name.get(name)
        if descendant is None:
            descendant = cls.by_name.get(name)

        return descendant

    @classmethod
    def register(cls, meta):
        if meta.name not in cls.by_name:
            cls.by_name[meta.name] = meta
            cls.by_qualified_name[meta.qualified_name] = meta

    @classmethod
    def children(cls, base):
        """
        Args:
            base (Serializable.__class__): Yields metas of all descendants inheriting given 'base' class

        Yields:
            (ClassMetaDescription): ._meta of each descendant
        """
        for meta in cls.by_qualified_name.values():
            if issubclass(meta.cls, base):
                yield meta

    @classmethod
    def call(cls, func_name, *args, **kwargs):
        """
        Args:
            func_name (str): Name of function to call on each registered descendant, if it has it (as a classmethod)
            *args: Passed-through to invoked function
            **kwargs: Passed-through to invoked function
        """
        for descendant in cls.by_qualified_name.values():
            func = getattr(descendant.cls, func_name, None)
            if func is not None:
                func(*args, **kwargs)


class ClassMetaDescription:
    """Info on class attributes and properties"""

    def __init__(self, cls, mbehavior=None):
        self.name = cls.__name__
        self.qualified_name = "%s.%s" % (cls.__module__, cls.__name__)
        self.cls = cls
        self.attributes = {}
        self.properties = []
        self.behavior = mbehavior.behavior if mbehavior is not None else DefaultBehavior.behavior_from_bases(cls)
        self.unique_identifier = None

        by_type = collections.defaultdict(list)
        for key, value in scan_all_attributes(cls):
            if not key.startswith("_"):
                if value is not None and "property" in value.__class__.__name__:
                    self.properties.append(key)
                    continue

                schema_type = _R.schema().determined_schema_type(value, required=False)
                if schema_type is not None:
                    if isinstance(schema_type, _R.schema().UniqueIdentifier):
                        if self.unique_identifier:
                            raise _R.schema().ValidationException(
                                "Multiple unique ids specified for %s: %s and %s"
                                % (self.qualified_name, self.unique_identifier, schema_type)
                            )
                        self.unique_identifier = key
                        schema_type = schema_type.subtype

                    self.attributes[key] = schema_type
                    by_type[schema_type.__class__].append(key)

        self._by_type = dict((k, sorted(v)) for k, v in by_type.items())  # Sorted to make things deterministic
        if self.attributes:
            SerializableDescendants.register(self)

        if self.behavior.hook:
            self.behavior.hook(self)

    def __repr__(self):
        return "%s (%s attributes, %s properties)" % (type_name(self.cls), len(self.attributes), len(self.properties))

    def attributes_by_type(self, schema_type):
        """
        Args:
            schema_type (Any): Schema type

        Returns:
            (list[str] | None): Attributes with `schema_type`, if any
        """
        return self._by_type.get(schema_type)

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
        given = {} if data is None else dict(data)  # Copy of data
        for name, schema_type in self.attributes.items():
            value = given.pop(name, schema_type.default)
            problem = schema_type.problem(value)
            if problem is None:
                value = schema_type.converted(value)

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
        for name, schema_type in self.attributes.items():
            problem = schema_type.problem(value.get(name))
            if problem is not None:
                return problem

        if self.behavior.extras:
            for key in value:
                if key not in self.attributes:
                    self.behavior.handle_extra(self.name, key)

    def changed_attributes(self, obj1, obj2):
        """
        Args:
            obj1 (Serializable): First object to inspect
            obj2 (Serializable): 2nd object to inspect

        Returns:
            (list): Tuple of attribute names and values for which values differ between `obj1` and `obj2`
        """
        assert obj1._meta is self and obj2._meta is self
        result = []
        for key in self.attributes:
            v1 = getattr(obj1, key)
            v2 = getattr(obj2, key)
            if v1 != v2:
                result.append((key, v1, v2))

        return sorted(result)


class BaseMetaInjector(type):
    """Used solely to provide common ancestor for `MetaInjector` and internal types returned by `with_behavior`"""


def add_metaclass(metaclass):
    """Class decorator for creating a class with a metaclass (taken from https://pypi.org/project/six/)."""

    def wrapper(cls):
        orig_vars = dict(cls.__dict__)
        slots = orig_vars.get("__slots__")
        if slots is not None:
            if isinstance(slots, str):
                orig_vars.pop(slots)

            else:
                for slots_var in slots:
                    orig_vars.pop(slots_var)

        orig_vars.pop("__dict__", None)
        orig_vars.pop("__weakref__", None)
        if hasattr(cls, "__qualname__"):
            orig_vars["__qualname__"] = cls.__qualname__

        return metaclass(cls.__name__, cls.__bases__, orig_vars)

    return wrapper


def filtered_bases(bases):
    fb = []
    mbehavior = None
    for base in bases:
        if base.__name__ == "_MBehavior":
            mbehavior = base

        else:
            fb.append(base)

    if mbehavior is None:
        return None, bases

    return mbehavior, tuple(fb)


def add_meta(meta_type):
    """A simplified metaclass that simply injects a `._meta` field of given type `meta_type`"""

    class MetaInjector(BaseMetaInjector):
        def __init__(cls, name, bases, dct):
            mbehavior, fb = filtered_bases(bases)
            super().__init__(name, fb, dct)
            cls._meta = meta_type(cls, mbehavior)

    return add_metaclass(MetaInjector)


@add_meta(ClassMetaDescription)
class Serializable:
    """Serializable object"""

    _meta = None  # type: ClassMetaDescription  # This describes fields and properties of descendant classes, populated via metaclass

    def __new__(cls, *_, **__):
        obj = super(Serializable, cls).__new__(cls)
        obj.reset()
        return obj

    def __eq__(self, other):
        if other is not None and other.__class__ is self.__class__:
            for name in self._meta.attributes:
                if not hasattr(other, name) or getattr(self, name) != getattr(other, name):
                    return False

            return True

    def __ne__(self, other):
        return not (self == other)

    def __copy__(self):
        return self.__class__.from_dict(self.to_dict())

    @classmethod
    def from_json(cls, path, default=None, fatal=False, logger=False):
        """
        Args:
            path (str): Path to json file
            default (dict | list | str | None): Default if file is not present, or can't be deserialized
            fatal (type | bool | None): True: abort execution on failure, False: don't abort but log, None: don't abort, don't log
            logger (callable | bool | None): Logger to use, True to print(), False to trace(), None to disable log chatter

        Returns:
            (cls): Deserialized object
        """
        result = cls()
        data = read_json(path, default=default, fatal=fatal or (default is None and cls._meta.behavior.strict), logger=logger)
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

    def set_from_dict(self, data, source=None, merge=False):
        """
        Args:
            data (dict): Raw data, coming for example from a json file
            source (str | None): Optional, description of source where 'data' came from
            merge (bool): If True, add `data` to existing fields
        """
        if data is not None:
            if merge:
                merged = self.to_dict()
                merged.update(data)
                data = merged

            self._meta.set_from_dict(self, data, source=source)

    def reset(self):
        """
        Reset all fields of this object to class defaults
        """
        for name, schema_type in self._meta.attributes.items():
            setattr(self, name, schema_type.default)

    def to_dict(self, stringify=stringified, dt=str, none=False):
        """
        Args:
            stringify (callable | None): Function to use to stringify non-builtin types
            dt (callable | None): Function to use to stringify dates
            none (str | bool): States how to treat `None` keys/values
                               - string: Replace `None` *keys* with given string (keep `None` *values* as-is)
                               - False (default): Filter out `None` keys/values
                               - True: No filtering, keep `None` keys/values as-is

        Returns:
            (dict): This object serialized to a dict
        """
        raw = dict((name, getattr(self, name)) for name in self._meta.attributes)
        return json_sanitized(raw, stringify=stringify, dt=dt, none=none)


def from_json(value, default=None, fatal=False, logger=False):
    """
    Args:
        value (str): Value to deserialize
        default (dict | list | str | None): Default returned if value can't be deserialized
        fatal (type | bool | None): True: abort execution on failure, False: don't abort but log, None: don't abort, don't log
        logger (callable | bool | None): Logger to use, True to print(), False to trace(), None to disable log chatter

    Returns:
        (dict | list | str): Deserialized data from file
    """
    if not value or not isinstance(value, str):
        return _R.habort(default, fatal, logger, "Can't deserialize '%s': not a string" % short(value))

    value = value.strip()
    if "%s%s" % (value[0], value[-1]) not in ("{}", "[]", '""'):
        return _R.habort(default, fatal, logger, "Can't deserialize '%s': does not contain json" % short(value))

    try:
        return json.loads(value)

    except Exception as e:
        return _R.habort(default, fatal, logger, "Can't deserialize json '%s'" % short(value), exc_info=e)


def read_json(path, default=None, fatal=False, logger=False):
    """
    Args:
        path (str | pathlib.Path | None): Path to file to deserialize
        default (dict | list | str | None): Default returned if file is not present, or can't be deserialized
        fatal (type | bool | None): True: abort execution on failure, False: don't abort but log, None: don't abort, don't log
        logger (callable | bool | None): Logger to use, True to print(), False to trace(), None to disable log chatter

    Returns:
        (dict | list | str): Deserialized data from file
    """
    try:
        with io.open(resolved_path(path)) as fh:
            return json.load(fh)

    except Exception as e:
        return _R.habort(default, fatal, logger, "Can't read %s" % short(path), exc_info=e)


def represented_json(data, stringify=stringified, dt=str, none=False, indent=2, sort_keys=True):
    """
    Args:
        data (object | None): Data to serialize
        stringify (callable | None): Function to use to stringify non-builtin types
        dt (callable | None): Function to use to stringify dates
        none (str | bool): States how to treat `None` keys/values
                           - string: Replace `None` *keys* with given string (keep `None` *values* as-is)
                           - False (default): Filter out `None` keys/values
                           - True: No filtering, keep `None` keys/values as-is
        indent (int | None): Indentation to use, if None: use compact (one line) mode
        sort_keys (bool): Whether keys should be sorted

    Returns:
        (dict | list | str): Serialized `data`, with defaults that are usually desirable for a nice and clean looking json
    """
    data = json_sanitized(data, stringify=stringify, dt=dt, none=none)
    rep = json.dumps(data, indent=indent, sort_keys=sort_keys, separators=K_INDENTED_SEPARATORS if indent else K_COMPACT_SEPARATORS)
    if indent:
        return "%s\n" % rep

    return rep


def save_json(data, path, stringify=stringified, dt=str, none=False, indent=2, sort_keys=True, fatal=True, logger=UNSET, dryrun=UNSET):
    """
    Args:
        data (object | None): Data to serialize and save
        path (str | None): Path to file where to save
        stringify (callable | None): Function to use to stringify non-builtin types
        dt (callable | None): Function to use to stringify dates
        none (str | bool): States how to treat `None` keys/values
                           - string: Replace `None` *keys* with given string (keep `None` *values* as-is)
                           - False (default): Filter out `None` keys/values
                           - True: No filtering, keep `None` keys/values as-is
        indent (int | None): Indentation to use, if None: use compact (one line) mode
        sort_keys (bool): Whether keys should be sorted
        fatal (type | bool | None): True: abort execution on failure, False: don't abort but log, None: don't abort, don't log
        logger (callable | bool | None): Logger to use, True to print(), False to trace(), None to disable log chatter
        dryrun (bool): Optionally override current dryrun setting

    Returns:
        (int): In non-fatal mode, 1: successfully done, 0: was no-op, -1: failed
    """
    if data is None or not path:
        return 0

    try:
        path = resolved_path(path)
        if _R.hdry(dryrun, logger, "save %s" % short(path)):
            return 1

        ensure_folder(parent_folder(path), fatal=fatal, logger=None)
        data = json_sanitized(data, stringify=stringify, dt=dt, none=none)
        with open(path, "wt") as fh:
            json.dump(data, fh, indent=indent, sort_keys=sort_keys, separators=K_INDENTED_SEPARATORS if indent else K_COMPACT_SEPARATORS)
            if indent:
                fh.write("\n")

        _R.hlog(logger, "Saved %s" % short(path))
        return 1

    except Exception as e:
        return abort("Can't save %s" % short(path), exc_info=e, return_value=-1, fatal=fatal, logger=logger)
