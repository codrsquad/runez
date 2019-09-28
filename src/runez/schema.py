"""
Allows to define a simple one-level-at-a-time schema to help control (de)serialization

Example:
    import runez
    from runez.serialize import Dict, Integer, Serializable, String

    class MyClass(Serializable):

        name = String(default="joe")  # All instances will get "joe" by default, and deserialization will ensure string

        map = Dict(String, Integer)  # No default value (ie: None), deserialization will ensure proper type is used
"""

from runez.base import string_type


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

    def problem(self, value, ignore):
        """
        Args:
            value: Value to inspect
            ignore (bool | list | None): See runes.Serializable.set_from_dict()

        Returns:
            (str | None): Explanation of compliance issue, if there is any
        """
        if value is None:
            return None

        return self._problem(value, ignore)

    def _problem(self, value, ignore):
        """To be re-defined by descendants, `value` is never `None`"""
        return None

    def converted(self, value, ignore):
        """
        Args:
            value: Value to inspect
            ignore (bool | list | None): See runes.Serializable.set_from_dict()

        Returns:
            Converted value complying to this type
        """
        if value is None:
            return None

        return self._converted(value, ignore)

    def _converted(self, value, ignore):
        """To be re-defined by descendants, `value` is never `None`"""
        return value


class Serializable(Any):
    """Represents a descendant of `runez.Serializable`"""

    def __init__(self, serializable):
        self.serializable = serializable  # type: runez.Serializable.__class__ # noqa
        super(Serializable, self).__init__(default=None, name=serializable.__name__)

    def _problem(self, value, ignore):
        if not isinstance(value, dict):
            return "expecting compliant dict, got '%s'" % value

        return self.serializable._meta.problem(value, ignore)

    def _converted(self, value, ignore):
        return self.serializable.from_dict(value, ignore=ignore)


class Date(Any):
    pass


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
        if isinstance(key, type):
            key = key()
        if isinstance(value, type):
            value = value()
        self.key = key  # type: Any
        self.value = value  # type: Any
        super(Dict, self).__init__(default=default, name=name)

    def representation(self):
        return "%s[%s, %s]" % (self.name, subtype_representation(self.key), subtype_representation(self.value))

    def _problem(self, value, ignore):
        if not isinstance(value, dict):
            return "expecting dict, got '%s'" % value

        for k, v in value.items():
            problem = subtype_problem(self.key, k, ignore)
            if problem is not None:
                return "key: %s" % problem

            problem = subtype_problem(self.value, v, ignore)
            if problem is not None:
                return "value: %s" % problem

    def _converted(self, value, ignore):
        return dict((subtype_converted(self.key, k, ignore), subtype_converted(self.value, v, ignore)) for k, v in value.items())


class Integer(Any):
    """Represents integer type"""

    def _problem(self, value, ignore):
        try:
            int(value)
            return None

        except (TypeError, ValueError):
            return "'%s' is not an integer" % value

    def _converted(self, value, ignore):
        return int(value)


class List(Any):
    """List with optionally values constrained as well"""

    def __init__(self, subtype=None, default=None, name=None):
        """
        Args:
            subtype: Optional constraint for values
            default: Default to use when no value was provided
            name (str | None): Name for this constraint (default: list)
        """
        if isinstance(subtype, type):
            subtype = subtype()
        self.subtype = subtype  # type: Any
        super(List, self).__init__(default=default, name=name)

    def representation(self):
        return "%s[%s]" % (self.name, subtype_representation(self.subtype))

    def _problem(self, value, ignore):
        if not isinstance(value, (list, set, tuple)):
            return "expecting list, got '%s'" % value

        for v in value:
            problem = subtype_problem(self.subtype, v, ignore)
            if problem is not None:
                return problem

    def _converted(self, value, ignore):
        return [subtype_converted(self.subtype, v, ignore) for v in value]


class String(Any):
    """Represents string type"""

    def _problem(self, value, ignore):
        if not isinstance(value, string_type):
            return "expecting string, got '%s'" % value


def subtype_representation(subtype):
    """
    Args:
        subtype (Any | None): Subtype to return representation of

    Returns:
        (str): Appropriate representation
    """
    return "*" if subtype is None else subtype.representation()


def subtype_problem(subtype, value, ignore):
    """
    Args:
        subtype (Any | None): Subtype to use
        value: Value to verify compliance of
        ignore (bool | list | None): Passed-through to subtype.problem()

    Returns:
        (str | None): Explanation of compliance issue, if there is any
    """
    if subtype is None:
        return None

    return subtype.problem(value, ignore)


def subtype_converted(subtype, value, ignore):
    """
    Args:
        subtype (Any | None): Subtype to use
        value: Value to convert
        ignore (bool | list | None): Passed-through to subtype.problem()

    Returns:
        Appropriately converted value
    """
    if subtype is None:
        return value

    return subtype.converted(value, ignore)
