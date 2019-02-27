import logging

import pytest

import runez
from runez.conftest import cli, isolated_log_setup, IsolatedLogSetup, logged, temp_folder


LOG = logging.getLogger(__name__)

# This is here only to satisfy flake8, mentioning the imported fixtures so they're not declared "unused"
assert all(s for s in [cli, isolated_log_setup, logged, temp_folder])


class TempLog(object):
    def __init__(self, folder, capture):
        """
        :param str folder: Temp folder
        :param runez.CaptureOutput capture: Log capture context manager
        """
        self.folder = folder
        self._capture = capture
        self.log = capture.log
        self.stdout = capture.stdout
        self.stderr = capture.stderr

    @property
    def logfile(self):
        if runez.log.file_handler:
            return runez.short(runez.log.file_handler.baseFilename)

    def expect_logged(self, *expected):
        assert self.logfile, "Logging to a file was not setup"
        remaining = set(expected)
        with open(runez.log.file_handler.baseFilename, "rt") as fh:
            for line in fh:
                found = [msg for msg in remaining if msg in line]
                remaining.difference_update(found)
        if remaining:
            LOG.info("File contents:")
            LOG.info("\n".join(runez.get_lines(runez.log.file_handler.baseFilename)))
        assert not remaining

    def clear(self):
        self._capture.clear()

    def __repr__(self):
        return str(self._capture)

    def __str__(self):
        return self.folder

    def __contains__(self, item):
        return item in self._capture

    def __len__(self):
        return len(self._capture)


@pytest.fixture
def temp_log():
    with runez.TempFolder(follow=True) as tmp:
        with IsolatedLogSetup() as isolated:
            with runez.CaptureOutput(anchors=tmp) as capture:
                assert not capture.log
                isolated.spec.tmp = tmp
                isolated.spec.console_format = "%(levelname)s %(message)s"
                yield TempLog(tmp, capture)
