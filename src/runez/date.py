#  -*- encoding: utf-8 -*-

import datetime
import re
import time

from runez.base import UNSET


DEFAULT_TIMEZONE = None
SECONDS_IN_ONE_MINUTE = 60
SECONDS_IN_ONE_HOUR = 60 * SECONDS_IN_ONE_MINUTE
SECONDS_IN_ONE_DAY = 24 * SECONDS_IN_ONE_HOUR


class timezone(datetime.tzinfo):

    __singletons = {}

    def __new__(cls, offset, name=None):
        existing = cls.__singletons.get(offset)
        if existing is None:
            existing = super(timezone, cls).__new__(cls, offset, name=name)
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
                    hours = - hours
                name = "{:+03d}:{:02d}".format(hours, minutes)
            self.name = name

    def __repr__(self):
        return self.name

    def utcoffset(self, dt):
        return self.offset

    def tzname(self, dt):
        return self.name

    def dst(self, dt):
        return self.offset


UTC = timezone(datetime.timedelta(0), "UTC")
EPOCH_MS_BREAK = 900000000000
RE_TZ = re.compile(r"([+-]?[0-9][0-9]):?([0-9][0-9])")
DEFAULT_DURATION_SPAN = 2


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
        started = datetime.datetime(started.year, started.month, started.day)

    if ended is None:
        ended = datetime.datetime.now(tz=started.tzinfo)
    elif not isinstance(ended, datetime.datetime):
        ended = datetime.datetime(ended.year, ended.month, ended.day)

    delta = ended - started
    return delta.total_seconds()


def get_local_timezone():
    """
    Returns:
        (str): Name of current timezone
    """
    try:
        return time.tzname[0]

    except (IndexError, TypeError):
        return ""


def _duration_span(count, name, short_form, immutable=False):
    if short_form:
        if not immutable:
            name = name[0]
    else:
        name = " %s%s" % (name, "" if immutable or count == 1 else "s")
    return "%s%s" % (count, name)


def represented_duration(seconds, span=UNSET, separator=" "):
    """
    Args:
        seconds (int | float): Duration in seconds
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

    return separator.join(result)


def timezone_from_text(text):
    """
    Args:
        text (str | None): Name of timezone, or offset of the form +01:00

    Returns:
        (datetime.tzinfo | None):
    """
    if text is None:
        return DEFAULT_TIMEZONE

    if text in ("Z", "UTC"):
        return UTC

    m = RE_TZ.match(text)
    if m:
        hours = int(m.group(1))
        minutes = int(m.group(2))
        return timezone(datetime.timedelta(hours=int(hours), minutes=int(minutes)))

    return DEFAULT_TIMEZONE
