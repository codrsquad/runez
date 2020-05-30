"""
Convenient (but flexible) small configuration client

Usage example:

    import runez

    # One time initialization, call this from your main()
    @runez.click.command()
    @runez.click.config(default="foo=5", env="MY_PROGRAM")
    def main():
        runez.config.use_json("~/.config/my-program.json", "/etc/my-program.json")

    # Get values from anywhere in your code
    runez.config.get("foo")
    runez.config.get_int("foo", minimum=5, maximum=10)
    runez.config.get_bytesize("foo", default="1k")
    ...
"""

import json
import os
import sys

from runez.convert import to_boolean, to_bytesize, to_float, to_int
from runez.file import readlines
from runez.system import decode, stringified


class Configuration:
    """
    Holds configuration from N providers.
    First provider with a value for a given key wins.

    Providers are identified by their provider_id()
    Adding a 2nd provider with same id as an existing one replaces it (instead of being added)
    """

    def __init__(self, providers=None, tracer=None):
        """
        Args:
            providers (list | None): Providers to use (optional)
            tracer (callable | None): Optional callable to report config activity (set to something like logging.debug for example)
        """
        self.providers = []
        self.tracer = tracer
        if providers is not None:
            for provider in providers:
                self.add(provider)

    def __repr__(self):
        if not self.providers:
            return "empty"

        return ", ".join(stringified(p) for p in self.providers)

    def __len__(self):
        return sum(len(p) for p in self.providers)

    @property
    def values(self):
        """dict: values in this provider"""
        result = {}
        for p in reversed(self.providers):
            v = p.values
            if v is not None:
                result.update(v)

        return result

    def overview(self, delimiter=", "):
        """str: A short overview of current providers"""
        return delimiter.join(p.overview() for p in self.providers)

    def _trace(self, message):
        if self.tracer:
            self.tracer(message)

    def clear(self):
        """Remove all providers"""
        self.providers = []

    def set_providers(self, *providers):
        """Replace current providers with given ones"""
        if self.providers:
            self.clear()

        for provider in providers:
            self.add(provider)

    def provider_by_name(self, name):
        for provider in self.providers:
            if provider.name == name:
                return provider

    def provider_id_slot(self, other):
        """
        Args:
            other (ConfigProvider): Provider to examine

        Returns:
            (int | None): Index of existing provider with same id, if any
        """
        if other:
            pid = other.provider_id()
            for i, provider in enumerate(self.providers):
                if provider.provider_id() == pid:
                    return i

        return None

    def use_json(self, *paths):
        """
        Args:
            *paths (str): Paths to files to add as static DictProvider-s, only existing files are added
        """
        for path in paths:
            if path:
                fpath = os.path.expanduser(path)
                if os.path.exists(fpath):
                    with open(fpath) as fh:
                        provider = DictProvider(json.load(fh), name=path)
                        self.add(provider)

    def add(self, provider, front=False):
        """
        Args:
            provider (ConfigProvider): Provider to add
            front (bool): If True, add provider to front of list
        """
        if not isinstance(provider, ConfigProvider):
            raise ValueError("Invalid config provider '%s'" % provider)

        i = self.provider_id_slot(provider)
        if i is not None:
            self._trace("Replacing config provider %s at index %s" % (provider, i))
            self.providers[i] = provider

        elif front and self.providers:
            self._trace("Adding config provider %s to front" % provider)
            self.providers.insert(0, provider)

        else:
            self._trace("Adding config provider %s" % provider)
            self.providers.append(provider)

    def get(self, key, default=None):
        """
        Args:
            key (str | None): Key to lookup
            default: Default to use if key is not configured

        Returns:
            Value of key, if defined
        """
        if key:
            for provider in self.providers:
                value = provider.get(key)
                if value is not None:
                    self._trace("Using %s='%s' from %s" % (key, value, provider))
                    return value

        return default

    def get_str(self, key, default=None):
        """
        Args:
            key (str | None): Key to lookup
            default (str | None): Default to use if key is not configured

        Returns:
            (str | None): Value of key, if defined
        """
        value = self.get(key, default=default)
        if value is None:
            return None
        return stringified(value)

    def get_int(self, key, default=None, minimum=None, maximum=None):
        """
        Args:
            key (str): Key to lookup
            default (int | None): Default to use if key is not configured
            minimum (int | None): If specified, result can't be below this minimum
            maximum (int | None): If specified, result can't be above this maximum

        Returns:
            (int | None): Value of key, if defined
        """
        return capped(to_int(self.get(key), default=default), minimum=minimum, maximum=maximum)

    def get_float(self, key, default=None, minimum=None, maximum=None):
        """
        Args:
            key (str): Key to lookup
            default (float | None): Default to use if key is not configured
            minimum (float | None): If specified, result can't be below this minimum
            maximum (float | None): If specified, result can't be above this maximum

        Returns:
            (float | None): Value of key, if defined
        """
        return capped(to_float(self.get(key), default=default), minimum=minimum, maximum=maximum)

    def get_bool(self, key, default=None):
        """
        Args:
            key (str): Key to lookup
            default (bool | None): Default to use if key is not configured

        Returns:
            (bool | None): Value of key, if defined
        """
        value = self.get_str(key)
        if value is not None:
            return to_boolean(value)

        return default

    def get_bytesize(self, key, default=None, minimum=None, maximum=None, default_unit=None, base=1024):
        """Size in bytes expressed by value configured under 'key'

        Args:
            key (str): Key to lookup
            default (int | str | None): Default to use if key is not configured
            minimum (int | str | None): If specified, result can't be below this minimum
            maximum (int | str | None): If specified, result can't be above this maximum
            default_unit (str | None): Default unit for unqualified values
            base (int): Base to use (usually 1024)

        Returns:
            (int): Size in bytes
        """
        value = to_bytesize(self.get_str(key), default_unit, base)
        if value is None:
            return to_bytesize(default, default_unit, base)

        return capped(value, to_bytesize(minimum, default_unit, base), to_bytesize(maximum, default_unit, base))

    def get_json(self, key, default=None):
        """
        Args:
            key (str): Key to lookup
            default (str | dict | list | None): Default to use if key is not configured

        Returns:
            (dict | list | str | int | None): Deserialized json, if any
        """
        value = self.get_str(key)
        if value is not None:
            value = from_json(value)
            if value is not None:
                return value

        if isinstance(default, (dict, list)):
            return default

        return from_json(default)


CONFIG = Configuration()  # Global config object, clients can decide to use this for simplicity


def capped(value, minimum=None, maximum=None):
    """
    Args:
        value: Value to cap
        minimum: If specified, value should not be lower than this minimum
        maximum: If specified, value should not be higher than this maximum

    Returns:
        `value` capped to `minimum` and `maximum` (if it is outside of those bounds)
    """
    if value is not None:
        if minimum is not None and value < minimum:
            return minimum

        if maximum is not None and value > maximum:
            return maximum

    return value


def get(key, default=None):
    """
    Args:
        key (str | None): Key to lookup
        default: Default to use if key is not configured

    Returns:
        Value of key, if defined
    """
    return CONFIG.get(key, default=default)


def get_str(key, default=None):
    """
    Args:
        key (str | None): Key to lookup
        default (str | None): Default to use if key is not configured

    Returns:
        (str | None): Value of key, if defined
    """
    return CONFIG.get_str(key, default=default)


def get_int(key, default=None, minimum=None, maximum=None):
    """
    Args:
        key (str): Key to lookup
        default (int | None): Default to use if key is not configured
        minimum (int | None): If specified, result can't be below this minimum
        maximum (int | None): If specified, result can't be above this maximum

    Returns:
        (int | None): Value of key, if defined
    """
    return CONFIG.get_int(key, default=default, minimum=minimum, maximum=maximum)


def get_float(key, default=None, minimum=None, maximum=None):
    """
    Args:
        key (str): Key to lookup
        default (float | None): Default to use if key is not configured
        minimum (float | None): If specified, result can't be below this minimum
        maximum (float | None): If specified, result can't be above this maximum

    Returns:
        (float | None): Value of key, if defined
    """
    return CONFIG.get_float(key, default=default, minimum=minimum, maximum=maximum)


def get_bool(key, default=None):
    """
    Args:
        key (str): Key to lookup
        default (bool | None): Default to use if key is not configured

    Returns:
        (bool | None): Value of key, if defined
    """
    return CONFIG.get_bool(key, default=default)


def get_bytesize(key, default=None, minimum=None, maximum=None, default_unit=None, base=1024):
    """Size in bytes expressed by value configured under 'key'

    Args:
        key (str): Key to lookup
        default (int | str | None): Default to use if key is not configured
        minimum (int | str | None): If specified, result can't be below this minimum
        maximum (int | str | None): If specified, result can't be above this maximum
        default_unit (str | None): Default unit for unqualified values
        base (int): Base to use (usually 1024)

    Returns:
        (int): Size in bytes
    """
    return CONFIG.get_bytesize(key, default=default, minimum=minimum, maximum=maximum, default_unit=default_unit, base=base)


def get_json(key, default=None):
    """
    Args:
        key (str): Key to lookup
        default (str | dict | list | None): Default to use if key is not configured

    Returns:
        (dict | list | str | int | None): Deserialized json, if any
    """
    return CONFIG.get_json(key, default=default)


class ConfigProvider:
    """
    Interface for config providers, that associate a value to a given key
    """

    def __repr__(self):
        return self.provider_id()

    def __len__(self):
        return 0

    @property
    def values(self):
        """dict: values in this provider"""

    def overview(self):
        """str: A short overview of this provider"""
        return "%s: %s values" % (self.provider_id(), len(self))

    def provider_id(self):
        """Id of this provider (there can only be one active at a time)"""
        return self.__class__.__name__.replace("Provider", "").lower()

    def get(self, key):
        """
        Args:
            key (str): Key to lookup

        Returns:
            Configured value, if any
        """


class PropsfsProvider(ConfigProvider):
    """
    Lookup values from a virtual folder, typically /mnt/props (or /Volumes/props on OSX)
    """

    def __init__(self, folder):
        """
        Args:
            folder (str): Path to propsfs virtual mount
        """
        if not folder:
            folder = "/%s/props" % ("Volumes" if sys.platform == "darwin" else "mnt")

        self.folder = folder

    def __len__(self):
        try:
            names = os.listdir(self.folder)
            return len(names)

        except (OSError, IOError):
            return 0

    @property
    def values(self):
        """dict: values in this provider"""
        result = {}
        names = os.listdir(self.folder)
        for name in names:
            path = os.path.join(self.folder, name)
            result[name] = "\n".join(readlines(path, default=[], errors="ignore"))

        return result

    def overview(self):
        """str: A short overview of this provider"""
        return "%s: %s" % (self, self.folder)

    def get(self, key):
        try:
            path = os.path.join(self.folder, key)
            with open(path) as fh:
                return decode(fh.read())

        except (OSError, IOError):
            return None


class DictProvider(ConfigProvider):
    """Key-value pairs from a given dict"""

    def __init__(self, values, name=None):
        """
        Args:
            values (dict | None): Given values
            name (str | None): Symbolic name given to this provider
        """
        self.name = name or "dict"
        self._values = values or {}

    def __len__(self):
        return len(self._values)

    @property
    def values(self):
        """dict: values in this provider"""
        return self._values

    def provider_id(self):
        return self.name

    def get(self, key):
        return self._values.get(key)


def from_json(value):
    """
    Args:
        value: Json to parse

    Returns:
        (dict | list | str | int | None): Deserialized value, if possible
    """
    try:
        return json.loads(value)

    except (TypeError, ValueError):
        return None
