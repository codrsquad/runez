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

    assert stdout.name == "stdout"
    assert stderr.name == "stderr"
    assert "StringIO" in buffer.name
    assert bogus.name is None
    assert foo.name == "foo"


def test_capture():
    """Exercise edge cases around capture"""
    c1 = runez.context.CaptureOutput(streams=None, handlers=None)
    c2 = runez.context.CaptureOutput(streams=None, handlers=None)

    assert c1 == c2
    assert c1 == ""
