import importlib.util
import os

import pytest

import runez
from runez.__main__ import main
from runez.conftest import cli, ClickRunner, IsolatedLogSetup, logged, temp_folder
from runez.http import GlobalHttpCalls
from runez.logsetup import LogManager
from runez.system import CaptureOutput, short

# Re-export fixtures so pytest discovers them, and ruff knows they're intentional
__all__ = ["cli", "logged", "temp_folder"]

# click is an optional dependency, its tests run only when it's installed (see tox env 'py314-no-click')
collect_ignore = [] if importlib.util.find_spec("click") else ["test_click.py"]

ClickRunner.default_main = main
GlobalHttpCalls.forbid()
runez.date.DEFAULT_TIMEZONE = runez.date.UTC
runez.serialize.set_default_behavior(strict=False, extras=True)


class TempLog:
    """Extra test-oriented convenience on top of runez.TrackedOutput"""

    def __init__(self, tracked):
        """
        Args:
            tracked (runez.TrackedOutput): Tracked output
        """
        self.folder = os.getcwd()
        self.tracked = tracked
        self.stdout = tracked.stdout
        self.stderr = tracked.stderr

    @property
    def logfile(self):
        return short(LogManager.file_handler.baseFilename) if LogManager.file_handler else None

    def pop(self):
        content = ""
        if self.stdout is not None:
            content += self.stdout.pop()

        if self.stderr is not None:
            content += "\n" + self.stderr.pop()

        return content.strip()

    def expect_logged(self, *expected):
        file_handler = LogManager.file_handler
        assert file_handler, "Logging to a file was not setup"
        remaining = set(expected)
        with open(file_handler.baseFilename) as fh:
            for line in fh:
                found = [msg for msg in remaining if msg in line]
                remaining.difference_update(found)

        assert not remaining

    def clear(self):
        self.tracked.clear()

    def __contains__(self, item):
        return item in self.tracked

    def __len__(self):
        return len(self.tracked)


@pytest.fixture
def temp_log():
    with IsolatedLogSetup(), CaptureOutput() as tracked:
        yield TempLog(tracked)


def exception_raiser(exc: BaseException | type[BaseException] = Exception):
    def _raise(*_, **__):
        raise exc

    return _raise
