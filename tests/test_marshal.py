import datetime

import runez
from runez import marshal as mm


def dt(*args, **kwargs):
    if len(args) == 3:
        return datetime.date(*args)

    kwargs.setdefault("tzinfo", runez.date.DEFAULT_TIMEZONE)
    return datetime.datetime(*args, **kwargs)


def test_date():
    d0 = mm.to_date("2019-01-02 03:04:05 UTC")
    d1 = mm.to_date("2019-01-02 03:04:05 -00:00")
    d2 = mm.to_date("2019-01-02 04:04:05 +01:00")
    assert d0 == d2
    assert d1 == d2

    assert mm.to_date(None) is None
    assert mm.to_date("foo") is None
    assert mm.to_date(["foo"]) is None

    assert mm.to_date("2019-01-02") == dt(2019, 1, 2)

    sample_date = dt(2019, 1, 2, 3, 4, 5, microsecond=678900)
    assert mm.to_date("2019-01-02T03:04:05.6789") == sample_date
    assert mm.to_date("2019-01-02 03:04:05.6789 Z") == sample_date
    assert mm.to_date("2019-01-02 03:04:05.6789 UTC") == sample_date
    assert mm.to_date("2019-01-02 03:04:05.6789 -00:00") == sample_date
    assert mm.to_date("2019-01-02 04:04:05.6789 +01:00") == sample_date

    assert mm.to_date("1500620000") == dt(2017, 7, 21, 6, 53, 20)
