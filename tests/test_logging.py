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
        assert "foo" in logged

    with runez.CaptureOutput() as logged:
        runez.warning("foo")
        assert "WARNING: foo" in logged

    runez.State.logging = False
