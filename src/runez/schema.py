"""
Allows to define a simple one-level-at-a-time schema to help control (de)serialization

Example:

>>> import runez
>>> from runez.schema import Dict, Integer, String

>>> class MyClass(runez.Serializable):
>>>     name = String(default="joe")  # All instances will get "joe" by default, and deserialization will ensure string
>>>     map = Dict(String, Integer)  # No default value (ie: None), deserialization will ensure proper type is used
"""

import inspect

from runez.convert import to_boolean, to_float, to_int
from runez.date import to_date, to_datetime, UTC
from runez.system import _R, string_type, stringified


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

    if isinstance(value, string_type):
        return String(default=value)  # User gave a string as value, assume they mean string type, and use value as default

    mapped = TYPE_MAP.get(value.__class__)
    if mapped is not None:
        return mapped(default=value)

    if not isinstance(value, type):
        value = value.__class__

    if issubclass(value, string_type):
        return String()

    if issubclass(value, _R.serializable()):
        return MetaSerializable(value._meta)

    if issubclass(value, Any):
        return value()

    mapped = TYPE_MAP.get(value)
    if mapped is not None:
        return mapped()


class Any(object):
    """Indicates that any value is accepted"""

    def __init__(self, default=None):
        """
        Args:
            default: Default to use (when no value is provided)
        """
        self.default = default
        self.name = self.__class__.__name__.lower()

    def __repr__(self):
        if self.default is None:
            return self.representation()

        return "%s (default: %s)" % (self.representation(), self.default)

    def representation(self):
        """
        Returns:
            (str): Textual representation for this type constraint
        """
        return self.name

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


class MetaSerializable(Any):
    """Represents a descendant of `runez.Serializable`"""

    def __init__(self, meta, default=None):
        """
        Args:
            meta: A runez.Serializable object, or its ._meta attribute
            default: Default to use (when no value is provided)
        """
        self.meta = getattr(meta, "_meta", meta)
        super(MetaSerializable, self).__init__(default=default)
        self.name = self.meta.cls.__name__

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
        super(Datetime, self).__init__(default=default)

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
        super(Dict, self).__init__(default=default)

    def representation(self):
        return "%s[%s, %s]" % (self.name, self.key, self.value)

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
        super(Enum, self).__init__(default=default)

    def representation(self):
        return "%s[%s]" % (self.name, ", ".join(sorted(self.values)))

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
        super(List, self).__init__(default=default)

    def representation(self):
        return "%s[%s]" % (self.name, self.subtype)

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
        if not isinstance(value, string_type):
            return "expecting string, got '%s'" % value

    def _converted(self, value):
        return stringified(value)


class UniqueIdentifier(Any):
    """Can be used to state that an attribute is an identifier (at most one per descendant)"""

    def __init__(self, subtype=None):
        """
        Args:
            subtype: Optional type constraint for this identifier (defaults to `String`)
        """
        self.subtype = determined_schema_type(subtype or String)  # type: Any
        super(UniqueIdentifier, self).__init__(default=None)


TYPE_MAP = {
    dict: Dict,
    int: Integer,
    list: List,
    set: List,
    tuple: List,
}
