import io
import sys

import runez


def test_captured_stream():
    """Exercise edge cases around stream hijacks"""
    stdout = runez.context.CapturedStream(sys.stdout)
    stderr = runez.context.CapturedStream(sys.stderr)
    buffer = runez.context.CapturedStream(io.StringIO())
    bogus = runez.context.CapturedStream(None)
    foo = runez.context.CapturedStream(None, name="foo")

    assert str(stdout) == "stdout: "
    assert str(stderr) == "stderr: "
    assert "StringIO" in str(buffer)
    assert str(bogus) == "None: "
    assert str(foo) == "foo: "


def test_capture():
    """Exercise edge cases around capture"""
    c1 = runez.context.CaptureOutput(streams=None, handlers=None)
    c2 = runez.context.CaptureOutput(streams=None, handlers=None)

    assert c1 == c2
    assert c1 == ""
