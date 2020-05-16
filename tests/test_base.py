# -*- coding: utf-8 -*-

import datetime
import os
import sys

import pytest
from mock import MagicMock, patch

import runez


def failed_function(*args):
    with patch("runez.base.logging.root") as root:
        root.handlers = None
        runez.abort(*args)


def test_abort(logged):
    assert runez.abort("aborted", fatal=(False, "some-return")) == "some-return"
    assert "aborted" in logged.pop()

    assert runez.abort("aborted", fatal=(False, "some-return"), code=0) == "some-return"
    assert "aborted" in logged
    assert "ERROR" not in logged.pop()

    assert runez.abort("aborted", fatal=(None, "some-return")) == "some-return"
    assert not logged
    assert "stderr: oops" in runez.verify_abort(failed_function, "oops")

    with patch("runez.base.AbortException", side_effect=str):
        assert runez.abort("oops", logger=None) == "1"


def test_anchored(temp_folder):
    assert runez.resolved_path(None) is None
    assert runez.resolved_path("some-file") == os.path.join(temp_folder, "some-file")
    assert runez.resolved_path("some-file", base="bar") == os.path.join(temp_folder, "bar", "some-file")

    assert runez.short(None) is None
    assert runez.short("") == ""
    assert runez.short(os.path.join(temp_folder, "some-file")) == "some-file"

    assert runez.represented_args(["ls", os.path.join(temp_folder, "some-file") + " bar", "-a"]) == 'ls "some-file bar" -a'

    user_path = runez.resolved_path("~/some-folder/bar")
    current_path = runez.resolved_path("./some-folder/bar")

    assert user_path != "~/some-folder/bar"
    assert runez.short(user_path) == "~/some-folder/bar"
    assert runez.short(current_path) == "some-folder/bar"

    with runez.Anchored(os.getcwd()):
        assert runez.short(current_path) == os.path.join("some-folder", "bar")


def mock_package(package, **kwargs):
    globs = {"__package__": package}
    for key, value in kwargs.items():
        globs["__%s__" % key] = value

    return MagicMock(f_globals=globs)


def test_auto_import_siblings():
    # Check that none of these invocations raise an exception
    assert not runez.base.actual_caller_frame(mock_package(None))
    assert not runez.base.actual_caller_frame(mock_package(""))
    assert not runez.base.actual_caller_frame(mock_package("_pydevd"))
    assert not runez.base.actual_caller_frame(mock_package("_pytest.foo"))
    assert not runez.base.actual_caller_frame(mock_package("pluggy.hooks"))
    assert not runez.base.actual_caller_frame(mock_package("runez"))
    assert not runez.base.actual_caller_frame(mock_package("runez.base"))

    assert runez.base.actual_caller_frame(mock_package("foo"))
    assert runez.base.actual_caller_frame(mock_package("runez.base", name="__main__"))

    with pytest.raises(ImportError):
        with patch("runez.base.find_caller_frame", return_value=None):
            runez.auto_import_siblings()

    with pytest.raises(ImportError):
        with patch("runez.base.find_caller_frame", return_value=mock_package("foo", name="__main__")):
            runez.auto_import_siblings()

    with pytest.raises(ImportError):
        with patch("runez.base.find_caller_frame", return_value=mock_package(None)):
            runez.auto_import_siblings()

    with pytest.raises(ImportError):
        with patch("runez.base.find_caller_frame", return_value=mock_package("foo")):
            runez.auto_import_siblings()

    with pytest.raises(ImportError):
        with patch("runez.base.find_caller_frame", return_value=mock_package("foo", file="/dev/null/foo")):
            runez.auto_import_siblings()

    with patch.dict(os.environ, {"TOX_WORK_DIR": "some-value"}, clear=True):
        imported = runez.auto_import_siblings(skip=["tests.test_base", "tests.test_serialize"])
        assert len(imported) == 21

        assert "tests.conftest" in imported
        assert "tests.secondary" in imported
        assert "tests.secondary.test_import" in imported
        assert "tests.test_base" not in imported
        assert "tests.test_click" in imported
        assert "tests.test_serialize" not in imported

    imported = runez.auto_import_siblings(skip=["tests.secondary"])
    assert len(imported) == 21
    assert "tests.conftest" in imported
    assert "tests.secondary" not in imported
    assert "tests.secondary.test_import" not in imported
    assert "tests.test_base" in imported


def test_base():
    assert runez.capped(123, minimum=200) == 200
    assert runez.capped(123, maximum=100) == 100
    assert runez.capped(123, minimum=100, maximum=200) == 123
    assert runez.capped(123, minimum=100, maximum=110) == 110

    assert runez.decode(None) is None
    assert runez.decode(" something ") == " something "
    assert runez.decode(" something ", strip=True) == "something"

    # len() depends on whether python was built with UCS-2 or UCS-4, we don't care here, just want to check decode() works OK with unicode
    assert len(runez.decode(" lucky leaf ☘ is lucky 😀 ")) in (25, 26)
    assert len(runez.decode(" lucky leaf ☘ is lucky 😀 ", strip=True)) in (23, 24)

    assert runez.decode(b" something ") == " something "
    assert runez.decode(b" something ", strip=True) == "something"

    assert runez.first_meaningful_line("") is None
    assert runez.first_meaningful_line("\n  \n\n") is None
    assert runez.first_meaningful_line("\n\n\n  foo  \n\bar") == "foo"

    # Verify that UNSET behaves as expected: evaluates to falsy, has correct representation
    assert not runez.UNSET
    assert bool(runez.UNSET) is False
    assert str(runez.UNSET) == "UNSET"

    assert runez.quoted(None) is None
    assert runez.quoted("") == ""
    assert runez.quoted(" ") == '" "'
    assert runez.quoted('"') == '"'
    assert runez.quoted("a b") == '"a b"'
    assert runez.quoted('a="b"') == 'a="b"'
    assert runez.quoted('foo a="b"') == """'foo a="b"'"""

    assert runez.represented_args(None) == ""
    assert runez.represented_args([]) == ""
    assert runez.represented_args([0, 1, 2]) == "0 1 2"
    assert runez.represented_args(["foo", {}, 0, [1, 2], {3: 4}, 5]) == 'foo {} 0 "[1, 2]" "{3: 4}" 5'

    # Edge cases with test_stringified()
    assert runez.stringified(5, converter=lambda x: None) == "5"
    assert runez.stringified(5, converter=lambda x: x) == "5"

    assert runez.base._formatted_string() == ""
    assert runez.base._formatted_string("test") == "test"
    assert runez.base._formatted_string("test", "bar") == "test"
    assert runez.base._formatted_string("test %s", "bar") == "test bar"
    assert runez.base._formatted_string("test %s %s", "bar") == "test %s %s"
    assert runez.base._formatted_string(None) is None
    assert runez.base._formatted_string(None, "bar") is None
    assert runez.base._formatted_string("test", None) == "test"

    assert runez.base.find_parent_folder("", {"foo"}) is None
    assert runez.base.find_parent_folder("/a/b//", {""}) is None
    assert runez.base.find_parent_folder("/a/b", {"a"}) == "/a"
    assert runez.base.find_parent_folder("/a/b//", {"a"}) == "/a"
    assert runez.base.find_parent_folder("//a/b//", {"a"}) == "//a"
    assert runez.base.find_parent_folder("/a/b", {"b"}) == "/a/b"
    assert runez.base.find_parent_folder("/a/B", {"a", "b"}) == "/a/B"  # case insensitive
    assert runez.base.find_parent_folder("/a/b", {"c"}) is None
    assert runez.base.find_parent_folder("/dev/null", {"foo"}) is None
    assert "test_base.py" in runez.current_test()


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


def test_descendants():
    class Cat(object):
        _foo = None

    class FastCat(Cat):
        pass

    class LittleCatKitty(Cat):
        pass

    class CatMeow(FastCat):
        pass

    # By default, root ancestor is skipped, common prefix/suffix is removed, and name is lowercase-d
    d = runez.class_descendants(Cat)
    assert len(d) == 3
    assert d["fast"] is FastCat
    assert d["littlecatkitty"] is LittleCatKitty
    assert d["meow"] is CatMeow

    # Keep names as-is, including root ancestor
    d = runez.class_descendants(Cat, adjust=lambda x, r: x.__name__)
    assert len(d) == 4
    assert d["Cat"] is Cat
    assert d["FastCat"] is FastCat
    assert d["LittleCatKitty"] is LittleCatKitty
    assert d["CatMeow"] is CatMeow

    assert FastCat._foo is None

    # The 'adjust' function can also be used to simply modify descendants (but not track them)
    def adjust(cls, root):
        cls._foo = cls.__name__.lower()

    d = runez.class_descendants(Cat, adjust=adjust)
    assert len(d) == 0
    assert FastCat._foo == "fastcat"


def test_flattened():
    assert runez.flattened(None) == [None]
    assert runez.flattened([None]) == [None]
    assert runez.flattened(None, split=runez.SANITIZED) == []
    assert runez.flattened(None, split=runez.SHELL) == []
    assert runez.flattened(None, split=runez.UNIQUE) == [None]

    assert runez.flattened(["-a", [None, "b", runez.UNSET], runez.UNSET]) == ["-a", None, "b", runez.UNSET, runez.UNSET]
    assert runez.flattened(["-a", [None, "b", runez.UNSET], runez.UNSET], split=runez.UNIQUE) == ["-a", None, "b", runez.UNSET]
    assert runez.flattened(["-a", [None, "b", runez.UNSET], runez.UNSET], split=runez.SANITIZED) == ["-a", "b"]
    assert runez.flattened(["-a", [None, "b", runez.UNSET], runez.UNSET], split=runez.SHELL) == ["b"]
    assert runez.flattened(["-a", [runez.UNSET, "b", runez.UNSET], runez.UNSET], split=runez.SHELL) == ["b"]

    assert runez.flattened(["a b"]) == ["a b"]
    assert runez.flattened([["a b"]]) == ["a b"]

    assert runez.flattened(["-r", None, "foo"]) == ["-r", None, "foo"]
    assert runez.flattened(["-r", None, "foo"], split=runez.SANITIZED) == ["-r", "foo"]
    assert runez.flattened(["-r", None, "foo"], split=runez.SHELL) == ["foo"]
    assert runez.flattened(["-r", None, "foo"], split=runez.UNIQUE) == ["-r", None, "foo"]
    assert runez.flattened(["-r", None, "foo"], split=runez.SANITIZED | runez.UNIQUE) == ["-r", "foo"]

    # Sanitized
    assert runez.flattened(("a", None, ["b", None]), split=runez.UNIQUE) == ["a", None, "b"]
    assert runez.flattened(("a", None, ["b", None]), split=runez.SANITIZED | runez.UNIQUE) == ["a", "b"]

    # Shell cases
    assert runez.flattened([None, "a", "-f", "b", "c", None], split=runez.SHELL) == ["a", "-f", "b", "c"]
    assert runez.flattened(["a", "-f", "b", "c"], split=runez.SHELL) == ["a", "-f", "b", "c"]
    assert runez.flattened([None, "-f", "b", None], split=runez.SHELL) == ["-f", "b"]
    assert runez.flattened(["a", "-f", None, "c"], split=runez.SHELL) == ["a", "c"]

    # Splitting on separator
    assert runez.flattened("a b b") == ["a b b"]
    assert runez.flattened("a b b", split=" ") == ["a", "b", "b"]
    assert runez.flattened("a b b", split=(" ", runez.UNIQUE)) == ["a", "b"]
    assert runez.flattened("a b b", split=(None, runez.UNIQUE)) == ["a b b"]
    assert runez.flattened("a b b", split=("", runez.UNIQUE)) == ["a b b"]
    assert runez.flattened("a b b", split=("+", runez.UNIQUE)) == ["a b b"]

    # Unique
    assert runez.flattened(["a", ["a", ["b", ["b", "c"]]]]) == ["a", "a", "b", "b", "c"]
    assert runez.flattened(["a", ["a", ["b", ["b", "c"]]]], split=runez.UNIQUE) == ["a", "b", "c"]

    assert runez.flattened(["a b", None, ["a b c"], "a"], split=runez.UNIQUE) == ["a b", None, "a b c", "a"]
    assert runez.flattened(["a b", None, ["a b c"], "a"], split=(" ", runez.UNIQUE)) == ["a", "b", None, "c"]
    assert runez.flattened(["a b", None, ["a b c"], "a"], split=(" ", runez.SANITIZED | runez.UNIQUE)) == ["a", "b", "c"]


def test_formatted():
    class Record(object):
        basename = "my-name"
        filename = "{basename}.txt"

    assert runez.formatted("{filename}", Record) == "my-name.txt"
    assert runez.formatted("{basename}/{filename}", Record) == "my-name/my-name.txt"

    assert runez.formatted("") == ""
    assert runez.formatted("", Record) == ""
    assert runez.formatted("{not_there}", Record) is None
    assert runez.formatted("{not_there}", Record, name="susan") is None
    assert runez.formatted("{not_there}", Record, not_there="psyched!") == "psyched!"
    assert runez.formatted("{not_there}", Record, strict=False) == "{not_there}"

    deep = dict(a="a", b="b", aa="{a}", bb="{b}", ab="{aa}{bb}", ba="{bb}{aa}", abba="{ab}{ba}", deep="{abba}")
    assert runez.formatted("{deep}", deep, max_depth=-1) == "{deep}"
    assert runez.formatted("{deep}", deep, max_depth=0) == "{deep}"
    assert runez.formatted("{deep}", deep, max_depth=1) == "{abba}"
    assert runez.formatted("{deep}", deep, max_depth=2) == "{ab}{ba}"
    assert runez.formatted("{deep}", deep, max_depth=3) == "{aa}{bb}{bb}{aa}"
    assert runez.formatted("{deep}", deep, max_depth=4) == "{a}{b}{b}{a}"
    assert runez.formatted("{deep}", deep, max_depth=5) == "abba"
    assert runez.formatted("{deep}", deep, max_depth=6) == "abba"

    cycle = dict(a="{b}", b="{a}")
    assert runez.formatted("{a}", cycle, max_depth=0) == "{a}"
    assert runez.formatted("{a}", cycle, max_depth=1) == "{b}"
    assert runez.formatted("{a}", cycle, max_depth=2) == "{a}"
    assert runez.formatted("{a}", cycle, max_depth=3) == "{b}"

    assert runez.formatted("{filename}") == "{filename}"


def test_get_version():
    with runez.CaptureOutput() as logged:
        expected = runez.get_version(runez)
        assert expected
        assert expected != "0.0.0"
        assert expected == runez.get_version(runez.__name__)
        assert expected == runez.get_version("runez")
        assert expected == runez.get_version("runez.base")
        assert not logged

    with runez.CaptureOutput() as logged:
        assert runez.get_version(None) == "0.0.0"
        assert not logged

        assert runez.get_version(["foo"]) == "0.0.0"
        assert "Can't determine version" in logged.pop()

    with runez.CaptureOutput() as logged:
        with patch("pkg_resources.get_distribution", side_effect=Exception("testing")):
            assert runez.get_version(runez) == "0.0.0"
        assert "Can't determine version for runez" in logged


def test_shortened():
    assert runez.shortened(None) == "None"
    assert runez.shortened("") == ""
    assert runez.shortened(5) == "5"
    assert runez.shortened(" some text ") == "some text"
    assert runez.shortened(" \n  some \n  long text", size=9) == "some l..."
    assert runez.shortened(" \n  some \n  long text", size=8) == "some ..."
    assert runez.shortened(" a \n\n  \n  b ") == "a b"

    assert runez.shortened([1, "b"]) == "[1, b]"
    assert runez.shortened((1, {"b": ["c", {"d", "e"}]})) == "(1, {b: [c, {d, e}]})"

    complex = {"a \n b": [1, None, "foo \n ,", {"a2": runez.abort, "c": runez.Anchored}], None: datetime.date(2019, 1, 1)}
    assert runez.shortened(complex) == "{None: 2019-01-01, a b: [1, None, foo ,, {a2: function 'abort', c: class runez.base.Anchored}]}"
    assert runez.shortened(complex, size=32) == "{None: 2019-01-01, a b: [1, N..."

    assert runez.shortened(" some  text ", size=32) == "some text"
    assert runez.shortened(" some  text ", size=7) == "some..."
    assert runez.shortened(" some  text ", size=0) == "some text"
