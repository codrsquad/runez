from argparse import Namespace

import pytest

import runez


def test_align():
    assert runez.align.cast("left") is runez.align.left
    assert runez.align.cast("CENTER") is runez.align.center
    assert runez.align.cast("foo", default=None) is None
    assert runez.align.cast("foo", default=runez.align.center) is runez.align.center
    assert runez.align.cast("foo", default="center") is runez.align.center
    assert runez.align.cast(None, default=runez.align.right) is runez.align.right
    assert runez.align.cast(runez.align.right) is runez.align.right

    with pytest.raises(ValueError):
        assert runez.align.cast("foo")

    with pytest.raises(ValueError):
        assert runez.align.cast("foo", "foo")

    assert runez.align.center("foo", 5) == " foo "
    assert runez.align.left("foo", 5) == "foo  "
    assert runez.align.left("foo", 5, fill="-") == "foo--"
    assert runez.align.right("foo", 5) == "  foo"


def test_border():
    t1 = runez.represent.PrettyBorder("empty")
    t2 = runez.represent.PrettyBorder()
    assert t1 == t2
    assert str(t1) == "c:,pad:1"

    assert runez.represent.PrettyBorder.cast(t1) is t1
    assert runez.represent.PrettyBorder.cast("empty") == t1

    # jira is a bit special with 2 delimiter chars
    tj = runez.represent.PrettyBorder("jira")
    assert str(tj) == "c:|||,hc:||||||,pad:1"

    # Exercise dict-base setting, for coverage
    tj2 = runez.represent.PrettyBorder(dict(c="|||", hc=dict(first="||", mid="||", last="||", h="")))
    assert tj == tj2

    tc = runez.represent.PrettyBorder("compact")
    assert str(tc) == "c:   ,h:   -,pad:1"

    # Exercise setting from object fields, for coverage
    tc2 = runez.represent.PrettyBorder("c:   ", h=Namespace(first=" ", mid=" ", last=" ", h="-"))
    assert tc2 == tc


def test_header():
    assert runez.header("") == ""
    assert runez.header("test", border="") == "test"

    assert runez.header("test", border="--") == "----------\n-- test --\n----------"
    assert runez.header("test", border="-- ") == "-- test\n-------"

    assert runez.header("test", border="=") == "========\n= test =\n========"
    assert runez.header("test", border="= ") == "= test\n======"


def test_pretty_table():
    with pytest.raises(ValueError):
        runez.PrettyTable(object)  # Invalid header

    t = runez.PrettyTable()
    assert len(t.header) == 0
    with pytest.raises(IndexError):
        t.header[0].style = "bold"  # Header columns are not auto-accommodated when accessing by index

    t.header.accomodate(2)
    assert len(t.header) == 2
    t.header[0].style = "bold"

    t = runez.PrettyTable("1,2,3", border="pad:0")
    assert len(t.header.columns) == 3
    t.add_rows("a b c".split(), "d e foo".split())

    t.header = 3  # Interpreted as 3 columns (but no header text)
    assert t.get_string() == "abc  \ndefoo"

    t.header = [1, 2, 3]  # Numbers will be stringified
    assert isinstance(t.header, runez.represent.PrettyHeader)
    t.align = "left"
    assert t.get_string() == "123  \nabc  \ndefoo"

    t.align = "center"
    assert t.get_string() == "12 3 \nab c \ndefoo"

    t.align = "right"
    assert t.get_string() == "12  3\nab  c\ndefoo"

    t.border = "ascii"
    s = t.get_string()
    assert s == "+===+===+=====+\n| 1 | 2 |   3 |\n+===+===+=====+\n| a | b |   c |\n+---+---+-----+\n| d | e | foo |\n+---+---+-----+"

    t.border = "empty"
    t.header.add_columns("x", "y")
    s = t.get_string()
    assert s == " 1  2    3  x  y \n a  b    c  -  - \n d  e  foo  -  - "

    t.missing = "*"
    t.style = "bold"
    t.header.columns[-2].shown = False
    s = t.get_string()
    assert s == " 1  2    3  y \n a  b    c  * \n d  e  foo  * "
