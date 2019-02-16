import logging

import pytest

import runez
from runez.conftest import cli, isolated_log_setup, logged, temp_folder


# This is here only to satisfy flake8, mentioning the imported fixtures so they're not declared "unused"
assert all(s for s in [cli, isolated_log_setup, logged, temp_folder])


class TempLog:
    def __init__(self, folder, capture):
        """
        :param str folder: Temp folder
        :param runez.CaptureOutput capture: Log capture context manager
        """
        self.folder = folder
        self.logged = capture
        self.stdout = capture.stdout
        self.stderr = capture.stderr

    @runez.prop
    def logfile(self):
        if runez.log.file_handler:
            return runez.short(runez.log.file_handler.baseFilename)

    def expect_logged(self, *expected):
        assert self.logfile, "Logging to a file was not setup"
        remaining = set(expected)
        with open(self.logfile, "rt") as fh:
            for line in fh:
                found = [msg for msg in remaining if msg in line]
                remaining.difference_update(found)
        if remaining:
            logging.info("File contents:")
            logging.info("\n".join(runez.get_lines(self.logfile)))
        assert not remaining

    def __repr__(self):
        return str(self.logged)

    def __str__(self):
        return self.folder

    def __contains__(self, item):
        return item in self.logged

    def __len__(self):
        return len(self.logged)


@pytest.fixture
def temp_log():
    with runez.logging.OriginalLogging():
        with runez.TempFolder(follow=True) as tmp:
            with runez.CaptureOutput(log=False, anchors=tmp) as capture:
                assert not capture.log
                runez.LogSpec.basename = "pytest"
                runez.LogSpec.dev = tmp
                runez.LogSpec.rotate = None
                runez.LogSpec.timezone = "UTC"
                runez.LogSpec.console_format = "%(levelname)s %(message)s"
                yield TempLog(tmp, capture)
