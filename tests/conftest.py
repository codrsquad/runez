import os

import pytest

import runez
from runez.conftest import cli, isolated_log_setup, logged, temp_folder  # noqa


class TempLog:
    def __init__(self, folder, cap):
        self.folder = folder
        self.logged = cap

    @property
    def files(self):
        return os.listdir(self.folder)

    def absent(self, filename, *expected):
        remaining = set(expected)
        with open(filename, "rt") as fh:
            for line in fh:
                remaining.difference_update([msg for msg in remaining if msg in line])
        return remaining

    def __repr__(self):
        return "TempLog: '%s'" % self.logged

    def __str__(self):
        return self.folder

    def __contains__(self, item):
        return item in self.logged


@pytest.fixture
def temp_log():
    with runez.log.OriginalLogging():
        with runez.CaptureOutput() as cap:
            with runez.TempFolder(follow=True) as tmp:
                runez.log.Settings.folders = [os.path.join(tmp, "{basename}")]
                runez.log.Settings.dev = tmp
                runez.log.Settings.rotate = None
                runez.log.Settings.timezone = "UTC"
                yield TempLog(tmp, cap)
