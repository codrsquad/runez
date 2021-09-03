"""
Allows to define a simple one-level-at-a-time schema to help control (de)serialization

Example:

>>> import runez
>>> from runez.schema import Dict, Integer, String

>>> class MyClass(runez.Serializable):
...     name = String(default="joe")  # All instances will get "joe" by default, and deserialization will ensure string
...     map = Dict(String, Integer)  # No default value (ie: None), deserialization will ensure proper type is used

>>> MyClass.name.default
'joe'
>>> MyClass.from_dict({}).name
'joe'
"""

import inspect

from runez.convert import to_boolean, to_float, to_int
from runez.date import to_date, to_datetime, UTC
from runez.system import _R, stringified


class ValidationException(Exception):
    """Thrown when type mismatch found during deserialization (and strict mode enabled)"""

    def __init__(self, message):
        self.message = message

    def __str__(self):
        return self.message


def determined_schema_type(value, required=True):
    """
    Args:
        value: Value given by user (as class attribute to describe their runez.Serializable schema)
        required (bool): If True, raise ValidationException() is no type could be determined

    Returns:
        (Any | None): Associated schema type (descendant of Any), if one is applicable
    """
    schema_type = _determined_schema_type(value)
    if required and schema_type is None:
        raise ValidationException("Invalid schema definition '%s'" % value)

    return schema_type


def _determined_schema_type(value):
    if value is None:
        return Any()  # User used None as value, no more info to be had

    if isinstance(value, Any):
        return value  # User specified their schema explicitly

    if inspect.isroutine(value):
        return None  # Routine, not a schema type

    if inspect.ismemberdescriptor(value):
        return Any()  # Member descriptor (such as slot)

    if isinstance(value, str):
        return String(default=value)  # User gave a string as value, assume they mean string type, and use value as default

    mapped = TYPE_MAP.get(value.__class__)
    if mapped is not None:
        return mapped(default=value)

    if not isinstance(value, type):
        value = value.__class__

    if issubclass(value, str):
        return String()

    if issubclass(value, _R.serializable()):
        return _MetaSerializable(value._meta)

    if issubclass(value, Any):
        return value()

    mapped = TYPE_MAP.get(value)
    if mapped is not None:
        return mapped()


class Any:
    """Indicates that any value is accepted"""

    def __init__(self, default=None):
        """
        Args:
            default: Default to use (when no value is provided)
        """
        self.default = default

    def __repr__(self):
        if self.default is None:
            return self.representation()

        return "%s (default: %s)" % (self.representation(), self.default)

    def representation(self):
        """
        Returns:
            (str): Textual representation for this type constraint
        """
        return _R._schema_type_name(self)

    def problem(self, value):
        """
        Args:
            value: Value to inspect

        Returns:
            (str | None): Explanation of compliance issue, if there is any
        """
        if value is None:
            return None

        return self._problem(value)

    def _problem(self, value):
        """To be re-defined by descendants, `value` is never `None`"""
        return None

    def converted(self, value):
        """
        Args:
            value: Value to inspect

        Returns:
            Converted value complying to this type
        """
        if value is None:
            return None

        return self._converted(value)

    def _converted(self, value):
        """To be re-defined by descendants, `value` is never `None`"""
        return value


class _MetaSerializable(Any):
    """Wraps descendants of `runez.Serializable` as schema fields (will be retired in the future)"""

    def __init__(self, meta, default=None):
        """
        Args:
            meta: A runez.Serializable object, or its ._meta attribute
            default: Default to use (when no value is provided)
        """
        self.meta = getattr(meta, "_meta", meta)
        super().__init__(default=default)

    def _problem(self, value):
        if not isinstance(value, dict):
            return "expecting compliant dict, got '%s'" % value

        return self.meta.problem(value)

    def _converted(self, value):
        return self.meta.from_dict(value)


class Boolean(Any):
    """Represents boolean type"""

    def _converted(self, value):
        return to_boolean(value)


class Date(Any):
    """Represents datetime type"""

    def _problem(self, value):
        if to_date(value) is None:
            return "expecting date, got '%s'" % value

    def _converted(self, value):
        return to_date(value)


class Datetime(Any):
    """Represents datetime type"""

    def __init__(self, default=None, tz=UTC):
        """
        Args:
            default: Default to use when no value was provided
            tz (datetime.tzinfo | None): Timezone info used as default if could not be determined from converted value
        """
        self.tz = tz
        super().__init__(default=default)

    def _problem(self, value):
        if to_datetime(value) is None:
            return "expecting datetime, got '%s'" % value

    def _converted(self, value):
        return to_datetime(value, tz=self.tz)


class Dict(Any):
    """Dict with optionally key/value constrained as well"""

    def __init__(self, key=None, value=None, default=None):
        """
        Args:
            key: Optional constraint for keys
            value: Optional constraint for values
            default: Default to use when no value was provided
        """
        self.key = determined_schema_type(key)  # type: Any
        self.value = determined_schema_type(value)  # type: Any
        super().__init__(default=default)

    def representation(self):
        return "%s[%s, %s]" % (_R._schema_type_name(self), self.key, self.value)

    def _problem(self, value):
        if not isinstance(value, dict):
            return "expecting dict, got '%s'" % value

        for k, v in value.items():
            problem = self.key.problem(k)
            if problem is not None:
                return "key: %s" % problem

            problem = self.value.problem(v)
            if problem is not None:
                return "value: %s" % problem

    def _converted(self, value):
        return dict((self.key.converted(k), self.value.converted(v)) for k, v in value.items())


class Enum(Any):
    """Represents an enum, given values should be a simple hashable type like str, or int"""

    def __init__(self, values, default=None):
        """
        Args:
            tz (str | list | tuple): Accepted values (space-separated if given as string)
            default: Default to use when no value was provided
        """
        if hasattr(values, "split"):
            values = values.split()
        self.values = set(values)
        super().__init__(default=default)

    def representation(self):
        return "%s[%s]" % (_R._schema_type_name(self), ", ".join(sorted(self.values)))

    def _problem(self, value):
        if value not in self.values:
            return "'%s' is not one of %s" % (value, self.representation())


class Integer(Any):
    """Represents integer type"""

    def _problem(self, value):
        if to_int(value) is None:
            return "expecting int, got '%s'" % value

    def _converted(self, value):
        return to_int(value)


class Float(Any):
    """Represents float type"""

    def _problem(self, value):
        if to_float(value) is None:
            return "expecting float, got '%s'" % value

    def _converted(self, value):
        return to_float(value)


class List(Any):
    """List with optionally values constrained as well"""

    def __init__(self, subtype=None, default=None):
        """
        Args:
            subtype: Optional constraint for values
            default: Default to use when no value was provided
        """
        self.subtype = determined_schema_type(subtype)  # type: Any
        super().__init__(default=default)

    def representation(self):
        return "%s[%s]" % (_R._schema_type_name(self), self.subtype)

    def _problem(self, value):
        if not isinstance(value, (list, set, tuple)):
            return "expecting list, got '%s'" % value

        for v in value:
            problem = self.subtype.problem(v)
            if problem is not None:
                return problem

    def _converted(self, value):
        return [self.subtype.converted(v) for v in value]


class String(Any):
    """Represents string type"""

    def _problem(self, value):
        if not isinstance(value, str):
            return "expecting string, got '%s'" % value

    def _converted(self, value):
        return stringified(value)


class Struct(Any):
    """Represents a composed object, similar to `Serializable`, but not intended to be the root of any schema"""

    def __init__(self, default=None):
        if not hasattr(self.__class__, "_meta"):
            self.__class__._meta = _R.meta_description(self)

        super().__init__(default=default)

    def __eq__(self, other):
        if other is not None and other.__class__ is self.__class__:
            for name in self.meta.attributes:
                if not hasattr(other, name) or getattr(self, name) != getattr(other, name):
                    return False

            return True

    def __ne__(self, other):
        return not (self == other)

    @property
    def meta(self):
        return self.__class__._meta

    @property
    def default(self):
        return self._default

    @default.setter
    def default(self, value):
        self._default = value

    def to_dict(self):
        """
        Returns:
            (dict): This object serialized to a dict
        """
        return dict((name, getattr(self, name)) for name in self.meta.attributes)

    def set_from_dict(self, data, source=None):
        """
        Args:
            data (dict): Raw data, coming for example from a json file
            source (str | None): Optional, description of source where 'data' came from
        """
        if data is not None:
            self.meta.set_from_dict(self, data, source=source)

    def _problem(self, value):
        if not isinstance(value, dict):
            return "expecting structure %s, got '%s'" % (_R._schema_type_name(self), value)

        return self.meta.problem(value)

    def _converted(self, value):
        return self.meta.from_dict(value)


class UniqueIdentifier(Any):
    """Can be used to state that an attribute is an identifier (at most one per descendant)"""

    def __init__(self, subtype=None):
        """
        Args:
            subtype: Optional type constraint for this identifier (defaults to `String`)
        """
        self.subtype = determined_schema_type(subtype or String)  # type: Any
        super().__init__(default=None)


TYPE_MAP = {
    dict: Dict,
    int: Integer,
    list: List,
    set: List,
    tuple: List,
}
