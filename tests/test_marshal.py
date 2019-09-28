import datetime

import runez
from runez import marshal as mm


def dt(*args, **kwargs):
    if len(args) == 3:
        return datetime.date(*args)

    return datetime.datetime(*args, **kwargs)


def test_date():
    assert mm.to_date(None) is None
    assert mm.to_date("foo") is None
    assert mm.to_date(["foo"]) is None

    assert mm.to_date("2019-01-02") == dt(2019, 1, 2)
    assert mm.to_date("2019-01-02T03:04:05.6789") == dt(2019, 1, 2, 3, 4, 5, microsecond=678900)
    assert mm.to_date("2019-01-02 03:04:05.6789 UTC") == dt(2019, 1, 2, 3, 4, 5, microsecond=678900, tzinfo=runez.date.UTC)
    assert mm.to_date("1500620000") == dt(2017, 7, 20, 23, 53, 20)
    print()
