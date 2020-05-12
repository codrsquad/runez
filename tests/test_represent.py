from argparse import Namespace

import runez


def test_align():
    assert runez.align.cast("left") is runez.align.left
    assert runez.align.cast("CENTER") is runez.align.center
    assert runez.align.cast("foo") is runez.align.left
    assert runez.align.cast("foo", default=runez.align.center) is runez.align.center
    assert runez.align.cast(None, default=runez.align.right) is runez.align.right
    assert runez.align.cast(runez.align.center) is runez.align.center

    assert runez.align.center("foo", 5) == " foo "

    assert runez.align.left("foo", 5) == "foo  "
    assert runez.align.left("foo", 5, fill="-") == "foo--"


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


def test_pretty_table():
    t = runez.PrettyTable("1,2,3", border="pad:0")
    t.add_rows("a b c".split(), "d e foo".split())

    assert str(runez.represent.PTable(t).columns[0])  # Exercise string representation useful in debugger

    t.header = 3  # Interpreted as 3 columns (but no header text)
    assert t.get_string() == "abc  \ndefoo"

    t.header = [1, 2, 3]  # Numbers will be stringified
    t.align = "left"
    assert t.get_string() == "123  \nabc  \ndefoo"

    t.align = "center"
    assert t.get_string() == "12 3 \nab c \ndefoo"

    t.align = "right"
    assert t.get_string() == "12  3\nab  c\ndefoo"

    t.border = "ascii"
    s = t.get_string()
    assert s == "+===+===+=====+\n| 1 | 2 |   3 |\n+===+===+=====+\n| a | b |   c |\n+---+---+-----+\n| d | e | foo |\n+---+---+-----+"

    t.border = runez.PrettyTable
