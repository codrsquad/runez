from argparse import Namespace

import runez


def test_align():
    assert runez.align_center("foo", 5) == " foo "

    assert runez.align_left("foo", 5) == "foo  "
    assert runez.align_left("foo", 5, fill="-") == "foo--"


def test_border():
    t1 = runez.represent.PBorder("empty")
    t2 = runez.represent.PBorder()
    assert t1 == t2
    assert str(t1) == "c:,pad:1"

    assert runez.represent.PBorder.cast(t1) is t1
    assert runez.represent.PBorder.cast("empty") == t1

    tc = runez.represent.PBorder("compact")
    assert str(tc) == "c:   ,h:   -,pad:1"

    n = Namespace(first=" ")
    tch = runez.represent.PChars(n, dict(mid=" ", last=" ", h="-"))
    assert tch == tc.h


def test_header():
    assert runez.header("") == ""
    assert runez.header("test", border="") == "test"

    assert runez.header("test", border="--") == "----------\n-- test --\n----------"
    assert runez.header("test", border="-- ") == "-- test\n-------"

    assert runez.header("test", border="=") == "========\n= test =\n========"
    assert runez.header("test", border="= ") == "= test\n======"
