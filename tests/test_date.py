#  -*- encoding: utf-8 -*-

import datetime
import time

from freezegun import freeze_time
from mock import patch

import runez


def check_date(expected, dt):
    actual = dt.strftime("%Y-%m-%d %H:%M:%S %Z").strip()
    assert actual == expected


def test_date_formats():
    ref = dt(2019, 1, 16)
    assert runez.to_date("2019-01-16") == ref
    assert runez.to_date("2019/01/16") == ref
    assert runez.to_date("01/16/2019") == ref

    assert runez.to_date("16/01/2019") is None
    assert runez.to_date("2019/01/2019") is None


def test_elapsed():
    d1 = datetime.date(2019, 9, 1)
    dt27 = datetime.datetime(2019, 9, 1, second=27)
    assert runez.elapsed(d1, ended=dt27) == 27
    assert runez.elapsed(dt27, ended=d1) == -27

    d2 = datetime.date(2019, 9, 2)
    dt1 = datetime.datetime(2019, 9, 1)
    assert runez.elapsed(d1, ended=d2) == 86400
    assert runez.elapsed(d2, ended=dt1) == -86400

    dt = runez.datetime_from_epoch(1567296012, tz=None)  # Naive date will depend on timezone (ie: where this test runs)
    assert dt.year == 2019
    assert dt.tzinfo is None
    assert runez.to_date(dt) is dt

    check_date("2019-09-01 02:00:12 +02:00", runez.datetime_from_epoch(1567296012, tz=runez.timezone_from_text("0200")))
    check_date("2019-09-01 00:00:12 UTC", runez.datetime_from_epoch(1567296012, tz=runez.UTC))
    check_date("2019-09-01 00:00:12 UTC", runez.datetime_from_epoch(1567296012000, tz=runez.UTC, in_ms=True))

    with freeze_time("2019-09-01 00:00:12"):
        assert runez.elapsed(datetime.datetime(2019, 9, 1, second=34)) == -22
        assert runez.elapsed(datetime.datetime(2019, 9, 1)) == 12


def test_epoch():
    assert runez.to_epoch(None) is None

    d = datetime.date(2019, 9, 1)
    dt27 = datetime.datetime(2019, 9, 1, second=27)
    assert runez.to_epoch(d) == 1567321200
    assert runez.to_epoch(d, in_ms=True) == 1567321200000
    assert runez.to_epoch(dt27) == 1567321227
    assert runez.to_epoch_ms(dt27) == 1567321227000


def test_represented_duration():
    assert runez.represented_duration(0) == "0 seconds"
    assert runez.represented_duration(1) == "1 second"
    assert runez.represented_duration(-1.00001) == "1 second 10 μs"
    assert runez.represented_duration(-180.00001) == "3 minutes"
    assert runez.represented_duration(-180.00001, span=None) == "3 minutes 10 μs"
    assert runez.represented_duration(5.1) == "5 seconds 100 ms"
    assert runez.represented_duration(180.1) == "3 minutes"

    assert runez.represented_duration(65) == "1 minute 5 seconds"
    assert runez.represented_duration(65, span=-2) == "1m 5s"
    assert runez.represented_duration(3667, span=-2) == "1h 1m"
    assert runez.represented_duration(3667, span=None) == "1 hour 1 minute 7 seconds"

    h2 = 2 * runez.SECONDS_IN_ONE_HOUR
    d8 = 8 * runez.SECONDS_IN_ONE_DAY
    a_week_plus = d8 + h2 + 13 + 0.00001
    assert runez.represented_duration(a_week_plus, span=None) == "1 week 1 day 2 hours 13 seconds 10 μs"
    assert runez.represented_duration(a_week_plus, span=-2, separator="+") == "1w+1d"
    assert runez.represented_duration(a_week_plus, span=3) == "1 week 1 day 2 hours"
    assert runez.represented_duration(a_week_plus, span=0) == "1w 1d 2h 13s 10μs"

    five_weeks_plus = (5 * 7 + 3) * runez.SECONDS_IN_ONE_DAY + runez.SECONDS_IN_ONE_HOUR + 5 + 0.0002
    assert runez.represented_duration(five_weeks_plus, span=-2, separator=", ") == "5w, 3d"
    assert runez.represented_duration(five_weeks_plus, span=0, separator=", ") == "5w, 3d, 1h, 5s, 200μs"

    assert runez.represented_duration(752 * runez.SECONDS_IN_ONE_DAY, span=3) == "2 years 3 weeks 1 day"


def test_timezone():
    assert runez.get_local_timezone() == time.tzname[0]
    with patch("runez.date.time") as runez_time:
        runez_time.tzname = []
        assert runez.get_local_timezone() == ""

    assert runez.timezone_from_text(None) is runez.date.DEFAULT_TIMEZONE
    assert runez.timezone_from_text("foo") is runez.date.DEFAULT_TIMEZONE
    assert runez.timezone_from_text("Z") == runez.UTC
    assert runez.timezone_from_text("UTC") == runez.UTC
    assert runez.timezone_from_text("0000") == runez.UTC
    assert runez.timezone_from_text("+0000") == runez.UTC
    assert runez.timezone_from_text("-00:00") == runez.UTC

    epoch = 1568348000
    check_date("2019-09-13 04:13:20 UTC", runez.datetime_from_epoch(epoch))

    tz = runez.timezone_from_text("-01:00")
    assert str(tz) == "-01:00"
    check_date("2019-09-13 03:13:20 -01:00", runez.datetime_from_epoch(epoch, tz=tz))

    tz = runez.timezone_from_text("0200")
    assert str(tz) == "+02:00"
    check_date("2019-09-13 06:13:20 +02:00", runez.datetime_from_epoch(epoch, tz=tz))


def dt(*args, **kwargs):
    if len(args) == 3:
        return datetime.date(*args)

    kwargs.setdefault("tzinfo", runez.date.DEFAULT_TIMEZONE)
    return datetime.datetime(*args, **kwargs)


def test_to_date():
    d0 = runez.to_date("2019-01-02 03:04:05 UTC")
    d1 = runez.to_date("2019-01-02 03:04:05 -00:00")
    d2 = runez.to_date("2019-01-02 04:04:05 +01:00")
    assert d0 == d2
    assert d1 == d2

    assert runez.to_date(None) is None
    assert runez.to_date("foo") is None
    assert runez.to_date(["foo"]) is None

    assert runez.to_date("2019-01-02") == dt(2019, 1, 2)

    sample_date = dt(2019, 1, 2, 3, 4, 5, microsecond=678900)
    assert runez.to_date("2019-01-02T03:04:05.6789") == sample_date
    assert runez.to_date("2019-01-02 03:04:05.6789 Z") == sample_date
    assert runez.to_date("2019-01-02 03:04:05.6789 UTC") == sample_date
    assert runez.to_date("2019-01-02 03:04:05.6789 -00:00") == sample_date
    assert runez.to_date("2019-01-02 04:04:05.6789 +01:00") == sample_date

    assert runez.to_date("1500620000") == dt(2017, 7, 21, 6, 53, 20)
