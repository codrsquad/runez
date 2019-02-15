import sys

import runez


def test_captured_stream():
    """Exercise edge cases around stream hijacks"""
    stdout = runez.context.CapturedStream(sys.stdout)
    stderr = runez.context.CapturedStream(sys.stderr)
    log = runez.context.CapturedStream(None)
    buffer = runez.context.CapturedStream(runez.context.StringIO())

    assert stdout.name == "stdout"
    assert stderr.name == "stderr"
    assert log.name == "log"
    assert "StringIO" in buffer.name


def test_capture():
    """Exercise edge cases around capture"""
    c1 = runez.CaptureOutput(streams=[])
    c2 = runez.CaptureOutput(streams=[])

    assert c1 == c2
    assert c1 == ""


def test_scope():
    with runez.CaptureOutput() as logged:
        assert len(logged.captured) == 3

    original = runez.context.CapturedStream._shared
    runez.context.CapturedStream._shared = None
    with runez.CaptureOutput() as logged:
        assert len(logged.captured) == 2
    runez.context.CapturedStream._shared = original
