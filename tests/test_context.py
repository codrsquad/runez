import logging
import sys

import runez


def test_capture():
    """Exercise edge cases around capture"""
    c1 = runez.CaptureOutput()
    c2 = runez.CaptureOutput()
    c3 = runez.CaptureOutput(stderr=False)

    assert c1 == c2
    assert c1.stdout == ""

    assert c1 != c3
    assert c1 != "hello"

    assert c1.stdout is not None
    assert c1.stderr is not None
    assert c1.log is not None

    assert c3.stdout is not None
    assert c3.stderr is None
    assert c3.log is not None

    assert c1 == "stdout: \nstderr: \nlog: \n"
    assert c3 == "stdout: \nlog: \n"

    c1d = c1.duplicate()
    assert c1d.stdout.name == "stdout*"
    assert c1d != c1


def test_scope():
    # With pytest present, we capture all 3
    assert len(runez.CaptureOutput().captured) == 3

    # If pytest isn't there, we capture stdout/stderr only by default
    original = runez.context.CapturedStream._shared
    runez.context.CapturedStream._shared = None
    assert len(runez.CaptureOutput().captured) == 2
    runez.context.CapturedStream._shared = original

    with runez.CaptureOutput() as logged:
        # Verify all channels are captured
        logging.debug("hello")
        assert "DEBUG    hello" in logged.pop()

        logging.info("hello")
        assert "INFO     hello" in logged.pop()

        logging.warning("hello")
        assert "WARNING  hello" in logged.pop()

        print("on stdout")
        sys.stderr.write("on stderr")
        assert "on stdout\non stderr" in logged.pop()

    with runez.CaptureOutput(stderr=False) as logged:
        # Verify that when stderr is off, it is not captured
        print("on stdout")
        sys.stderr.write("on stderr")

        assert "on stdout\n" in logged
        assert "on stderr" not in logged
