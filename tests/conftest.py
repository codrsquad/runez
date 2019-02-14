import os

import pytest

import runez


TESTS = runez.parent_folder(__file__)
PROJECT = runez.parent_folder(TESTS)
INEXISTING_FILE = "/dev/null/foo/bar"

runez.State.testing = True


class SnapshotSettings:
    """
    Context manager for changing the current working directory
    """

    def __init__(self, folder=None):
        self.folder = folder
        self.snap = None

    def __enter__(self):
        self.snap = runez.log.Settings.snapshot()
        if self.folder:
            runez.log.Settings.program_path = "/some/test.py"
            runez.log.Settings.folders = [os.path.join(self.folder, "{basename}")]
            runez.log.Settings.dev = self.folder
            runez.log.Settings.rotate = None
            runez.log.Settings.timezone = "UTC"

    def __exit__(self, *_):
        runez.log.SETUP.restore(self.snap)


class TempLog:
    def __init__(self, folder, logged):
        self.folder = folder
        self.logged = logged

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
def temp_base():
    with runez.TempFolder() as path:
        yield path


@pytest.fixture
def temp_settings():
    with SnapshotSettings() as snap:
        yield snap


@pytest.fixture
def temp_log():
    with runez.CaptureOutput() as logged:
        with runez.TempFolder(follow=True) as tmp:
            with SnapshotSettings(folder=tmp):
                yield TempLog(tmp, logged)
