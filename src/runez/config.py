"""
Convenient (but flexible) small configuration client

Usage example:

    import runez

    # One time initialization, call this from your main()
    @click.command()
    @click.option("--config", metavar="KEY=VALUE", multiple=True, help="Override configuration")
    def main(config):
        runez.config.use_cli(config)
        runez.config.use_env_vars(prefix="MY_PROGRAM_")
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

from runez.base import decode, stringified
from runez.convert import affixed, capped, flattened, SANITIZED, snakified, to_boolean, to_bytesize, to_float, to_int


class Configuration:
    """
    Holds configuration from N providers.
    First provider with a value for a given key wins.

    Providers are identified by their provider_id()
    Adding a 2nd provider with same id as an existing one replaces it (instead of being added)
    """

    # Optional callable to report which values were successfully looked up (set to something like logging.debug for example)
    tracer = None  # type: callable

    def __init__(self, *providers):
        """
        Args:
            *providers: Providers to use (optional)
        """
        self.providers = []
        self.set_providers(*providers)

    def __repr__(self):
        if not self.providers:
            return "empty"

        return ", ".join(stringified(p) for p in self.providers)

    def overview(self, separator=", "):
        """str: A short overview of current providers"""
        return separator.join(p.overview() for p in self.providers)

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

    def use_propsfs(self, folder=None, front=False):
        """
        Args:
            folder (str | unicode | None): Optional custom mount folder (defaults to /mnt/props on Linux, and /Volumes/props on OSX)
            front (bool): If True, add provider to front of list
        """
        if folder is None:
            folder = "/%s/props" % ("Volumes" if sys.platform == "darwin" else "mnt")

        self.add(PropsfsProvider(folder), front=front)

    def use_cli(self, config, prefix=None, name="--config", front=True):
        """
        Args:
            config: Multi-value option, typically tuple from click CLI flag such as --config
            prefix (str | unicode | None): Prefix to add to all provided keys
            name (str | unicode): Name of cli flag
            front (bool): If True, add provider to front of list
        """
        if config is not None:
            provider = DictProvider(parsed_dict(config, prefix=prefix), name=name)
            self.add(provider, front=front)

    def use_env_vars(self, prefix=None, suffix=None, normalizer=snakified, name=None, front=True):
        """
        Args:
            prefix (str | None): Prefix to normalize keys with
            suffix (str | None): Suffix to normalize keys with
            normalizer (callable | None): Optional key normalizer to use (default: uppercase + snakified)
            name (str | unicode): Name to identify config provider as
            front (bool): If True, add provider to front of list
        """
        if name is None:
            if prefix or suffix:
                name = "%s env vars" % affixed("*", prefix=prefix, suffix=suffix)

            else:
                name = "env vars"

        provider = DictProvider(os.environ, name=name, prefix=prefix, suffix=suffix, normalizer=normalizer)
        self.add(provider, front=front)

    def use_json(self, *paths):
        """
        Args:
            *paths (str | unicode): Paths to files to add as static DictProvider-s, only existing files are added
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
        if provider:
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
            key (str | unicode | None): Key to lookup
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
            key (str | unicode | None): Key to lookup
            default (str | unicode | None): Default to use if key is not configured

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
            key (str | unicode): Key to lookup
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
            key (str | unicode): Key to lookup
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
            key (str | unicode): Key to lookup
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
            key (str | unicode): Key to lookup
            default (int | str | unicode | None): Default to use if key is not configured
            minimum (int | str | unicode | None): If specified, result can't be below this minimum
            maximum (int | str | unicode | None): If specified, result can't be above this maximum
            default_unit (str | unicode | None): Default unit for unqualified values
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
            key (str | unicode): Key to lookup
            default (str | unicode | dict | list | None): Default to use if key is not configured

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


CONFIG = Configuration()

clear = CONFIG.clear
set_providers = CONFIG.set_providers
use_propsfs = CONFIG.use_propsfs
use_cli = CONFIG.use_cli
use__env_vars = CONFIG.use_env_vars
use_json = CONFIG.use_json
get = CONFIG.get
get_str = CONFIG.get_str
get_int = CONFIG.get_int
get_float = CONFIG.get_float
get_bool = CONFIG.get_bool
get_bytesize = CONFIG.get_bytesize
get_json = CONFIG.get_json


class ConfigProvider:
    """
    Interface for config providers, that associate a value to a given key
    """

    key_normalizer = None  # Optional callable to use to normalize keys on query
    prefix = None  # Optional prefix to use
    suffix = None  # Optional suffix to use

    def __repr__(self):
        return self.provider_id()

    def overview(self):
        """str: A short overview of this provider"""
        return stringified(self)

    def provider_id(self):
        """Id of this provider (there can only be one active at a time)"""
        return self.__class__.__name__.replace("Provider", "").lower()

    def normalized_key(self, key):
        """
        Args:
            key (str | unicode): Key being looked up

        Returns:
            (str): Normalized key to effectively use for lookup in this provider
        """
        return affixed(key, prefix=self.prefix, suffix=self.suffix, normalize=self.key_normalizer)

    def get(self, key):
        """
        Args:
            key (str | unicode): Key to lookup

        Returns:
            Configured value, if any
        """
        normal_key = self.normalized_key(key)
        return self._get(normal_key)

    def _get(self, key):
        """Effective implementation, to be provided by descendants"""


class PropsfsProvider(ConfigProvider):
    """
    Lookup values from a virtual folder, typically /mnt/props (or /Volumes/props on OSX)
    """

    def __init__(self, folder):
        """
        Args:
            folder (str | unicode): Path to propsfs virtual mount
        """
        self.folder = folder

    def overview(self):
        """str: A short overview of this provider"""
        return "%s: %s" % (self, self.folder)

    def _get(self, key):
        try:
            path = os.path.join(self.folder, key)
            with open(path) as fh:
                return decode(fh.read())

        except IOError:
            pass

        return None


class DictProvider(ConfigProvider):
    """Key-value pairs from a given dict"""

    def __init__(self, values, name=None, prefix=None, suffix=None, normalizer=None):
        """
        Args:
            values (dict | None): Given values
            name (str | unicode | None): Symbolic name given to this provider
            prefix (str | None): Prefix to normalize keys with
            suffix (str | None): Suffix to normalize keys with
            normalizer (callable | None): Optional key normalizer to use
        """
        self.name = name or "dict"
        self.values = values or {}
        self.key_normalizer = normalizer
        self.prefix = prefix
        self.suffix = suffix

    def overview(self):
        """str: A short overview of this provider"""
        return "%s: %s values" % (self.name, len(self.values))

    def provider_id(self):
        return self.name

    def _get(self, key):
        return self.values.get(key)


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


def parsed_dict(value, prefix=None, separators="=,"):
    """
    Args:
        value (str | None): Text with key/value pairs to parse into a dict
        prefix (str | unicode | None): Optional prefix for keys (if provided, `prefix.` is added to all keys)
        separators (str | unicode): 2 chars: 1st is assignment separator, 2nd is key-value pair separator

    Returns:
        (dict): Parse key/values
    """
    if not value or isinstance(value, dict):
        return value or {}

    result = {}
    for val in flattened(value, split=(separators[1], SANITIZED)):
        if not val:
            continue

        if hasattr(val, "partition"):
            k, _, v = val.partition(separators[0])
            k = k.strip()
            if k:
                v = v.strip()
                if prefix and not k.startswith(prefix):
                    k = "%s.%s" % (prefix, k)
                result[k] = v

    return result
