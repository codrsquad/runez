import datetime
import time

from freezegun import freeze_time

import runez


def check_date(expected, dt):
    actual = dt.strftime("%Y-%m-%d %H:%M:%S %Z").strip()
    assert actual == expected


def test_date_formats():
    ref = datetime.date(2019, 1, 16)
    assert runez.to_date("2019-01-16") == ref
    assert runez.to_date("  2019/01/16 ") == ref
    assert runez.to_date("01/16/2019") == ref

    assert runez.to_date("2019- 01-16") is None
    assert runez.to_date("16/01/2019") is None
    assert runez.to_datetime("2019/01/2019") is None

    with freeze_time("2019-09-01 20:00:12"):
        assert str(runez.to_date(" 1w")) == "2019-08-25"
        assert str(runez.to_date("1y")) == "2018-09-01"
        assert str(runez.to_date("1y1w")) == "2018-08-25"
        assert str(runez.to_date(" 1y 1w ")) == "2018-08-25"

        assert str(runez.to_datetime("1y", tz=runez.date.UTC)) == "2018-09-01 14:11:00+00:00"


def test_elapsed():
    d1 = datetime.date(2019, 9, 1)
    dt27 = dt(2019, 9, 1, second=27)

    assert runez.to_date(d1) is d1
    assert runez.to_datetime(dt27) is dt27

    assert runez.elapsed(d1, ended=dt27) == 27
    assert runez.elapsed(dt27, ended=d1) == -27

    d2 = datetime.date(2019, 9, 2)
    dt1 = dt(2019, 9, 1)
    assert runez.elapsed(d1, ended=d2) == 86400
    assert runez.elapsed(d2, ended=dt1) == -86400

    d3 = runez.datetime_from_epoch(1567296012, tz=None)  # Naive date will depend on timezone (ie: where this test runs)
    assert d3.year == 2019
    assert d3.tzinfo is None
    assert runez.to_datetime(d3) is d3

    check_date("2019-09-01 02:00:12 +02:00", runez.datetime_from_epoch(1567296012, tz=runez.timezone_from_text("0200", default=None)))
    check_date("2019-09-01 00:00:12 UTC", runez.datetime_from_epoch(1567296012, tz=runez.date.UTC))
    check_date("2019-09-01 00:00:12 UTC", runez.datetime_from_epoch(1567296012000, tz=runez.date.UTC, in_ms=True))

    with freeze_time("2019-09-01 00:00:12"):
        assert runez.elapsed(dt(2019, 9, 1, second=34)) == -22
        assert runez.elapsed(dt(2019, 9, 1)) == 12


def test_epoch():
    assert runez.to_epoch(None) is None

    d = datetime.date(2019, 9, 1)
    dt27 = datetime.datetime(2019, 9, 1, second=27, tzinfo=runez.date.UTC)
    assert runez.to_epoch(d) == 1567296000
    assert runez.to_epoch(d, in_ms=True) == 1567296000000
    assert runez.to_epoch(dt27) == 1567296027
    assert runez.to_epoch_ms(dt27) == 1567296027000


def test_represented_duration():
    assert runez.represented_duration(None) == "None"
    assert runez.represented_duration("foo") == "foo"  # verify non-duration left as-is...
    assert runez.represented_duration(runez.UNSET) == "UNSET"

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

    h2 = 2 * runez.date.SECONDS_IN_ONE_HOUR
    d8 = 8 * runez.date.SECONDS_IN_ONE_DAY
    a_week_plus = d8 + h2 + 13 + 0.00001
    assert runez.represented_duration(a_week_plus, span=None) == "1 week 1 day 2 hours 13 seconds 10 μs"
    assert runez.represented_duration(a_week_plus, span=-2, delimiter="+") == "1w+1d"
    assert runez.represented_duration(a_week_plus, span=3) == "1 week 1 day 2 hours"
    assert runez.represented_duration(a_week_plus, span=0) == "1w 1d 2h 13s 10μs"

    five_weeks_plus = (5 * 7 + 3) * runez.date.SECONDS_IN_ONE_DAY + runez.date.SECONDS_IN_ONE_HOUR + 5 + 0.0002
    assert runez.represented_duration(five_weeks_plus, span=-2, delimiter=", ") == "5w, 3d"
    assert runez.represented_duration(five_weeks_plus, span=0, delimiter=", ") == "5w, 3d, 1h, 5s, 200μs"

    assert runez.represented_duration(752 * runez.date.SECONDS_IN_ONE_DAY, span=3) == "2 years 3 weeks 1 day"


def test_timezone(monkeypatch):
    assert runez.local_timezone() == time.tzname[0]
    monkeypatch.setattr(runez.date.time, "tzname", [])
    assert runez.local_timezone() == ""

    assert runez.timezone_from_text(None) is runez.date.DEFAULT_TIMEZONE
    assert runez.timezone_from_text("foo", default=None) is None
    assert runez.timezone_from_text("-00: 00", default=None) is None
    assert runez.timezone_from_text(" +00 00", default=None) is None

    assert runez.timezone_from_text(" Z", default=None) == runez.date.UTC
    assert runez.timezone_from_text("UTC ", default=None) == runez.date.UTC
    assert runez.timezone_from_text(" 0000  ", default=None) == runez.date.UTC
    assert runez.timezone_from_text("+0000", default=None) == runez.date.UTC
    assert runez.timezone_from_text(" -00:00", default=None) == runez.date.UTC
    assert runez.timezone_from_text("+0100", default=None) != runez.date.UTC

    epoch = 1568332800
    assert runez.to_date(epoch) == datetime.date(2019, 9, 13)
    assert runez.to_date(epoch) == runez.to_date(epoch * 1000)
    assert runez.to_datetime(epoch) == dt(2019, 9, 13, 0, 0, 0)

    epoch = 1568348000
    check_date("2019-09-13 04:13:20 UTC", runez.datetime_from_epoch(epoch))

    assert runez.to_date(epoch) == datetime.date(2019, 9, 13)
    assert runez.to_datetime(epoch) == dt(2019, 9, 13, 4, 13, 20)

    tz1 = runez.timezone(datetime.timedelta(seconds=12 * 60))
    dtutc = runez.datetime_from_epoch(epoch, tz=runez.date.UTC)
    dt1 = runez.datetime_from_epoch(epoch, tz=tz1)
    eutc = runez.to_epoch(dtutc)
    et1 = runez.to_epoch(dt1)
    assert et1 - eutc == 720
    assert dtutc == dt1

    tz = runez.timezone_from_text("-01:00", default=None)
    assert str(tz) == "-01:00"
    check_date("2019-09-13 03:13:20 -01:00", runez.datetime_from_epoch(epoch, tz=tz))

    tz = runez.timezone_from_text("0200", default=None)
    assert str(tz) == "+02:00"
    check_date("2019-09-13 06:13:20 +02:00", runez.datetime_from_epoch(epoch, tz=tz))


def dt(*args, **kwargs):
    tzinfo = kwargs.pop("tzinfo", runez.date.DEFAULT_TIMEZONE)
    return datetime.datetime(*args, tzinfo=tzinfo, **kwargs)


def test_to_date():
    assert runez.to_date("") is None
    assert runez.to_date("   ") is None
    assert runez.to_datetime("") is None
    assert runez.to_datetime("  ") is None

    tz1 = runez.timezone(datetime.timedelta(seconds=12 * 60))
    assert runez.to_datetime("2019-01-02 03:04:05").tzinfo is runez.date.DEFAULT_TIMEZONE
    assert runez.to_datetime("2019-01-02 03:04:05", tz=tz1).tzinfo is tz1
    assert runez.to_datetime("2019-01-02 03:04:05 -00:12").tzinfo == tz1
    assert runez.to_datetime("2019-01-02 03:04:05 UTC").tzinfo is runez.date.UTC

    d0 = runez.to_datetime("2019-01-02 03:04:05  UTC")
    d1 = runez.to_datetime(" 2019-01-02 03:04:05 -00:00 ")
    d2 = runez.to_datetime("2019-01-02 04:04:05 +01:00")
    assert d0 == d2
    assert d1 == d2

    assert runez.to_date(d0) == datetime.date(2019, 1, 2)

    assert runez.to_datetime(None) is None
    assert runez.to_datetime("foo") is None
    assert runez.to_datetime(["foo"]) is None

    assert runez.to_date("2019-01-02") == datetime.date(2019, 1, 2)
    assert runez.to_date("2019-01-02 00:01:00UTC") == datetime.date(2019, 1, 2)
    assert runez.to_date("2019-01-02 00:01:00 UTC") == datetime.date(2019, 1, 2)
    assert runez.to_date("2019-01-02 00:01:00  UTC ") == datetime.date(2019, 1, 2)
    assert runez.to_datetime("2019-01-02") == dt(2019, 1, 2, 0, 0, 0)
    assert runez.to_datetime("2019-01-02 00:01:00 UTC") == dt(2019, 1, 2, 0, 1, 0)

    sample_date = dt(2019, 1, 2, 3, 4, 5, microsecond=678900)
    assert runez.to_datetime("2019-01-02T03:04:05.6789") == sample_date
    assert runez.to_datetime("2019-01-02 03:04:05.6789Z") == sample_date
    assert runez.to_datetime("2019-01-02 03:04:05.6789 Z") == sample_date
    assert runez.to_datetime("2019-01-02 03:04:05.6789 UTC") == sample_date
    assert runez.to_datetime("2019-01-02 03:04:05.6789 -00:00") == sample_date
    assert runez.to_datetime("2019-01-02 04:04:05.6789 +01:00") == sample_date

    assert runez.to_datetime("1500620000") == dt(2017, 7, 21, 6, 53, 20)


def test_to_seconds():
    assert runez.to_seconds(None) is None
    assert runez.to_seconds("foo") is None
    assert runez.to_seconds("1k") is None
    assert runez.to_seconds("1 m") is None
    assert runez.to_seconds("1 m2s") is None
    assert runez.to_seconds("1m 2") is None
    assert runez.to_seconds("1month") is None
    assert runez.to_seconds([1]) is None  # verify no crash on bogus type

    assert runez.to_seconds("") == 0
    assert runez.to_seconds(5) == 5
    assert runez.to_seconds("1d1h5s") == 90005
    assert runez.to_seconds("1h  2s") == 3602
    assert runez.to_seconds(" 1h 2s ") == 3602
    assert runez.to_seconds(" 1m ") == 60
    assert runez.to_seconds("1y") == 31556952
    assert datetime.timedelta(seconds=runez.to_seconds("1d1h5s")) == datetime.timedelta(days=1, seconds=3605)
    assert datetime.timedelta(seconds=runez.to_seconds("1w5s")) == datetime.timedelta(days=7, seconds=5)
    assert datetime.timedelta(seconds=runez.to_seconds(" 1w 1s ")) == datetime.timedelta(days=7, seconds=1)

    assert runez.to_seconds(datetime.timedelta(minutes=60)) == 3600
    assert runez.to_seconds(runez.date.UTC.offset) == 0
    tz = runez.timezone_from_text("+0100", default=None)
    assert isinstance(tz, runez.timezone)
    assert runez.to_seconds(tz.offset) == 3600

    with freeze_time("2020-01-02 00:00:12"):
        assert runez.to_seconds("2020-01-01 ") == 86412
        assert runez.to_seconds("2020-01-02 00:00:01") == 11
        assert runez.to_seconds("2020-01-02 00:01:12") == -60
