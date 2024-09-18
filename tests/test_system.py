import datetime
import logging
import os
import sys
from unittest.mock import mock_open, patch

import pytest

import runez
from runez.program import RunResult
from runez.system import _R, AbortException, PlatformId, SystemInfo, TerminalInfo, TerminalProgram

VERSION = "1.2.3.dev4"


def test_abort(logged, monkeypatch):
    assert runez.abort("aborted", fatal=False) is None
    assert "aborted" in logged.pop()

    assert runez.abort("aborted", fatal=None) is None
    assert not logged

    assert runez.abort("aborted", return_value="some-return", fatal=False) == "some-return"
    assert "ERROR" in logged
    assert "aborted" in logged.pop()

    # User wants their own logger called
    assert runez.abort("aborted", return_value="some-return", fatal=False, logger=logging.debug) == "some-return"
    assert "ERROR" not in logged
    assert "DEBUG" in logged
    assert "aborted" in logged.pop()

    assert runez.abort("aborted", return_value="some-return", fatal=False, logger=print) == "some-return"
    assert not logged.stderr
    assert logged.pop().strip() == "aborted"

    def on_log(message):
        print(message)

    # Verify that a logger callback that does not accept exc_info= doesn't fail at logging time
    with pytest.raises(AbortException):
        runez.abort("failed", exc_info=Exception("oops"), logger=on_log)
    assert not logged.stderr
    assert logged.stdout.pop().strip() == "failed: oops"

    assert runez.abort("aborted", return_value="some-return", fatal=False, logger=on_log, exc_info=Exception("oops")) == "some-return"
    assert not logged.stderr
    assert logged.pop().strip() == "aborted: oops"

    assert runez.abort("aborted", return_value="some-return", fatal=False, logger=on_log) == "some-return"
    assert not logged.stderr
    assert logged.pop().strip() == "aborted"

    assert runez.abort("aborted", return_value="some-return", fatal=None) == "some-return"
    assert not logged

    monkeypatch.setattr(runez.system.logging.root, "handlers", [])
    with pytest.raises(runez.system.AbortException):
        # logger is UNSET -> log failure
        runez.abort("oops")
    assert "oops" in logged.pop()

    with pytest.raises(runez.system.AbortException) as exc:
        # Message not logged, but part of raised exception
        runez.abort("oops", logger=None)
    assert "oops" in str(exc)
    assert not logged

    with pytest.raises(SystemExit):
        # Failure logged anyway due to sys.exit()
        runez.abort("oops", fatal=SystemExit, logger=None)
    assert "oops" in logged.pop()

    # Verify we still log failure when we're about to sys.exit(), even when logger given is explicitly None
    monkeypatch.setattr(runez.system, "AbortException", SystemExit)
    with pytest.raises(SystemExit):
        runez.abort("oops", logger=None)
    assert "oops" in logged.pop()


def test_capped():
    assert runez.capped(None, minimum=1, maximum=10) == 1
    assert runez.capped(None, maximum=10) == 10
    assert runez.capped(None, minimum=1, none_ok=True) is None

    with pytest.raises(ValueError, match="'None' is not acceptable"):
        runez.capped(None, minimum=1, key="testing")

    assert runez.capped(123, minimum=200) == 200
    assert runez.capped(123, maximum=100) == 100
    assert runez.capped(123, minimum=100, maximum=200) == 123
    assert runez.capped(123, minimum=100, maximum=110) == 110

    with pytest.raises(ValueError, match="132 is lower than minimum 200"):
        runez.capped(132, minimum=200, key="testing")

    with pytest.raises(ValueError, match="132 is greater than maximum 100"):
        runez.capped(132, maximum=100, key="testing")


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


def test_current_folder(temp_folder):
    assert temp_folder == os.getcwd()
    sample = runez.to_path(temp_folder) / "sample"
    assert runez.ensure_folder("sample") == 1

    with runez.CurrentFolder("sample", anchor=False):
        cwd = runez.to_path(os.getcwd())
        assert sample == cwd
        assert runez.short(os.path.join(cwd, "some-file")) == os.path.join("sample", "some-file")

    with runez.CurrentFolder("sample", anchor=True):
        cwd = runez.to_path(os.getcwd())
        assert cwd == sample
        assert runez.short(os.path.join(cwd, "some-file")) == "some-file"
        assert runez.short(cwd / "some-file") == "some-file"

    assert temp_folder == os.getcwd()


def test_decode():
    assert runez.decode(None) is None
    assert runez.decode(" something ") == " something "
    assert runez.decode(" something ", strip=True) == "something"

    # len() depends on whether python was built with UCS-2 or UCS-4, we don't care here, just want to check decode() works OK with unicode
    assert len(runez.decode(" lucky leaf ☘ is lucky 😀 ")) in (25, 26)
    assert len(runez.decode(" lucky leaf ☘ is lucky 😀 ", strip=True)) in (23, 24)

    assert runez.decode(b" something ") == " something "
    assert runez.decode(b" something ", strip=True) == "something"


def test_docker_detection(monkeypatch):
    monkeypatch.setenv("container", "foo")
    info = SystemInfo()
    assert info.is_running_in_docker is True

    monkeypatch.setenv("container", "")
    with patch("runez.system.open", side_effect=OSError):
        info = SystemInfo()
        assert info.is_running_in_docker is False

    if sys.version_info[:2] >= (3, 7):  # unittest.mock doesn't work correctly before 3.7
        with patch("runez.system.open", mock_open(read_data="1: /docker/foo")):
            info = SystemInfo()
            assert info.is_running_in_docker is True


def test_find_parent_folder(monkeypatch):
    assert _R.find_parent_folder("", {"foo"}) is None
    assert _R.find_parent_folder(os.path.join("/foo", "b"), {""}) is None
    assert _R.find_parent_folder(os.path.join("/foo", "b"), {"foo"}) == "/foo"
    assert _R.find_parent_folder(os.path.join("/foo", "b"), {"b"}) == os.path.join("/foo", "b")
    assert _R.find_parent_folder(os.path.join("/foo", "B"), {"foo", "b"}) == os.path.join("/foo", "B")  # case insensitive
    assert _R.find_parent_folder(os.path.join("/foo", "b"), {"c"}) is None
    assert _R.find_parent_folder("/dev/null", {"foo"}) is None

    # Verify that VIRTUAL_ENV does not impact finding DEV.venv_path()
    monkeypatch.setenv("VIRTUAL_ENV", "")
    assert runez.system.DevInfo().venv_path() == runez.DEV.venv_folder

    monkeypatch.setenv("VIRTUAL_ENV", "bar")
    assert runez.system.DevInfo().venv_path() == runez.DEV.venv_folder

    monkeypatch.setattr(runez.SYS_INFO, "venv_bin_folder", None)
    assert runez.system.DevInfo().venv_folder is None


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
    assert runez.flattened(None) == []
    assert runez.flattened([None]) == []
    assert runez.flattened([None], keep_empty=True) == [None]

    assert runez.flattened(["1"], "2", transform=int) == [1, 2]

    assert runez.flattened(None, [runez.UNSET, 0]) == [0]
    assert runez.flattened(None, [runez.UNSET, 0], shellify=True) == ["0"]
    assert runez.flattened(None, [runez.UNSET, 0], keep_empty=None) == []
    assert runez.flattened(None, [runez.UNSET, 0], keep_empty=False) == [0]
    assert runez.flattened(None, [runez.UNSET, 0], keep_empty=True) == [None, 0]
    assert runez.flattened(None, [runez.UNSET, 0], keep_empty="") == ["", 0]
    assert runez.flattened(None, [runez.UNSET, 0], keep_empty="null") == ["null", 0]
    assert runez.flattened(None, [runez.UNSET, 0], None, keep_empty="null", unique=False) == ["null", 0, "null"]
    assert runez.flattened(None, [runez.UNSET, 0], None, keep_empty="null", unique=True) == ["null", 0]
    assert runez.flattened(None, [runez.UNSET, 0], keep_empty="", shellify=True) == ["", "0"]

    assert runez.flattened(None, None, keep_empty=False, unique=True) == []
    assert runez.flattened(None, None, shellify=True) == []
    assert runez.flattened(None, None, runez.UNSET, None, runez.UNSET, unique=True) == []
    assert runez.flattened(None, None, runez.UNSET, None, runez.UNSET, keep_empty=True, unique=True) == [None]

    assert runez.flattened(None, None, keep_empty=None) == []
    assert runez.flattened(None, None, keep_empty="") == ["", ""]
    assert runez.flattened(None, None, keep_empty="null") == ["null", "null"]
    assert runez.flattened(None, None, keep_empty="null", unique=True) == ["null"]

    assert runez.flattened(["-a", [None, "b", runez.UNSET], runez.UNSET]) == ["-a", "b"]
    assert runez.flattened(["-a", [None, "b", runez.UNSET], runez.UNSET], unique=True) == ["-a", "b"]
    assert runez.flattened(["-a", [None, "b", runez.UNSET], runez.UNSET], keep_empty=True) == ["-a", None, "b"]
    assert runez.flattened(["-a", [None, "b", runez.UNSET], runez.UNSET], keep_empty="") == ["-a", "", "b"]
    assert runez.flattened(["-a", [None, "b", runez.UNSET], runez.UNSET], shellify=True) == ["b"]
    assert runez.flattened(["-a", [runez.UNSET, "b", runez.UNSET], runez.UNSET], shellify=True) == ["b"]

    assert runez.flattened(["a b"]) == ["a b"]
    assert runez.flattened([["a b"]]) == ["a b"]

    assert runez.flattened(["-r", None, "foo"]) == ["-r", "foo"]
    assert runez.flattened(["-r", None, "foo"], keep_empty=True) == ["-r", None, "foo"]
    assert runez.flattened(["foo", "-r", None, "bar"], shellify=True) == ["foo", "bar"]
    assert runez.flattened(["-r", None, "foo"], unique=True) == ["-r", "foo"]
    assert runez.flattened(["-r", None, "foo"], keep_empty=True, unique=True) == ["-r", None, "foo"]

    # Sanitized
    assert runez.flattened(("a", None, ["b", None]), unique=True) == ["a", "b"]
    assert runez.flattened(("a", None, ["b", None]), keep_empty=True, unique=True) == ["a", None, "b"]

    # Shell cases
    assert runez.flattened([None, "a", "-f", "b", "c", None], shellify=True) == ["a", "-f", "b", "c"]
    assert runez.flattened(["a", "-f", "b", "c"], shellify=True) == ["a", "-f", "b", "c"]
    assert runez.flattened([None, "-f", "b", None], shellify=True) == ["-f", "b"]
    assert runez.flattened(["a", "-f", None, "c"], shellify=True) == ["a", "c"]

    # Verify -flag gets removed with shellify
    assert runez.flattened(["a", "-f", None, "c"], shellify=True) == ["a", "c"]
    assert runez.flattened(["a", "-f", None, "c"], keep_empty=False, shellify=True) == ["a", "c"]
    assert runez.flattened(["a", "-f", None, "c"], keep_empty=True, shellify=True) == ["a", "c"]

    # shellify influences keep_empty
    expected = ["a", "-f", "", "c", "0", ""]
    assert runez.flattened(["a", "-f", "", "c", None, 0, ""], shellify=True) == expected
    assert runez.flattened(["a", "-f", "", "c", None, 0, ""], keep_empty=False, shellify=True) == expected
    assert runez.flattened(["a", "-f", "", "c", None, 0, ""], keep_empty=True, shellify=True) == expected

    # Override keep_empty
    assert runez.flattened(["a", "-f", None, "c"], keep_empty=None, shellify=True) == ["a", "c"]
    assert runez.flattened(["a", "-f", None, "c"], keep_empty="", shellify=True) == ["a", "-f", "", "c"]
    assert runez.flattened(["a", "-f", None, "c"], keep_empty="null", shellify=True) == ["a", "-f", "null", "c"]
    assert runez.flattened(["a", "-f", "", "c", None, 0, ""], keep_empty=None, shellify=True) == ["a", "c"]
    assert runez.flattened(["a", "-f", "", "c", None, 0, ""], keep_empty="", shellify=True) == ["a", "-f", "", "c", "", "0", ""]
    assert runez.flattened(["a", "-f", "", "c", None, 0, ""], keep_empty="null", shellify=True) == ["a", "-f", "", "c", "null", "0", ""]

    # keep_empty with transform
    def keep_odds(i):
        if i % 2:
            return i

        return 0 if i % 4 else None

    sample = list(range(8))
    assert runez.flattened(sample, transform=keep_odds, keep_empty=True) == [None, 1, 0, 3, None, 5, 0, 7]
    assert runez.flattened(sample, transform=keep_odds, keep_empty=False) == [1, 0, 3, 5, 0, 7]
    assert runez.flattened(sample, transform=keep_odds, keep_empty=None) == [1, 3, 5, 7]
    assert runez.flattened(sample, transform=keep_odds, keep_empty="foo") == ["foo", 1, 0, 3, "foo", 5, 0, 7]


def test_flattened_split():
    # Splitting on a given char
    assert runez.flattened("a b b") == ["a b b"]
    assert runez.flattened("a b\n b", split=" ") == ["a", "b", "b"]
    assert runez.flattened("a b\n b", split=True) == ["a", "b", "b"]
    assert runez.flattened("a b\n \n \n b", split=" ", unique=True) == ["a", "b"]
    assert runez.flattened("a b b", unique=True) == ["a b b"]
    assert runez.flattened("a b b", split="", unique=True) == ["a b b"]
    assert runez.flattened("a b b", split="+", unique=True) == ["a b b"]
    assert runez.flattened("a,,b", "c", split=",") == ["a", "b", "c"]

    # Unique
    assert runez.flattened(["a", ["a", ["b", ["b", "c"]]]]) == ["a", "a", "b", "b", "c"]
    assert runez.flattened(["a", ["a", ["b", ["b", "c"]]]], unique=True) == ["a", "b", "c"]

    assert runez.flattened(["a b", None, ["a b c"], "a"], unique=True) == ["a b", "a b c", "a"]
    assert runez.flattened(["a b", None, ["a b c"], "a"], keep_empty=True, unique=True) == ["a b", None, "a b c", "a"]
    assert runez.flattened(["a b", None, ["a b c"], "a"], split=" ", unique=True) == ["a", "b", "c"]
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
        assert runez.get_version(None) is None
        assert runez.get_version(["foo"], default="0.0.0", logger=logging.debug) is None  # Ignore if given name is not a string or module
        assert runez.get_version(__name__) == VERSION
        assert not logged

        assert runez.get_version("foo", logger=logging.debug) == "0.0.0"
        assert "Can't determine version" in logged.pop()


def test_joined():
    def gen():
        yield "foo"
        yield None
        yield runez.UNSET
        yield "bar"

    assert runez.joined() == ""
    assert runez.joined(None) == ""
    assert runez.joined(None, keep_empty=True) == "None"

    assert runez.joined("") == ""
    assert runez.joined("", "") == ""
    assert runez.joined("", "", keep_empty=None) == ""
    assert runez.joined("", "", keep_empty=True) == " "

    assert runez.joined(" a ", " b ", keep_empty=None) == " a   b "
    assert runez.joined(" a ", " b ", keep_empty=None, strip=True) == "a b"
    assert runez.joined(" a ", " b ", keep_empty=None, strip=" ") == "a b"
    assert runez.joined(" a ", " b ", keep_empty=None, strip="/") == " a   b "

    assert runez.joined("", runez.UNSET, None, "foo", 0, "", None) == "foo 0"
    assert runez.joined("", runez.UNSET, None, "foo", 0, "", None, keep_empty=None) == "foo"
    assert runez.joined("", runez.UNSET, None, "foo", 0, "", None, keep_empty=False) == "foo 0"
    assert runez.joined("", runez.UNSET, None, "foo", 0, "", None, keep_empty=True) == " None foo 0  None"
    assert runez.joined("", runez.UNSET, None, "foo", 0, "", None, keep_empty="") == "  foo 0  "
    assert runez.joined("", runez.UNSET, None, "foo", 0, "", None, keep_empty="null") == " null foo 0  null"

    assert runez.joined(1, gen(), "hello", [True, runez.UNSET, 5]) == "1 foo bar hello True 5"
    assert runez.joined(1, gen(), "hello", [True, runez.UNSET, 5], keep_empty=True) == "1 foo None bar hello True 5"
    assert runez.joined(1, 2, delimiter=",") == "1,2"
    assert runez.joined(1, 2, stringify=lambda _: "foo") == "foo foo"


def test_path_resolution(temp_folder):
    assert runez.resolved_path(None) is None
    assert runez.resolved_path("some-file") == os.path.join(temp_folder, "some-file")
    assert runez.resolved_path("some-file", base="bar") == os.path.join(temp_folder, "bar", "some-file")

    assert runez.quoted(["ls", os.path.join(temp_folder, "some-file") + " bar", "-a", " foo "]) == 'ls "some-file bar" -a " foo "'


def test_platform_identification():
    current = PlatformId()
    assert str(current)
    assert current.arch  # Will depend on where we're running this
    assert current.platform
    assert current.canonical_platform("linux2") == "linux"
    assert current.canonical_platform("win32") == "windows"
    assert current.canonical_platform("foo") == "foo"
    assert current.canonical_compress_extension("foo") is None
    assert current.canonical_compress_extension("foo.zip") is None
    assert current.canonical_compress_extension(".tar") == "tar"
    assert current.canonical_compress_extension(".zip") == "zip"
    assert current.canonical_compress_extension(".bz2") == "tar.bz2"
    assert current.canonical_compress_extension(".gz") == "tar.gz"
    assert current.canonical_compress_extension(".tar.bz2") == "tar.bz2"
    assert current.canonical_compress_extension(".tar.gz") == "tar.gz"
    assert current.canonical_compress_extension("tar.gz") == "tar.gz"
    assert current.canonical_compress_extension(".bz2", short_form=True) == "bz2"
    assert current.canonical_compress_extension("tar.bz2", short_form=True) == "bz2"
    assert current.canonical_compress_extension(".tar.gz", short_form=True) == "gz"
    assert current.canonical_compress_extension("tar.xz", short_form=True) == "xz"
    with pytest.raises(ValueError, match="Invalid compression extension"):
        current.composed_basename("foo", extension="bar.zip")

    linux_arm = PlatformId("linux-arm64")
    assert str(linux_arm) == "linux-arm64"
    assert linux_arm.canonical_compress_extension() == "tar.gz"

    assert linux_arm == PlatformId("linux-arm64-")
    assert linux_arm == PlatformId("linux-arm64", subsystem="")
    assert linux_arm == PlatformId(platform="linux", arch="arm64", subsystem="")

    linux_musl = PlatformId("linux-arm64-musl")
    assert str(linux_musl) == "linux-arm64-musl"
    assert linux_musl == PlatformId(platform="linux", arch="arm64", subsystem="musl")
    assert linux_musl.is_base_lib("linux-vdso.so.1")
    assert not linux_musl.is_base_lib("libc.so.6")
    assert linux_musl.is_system_lib("/lib/foo.so")
    assert linux_musl.is_system_lib("/usr/lib/foo.so")
    assert not linux_musl.is_system_lib("/System/Library/foo.so")
    assert linux_musl.composed_basename("foo", "1.2.3") == "foo-1.2.3-linux-arm64-musl.tar.gz"
    assert linux_musl.composed_basename("foo", "1.2.3", extension="bz2") == "foo-1.2.3-linux-arm64-musl.tar.bz2"
    assert linux_musl.composed_basename("foo", "1.2.3", extension=".bz2") == "foo-1.2.3-linux-arm64-musl.tar.bz2"
    assert linux_musl != linux_arm
    assert linux_arm < linux_musl  # Alphabetical order

    linux_arm_libc = PlatformId("linux-arm64-libc")
    assert str(linux_arm_libc) == "linux-arm64-libc"
    assert linux_arm_libc.is_base_lib("linux-vdso.so.1")
    assert linux_arm_libc.is_base_lib("libc.so.6")
    assert not linux_arm_libc.is_base_lib("@rpath/foo")

    m1 = PlatformId("macos-arm64")
    assert str(m1) == "macos-arm64"
    assert m1.canonical_compress_extension() == "tar.gz"
    assert not m1.is_base_lib("linux-vdso.so.1")
    assert not m1.is_base_lib("libc.so.6")
    assert m1.is_base_lib("@rpath/foo")
    assert m1.is_base_lib("/usr/lib/libSystem.B.dylib")
    assert not m1.is_system_lib("/lib/foo.so")
    assert m1.is_system_lib("/usr/lib/foo.so")
    assert m1.is_system_lib("/System/Library/foo.so")

    win = PlatformId("windows-x86_64")
    assert str(win) == "windows-x86_64"
    assert win.canonical_compress_extension() == "zip"
    assert win.is_windows
    assert win.composed_basename("cpython", "1.2.3") == "cpython-1.2.3-windows-x86_64.zip"
    assert win.composed_basename("foo", extension="gz") == "foo-windows-x86_64.tar.gz"
    assert win.composed_basename("foo", extension="tar.gz") == "foo-windows-x86_64.tar.gz"
    assert win.composed_basename("foo", extension="zip") == "foo-windows-x86_64.zip"


def test_quoted():
    assert runez.quoted(None) == "None"
    assert runez.quoted("") == ""
    assert runez.quoted(" ") == '" "'
    assert runez.quoted(" ", stringify=runez.short) == ""
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

    c = {"a \n b": [1, None, "foo \n ,", {"a2": runez.abort, "c": runez.Anchored}], None: datetime.date(2019, 1, 1)}
    assert runez.short(c) == "{None: 2019-01-01, a b: [1, None, foo ,, {a2: function 'abort', c: class runez.system.Anchored}]}"
    assert runez.short(c, size=32) == "{None: 2019-01-01, a b: [1, N..."

    assert runez.short(" some  text ", size=32) == "some text"
    assert runez.short(" some  text ", size=7) == "some..."
    assert runez.short(" some  text ", size=0) == "some text"

    # Verify that coloring is not randomly truncated
    assert runez.short("\033[38;2;255;0;0mfoo bar baz\033[39m", size=6, uncolor=True) == "foo..."

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
    assert runez.stringified(None, none=None) == "None"
    assert runez.stringified(None, none=False) == ""
    assert runez.stringified(None, none=True) == "None"
    assert runez.stringified(None, none=0) == "0"
    assert runez.stringified(None, none=1) == "1"
    assert runez.stringified(None, none="null") == "null"
    assert runez.stringified("", none="null") == ""
    assert runez.stringified(5) == "5"
    assert runez.stringified(b"foo") == "foo"
    assert runez.stringified([0, None, 1], none="null") == "[0, None, 1]"  # `none=` applies only to values (not items in lists etc...)
    assert runez.stringified([1, 2], converter=lambda _: None) == "[1, 2]"  # If converter returns None, we keep the value
    assert runez.stringified(5, converter=lambda x: x) == "5"  # No-op converter


def test_system():
    assert str(runez.system.PlatformInfo("")) == "unknown-os"
    assert str(runez.system.PlatformInfo("foo")) == "foo"
    assert str(runez.system.PlatformInfo("Darwin 20.5.0 x86_64 i386")) == "Darwin/20.5.0; x86_64 i386"
    assert str(runez.system.PlatformInfo("Linux 5.10.25 x86_64 x86_64")) == "Linux/5.10.25; x86_64"

    assert runez.DRYRUN is False
    with runez.OverrideDryrun(True) as prior1:
        assert runez.DRYRUN is True
        assert prior1 is False
        with runez.OverrideDryrun(False) as prior2:
            # Flip-flopping OK
            assert runez.DRYRUN is False
            assert prior2 is True

            with runez.OverrideDryrun(False) as prior3:
                # Overriding twice with the same value OK
                assert runez.DRYRUN is False
                assert prior3 is False

        assert runez.DRYRUN is True

    assert runez.DRYRUN is False

    ct = runez.DEV.current_test()
    assert ct
    assert not ct.is_main
    assert ct.function_name == "test_system"
    assert str(ct) == "tests.test_system.test_system"

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


def check_terminal_program_name(*names):
    for name in names:
        assert TerminalProgram.known_terminal(name) == name


def test_terminal(monkeypatch):
    assert TerminalProgram.known_terminal("termin") is None
    monkeypatch.delenv("COLUMNS", raising=False)
    monkeypatch.delenv("LINES", raising=False)
    check_terminal_program_name(
        "alacritty",
        "eterm",
        "gnome-terminal-server",
        "guake",
        "terminal",
        "terminator",
        "terminology",
        "Terminal.app",
        "tilix",
        "rxvt",
        "xfce4-terminal",
        "xterm",
        "yakuake",
    )
    if hasattr(os, "terminal_size"):
        t = TerminalInfo()
        assert not t.is_stdout_tty  # False when testing
        assert not t.is_stderr_tty
        assert t.get_size() == (160, 25)
        assert t.columns == 160
        assert t.lines == 25
        assert t.padded_columns() == 160
        assert t.padded_columns(padding=6) == 154
        assert t.padded_columns(padding=180, minimum=7) == 7
        with patch("runez.program.run", return_value=RunResult("12", code=0)):  # Simulate tput output
            assert t.get_columns() == 12
            assert t.get_lines() == 12

    with patch.dict(os.environ, {"LC_TERMINAL": "foo", "LC_TERMINAL_VERSION": "2", "TERM": "screen-256color"}):
        t = TerminalInfo()
        p = t.term_program
        assert str(p) == "foo v2 screen-256color"
        p.extra_info = None
        assert str(p) == "foo screen-256color"

    with patch.dict(os.environ, {"LC_TERMINAL": "", "TERM_PROGRAM": "", "TERM": ""}):
        # Simulate a known terminal
        ps = runez.PsInfo()
        ps.followed_parent.cmd = "/dev/null/tilix"
        ps.followed_parent.cmd_basename = "tilix"
        p = TerminalProgram(ps=ps)
        assert str(p) == "tilix /dev/null/tilix"
        assert str(p) == repr(p)  # Identical when coloring is off

    with patch.dict(os.environ, {"COLUMNS": "foo", "LINES": "bar", "PYCHARM_HOSTED": "true"}, clear=True):
        t = TerminalInfo()
        assert not t.is_stdout_tty  # Still false when testing
        assert t.columns == 160
        assert t.lines == 25

    with patch.dict(os.environ, {"COLUMNS": "10", "LINES": "15"}, clear=True):
        t = TerminalInfo()
        assert t.columns == 10
        assert t.lines == 15

    with patch.dict(os.environ, {"PYCHARM_HOSTED": "true"}, clear=True):
        with patch("runez.DEV.current_test", return_value=None):  # simulate not running in test
            t = TerminalInfo()
            assert t.is_stdout_tty  # Now True


def test_user_id(monkeypatch):
    monkeypatch.setenv("USER", "foo")
    s = SystemInfo()
    assert s.userid == "foo"


def test_wcswidth():
    assert runez.wcswidth(None) == 0
    assert runez.wcswidth("") == 0
    assert runez.wcswidth("foo") == 3
    assert runez.wcswidth("コンニチハ, セカイ!") == 19
    assert runez.wcswidth("abc\x00def") == 6
    assert runez.wcswidth("--\u05bf--") == 4
    assert runez.wcswidth("café") == 4
    assert runez.wcswidth("\u0410\u0488") == 1

    assert runez.wcswidth("😊") == 2
    assert runez.wcswidth("⚡") == 2
    assert runez.wcswidth("hello ⚡ world") == 14
    assert runez.wcswidth("\x1b[33mhello ⚡ world\x1b[39m") == 14  # ANSI coloring

    assert runez.wcswidth("hello world") == 11
    assert runez.wcswidth("\x1b[0m") == 0
    assert runez.wcswidth("\x1b[0mhello") == 5
