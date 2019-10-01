"""
Allows to define a simple one-level-at-a-time schema to help control (de)serialization

Example:
    import runez
    from runez.serialize import Dict, Integer, Serializable, String

    class MyClass(Serializable):

        name = String(default="joe")  # All instances will get "joe" by default, and deserialization will ensure string

        map = Dict(String, Integer)  # No default value (ie: None), deserialization will ensure proper type is used
"""

import inspect

from runez.base import string_type
from runez.convert import to_float, to_int, TRUE_TOKENS
from runez.date import to_date


Serializable = None  # type: type # Set to runez.Serializable class once parsing of runez.serialize.py is past that class definition


class ValidationException(Exception):
    """
    Thrown when type mismatch found during deserialization (and strict mode enabled)
    """

    def __init__(self, message):
        self.message = message


def get_descriptor(value, required=True):
    """
    Args:
        value: Value given by user (as class attribute to describe their runez.Serializable schema)
        required (bool): If True, raise ValidationException() is no descriptor could be found

    Returns:
        (Any | None): Descriptor if one is applicable
    """
    descriptor = _get_descriptor(value)
    if required and descriptor is None:
        raise ValidationException("Invalid schema definition '%s'" % value)
    return descriptor


def _get_descriptor(value):
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

    if Serializable and issubclass(value, Serializable):
        return MetaSerializable(value._meta)

    if issubclass(value, Any):
        return value()

    mapped = TYPE_MAP.get(value)
    if mapped is not None:
        return mapped()


class Any(object):
    """Indicates that any value is accepted"""

    def __init__(self, default=None, name=None):
        """
        Args:
            default: Default to use (when no value is provided)
            name (str | None): Name for this constraint (default: lowercase of implementation class)
        """
        self.default = default
        self.name = name or self.__class__.__name__.lower()

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

    def __init__(self, meta):
        self.meta = getattr(meta, "_meta", meta)  # type: runez.ClassMetaDescription.__class__ # noqa
        super(MetaSerializable, self).__init__(default=None, name=self.meta.cls.__name__)

    def _problem(self, value):
        if not isinstance(value, dict):
            return "expecting compliant dict, got '%s'" % value

        return self.meta.problem(value)

    def _converted(self, value):
        return self.meta.from_dict(value)


class Boolean(Any):
    """Represents boolean type"""

    def _converted(self, value):
        if isinstance(value, string_type):
            return value.lower() in TRUE_TOKENS

        return bool(value)


class Date(Any):
    """Represents date/datetime type"""

    def _problem(self, value):
        if to_date(value) is None:
            return "expecting date, got '%s'" % value

    def _converted(self, value):
        return to_date(value)


class Dict(Any):
    """Dict with optionally key/value constrained as well"""

    def __init__(self, key=None, value=None, default=None, name=None):
        """
        Args:
            key: Optional constraint for keys
            value: Optional constraint for values
            default: Default to use when no value was provided
            name (str | None): Name for this constraint (default: dict)
        """
        self.key = get_descriptor(key)  # type: Any
        self.value = get_descriptor(value)  # type: Any
        super(Dict, self).__init__(default=default, name=name)

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

    def __init__(self, subtype=None, default=None, name=None):
        """
        Args:
            subtype: Optional constraint for values
            default: Default to use when no value was provided
            name (str | None): Name for this constraint (default: list)
        """
        self.subtype = get_descriptor(subtype)  # type: Any
        super(List, self).__init__(default=default, name=name)

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


TYPE_MAP = {
    dict: Dict,
    int: Integer,
    list: List,
    set: List,
    string_type: String,
    tuple: List,
}
