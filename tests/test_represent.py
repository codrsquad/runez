import runez


def test_header():
    assert runez.header("") == ""
    assert runez.header("test", width=0) == "test"

    assert runez.header("test", width=1) == "--------\n- test -\n--------"
    assert runez.header("test", width=-1) == "- test\n------"

    assert runez.header("test", dash="=", width=1) == "========\n= test =\n========"
    assert runez.header("test", dash="=", width=-1) == "= test\n======"
