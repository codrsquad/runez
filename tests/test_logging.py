import sys

import runez


def test_abort():
    runez.State.logging = True

    with runez.CaptureOutput() as logged:
        assert runez.abort("aborted", fatal=False, return_value="foo") == "foo"
        assert "ERROR: aborted" in logged

    with runez.CaptureOutput() as logged:
        assert runez.abort("aborted", fatal=False, code=0, return_value="foo") == "foo"
        assert "aborted" in logged
        assert "ERROR:" not in logged

    with runez.CaptureOutput() as logged:
        assert runez.abort("aborted", fatal=False, quiet=True, return_value="foo") == "foo"
        assert not logged


def test_logging():
    runez.State.logging = True

    with runez.CaptureOutput() as logged:
        runez.debug("foo")
        assert "foo\n" == logged.pop()

        runez.info("foo")
        assert "foo\n" == logged.pop()

        runez.warning("foo")
        assert "WARNING: foo" in logged.pop()

        print("on stdout")
        sys.stderr.write("on stderr")
        assert "on stdout\non stderr" in logged.pop()

    with runez.CaptureOutput(stderr=False) as logged:
        print("on stdout")
        sys.stderr.write("on stderr")

        assert "on stdout\n" in logged.pop()

    runez.State.logging = False
