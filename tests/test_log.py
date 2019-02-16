import logging

import pytest

import runez


def test_settings(isolated_log_setup):
    assert runez.log.Settings.basename == "pytest"

    assert runez.log.Settings.formatted("") == ""
    assert runez.log.Settings.formatted("{foo}") is None
    assert runez.log.Settings.formatted("{filename}") == "pytest.log"

    assert runez.log.Settings.find_dev("") is None
    assert runez.log.Settings.find_dev("foo/.venv/bar/baz") == "foo/.venv"

    fmt = "%(asctime)s %(context)s%(levelname)s - %(message)s"
    assert runez.log.is_using_format("", fmt) is False
    assert runez.log.is_using_format("%(lineno)d", fmt) is False
    assert runez.log.is_using_format("%(context)s", fmt) is True
    assert runez.log.is_using_format("%(context)s %(lineno)d", fmt) is True
    assert runez.log.is_using_format("%(context)s", "") is False

    with runez.TempFolder():
        runez.touch("some-file")
        assert runez.log.Settings.usable_location("") is None
        assert runez.log.Settings.usable_location("./foo.log") == "./foo.log"
        assert runez.log.Settings.usable_location("./foo/bar.log") == "./foo/bar.log"
        assert runez.log.Settings.usable_location("./too/many/subfolders.log") is None
        assert runez.log.Settings.usable_location("./some-file/bar.log") is None
        assert runez.log.Settings.usable_location("./some-file/foo/bar.log") is None

        assert runez.log.Settings.usable_location("foo.log") == "foo.log"
        assert runez.log.Settings.usable_location("foo/bar.log") == "foo/bar.log"

    with pytest.raises(Exception):
        runez.log.setup()
        runez.log.setup()


def test_console(temp_log):
    runez.log.setup(location="")
    assert temp_log.logfile is None
    logging.info("hello")
    assert "INFO hello" in temp_log.stderr


def test_default(temp_log):
    runez.log.set_global_context(version="1.0")
    runez.log.add_global_context(worker="mark")
    runez.log.add_thread_context(worker="joe", foo="bar")
    runez.log.set_thread_context(worker="joe")
    runez.log.setup()

    assert temp_log.logfile == "pytest.log"
    logging.info("hello")

    temp_log.expect_logged("UTC [MainThread] [[version=1.0,worker=joe]] INFO - hello")
    assert "INFO hello" in temp_log.stderr


def test_no_context(temp_log):
    runez.log.set_global_context(version="1.0")
    runez.log.Settings.file_format = "%(asctime)s %(timezone)s [%(threadName)s] %(levelname)s - %(message)s"
    runez.log.setup()
    logging.info("hello")
    temp_log.expect_logged("UTC [MainThread] INFO - hello")
