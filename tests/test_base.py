import runez


def test_decode():
    assert runez.decode(None) is None

    assert runez.decode(" something ") == " something "
    assert runez.decode(" something ", strip=True) == "something"

    assert runez.decode(b" something ") == " something "
    assert runez.decode(b" something ", strip=True) == "something"


def test_undefined():
    assert str(runez.UNSET) == "UNSET"
