import logging
import os

import pytest

from runez.conftest import cli, isolated_log_setup, IsolatedLogSetup, logged, temp_folder
from runez.context import CaptureOutput
from runez.convert import short
from runez.file import get_lines
from runez.logsetup import LogManager


LOG = logging.getLogger(__name__)

# This is here only to satisfy flake8, mentioning the imported fixtures so they're not declared "unused"
assert all(s for s in [cli, isolated_log_setup, logged, temp_folder])


class TempLog(object):
    def __init__(self, folder, tracked):
        """
        :param str folder: Temp folder
        :param runez.TrackedOutput tracked: Tracked output
        """
        self.folder = folder
        self.tracked = tracked
        self.stdout = tracked.stdout
        self.stderr = tracked.stderr

    @property
    def logfile(self):
        if LogManager.file_handler:
            return short(LogManager.file_handler.baseFilename)

    def expect_logged(self, *expected):
        assert self.logfile, "Logging to a file was not setup"
        remaining = set(expected)
        with open(LogManager.file_handler.baseFilename, "rt") as fh:
            for line in fh:
                found = [msg for msg in remaining if msg in line]
                remaining.difference_update(found)
        if remaining:
            LOG.info("File contents:")
            LOG.info("\n".join(get_lines(LogManager.file_handler.baseFilename)))
        assert not remaining

    def clear(self):
        self.tracked.clear()

    def __repr__(self):
        return str(self.tracked)

    def __str__(self):
        return self.folder

    def __contains__(self, item):
        return item in self.tracked

    def __len__(self):
        return len(self.tracked)


@pytest.fixture
def temp_log():
    with IsolatedLogSetup():
        with CaptureOutput() as tracked:
            yield TempLog(os.getcwd(), tracked)
