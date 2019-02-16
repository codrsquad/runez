import logging
import sys

import runez


def test_capture():
    """Exercise edge cases around capture"""
    c1 = runez.CaptureOutput()
    c2 = runez.CaptureOutput()
    c3 = runez.CaptureOutput(stderr=False)

    assert c1 == c2
    assert c1 != c3

    assert c1.stdout is not None
    assert c1.stderr is not None
    assert c1.log is not None

    assert c3.stdout is not None
    assert c3.stderr is None
    assert c3.log is not None

    assert c1 == "stdout: stderr: log: "
    assert c3 == "stdout: log: "


def test_scope():
    # With pytest present, we capture all 3
    assert str(runez.CaptureOutput()) == "stdout: stderr: log: "

    # If pytest isn't there, we capture stdout/stderr only by default
    original = runez.context.CapturedStream._shared
    runez.context.CapturedStream._shared = None
    assert str(runez.CaptureOutput()) == "stdout: stderr: "
    runez.context.CapturedStream._shared = original

    with runez.CaptureOutput() as logged:
        # Verify all channels are captured
        logging.debug("foo")
        assert "DEBUG    foo" in logged.pop()

        logging.info("foo")
        assert "INFO     foo" in logged.pop()

        logging.warning("foo")
        assert "WARNING  foo" in logged.pop()

        print("on stdout")
        sys.stderr.write("on stderr")
        assert "on stdout\non stderr" in logged.pop()

    with runez.CaptureOutput(stderr=False) as logged:
        # Verify that when stderr is off, it is not captured
        print("on stdout")
        sys.stderr.write("on stderr")

        assert "on stdout\n" in logged
        assert "on stderr" not in logged
