# -*- coding: utf-8 -*-

import datetime
import logging
import os
import sys

import pytest
from mock import patch

import runez
from runez.conftest import verify_abort
from runez.system import TerminalInfo


VERSION = "1.2.3.dev4"


def failed_function(message, fatal=True, logger=runez.UNSET):
    with patch("runez.system.logging.root") as root:
        root.handlers = None
        runez.abort(message, fatal=fatal, logger=logger)


def test_abort(logged):
    assert runez.abort("aborted", return_value="some-return", fatal=False) == "some-return"
    assert "ERROR" in logged
    assert "aborted" in logged.pop()

    # User wants their own logger called
    assert runez.abort("aborted", return_value="some-return", fatal=False, logger=logging.debug) == "some-return"
    assert "ERROR" not in logged
    assert "DEBUG" in logged
    assert "aborted" in logged.pop()

    assert runez.abort("aborted", return_value="some-return", fatal=None) == "some-return"
    assert not logged

    assert "stderr: oops" in verify_abort(failed_function, "oops")  # logger is UNSET -> log failure
    assert "oops" not in verify_abort(failed_function, "oops", logger=None)  # logger is None -> don't log failure

    # Verify experimental passing of exception via 'fatal' works
    assert "stderr: oops" in verify_abort(failed_function, "oops", fatal=SystemExit, logger=None)  # log failure anyway due to sys.exit()

    # Verify we still log failure when we're about to sys.exit(), even when logger given is explicitly None
    prev = runez.system.AbortException
    runez.system.AbortException = SystemExit
    assert "stderr: oops" in verify_abort(failed_function, "oops", logger=None)  # logger is None -> log failure anyway
    runez.system.AbortException = prev
    assert not logged


def test_capture_scope():
    with runez.CaptureOutput() as logged:
        print("on stdout")
        sys.stderr.write("on stderr")
        assert "on stdout" in logged.stdout
        assert "on stderr" in logged.stderr

    with runez.CaptureOutput(stderr=False) as logged:
        print("on stdout")
        sys.stderr.write("on stderr")

        # Verify that stderr was not captured, but stdout was
        assert "on stdout" in logged.stdout
        assert "on stderr" not in logged
        assert logged.stderr is None


def test_capture_nested():
    with runez.CaptureOutput(stdout=True, stderr=True) as logged1:
        # Capture both stdout and stderr
        print("print1")
        sys.stderr.write("err1\n")

        assert "print1" in logged1.stdout
        assert "err1" in logged1.stderr

        with runez.CaptureOutput(stdout=True, stderr=False) as logged2:
            # Capture only stdout on 2nd level
            print("print2")
            sys.stderr.write("err2\n")

            # Verify that we did capture, and are isolated from prev level
            assert "print1" not in logged2.stdout
            assert "print2" in logged2.stdout

            with runez.CaptureOutput(stdout=False, stderr=True) as logged3:
                # Capture only stderr on 3rd level
                print("print3")
                sys.stderr.write("err3\n")

                # Verify that we did capture, and are isolated from prev level
                assert "err1" not in logged3.stderr
                assert "err2" not in logged3.stderr
                assert "err3" in logged3.stderr

        # Verify that 1st level was not impacted by the others
        assert "print1" in logged1.stdout
        assert "err1" in logged1.stderr

        # err2 should have passed through as we weren't capturing stderr in logged2
        assert "err2" in logged1.stderr

        assert "print2" not in logged1.stdout
        assert "print3" not in logged1.stdout
        assert "err3" not in logged1.stderr


def test_current_folder(temp_folder):
    sample = os.path.join(temp_folder, "sample")
    assert os.getcwd() == temp_folder
    assert runez.ensure_folder("sample") == 1

    with runez.CurrentFolder("sample", anchor=False):
        cwd = os.getcwd()
        assert cwd == sample
        assert runez.short(os.path.join(cwd, "some-file")) == os.path.join("sample", "some-file")

    with runez.CurrentFolder("sample", anchor=True):
        cwd = os.getcwd()
        sample = os.path.join(temp_folder, "sample")
        assert cwd == sample
        assert runez.short(os.path.join(cwd, "some-file")) == "some-file"

    assert os.getcwd() == temp_folder


def test_decode():
    assert runez.decode(None) is None
    assert runez.decode(" something ") == " something "
    assert runez.decode(" something ", strip=True) == "something"

    # len() depends on whether python was built with UCS-2 or UCS-4, we don't care here, just want to check decode() works OK with unicode
    assert len(runez.decode(" lucky leaf ☘ is lucky 😀 ")) in (25, 26)
    assert len(runez.decode(" lucky leaf ☘ is lucky 😀 ", strip=True)) in (23, 24)

    assert runez.decode(b" something ") == " something "
    assert runez.decode(b" something ", strip=True) == "something"


def test_expanded():
    class Record(object):
        basename = "my-name"
        filename = "{basename}.txt"

    assert runez.expanded("{filename}", Record) == "my-name.txt"
    assert runez.expanded("{basename}/~/{filename}", Record) == "my-name/~/my-name.txt"
    assert runez.expanded("~/{basename}/{filename}", Record) == os.path.expanduser("~/my-name/my-name.txt")

    assert runez.expanded("") == ""
    assert runez.expanded("", Record) == ""
    assert runez.expanded("{not_there}", Record) is None
    assert runez.expanded("{not_there}", Record, name="susan") is None
    assert runez.expanded("{not_there}", Record, not_there="psyched!") == "psyched!"
    assert runez.expanded("{not_there}", Record, strict=False) == "{not_there}"

    deep = dict(a="a", b="b", aa="{a}", bb="{b}", ab="{aa}{bb}", ba="{bb}{aa}", abba="{ab}{ba}", deep="{abba}")
    assert runez.expanded("{deep}", deep, max_depth=-1) == "{deep}"
    assert runez.expanded("{deep}", deep, max_depth=0) == "{deep}"
    assert runez.expanded("{deep}", deep, max_depth=1) == "{abba}"
    assert runez.expanded("{deep}", deep, max_depth=2) == "{ab}{ba}"
    assert runez.expanded("{deep}", deep, max_depth=3) == "{aa}{bb}{bb}{aa}"
    assert runez.expanded("{deep}", deep, max_depth=4) == "{a}{b}{b}{a}"
    assert runez.expanded("{deep}", deep, max_depth=5) == "abba"
    assert runez.expanded("{deep}", deep, max_depth=6) == "abba"

    cycle = dict(a="{b}", b="{a}")
    assert runez.expanded("{a}", cycle, max_depth=0) == "{a}"
    assert runez.expanded("{a}", cycle, max_depth=1) == "{b}"
    assert runez.expanded("{a}", cycle, max_depth=2) == "{a}"
    assert runez.expanded("{a}", cycle, max_depth=3) == "{b}"

    assert runez.expanded("{filename}") == "{filename}"


def test_fallback(logged):
    def oopsie(x):
        raise Exception()

    def do_nothing():
        pass

    # Sample chain with 1 failing and one succeeding function
    c1 = runez.FallbackChain(oopsie, lambda x: x, description="test chain")

    # First run takes the failing function out of the loop
    assert str(c1) == "[test chain] oopsie (+1)"
    assert c1("foo") == "foo"
    assert len(c1.failed) == 1

    # Subsequent runs keep using the succeeding one
    assert str(c1) == "[test chain] <lambda> (+0), failed: oopsie"
    assert c1("bar") == "bar"
    assert c1("hello") == "hello"
    assert len(c1.failed) == 1
    assert str(c1) == "[test chain] <lambda> (+0), failed: oopsie"

    class MyRunner(object):
        def prepare(self):
            """Preparation succeeds"""

        def run(self, x):
            return x

    # More complex sample
    c2 = runez.FallbackChain(
        description="sample",
        a=oopsie,  # Will fail on call
        b=dict(run=oopsie, prepare=do_nothing),  # Will fail on call, prepare will succeed
        c=dict(run=lambda x: x, prepare=oopsie),  # Will fail on prepare
        d=MyRunner(),
    )
    assert str(c2) == "[sample] a (+3)"
    assert c2("hello") == "hello"
    assert str(c2) == "[sample] d (+0), failed: a, b, c"

    assert c2("foo") == "foo"
    assert c2("bar") == "bar"
    assert str(c2) == "[sample] d (+0), failed: a, b, c"

    # Sample chain with all failing functions
    c3 = runez.FallbackChain(oopsie, a=oopsie, description="all failing", logger=logging.error)
    assert str(c3) == "[all failing] oopsie (+1)"
    assert not logged

    with pytest.raises(Exception):  # Raises "Fallback chain exhausted"
        c3("foo")
    assert str(c3) == "[all failing] None (+0), failed: oopsie, a"
    assert "oopsie failed" in logged.pop()

    with pytest.raises(Exception):  # Keeps raising
        c3("hello")
    assert not logged
    assert str(c3) == "[all failing] None (+0), failed: oopsie, a"


def test_first_line():
    assert runez.first_line(None) is None
    assert runez.first_line("") is None
    assert runez.first_line("\n  \n\n") is None
    assert runez.first_line("\n  \n\n", default="foo") == "foo"
    assert runez.first_line("  \n\n", keep_empty=True) == "  "
    assert runez.first_line("  \n\n", keep_empty=True, default="foo") == "  "
    assert runez.first_line("\n  \n\n", keep_empty=True) == ""
    assert runez.first_line("\n\n\n  foo  \n\bar") == "foo"
    assert runez.first_line("\n\n\n  foo  \n\bar", keep_empty=True) == ""
    assert runez.first_line([]) is None
    assert runez.first_line([], keep_empty=True) is None
    assert runez.first_line([], default="foo") == "foo"
    assert runez.first_line([], keep_empty=True, default="foo") == "foo"
    assert runez.first_line([" "]) is None
    assert runez.first_line([" "], default="foo") == "foo"
    assert runez.first_line([" "], keep_empty=True, default="foo") == " "
    assert runez.first_line([" ", "b"]) == "b"
    assert runez.first_line([" ", "b"], default="foo") == "b"
    assert runez.first_line([" ", "b"], keep_empty=True) == " "
    assert runez.first_line([" ", "b"], keep_empty=True, default="foo") == " "


def test_flattened():
    with pytest.raises(TypeError):  # TODO: remove once py2 support is dropped
        runez.flattened("", foo=1)

    assert runez.flattened(None) == [None]
    assert runez.flattened([None]) == [None]

    assert runez.flattened(None, [runez.UNSET, 0]) == [None, runez.UNSET, 0]
    assert runez.flattened(None, [runez.UNSET, 0], shellify=True) == ["0"]
    assert runez.flattened(None, [runez.UNSET, 0], keep_empty=None) == []
    assert runez.flattened(None, [runez.UNSET, 0], keep_empty=False) == [0]
    assert runez.flattened(None, [runez.UNSET, 0], keep_empty=True) == [None, runez.UNSET, 0]
    assert runez.flattened(None, [runez.UNSET, 0], keep_empty="") == ["", "", 0]
    assert runez.flattened(None, [runez.UNSET, 0], keep_empty="null") == ["null", "null", 0]
    assert runez.flattened(None, [runez.UNSET, 0], keep_empty="null", unique=False) == ["null", "null", 0]
    assert runez.flattened(None, [runez.UNSET, 0], keep_empty="null", unique=True) == ["null", 0]
    assert runez.flattened(None, [runez.UNSET, 0], keep_empty="", shellify=True) == ["0"]

    assert runez.flattened(None, None, keep_empty=False, unique=True) == []
    assert runez.flattened(None, None, shellify=True) == []
    assert runez.flattened(None, None, runez.UNSET, None, runez.UNSET, unique=True) == [None, runez.UNSET]

    assert runez.flattened(None, None, keep_empty=None) == []
    assert runez.flattened(None, None, keep_empty="") == ["", ""]
    assert runez.flattened(None, None, keep_empty="null") == ["null", "null"]
    assert runez.flattened(None, None, keep_empty="null", unique=True) == ["null"]

    assert runez.flattened(["-a", [None, "b", runez.UNSET], runez.UNSET]) == ["-a", None, "b", runez.UNSET, runez.UNSET]
    assert runez.flattened(["-a", [None, "b", runez.UNSET], runez.UNSET], unique=True) == ["-a", None, "b", runez.UNSET]
    assert runez.flattened(["-a", [None, "b", runez.UNSET], runez.UNSET], keep_empty=False) == ["-a", "b"]
    assert runez.flattened(["-a", [None, "b", runez.UNSET], runez.UNSET], shellify=True) == ["b"]
    assert runez.flattened(["-a", [runez.UNSET, "b", runez.UNSET], runez.UNSET], shellify=True) == ["b"]

    assert runez.flattened(["a b"]) == ["a b"]
    assert runez.flattened([["a b"]]) == ["a b"]

    assert runez.flattened(["-r", None, "foo"]) == ["-r", None, "foo"]
    assert runez.flattened(["-r", None, "foo"], keep_empty=False) == ["-r", "foo"]
    assert runez.flattened(["foo", "-r", None, "bar"], shellify=True) == ["foo", "bar"]
    assert runez.flattened(["-r", None, "foo"], unique=True) == ["-r", None, "foo"]
    assert runez.flattened(["-r", None, "foo"], keep_empty=False, unique=True) == ["-r", "foo"]

    # Sanitized
    assert runez.flattened(("a", None, ["b", None]), unique=True) == ["a", None, "b"]
    assert runez.flattened(("a", None, ["b", None]), keep_empty=False, unique=True) == ["a", "b"]

    # Shell cases
    assert runez.flattened([None, "a", "-f", "b", "c", None], shellify=True) == ["a", "-f", "b", "c"]
    assert runez.flattened(["a", "-f", "b", "c"], shellify=True) == ["a", "-f", "b", "c"]
    assert runez.flattened([None, "-f", "b", None], shellify=True) == ["-f", "b"]
    assert runez.flattened(["a", "-f", None, "c"], shellify=True) == ["a", "c"]

    assert runez.flattened(["a", "-f", None, "c"], keep_empty=None, shellify=True) == ["a", "c"]
    assert runez.flattened(["a", "-f", None, "c"], keep_empty=False, shellify=True) == ["a", "c"]
    assert runez.flattened(["a", "-f", None, "c"], keep_empty=True, shellify=True) == ["a", "c"]
    assert runez.flattened(["a", "-f", None, "c"], keep_empty="", shellify=True) == ["a", "c"]
    assert runez.flattened(["a", "-f", None, "c"], keep_empty="null", shellify=True) == ["a", "c"]

    # In shellify mode, empty strings are only filtered out with keep_empty=None
    assert runez.flattened(["a", "-f", "", "c"], shellify=True) == ["a", "-f", "", "c"]
    assert runez.flattened(["a", "-f", "", "c"], keep_empty=None, shellify=True) == ["a", "c"]
    assert runez.flattened(["a", "-f", "", "c"], keep_empty=False, shellify=True) == ["a", "-f", "", "c"]
    assert runez.flattened(["a", "-f", "", "c"], keep_empty=True, shellify=True) == ["a", "-f", "", "c"]
    assert runez.flattened(["a", "-f", "", "c"], keep_empty="", shellify=True) == ["a", "-f", "", "c"]
    assert runez.flattened(["a", "-f", "", "c"], keep_empty="null", shellify=True) == ["a", "-f", "", "c"]

    # Splitting on a given char
    assert runez.flattened("a b b") == ["a b b"]
    assert runez.flattened("a b b", split=" ") == ["a", "b", "b"]
    assert runez.flattened("a b b", split=" ", unique=True) == ["a", "b"]
    assert runez.flattened("a b b", unique=True) == ["a b b"]
    assert runez.flattened("a b b", split="", unique=True) == ["a b b"]
    assert runez.flattened("a b b", split="+", unique=True) == ["a b b"]

    # Unique
    assert runez.flattened(["a", ["a", ["b", ["b", "c"]]]]) == ["a", "a", "b", "b", "c"]
    assert runez.flattened(["a", ["a", ["b", ["b", "c"]]]], unique=True) == ["a", "b", "c"]

    assert runez.flattened(["a b", None, ["a b c"], "a"], unique=True) == ["a b", None, "a b c", "a"]
    assert runez.flattened(["a b", None, ["a b c"], "a"], split=" ", unique=True) == ["a", "b", None, "c"]
    assert runez.flattened(["a b", None, ["a b c"], "a"], split=" ", keep_empty=False, unique=True) == ["a", "b", "c"]


def test_get_version():
    with runez.CaptureOutput() as logged:
        expected = runez.get_version(runez)
        assert expected
        assert expected != "0.0.0"
        assert expected == runez.get_version(runez.__name__)
        assert expected == runez.get_version("runez")
        assert expected == runez.get_version("runez.system")
        assert not logged

    with runez.CaptureOutput() as logged:
        assert runez.get_version(None) == "0.0.0"
        assert runez.get_version(__name__) == VERSION
        assert not logged

        assert runez.get_version(["foo"]) == "0.0.0"
        assert "Can't determine version" in logged.pop()

        assert runez.get_version(["foo"], logger=None) == "0.0.0"
        assert not logged


def test_joined():
    with pytest.raises(TypeError):  # TODO: remove once py2 support is dropped
        runez.joined("", foo=1)

    def gen():
        yield "foo"
        yield None
        yield "bar"

    assert runez.joined() == ""
    assert runez.joined(None) == "None"
    assert runez.joined(None, keep_empty=False) == ""

    assert runez.joined("") == ""
    assert runez.joined("", "") == " "
    assert runez.joined("", "", keep_empty=None) == ""

    assert runez.joined("", runez.UNSET, None, "foo", 0, "", None) == " UNSET None foo 0  None"
    assert runez.joined("", runez.UNSET, None, "foo", 0, "", None, keep_empty=None) == "foo"
    assert runez.joined("", runez.UNSET, None, "foo", 0, "", None, keep_empty=False) == " foo 0 "
    assert runez.joined("", runez.UNSET, None, "foo", 0, "", None, keep_empty=True) == " UNSET None foo 0  None"
    assert runez.joined("", runez.UNSET, None, "foo", 0, "", None, keep_empty="") == "   foo 0  "
    assert runez.joined("", runez.UNSET, None, "foo", 0, "", None, keep_empty="null") == " null null foo 0  null"

    assert runez.joined(1, gen(), "hello", [True, runez.UNSET, 5]) == "1 foo None bar hello True UNSET 5"
    assert runez.joined(1, gen(), "hello", [True, runez.UNSET, 5], keep_empty=False) == "1 foo bar hello True 5"
    assert runez.joined(1, 2, delimiter=",") == "1,2"
    assert runez.joined(1, 2, stringify=lambda x: "foo") == "foo foo"


def test_path_resolution(temp_folder):
    assert runez.resolved_path(None) is None
    assert runez.resolved_path("some-file") == os.path.join(temp_folder, "some-file")
    assert runez.resolved_path("some-file", base="bar") == os.path.join(temp_folder, "bar", "some-file")

    assert runez.quoted(["ls", os.path.join(temp_folder, "some-file") + " bar", "-a", " foo "]) == 'ls "some-file bar" -a " foo "'


def test_quoted():
    with pytest.raises(TypeError):  # TODO: remove once py2 support is dropped
        runez.quoted("", foo=1)

    assert runez.quoted(None) == "None"
    assert runez.quoted("") == ""
    assert runez.quoted(" ") == '" "'
    assert runez.quoted(" ", adapter=runez.short) == ""
    assert runez.quoted('"') == '"'
    assert runez.quoted("a b") == '"a b"'
    assert runez.quoted('a="b"') == 'a="b"'
    assert runez.quoted('foo a="b"') == """'foo a="b"'"""

    assert runez.quoted([]) == ""
    assert runez.quoted([0, 1, 2]) == "0 1 2"
    assert runez.quoted(["foo", {}, 0, [1, 2], {3: 4}, 5]) == 'foo {} 0 1 2 "{3: 4}" 5'


def test_shortening():
    assert runez.short(None) == "None"
    assert runez.short("") == ""
    assert runez.short(5) == "5"
    assert runez.short(" some text ") == "some text"
    assert runez.short(" \n  some \n  long text", size=9) == "some l..."
    assert runez.short(" \n  some \n  long text", size=8) == "some ..."
    assert runez.short(" a \n\n  \n  b ") == "a b"

    assert runez.short([1, "b"]) == "[1, b]"
    assert runez.short((1, {"b": ["c", {"d", "e"}]})) == "(1, {b: [c, {d, e}]})"

    complex = {"a \n b": [1, None, "foo \n ,", {"a2": runez.abort, "c": runez.Anchored}], None: datetime.date(2019, 1, 1)}
    assert runez.short(complex) == "{None: 2019-01-01, a b: [1, None, foo ,, {a2: function 'abort', c: class runez.system.Anchored}]}"
    assert runez.short(complex, size=32) == "{None: 2019-01-01, a b: [1, N..."

    assert runez.short(" some  text ", size=32) == "some text"
    assert runez.short(" some  text ", size=7) == "some..."
    assert runez.short(" some  text ", size=0) == "some text"

    with patch("runez.system._R.terminal_info", return_value=TerminalInfo(12, 34)):
        assert runez.short(" some  text ", size=-5) == "some..."

    with runez.TempFolder() as tmp:
        assert runez.short(os.path.join(tmp, "some-file")) == "some-file"

        user_path = runez.resolved_path("~/some-folder/bar")
        current_path = runez.resolved_path("./some-folder/bar")
        assert user_path != "~/some-folder/bar"
        assert runez.short(user_path) == "~/some-folder/bar"
        assert runez.short(current_path) == "some-folder/bar"

        with runez.Anchored(os.getcwd(), "./foo"):
            assert runez.short(current_path) == os.path.join("some-folder", "bar")
            assert runez.short("./foo") == "./foo"
            assert runez.short(runez.resolved_path("foo")) == "foo"
            assert runez.short(runez.resolved_path("./foo/bar")) == "bar"

        assert not runez.Anchored._paths


def test_stringified():
    assert runez.stringified(None) == "None"
    assert runez.stringified(None, none=None) == ""
    assert runez.stringified(None, none=False) == ""
    assert runez.stringified(None, none=True) == "None"
    assert runez.stringified(None, none=0) == ""  # Edge-case: accept any kind of false/true-ish values for `none=`
    assert runez.stringified(None, none=1) == "None"
    assert runez.stringified(None, none="null") == "null"
    assert runez.stringified("", none="null") == ""
    assert runez.stringified(5) == "5"
    assert runez.stringified(b"foo") == "foo"
    assert runez.stringified([0, None, 1], none="null") == "[0, None, 1]"  # `none=` applies only to values (not items in lists etc...)
    assert runez.stringified([1, 2], converter=lambda x: None) == "[1, 2]"  # If converter returns None, we keep the value
    assert runez.stringified(5, converter=lambda x: x) == "5"  # No-op converter


def test_system():
    # Ensure we stop once callstack is exhausted
    assert runez.system.find_caller_frame(lambda f: None, maximum=None) is None

    assert not runez.is_tty()  # False when testing

    assert runez.python_version()

    # Verify that UNSET behaves as expected: evaluates to falsy, has correct representation
    assert not runez.UNSET
    assert bool(runez.UNSET) is False
    assert str(runez.UNSET) == "UNSET"


def test_temp_folder():
    cwd = os.getcwd()

    with runez.CaptureOutput(anchors=[os.path.join("/tmp"), os.path.join("/etc")]) as logged:
        with runez.TempFolder() as tmp:
            assert os.path.isdir(tmp)
            assert tmp != runez.system.SYMBOLIC_TMP
        assert not os.path.isdir(tmp)
        assert os.getcwd() == cwd

        assert runez.short(os.path.join("/tmp", "some-file")) == "some-file"
        assert runez.short(os.path.join("/etc", "some-file")) == "some-file"

        assert not logged

    symbolic = os.path.join(runez.system.SYMBOLIC_TMP, "some-file")
    with runez.CaptureOutput(dryrun=True) as logged:
        assert os.getcwd() == cwd
        with runez.TempFolder() as tmp:
            assert tmp == runez.system.SYMBOLIC_TMP
            assert runez.short(symbolic) == "some-file"

        assert os.getcwd() == cwd
        with runez.TempFolder(anchor=False) as tmp:
            assert tmp == runez.system.SYMBOLIC_TMP
            assert runez.short(symbolic) == symbolic

        assert not logged

    assert os.getcwd() == cwd


def test_terminal_width():
    if hasattr(os, "terminal_size"):
        t = TerminalInfo()
        t.shutil_terminal_size = os.terminal_size((10, 20))
        assert t.columns == 10
        assert t.lines == 20

    with patch.dict(os.environ, {"COLUMNS": "foo", "LINES": "bar"}, clear=True):
        t = TerminalInfo(default_columns=20, default_lines=30)
        t.shutil_terminal_size = None
        assert t.columns == 20
        assert t.lines == 30

    with patch.dict(os.environ, {"COLUMNS": "12", "LINES": "34"}, clear=True):
        t = TerminalInfo()
        t.shutil_terminal_size = None
        assert t.columns == 12
        assert t.lines == 34
