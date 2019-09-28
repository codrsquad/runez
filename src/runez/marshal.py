import datetime
import re

from runez.base import string_type
from runez.convert import _float_from_text
from runez.date import datetime_from_epoch, timezone_from_text


BASE_BOOLEAN = r"(false|False|FALSE|true|True|TRUE)"
BASE_NUMBER = r"([-+]?[0-9_]*\.?[0-9_]*([eE][-+]?[0-9_]+)?|[-+]?\.inf|[-+]?\.Inf|[-+]?\.INF|\.nan|\.NaN|\.NAN|0o[0-7]+|0x[0-9a-fA-F]+)"
BASE_DATE = r"(([0-9]{4})-([0-9][0-9]?)-([0-9][0-9]?)" \
            r"([Tt \t]([0-9][0-9]?):([0-9][0-9]?):([0-9][0-9]?)(\.[0-9]*)?" \
            r"([ \t]*(Z|[A-Z]{3}|[+-][0-9][0-9]?(:([0-9][0-9]?))?))?)?)"


def composed_regex(*parts):
    if len(parts) == 1:
        return re.compile("^%s$" % parts[0])

    return re.compile("^(%s)$" % "|".join(parts))


RE_SCALAR = composed_regex(BASE_BOOLEAN, BASE_NUMBER, BASE_DATE)


def to_date(value):
    """
    Args:
        value: Value to convert to date

    Returns:
        (datetime.date | datetime.datetime | None): Extracted date or datetime if possible, otherwise `None`
    """
    if isinstance(value, string_type):
        return _date_from_text(value)


def to_scalar(value):
    """
    Args:
        value: Value to turn into most appropriate scalar (eg: int, float, date, ...)

    Returns:
        (str | bool | int | float | datetime.date | datetime.datetime | None): Most appropriate scalar, otherwise `text` as-is
    """
    if isinstance(value, string_type):
        return _scalar_from_text(value)

    if isinstance(value, (bool, int, float, datetime.date, datetime.datetime)):
        return value


def to_tzinfo(value):
    """
    Args:
        value: Value to interpret as timezone

    Returns:
        (datetime.tzinfo | None): Corresponding timezone, if any
    """
    if isinstance(value, string_type):
        return timezone_from_text(value)


def _date_from_number(value):
    return datetime_from_epoch(value)


def _date_from_components(components):
    y, m, d, _, hh = components[:5]

    y = int(y)
    m = int(m)
    d = int(d)
    if hh is None:
        return datetime.date(y, m, d)

    mm, ss, sf, _, tz = components[5:10]
    hh = int(hh)
    mm = int(mm)
    ss = int(ss)
    sf = int(round(float(sf or 0) * 1000000))
    return datetime.datetime(y, m, d, hh, mm, ss, sf, timezone_from_text(tz))


def _date_from_text(text):
    """
    Args:
        text (str): Value to turn into date or datetime

    Returns:
        (datetime.date | datetime.datetime | None): Extracted date, if possible
    """
    match = RE_SCALAR.match(text)
    if match is None:
        return None

    # _, boolean, number, _, _, y, m, d, _, hh, mm, ss, sf, _, tz, _, _ = match.groups()
    components = match.groups()
    if components[1] is not None:
        return None

    if components[2]:
        value = _float_from_text(components[2], lenient=True)
        if value is None:
            return None

        return _date_from_number(value)

    return _date_from_components(components[5:15])


def _scalar_from_text(text):
    """
    Args:
        text (str): Value to turn into most appropriate scalar (eg: int, float, date, ...)

    Returns:
        (str | int | float | datetime.date | datetime.datetime): Most appropriate scalar, otherwise `text` as-is
    """
    match = RE_SCALAR.match(text)
    if match is None:
        return text

    # _, boolean, number, _, _, y, m, d, _, hh, mm, ss, sf, _, tz, _, _ = match.groups()
    components = match.groups()
    if components[1] is not None:
        return components[1].lower() == "true"

    if components[2]:
        value = _float_from_text(components[2], lenient=True)
        return text if value is None else value

    return _date_from_components(components[5:15])
