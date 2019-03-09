import runez


def test_header():
    assert runez.header("") == ""
    assert runez.header("test", border="") == "test"

    assert runez.header("test", border="--") == "----------\n-- test --\n----------"
    assert runez.header("test", border="-- ") == "-- test\n-------"

    assert runez.header("test", border="=") == "========\n= test =\n========"
    assert runez.header("test", border="= ") == "= test\n======"
