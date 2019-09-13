#  -*- encoding: utf-8 -*-

"""
This is module should not import any other runez module, it's the lowest on the import chain
"""

import datetime
import os
import re

from runez.base import UNSET


SYMBOLIC_TMP = "<tmp>"
RE_FORMAT_MARKERS = re.compile(r"{([^}]*?)}")
RE_WORDS = re.compile(r"[^\w]+")

SANITIZED = 1
SHELL = 2
UNIQUE = 4

SECONDS_IN_ONE_MINUTE = 60
SECONDS_IN_ONE_HOUR = 60 * SECONDS_IN_ONE_MINUTE
SECONDS_IN_ONE_DAY = 24 * SECONDS_IN_ONE_HOUR

DEFAULT_DURATION_SPAN = 2
EPOCH_MS_BREAK = 900000000000


def flattened(value, split=None):
    """
    Args:
        value: Possibly nested arguments (sequence of lists, nested lists)
        split (int | str | unicode | (str | unicode | None, int) | None): How to split values:
            - None: simply flatten, no further processing
            - one char string: split() on specified char
            - SANITIZED: discard all None items
            - UNIQUE: each value will appear only once
            - SHELL:  filter out sequences of the form ["-f", None] (handy for simplified cmd line specification)

    Returns:
        list: 'value' flattened out (leaves from all involved lists/tuples)
    """
    result = []
    separator = None
    mode = 0
    if isinstance(split, tuple):
        separator, mode = split
    elif isinstance(split, int):
        mode = split
    else:
        separator = split
    _flatten(result, value, separator, mode)
    return result


def formatted(text, *args, **kwargs):
    """
    Args:
        text (str | unicode): Text to format
        *args: Objects to extract values from (as attributes)
        **kwargs: Optional values provided as named args

    Returns:
        (str): Attributes from this class are expanded if mentioned
    """
    if not text or "{" not in text:
        return text
    strict = kwargs.pop("strict", True)
    max_depth = kwargs.pop("max_depth", 3)
    objects = list(args) + [kwargs] if kwargs else args[0] if len(args) == 1 else args
    if not objects:
        return text
    definitions = {}
    markers = RE_FORMAT_MARKERS.findall(text)
    while markers:
        key = markers.pop()
        if key in definitions:
            continue
        val = _find_value(key, objects)
        if strict and val is None:
            return None
        val = str(val) if val is not None else "{%s}" % key
        markers.extend(m for m in RE_FORMAT_MARKERS.findall(val) if m not in definitions)
        definitions[key] = val
    if not max_depth or not isinstance(max_depth, int) or max_depth <= 0:
        return text
    expanded = dict((k, _rformat(k, v, definitions, max_depth)) for k, v in definitions.items())
    return text.format(**expanded)


def quoted(text):
    """
    Args:
        text (str | unicode | None): Text to optionally quote

    Returns:
        (str): Quoted if 'text' contains spaces
    """
    if text and " " in text:
        sep = "'" if '"' in text else '"'
        return "%s%s%s" % (sep, text, sep)
    return text


def represented_args(args, separator=" "):
    """
    Args:
        args (list | tuple | None): Arguments to represent
        separator (str | unicode): Separator to use

    Returns:
        (str): Quoted as needed textual representation
    """
    result = []
    if args:
        for text in args:
            result.append(quoted(short(text)))
    return separator.join(result)


def duration_unit(count, name, short_form, immutable=False):
    if short_form:
        if not immutable:
            name = name[0]
    else:
        name = " %s%s" % (name, "" if immutable or count == 1 else "s")
    return "%s%s" % (count, name)


def datetime_from_epoch(epoch, flavor=None):
    """
    Args:
        epoch (int | float): Unix epoch in seconds or milliseconds, utc or local (see `flavor`)
        flavor (str | None): Default:
                             '_' separated designation when specified, `utc`, `ms` or `s` accepted
                             None or "" or "epoch": local auto-determined seconds vs milliseconds
                             "utc_ms": epoch is considered utc, in milliseconds
                             "epoch_s": epoch is considered local, explicitly in seconds

    Returns:
        (datetime.datetime): Corresponding datetime object
    """
    in_utc = None
    in_ms = None
    if flavor:
        parts = flavor.split("_")
        if parts[0] == "epoch":
            parts = parts[1:]
        if parts and parts[0] == "utc":
            in_utc = True
            parts = parts[1:]
        if parts and parts[0] in ("ms", "s"):
            in_ms = parts[0] == "ms"
            parts = parts[1:]
        if parts:
            raise Exception("Invalid epoch flavor '%s'" % flavor)
    if in_ms or (in_ms is None and epoch > EPOCH_MS_BREAK):
        epoch = epoch / 1000
    if in_utc:
        return datetime.datetime.utcfromtimestamp(epoch)
    return datetime.datetime.fromtimestamp(epoch)


def duration_in_seconds(duration=UNSET, **kwargs):
    """
    Args:
        duration (int | float | datetime.date | datetime.datetime | UNSET): Object to convert to seconds
                          (UNSET): look for `epoch`, `utc`, `utc_ms` etc keyword argument, see `datetime_from_epoch`
                          (int | float): number of seconds representing the duration
                          (datetime | date): Compute duration between given datetime and now
                          (timedelta): Take total seconds from time delta
        kwargs: Optional combination of 'epoch', 'utc', `ms` or `s`, see `datetime_from_epoch`

    Returns:
        (float | int | None): Corresponding number of seconds
    """
    if duration is UNSET:
        if not kwargs or len(kwargs) != 1:
            raise Exception("Duration not provided")
        flavor, value = list(kwargs.items())[0]
        duration = datetime_from_epoch(value, flavor)
        kwargs = None

    if kwargs:
        raise Exception("No keyword arguments expected, but got: %s" % kwargs)

    if isinstance(duration, datetime.date) and not isinstance(duration, datetime.datetime):
        duration = datetime.datetime(duration.year, duration.month, duration.day)

    if isinstance(duration, datetime.datetime):
        duration = datetime.datetime.now() - duration

    if isinstance(duration, datetime.timedelta):
        return duration.total_seconds()

    return duration


def represented_duration(duration=UNSET, span=UNSET, separator=" ", **kwargs):
    """
    Args:
        duration: Duration in seconds, or timedelta (see `duration_in_seconds`)
        span (int | None): If specified, return `span` most significant parts of the duration, specify <= 0 for short form
                           > 0: N most significant long parts, example: 1 hour 5 seconds
                           None: all parts, example: 1 hour 2 minutes 5 seconds 20 ms
                           0: all parts, short form, example: 1h 2m 5s 20ms
                           < 0: N most significant parts, short form, example: 1h 5s
                           UNSET: use `DEFAULT_DURATION_SPAN` (which can set globally per app, for convenience)
        separator (str): Separator to use between parts

    Returns:
        (str): Human friendly duration representation
    """
    seconds = duration_in_seconds(duration=duration, **kwargs)
    if not isinstance(seconds, (int, float)):
        return "" if seconds is None else str(seconds)

    if span is UNSET:
        span = DEFAULT_DURATION_SPAN
    short_form = span is not None and span <= 0
    if span is not None:
        span = abs(span)

    seconds = abs(seconds)
    microseconds = 0 if span and seconds > 10 else int(round((seconds - int(seconds)) * 1000000))
    seconds = int(seconds)

    result = []
    # First, separate seconds and days
    days = seconds // SECONDS_IN_ONE_DAY
    seconds -= days * SECONDS_IN_ONE_DAY

    # Break down days into years, weeks and days
    years = days // 365
    days -= years * 365
    weeks = days // 7
    days -= weeks * 7

    # Break down seconds into hours, minutes and seconds
    hours = seconds // SECONDS_IN_ONE_HOUR
    seconds -= hours * SECONDS_IN_ONE_HOUR
    minutes = seconds // SECONDS_IN_ONE_MINUTE
    seconds -= minutes * SECONDS_IN_ONE_MINUTE

    if years:
        result.append(duration_unit(years, "year", short_form))
    if weeks:
        result.append(duration_unit(weeks, "week", short_form))
    if days:
        result.append(duration_unit(days, "day", short_form))

    if hours:
        result.append(duration_unit(hours, "hour", short_form))
    if minutes:
        result.append(duration_unit(minutes, "minute", short_form))
    if seconds:
        result.append(duration_unit(seconds, "second", short_form))

    if microseconds:
        milliseconds = microseconds // 1000
        microseconds = microseconds % 1000
        if milliseconds:
            result.append(duration_unit(milliseconds, "ms", short_form, immutable=True))
        if microseconds:
            result.append(duration_unit(microseconds, "μs", short_form, immutable=True))

    if not result:
        result.append(duration_unit(seconds, "second", short_form))

    if span:
        result = result[:span]

    return separator.join(result)


def resolved_path(path, base=None):
    """
    Args:
        path (str | unicode | None): Path to resolve
        base (str | unicode | None): Base path to use to resolve relative paths (default: current working dir)

    Returns:
        (str): Absolute path
    """
    if not path or path.startswith(SYMBOLIC_TMP):
        return path

    path = os.path.expanduser(path)
    if base and not os.path.isabs(path):
        return os.path.join(resolved_path(base), path)

    return os.path.abspath(path)


def short(path):
    return Anchored.short(path)


def shortened(text, size=120):
    """
    Args:
        text (str | unicode): Text to shorten
        size (int): Max chars

    Returns:
        (str): Leading part of 'text' with at most 'size' chars
    """
    if text:
        text = text.strip()
        if len(text) > size:
            return "%s..." % text[:size - 3].strip()
    return text


class Anchored(object):
    """
    An "anchor" is a known path that we don't wish to show in full when printing/logging
    This allows to conveniently shorten paths, and show more readable relative paths
    """

    paths = []  # Folder paths that can be used to shorten paths, via short()
    home = os.path.expanduser("~")

    def __init__(self, folder):
        self.folder = resolved_path(folder)

    def __enter__(self):
        Anchored.add(self.folder)

    def __exit__(self, *_):
        Anchored.pop(self.folder)

    @classmethod
    def set(cls, *anchors):
        """
        Args:
            *anchors (str | unicode | list): Optional paths to use as anchors for short()
        """
        cls.paths = sorted(flattened(anchors, split=SANITIZED | UNIQUE), reverse=True)

    @classmethod
    def add(cls, anchors):
        """
        Args:
            anchors (str | unicode | list): Optional paths to use as anchors for short()
        """
        cls.set(cls.paths, anchors)

    @classmethod
    def pop(cls, anchors):
        """
        Args:
            anchors (str | unicode | list): Optional paths to use as anchors for short()
        """
        for anchor in flattened(anchors, split=SANITIZED | UNIQUE):
            if anchor in cls.paths:
                cls.paths.remove(anchor)

    @classmethod
    def short(cls, path):
        """
        Example:
            short("examined /Users/joe/foo") => "examined ~/foo"

        Args:
            path: Path to represent in its short form

        Returns:
            (str): Short form, using '~' if applicable
        """
        if path is None:
            return path

        path = str(path)
        if cls.paths:
            for p in cls.paths:
                if p:
                    path = path.replace(p + "/", "")

        path = path.replace(cls.home, "~")
        return path


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


def camel_cased(text, separator=""):
    """
    Args:
        text (str): Text to camel case
        separator (str): Separator to use

    Returns:
        (str): Camel-cased text
    """
    return wordified(text, separator=separator, normalize=str.title)


def entitled(text, separator=" "):
    """
    Args:
        text (str): Text to turn into title
        separator (str): Separator to use

    Returns:
        (str): First letter (of 1st word only) upper-cased
    """
    words = get_words(text)
    if words:
        words[0] = words[0].title()
    return separator.join(words)


def get_words(text, normalize=None):
    """
    Args:
        text (str | None): Text to extract words from
        normalize (callable | None): Optional function to apply on each word

    Returns:
        (list | None): Words, if any
    """
    if not text:
        return []

    words = [s.strip().split("_") for s in RE_WORDS.split(text)]
    words = [s for s in flattened(words) if s]
    if normalize:
        words = [normalize(s) for s in words]
    return words


def snakified(text, normalize=str.upper):
    """
    Args:
        text (str): Text to transform
        normalize (callable | None): Optional function to apply on each word

    Returns:
        (str | None): Upper-cased and snake-ified
    """
    return wordified(text, normalize=normalize)


def wordified(text, separator="_", normalize=None):
    """
    Args:
        text (str | None): Text to process as words
        separator (str): Separator to use to join words back
        normalize (callable | None): Optional function to apply on each word

    Returns:
        (str): Dashes replaced by underscore
    """
    if text is None:
        return None

    return separator.join(get_words(text, normalize=normalize))


def _rformat(key, value, definitions, max_depth):
    if max_depth > 1 and value and "{" in value:
        value = value.format(**definitions)
        return _rformat(key, value, definitions, max_depth=max_depth - 1)
    return value


def _flatten(result, value, separator, mode):
    """
    Args:
        result (list): Will hold all flattened values
        value: Possibly nested arguments (sequence of lists, nested lists)
        separator (str | unicode | None): Split values with `separator` if specified
        mode (int): Describes how keep flattenened values

    Returns:
        list: 'value' flattened out (leaves from all involved lists/tuples)
    """
    if value is None or value is UNSET:
        if mode & SHELL:
            # Convenience: allow to filter out ["--switch", None] easily
            if result and result[-1].startswith("-"):
                result.pop(-1)
            return

        if mode & SANITIZED:
            return

    if value is not None:
        if isinstance(value, (list, tuple, set)):
            for item in value:
                _flatten(result, item, separator, mode)
            return

        if separator and hasattr(value, "split") and separator in value:
            _flatten(result, value.split(separator), separator, mode)
            return

        if mode & SHELL:
            value = "%s" % value

    if (mode & UNIQUE == 0) or value not in result:
        result.append(value)


def _get_value(obj, key):
    """Get a value for 'key' from 'obj', if possible"""
    if obj is not None:
        if isinstance(obj, (list, tuple)):
            for item in obj:
                v = _find_value(key, item)
                if v is not None:
                    return v
            return None
        if hasattr(obj, "get"):
            return obj.get(key)
        return getattr(obj, key, None)


def _find_value(key, *args):
    """Find a value for 'key' in any of the objects given as 'args'"""
    for arg in args:
        v = _get_value(arg, key)
        if v is not None:
            return v
