"""
This is module should not import any other runez module, it's the lowest on the import chain
"""

import pathlib
import re
from collections import defaultdict

from runez.system import _R, flattened, joined, stringified


DEFAULT_BASE = 1000
DEFAULT_UNITS = "KMGTP"
RE_CAMEL_CASE_WORDS = re.compile(r"(^[a-z]+|[A-Z](?:[a-z]+|[A-Z]*(?=[A-Z]|$)))")
RE_WORDS = re.compile(r"[^\w]+")
TRUE_TOKENS = {"on", "true", "y", "yes"}


def parsed_tabular(content):
    """
    Args:
        content (str): Tabular output, such as the output of `ps -f`

    Returns:
        (list[dict]): Parsed output, one entry per parsed line, each line is a dict keyed by the stated header from output
    """
    if isinstance(content, str):
        content = content.splitlines()

    return list(_TabularHeader.parsed_lines(content))


def represented_bytesize(size, unit="B", base=1024, delimiter=" ", prefixes=DEFAULT_UNITS):
    """Human friendly byte size representation

    >>> represented_bytesize(1024)
    '1 KB'
    >>> represented_bytesize(10_000_000_000)
    '9 GB'
    >>> represented_bytesize(10_000_000_000, unit="b", delimiter="", base=1000)
    '10Gb'

    Args:
        size (int | float | pathlib.Path): Size to represent
        unit (str): Unit symbol
        base (int): Base to represent it in (example: 1024 for bytes, 1000 for bits)
        delimiter (str): Delimiter to use between number and units
        prefixes (str): Prefixes to use per power (kilo, mega, giga, tera, peta, ...)

    Returns:
        (str): Human friendly byte size representation
    """
    if isinstance(size, pathlib.Path):
        size = _R.filesize(size)

    return _represented_with_units(size, unit, base, delimiter, prefixes)


def represented_with_units(size, unit="", base=1000, delimiter="", prefixes=DEFAULT_UNITS):
    """
    Args:
        size (int | float): Size to represent
        unit (str): Unit symbol
        base (int): Base to represent it in (example: 1024 for bytes, 1000 for bits)
        delimiter (str): Delimiter to use between number and units
        prefixes (str): Prefixes to use per power (kilo, mega, giga, tera, peta, ...)

    Returns:
        (str): Human friendly representation with units, avoids having to read/parse visually large numbers
    """
    return _represented_with_units(size, unit, base, delimiter, prefixes)


def to_boolean(value):
    """Convert `value` to boolean, strings considered to represent True are limited to: "true", "yes", "y" or "on".
    For all other types: python truthiness applies.

    Args:
        value: Value to convert to bool

    Returns:
        (bool): Deduced boolean value
    """
    if isinstance(value, str):
        if value.lower() in TRUE_TOKENS:
            return True

        return bool(to_float(value))

    return bool(value)


def to_bytesize(value, default_unit=None, base=1024):
    """Convert `value` to bytes, accepts notations such as "4k" to mean 4096 bytes

    Args:
        value (str | int | None): Number of bytes optionally suffixed by 1 or 2 chars designating unit (ie: "m" or "kb" etc)
        default_unit (str | None): Default unit to use for unqualified values
        base (int): Base to use (usually 1024)

    Returns:
        (int | None): Deduced bytesize value, if possible
    """
    if value is not None:
        v = to_float(value)
        if v is not None:
            return unitized(v, default_unit, base)

        try:
            if value[-1].lower() == "b":
                # Accept notations such as "1mb", as they get used out of habit
                value = value[:-1]

            unit = value[-1:].lower()
            if unit.isdigit():
                unit = default_unit

            else:
                value = value[:-1]

            return unitized(to_float(value), unit, base)

        except (AttributeError, IndexError, KeyError, TypeError, ValueError):
            return None


def to_float(value, lenient=False, default=None):
    """
    Args:
        value: Value to convert to float
        lenient (bool): If True, returned number is returned as an `int` if possible first, float otherwise
        default: Default to return when value can't be converted

    Returns:
        (float | int | None): Extracted float if possible, otherwise `None`
    """
    if isinstance(value, str):
        return _float_from_text(value, lenient=lenient, default=default)

    if lenient:
        try:
            return int(value)

        except (TypeError, ValueError):
            pass

    try:
        return float(value)

    except (TypeError, ValueError):
        return default


def to_int(value, default=None):
    """
    Args:
        value: Value to convert to int
        default: Default to return when value can't be converted

    Returns:
        (int | None): Extracted int if possible, otherwise `None`
    """
    if isinstance(value, str):
        return _int_from_text(value, default=default)

    try:
        return int(value)

    except (TypeError, ValueError):
        return default


def affixed(text, prefix=None, suffix=None, normalize=None):
    """
    Args:
        text (str | None): Text to ensure prefixed
        prefix (str | None): Prefix to add (if not already there)
        suffix (str | None): Suffix to add (if not already there)
        normalize (callable | None): Optional function to apply to `text`

    Returns:
        (str | None): `text' guaranteed starting with `prefix` and ending with `suffix`
    """
    if text is not None:
        if normalize:
            text = normalize(text)

        if prefix and not text.startswith(prefix):
            text = prefix + text

        if suffix and not text.endswith(suffix):
            text = text + suffix

    return text


def camel_cased(text, delimiter=""):
    """
    Args:
        text (str): Text to camel case
        delimiter (str): Delimiter to use to join the words back

    Returns:
        (str): Camel-cased text
    """
    return wordified(text, delimiter=delimiter, normalize=str.title)


def entitled(text, delimiter=" "):
    """
    Args:
        text (str): Text to turn into title
        delimiter (str): Delimiter to use to join the words back

    Returns:
        (str): First letter (of 1st word only) upper-cased
    """
    strings = words(text)
    if strings:
        strings[0] = strings[0].title()

    return delimiter.join(strings)


def identifiers(text):
    """Identifiers extracted from `text` (words, NOT split on underscore character)

    Args:
        text: Text to extract identifiers from

    Returns:
        (list): Identifiers found
    """
    return words(text, split=None)


class Pluralizer:
    """Quick heuristic to pluralize most common english words"""

    letter_based = {"s": "ses", "x": "xes", "y": "ies"}
    suffix_based = {"ch": "ches", "fe": "ves", "man": "men", "sh": "shes"}
    word_based = {"child": "children", "person": "people"}

    @classmethod
    def find_letter_based(cls, singular):
        irregular = cls.letter_based.get(singular[-1])
        if irregular is not None:
            return 1, irregular

    @classmethod
    def plural(cls, singular):
        irregular = cls.word_based.get(singular)
        if irregular:
            return irregular

        for suffix in cls.suffix_based:
            if singular.endswith(suffix):
                c = len(suffix)
                return "%s%s" % (singular[:-c], cls.suffix_based[suffix])

        irregular = cls.find_letter_based(singular)
        if irregular:
            return singular[:-irregular[0]] + irregular[1]

        return "%ss" % singular


def plural(countable, singular=None, base=1000, prefixes=DEFAULT_UNITS):
    """
    Args:
        countable: How many things there are (can be int, or something countable)
        singular: What is counted (example: "record", or "chair", etc...)
        base (int | None): Optional base to unitize count representation
        prefixes (str | None): Prefixes to use per power (kilo, mega, giga, tera, peta, ...)

    Returns:
        (str): Rudimentary, best-effort plural of "<count> <name>(s)"
    """
    if isinstance(countable, str) and singular is None:
        return Pluralizer.plural(countable)

    if singular is None:
        singular = "value"

    count = len(countable) if hasattr(countable, "__len__") else countable
    if count == 1:
        return "1 %s" % singular

    plural = Pluralizer.plural(singular)
    if count is None:
        return "no %s" % plural

    count = _represented_with_units(count, "", base, "", prefixes)
    return "%s %s" % (count, plural)


def snakified(text, normalize=str.upper):
    """
    Args:
        text (str): Text to transform
        normalize (callable | None): Optional function to apply on each word

    Returns:
        (str | None): Upper-cased and snake-ified
    """
    return wordified(text, normalize=normalize)


def wordified(text, delimiter="_", normalize=None):
    """
    Args:
        text (str | None): Text to process as words
        delimiter (str): Delimiter to use to join the words back
        normalize (callable | None): Optional function to apply on each word

    Returns:
        (str): Dashes replaced by underscore
    """
    if text is None:
        return None

    return delimiter.join(words(text, normalize=normalize))


def words(text, normalize=None, split="_", decamel=False):
    """Words extracted from `text` (split on underscore character as well by default)

    Args:
        text: Text to extract words from
        normalize (callable | None): Optional function to apply on each word
        split (str | None): Optional extra character to split words on
        decamel (bool): If True, extract CamelCase words as well

    Returns:
        (list): Extracted words
    """
    if not text:
        return []

    if isinstance(text, list):
        result = []
        for line in text:
            result.extend(words(line, normalize=normalize, split=split, decamel=decamel))

        return result

    strings = RE_WORDS.split(stringified(text))
    strings = flattened(strings, split=split, strip=True)
    if decamel:
        strings = flattened(RE_CAMEL_CASE_WORDS.findall(s) for s in strings)

    if normalize:
        strings = [normalize(s) for s in strings]

    return strings


def unitized(value, unit, base=DEFAULT_BASE, unitseq=DEFAULT_UNITS):
    """
    Args:
        value (int | float): Value to expand
        unit (str): Given unit
        base (int): Base to use (usually 1024)
        unitseq (str): Sequence of 1-letter representation for each exponent level

    Returns:
        Deduced value (example: "1k" becomes 1000)
    """
    exponent = _get_unit_exponent(unit, unitseq)
    if exponent is not None:
        return int(round(value * (base ** exponent)))


def _get_unit_exponent(unit, unitseq, default=None):
    try:
        return 0 if not unit else unitseq.upper().index(unit.upper()) + 1

    except ValueError:
        return default


def _int_from_text(text, base=None, default=None):
    """
    Args:
        text (str): Text to convert to int
        base (int | None): Base to use (managed internally, no need to specify)
        default: Default to return when value can't be converted

    Returns:
        (int | None): Extracted int if possible, otherwise `None`
    """
    try:
        if base is None:
            return int(text)

        return int(text, base=base)

    except ValueError:
        if base is None:
            if len(text) >= 3 and text[0] == "0":
                if text[1] == "o":
                    return _int_from_text(text, base=8, default=default)

                if text[1] == "x":
                    return _int_from_text(text, base=16, default=default)

    return default


def _float_from_text(text, lenient=True, default=None):
    """
    Args:
        text (str): Text to convert to float (yaml-like form ".inf" also accepted)
        lenient (bool): If True, returned number is returned as an `int` if possible first, float otherwise
        default: Default to return when value can't be converted

    Returns:
        (float | None): Extracted float if possible, otherwise `None`
    """
    value = _int_from_text(text, default=default)  # Allows to also support hex/octal numbers
    if value is not None:
        return value if lenient else float(value)

    try:
        return float(text)

    except ValueError:
        if len(text) >= 3 and text[-1] in "fF" and (text[0] == "." or text[1] == "."):
            try:
                return float(text.replace(".", "", 1))  # Edge case: "[+-]?.inf"

            except ValueError:
                pass

    return default


def _represented_with_units(size, unit, base, delimiter, prefixes, exponent=0):
    if not base:
        return "%g" % size

    if size >= base and exponent < len(prefixes):
        size = float(size) / base
        return _represented_with_units(size, unit, base, delimiter, prefixes, exponent=exponent + 1)

    if exponent == 0:
        if unit:
            return "%g%s%s" % (size, delimiter, unit)

        return "%g" % size

    fmt = "%.{precision}f".format(precision=0 if size > 9 else 1)
    represented_size = fmt % size
    if "." in represented_size:
        represented_size = represented_size.strip("0").strip(".")

    return "%s%s%s%s" % (represented_size, delimiter, prefixes[exponent - 1], unit)


class _TabularInterval:
    """Allows to parse tabulated output such as given by the `ps` command, tracks header column positions"""

    def __init__(self, name, start=0, end=0):
        self.name = name
        self.start = start
        self.end = end
        self.next = None

    def __repr__(self):  # pragma: no cover, for debugging
        return "%s [%s:%s]" % (self.name, self.start or "", self.end or "")

    def intersect(self, index):
        """Find next interval intersecting with given 'index'"""
        if self.next is not None and index >= self.next.start:
            return self.next.intersect(index)

        return self


class _TabularHeader:
    """Allows to parse `ps` tabulated output, parses header then can extract rest of `ps` output info"""

    regex = re.compile(r"(\s*)(\S+)")

    def __init__(self, header):
        """
        Args:
            header (str): First line from `ps -f` output
        """
        self.header = header
        self.tabs = []
        self.tabs_by_name = {}
        m = self.regex.search(header, 0)
        prev_tab = None
        while m:
            wstart, wend = m.span(2)
            word = header[wstart:wend].upper()
            tab = _TabularInterval(word, wstart, wend)
            self.tabs.append(tab)
            self.tabs_by_name[word] = tab
            if prev_tab is not None:
                prev_tab.next = tab

            prev_tab = tab
            m = self.regex.search(header, wend + 1)

        if self.tabs:
            self.tabs[0].start = 0

    def __repr__(self):  # pragma: no cover, for debugging
        return joined(self.tabs)

    @classmethod
    def parsed_lines(cls, lines):
        """
        Args:
            lines (list): Lines to parse
        """
        if lines:
            parser = None
            for line in lines:
                if parser is None:
                    parser = _TabularHeader(line)
                    if not parser.tabs:
                        return

                else:
                    data = parser.parsed_line(line)
                    if data:
                        yield data

    def parsed_line(self, line):
        """
        Args:
            line (str): Parsed subsequent (non-header) line

        Returns:
            (dict): Extracted info
        """
        data = defaultdict(list)
        current = self.tabs[0]
        m = self.regex.search(line, 0)
        while m:
            wstart, wend = m.span(2)
            text = line[wstart:wend]
            current = current.intersect(wend)
            data[current.name].append(text)
            m = self.regex.search(line, wend + 1)

        data = dict((k, joined(v)) for k, v in data.items())
        return data
