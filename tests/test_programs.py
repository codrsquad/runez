import runez


def test_executable(temp_base):
    with runez.CaptureOutput(dryrun=True) as logged:
        assert runez.make_executable("foo") == 1
        assert "Would make foo executable" in logged

    assert runez.touch("foo") == 1
    assert runez.make_executable("foo") == 1
    assert runez.is_executable("foo")
    assert runez.make_executable("foo") == 0

    assert runez.delete_file("foo") == 1
    assert not runez.is_executable("foo")

    with runez.CaptureOutput() as logged:
        assert runez.make_executable("/dev/null/foo", fatal=False) == -1
        assert "does not exist, can't make it executable" in logged


def test_which():
    assert runez.which(None) is None
    assert runez.which("/dev/null") is None
    assert runez.which("dev/null") is None
    assert runez.which("ls")


def test_pids():
    assert runez.check_pid(0)
    assert not runez.check_pid(1)
