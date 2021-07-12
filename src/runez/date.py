import datetime
import re
import time

from runez.convert import _float_from_text
from runez.system import stringified, UNSET


DEFAULT_TIMEZONE = None
SECONDS_IN_ONE_MINUTE = 60
SECONDS_IN_ONE_HOUR = 60 * SECONDS_IN_ONE_MINUTE
SECONDS_IN_ONE_DAY = 24 * SECONDS_IN_ONE_HOUR
SECONDS_IN_ONE_YEAR = 365.2425 * SECONDS_IN_ONE_DAY

RE_DURATION = re.compile(r"^\s*([0-9]+[ywdhms]\s*)+$")
RE_BASE_NUMBER = r"([-+]?[0-9_]*\.?[0-9_]*([eE][-+]?[0-9_]+)?|[-+]?\.inf|[-+]?\.Inf|[-+]?\.INF|\.nan|\.NaN|\.NAN|0o[0-7]+|0x[0-9a-fA-F]+)"
RE_BASE_DATE = (
    r"(([0-9]{1,4})[-/]([0-9][0-9]?)[-/]([0-9]{1,4})"
    r"([Tt \t]([0-9][0-9]?):([0-9][0-9]?):([0-9][0-9]?)(\.[0-9]*)?"
    r"([ \t]*(Z|[A-Z]{3}|[+-][0-9][0-9]?(:([0-9][0-9]?))?))?)?)"
)

RE_DATE = re.compile(r"^\s*(%s)\s*$" % "|".join((RE_BASE_NUMBER, RE_BASE_DATE)))
EPOCH_MS_BREAK = 900000000000
RE_TZ = re.compile(r"\s*(Z|UTC|([+-]?[0-9][0-9]):?([0-9][0-9]))\s*")
DEFAULT_DURATION_SPAN = 2


class timezone(datetime.tzinfo):
    """
    There is no handy timezone object available in stdlib.
    We provide this summary implementation in order to mostly support date extraction from text.
    This timezone implementation does not take into account any DST nonsense (do not use this if you care about DST).
    Supported timezone are simply: UTC, and explicit offsets like +01:00
    """

    __singletons = {}  # Cached timezone objects per offset

    def __new__(cls, offset, name=None):
        existing = cls.__singletons.get(offset)
        if existing is None:
            existing = super().__new__(cls)
            cls.__singletons[offset] = existing

        return existing

    def __init__(self, offset, name=None):
        if not hasattr(self, "name"):
            self.offset = offset
            if name is None:
                total_seconds = offset.days * SECONDS_IN_ONE_DAY + offset.seconds
                seconds = abs(total_seconds)
                hours = seconds // SECONDS_IN_ONE_HOUR
                seconds -= hours * SECONDS_IN_ONE_HOUR
                minutes = seconds // SECONDS_IN_ONE_MINUTE
                if total_seconds < 0:
                    hours = -hours

                name = "{:+03d}:{:02d}".format(hours, minutes)

            self.name = name

    def __repr__(self):
        return self.name

    def __eq__(self, other):
        if isinstance(other, datetime.tzinfo):
            return self.offset == other.utcoffset(datetime.datetime.now(tz=UTC))

    def utcoffset(self, dt):
        return self.offset

    def tzname(self, dt):
        return self.name

    def dst(self, dt):
        return self.offset


UTC = timezone(datetime.timedelta(0), "UTC")
NAMED_TIMEZONES = dict(Z=UTC, UTC=UTC)


def date_from_epoch(epoch, in_ms=None):
    """
    Args:
        epoch (int | float): Unix epoch in seconds or milliseconds, utc or local
        in_ms (bool | None): In milliseconds if True, auto-determined if None

    Returns:
        (datetime.date): Corresponding datetime object
    """
    if in_ms or (in_ms is None and epoch > EPOCH_MS_BREAK):
        epoch = epoch / 1000

    return datetime.datetime.utcfromtimestamp(epoch).date()


def datetime_from_epoch(epoch, tz=UNSET, in_ms=None):
    """
    Args:
        epoch (int | float): Unix epoch in seconds or milliseconds, utc or local
        tz (datetime.tzinfo | None): Optional timezone info object, passed through to created datetime
        in_ms (bool | None): In milliseconds if True, auto-determined if None

    Returns:
        (datetime.datetime): Corresponding datetime object
    """
    if tz is UNSET:
        tz = DEFAULT_TIMEZONE

    if in_ms or (in_ms is None and epoch > EPOCH_MS_BREAK):
        epoch = float(epoch) / 1000

    return datetime.datetime.fromtimestamp(epoch, tz=tz)


def elapsed(started, ended=None):
    """
    Args:
        started (datetime.date | datetime.datetime): When operation was started
        ended (datetime.date | datetime.datetime | None): When operation was ended (None means now)

    Returns:
        (float): Elapsed number of seconds
    """
    if not isinstance(started, datetime.datetime):
        tzinfo = None if ended is None else getattr(ended, "tzinfo", None)
        started = datetime.datetime(started.year, started.month, started.day, tzinfo=tzinfo)

    if ended is None:
        ended = datetime.datetime.now(tz=started.tzinfo)

    elif not isinstance(ended, datetime.datetime):
        ended = datetime.datetime(ended.year, ended.month, ended.day, tzinfo=started.tzinfo)

    delta = ended - started
    return delta.total_seconds()


def local_timezone():
    """
    Returns:
        (str): Name of current local timezone
    """
    try:
        return time.tzname[0]

    except (IndexError, TypeError):
        return ""


def represented_duration(seconds, span=UNSET, delimiter=" "):
    """
    Args:
        seconds (int | float | None): Duration in seconds
        span (int | None): If specified, return `span` most significant parts of the duration, specify <= 0 for short form
                           > 0: N most significant long parts, example: 1 hour 5 seconds
                           None: all parts, example: 1 hour 2 minutes 5 seconds 20 ms
                           0: all parts, short form, example: 1h 2m 5s 20ms
                           < 0: N most significant parts, short form, example: 1h 5s
                           UNSET: use `DEFAULT_DURATION_SPAN` (which can set globally per app, for convenience)
        delimiter (str): Delimiter to use between parts

    Returns:
        (str): Human friendly duration representation
    """
    if not isinstance(seconds, (int, float)):
        return stringified(seconds)

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
        result.append(_duration_span(years, "year", short_form))
    if weeks:
        result.append(_duration_span(weeks, "week", short_form))
    if days:
        result.append(_duration_span(days, "day", short_form))

    if hours:
        result.append(_duration_span(hours, "hour", short_form))
    if minutes:
        result.append(_duration_span(minutes, "minute", short_form))
    if seconds:
        result.append(_duration_span(seconds, "second", short_form))

    if microseconds:
        milliseconds = microseconds // 1000
        microseconds = microseconds % 1000
        if milliseconds:
            result.append(_duration_span(milliseconds, "ms", short_form, immutable=True))
        if microseconds:
            result.append(_duration_span(microseconds, "μs", short_form, immutable=True))

    if not result:
        result.append(_duration_span(seconds, "second", short_form))

    if span:
        result = result[:span]

    return delimiter.join(result)


def timezone_from_text(value, default=UNSET):
    """
    Args:
        value (str | None): Name of timezone, or offset of the form +01:00

    Returns:
        (datetime.tzinfo | None): Timezone, if one could be parsed
    """
    if isinstance(value, timezone):
        return value

    if default is UNSET:
        default = DEFAULT_TIMEZONE

    if not value:
        return default

    if value in ("Z", "UTC"):
        return UTC

    m = RE_TZ.match(value)
    if m:
        hours = m.group(2)
        if hours is not None:
            return timezone(datetime.timedelta(hours=int(hours), minutes=int(m.group(3))))

        return NAMED_TIMEZONES.get(m.group(1), default)

    return default


def to_date(value):
    """
    Args:
        value: Value to convert to date
        tz (datetime.tzinfo | None): Optional timezone info, used as default if could not be determined from `value`

    Returns:
        (datetime.date | None): Extracted date if possible, otherwise `None`
    """
    if isinstance(value, (int, float)):
        return date_from_epoch(value)

    if isinstance(value, str):
        value = _date_from_text(value, date_from_epoch)

    if isinstance(value, datetime.datetime):
        return value.date()

    if isinstance(value, datetime.date):
        return value


def to_datetime(value, tz=UNSET):
    """
    Args:
        value: Value to convert to date
        tz (datetime.tzinfo | None): Optional timezone info, used as default if could not be determined from `value`

    Returns:
        (datetime.datetime | None): Extracted date or datetime if possible, otherwise `None`
    """
    if isinstance(value, (int, float)):
        return datetime_from_epoch(value, tz=tz)

    if isinstance(value, str):
        value = _date_from_text(value, datetime_from_epoch, tz=tz)

    if isinstance(value, datetime.datetime):
        return value

    if isinstance(value, datetime.date):
        return datetime.datetime(value.year, value.month, value.day, tzinfo=timezone_from_text(tz))


def to_epoch(date, in_ms=False, tz=UTC):
    """
    Args:
        date (datetime.date | datetime.datetime | None): Date to convert to epoch
        in_ms (bool): If True, return epoch in milliseconds
        tz (datetime.tzinfo | None): Timezone to use for non-datetime `date`-s received

    Returns:
        (int): Epoch in seconds
    """
    if date:
        if not isinstance(date, datetime.datetime):
            date = datetime.datetime(date.year, date.month, date.day, tzinfo=tz)

        ep = (date - datetime.datetime(1970, 1, 1, tzinfo=date.tzinfo)).total_seconds()
        if in_ms:
            return ep * 1000

        return ep


def to_epoch_ms(date, tz=UTC):
    """
    Args:
        date (datetime.date | datetime.datetime): Date to convert to epoch
        tz (datetime.tzinfo | None): Timezone to use for non-datetime `date`-s received

    Returns:
        (int): Epoch in seconds
    """
    return to_epoch(date, in_ms=True, tz=tz)


def to_seconds(duration):
    """
    Args:
        duration (str | int | datetime.timedelta | None): Text representing duration, like 30m or 1h or 1h30m
            Accepted input if of the form <number><unit>, N times
            Possible units are: w: weeks, d: days, h: hours, m: minutes, s: seconds

    Returns:
        (int | None): Duration in seconds
    """
    if isinstance(duration, (int, float)):
        return duration

    if isinstance(duration, datetime.timedelta):
        return duration.total_seconds()

    if not isinstance(duration, str):
        return None

    duration = duration.strip()
    if not duration:
        return 0

    m = RE_DURATION.match(duration)
    if not m:
        dt = to_datetime(duration)
        if dt is not None:
            return elapsed(dt)

        return None

    v = m.group(1)
    seconds = to_seconds(duration.replace(v, ""))

    # v = v.strip()
    if v.endswith("w"):
        seconds += int(v[:-1], 0) * SECONDS_IN_ONE_DAY * 7

    elif v.endswith("d"):
        seconds += int(v[:-1], 0) * SECONDS_IN_ONE_DAY

    elif v.endswith("h"):
        seconds += int(v[:-1]) * SECONDS_IN_ONE_HOUR

    elif v.endswith("m"):
        seconds += int(v[:-1]) * SECONDS_IN_ONE_MINUTE

    elif v.endswith("y"):
        seconds += int(v[:-1]) * SECONDS_IN_ONE_YEAR

    else:
        seconds += int(v[:-1])

    return seconds


def _date_from_components(components, tz=UNSET):
    """
    Args:
        components: Components from regex
        tz (datetime.tzinfo | runez.Undefined | None): Optional timezone info, used as default if could not be determined from `components`

    Returns:
        (datetime.date | datetime.datetime | None)
    """
    y, m, d, _, hh = components[:5]

    try:
        y = int(y)
        m = int(m)
        d = int(d)
        if y < 100 < d:
            m, d, y = y, m, d  # Best effort: allow for european-style notation month/day/year

        if hh is None:
            return datetime.date(y, m, d)

        mm, ss, sf, _, ctz = components[5:10]
        hh = int(hh)
        mm = int(mm)
        ss = int(ss)
        sf = int(round(float(sf or 0) * 1000000))
        return datetime.datetime(y, m, d, hh, mm, ss, sf, timezone_from_text(ctz or tz))

    except (ValueError, TypeError):
        return None  # Funky date style, ignore


def _date_from_text(text, epocher, tz=UNSET):
    """
    Args:
        text (str): Value to turn into date or datetime
        epocher (callable): Function to use to transform int to date or datetime

    Returns:
        (datetime.date | datetime.datetime | None): Extracted date, if possible
    """
    match = RE_DATE.match(text)
    if match is None:
        m = RE_DURATION.match(text)
        if m:
            tz = UTC if tz is UNSET else tz
            offset = to_seconds(text)
            now = datetime.datetime.now(tz=tz)
            return to_datetime(to_epoch(now) - offset, tz=tz)

        return None

    # _, number, _, _, y, m, d, _, hh, mm, ss, sf, _, tz, _, _ = match.groups()
    components = match.groups()
    if components[1]:
        return epocher(_float_from_text(components[1], lenient=True), tz=tz)

    return _date_from_components(components[4:14], tz=tz)


def _duration_span(count, name, short_form, immutable=False):
    if short_form:
        if not immutable:
            name = name[0]

    else:
        name = " %s%s" % (name, "" if immutable or count == 1 else "s")

    return "%s%s" % (count, name)
