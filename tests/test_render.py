import os
import sys
from argparse import Namespace
from unittest.mock import patch

import pytest

from runez.render import Align, Header, PrettyBorder, PrettyHeader, PrettyTable
from runez.system import SYS_INFO, SystemInfo, UNSET


def test_align():
    assert Align.cast("left") is Align.left
    assert Align.cast("CENTER") is Align.center
    assert Align.cast("foo", default=None) is None
    assert Align.cast("foo", default=Align.center) is Align.center
    assert Align.cast("foo", default="center") is Align.center
    assert Align.cast(None, default=Align.right) is Align.right
    assert Align.cast(Align.right) is Align.right

    with pytest.raises(ValueError, match="Invalid horizontal alignment 'foo'"):
        assert Align.cast("foo")

    with pytest.raises(ValueError, match="Invalid default horizontal alignment"):
        assert Align.cast("foo", "bar")

    assert Align.center("foo", 5) == " foo "
    assert Align.left("foo", 5) == "foo  "
    assert Align.left("foo", 5, fill="-") == "foo--"
    assert Align.right("foo", 5) == "  foo"


def test_border():
    t1 = PrettyBorder("empty")
    t2 = PrettyBorder()
    assert t1 == t2
    assert str(t1) == "c:,pad:1"

    assert PrettyBorder.cast(t1) is t1
    assert PrettyBorder.cast("empty") == t1

    tc = PrettyBorder("compact")
    assert str(tc) == "c:   ,h:   -,pad:1"

    # Exercise setting from object fields, for coverage
    tc2 = PrettyBorder("c:   ", h=Namespace(first=" ", mid=" ", last=" ", h="-"))
    assert tc2 == tc


EXPECTED_DIAGNOSTICS = """
  foo : bar
  opt : -missing-
  --- :

Other section:
    --- :
  diag2 : UNSET

Some section:
   key1 : value1
   key2 : -missing-
    --- :
  diag2 : UNSET

some additional text
"""


def test_diagnostics(monkeypatch):
    def _diag1(opt=None):
        yield "foo", "bar"
        yield "opt", opt
        yield "---"

    def _diag2():
        yield "---"
        yield "diag2", UNSET

    data = {"key1": "value1", "key2": None}
    sections = {"Some section": [data, _diag2], "Other section": _diag2}
    diag1 = PrettyTable.two_column_diagnostics(_diag1, sections, "some additional text")
    assert diag1 == EXPECTED_DIAGNOSTICS.strip("\n")

    # Same, but with calling the generators first
    sections = {"Some section": [data, _diag2()], "Other section": _diag2()}
    diag1 = PrettyTable.two_column_diagnostics(_diag1(), sections, "some additional text")
    assert diag1 == EXPECTED_DIAGNOSTICS.strip("\n")

    diag2 = PrettyTable.two_column_diagnostics(_diag2(), SYS_INFO.diagnostics())
    assert "diag2 : UNSET" in diag2
    assert "sys.executable" in diag2
    assert "invoker" in diag2  # Present when running from venv

    silly_edge_case = PrettyTable.two_column_diagnostics(0, 1, [2])
    assert silly_edge_case == "  0 :\n  1 :\n  2 :"

    with patch.dict(os.environ, {"LC_TERMINAL": "foo", "LC_TERMINAL_VERSION": "2"}):
        monkeypatch.setattr(sys, "executable", "foo")
        s = SystemInfo()
        x = PrettyTable.two_column_diagnostics(s.diagnostics())
        assert "terminal : foo v2" in x
        assert "via : " in x

        x = PrettyTable.two_column_diagnostics(s.diagnostics(via=None))
        assert "via : " not in x


def test_header():
    assert Header.aerated("") == ""
    assert Header.aerated("test", border="") == "test"

    assert Header.aerated("test", border="--") == "----------\n-- test --\n----------"
    assert Header.aerated("test", border="-- ") == "-- test\n-------"

    assert Header.aerated("test", border="=") == "========\n= test =\n========"
    assert Header.aerated("test", border="= ") == "= test\n======"


def test_pretty_table():
    with pytest.raises(ValueError, match="Invalid header"):
        PrettyTable(object)

    t = PrettyTable()
    assert len(t.header) == 0
    with pytest.raises(IndexError):
        t.header[0].style = "bold"  # Header columns are not auto-accommodated when accessing by index

    t.header.accommodate(2)
    assert len(t.header) == 2
    t.header[0].style = "bold"

    t = PrettyTable("1,2,,3", border="pad:0")
    assert len(t.header.columns) == 4
    t.add_rows("a b c".split(), "d e foo".split())

    t.header = 3  # Interpreted as 3 columns (but no header text)
    assert t.get_string() == "abc\ndefoo"

    t.header = [1, 2, 3]  # Numbers will be stringified
    assert isinstance(t.header, PrettyHeader)
    t.align = "left"
    assert t.get_string() == "123\nabc\ndefoo"

    t.align = "center"
    assert t.get_string() == "12 3\nab c\ndefoo"

    t.align = "right"
    assert t.get_string() == "12  3\nab  c\ndefoo"

    t.border = "ascii"
    s = t.get_string()
    assert s == "+===+===+=====+\n| 1 | 2 |   3 |\n+===+===+=====+\n| a | b |   c |\n+---+---+-----+\n| d | e | foo |\n+---+---+-----+"

    t.border = "empty"
    t.header.add_columns("x", "y")
    s = t.get_string()
    assert s == " 1  2    3  x  y\n a  b    c  -  -\n d  e  foo  -  -"

    t.missing = "*"
    t.style = "bold"
    assert t.header["x"] is t.header.columns[-2]

    assert t.header["x"].shown is True
    t.header.hide(-2, 0, "y")
    assert t.header[0].shown is False
    assert t.header["x"].shown is False
    assert t.header["y"].shown is False

    s = t.get_string()
    assert s == " 2    3\n b    c\n e  foo"

    assert t.header[0].shown is False
    with pytest.raises(KeyError):
        t.header.show(0, "foo")

    # Successfully shown column 0, but failed after that on "foo"
    assert t.header[0].shown is True

    assert str(t.header[0]) == "[c0] '1'"
    t.header[0].text = None
    assert str(t.header[0]) == "[c0]"

    with pytest.raises(IndexError):
        _ = t.header.columns[-55]

    with pytest.raises(KeyError):
        _ = t.header["foo"]


EXPECTED_TABLE_RENDER = """
+==========+====================+
| Location | French café        |
+----------+--------------------+
| Name     | コンニチハ, セカイ |
+----------+--------------------+
"""


def test_pretty_table_render():
    t = PrettyTable(border="ascii")
    t.add_row("Location", "French café")
    t.add_row("Name", "コンニチハ, セカイ")
    x = t.get_string()
    assert x == EXPECTED_TABLE_RENDER.strip()
