import os
import shutil
from tempfile import mkdtemp

import pytest

import runez


TESTS = runez.parent(__file__)
PROJECT = runez.parent(TESTS)
INEXISTING_FILE = "/dev/null/foo/bar"

runez.State.testing = True


@pytest.fixture
def temp_base():
    old_cwd = os.getcwd()
    # Yielding realpath() to properly resolve for example symlinks on OSX temp paths
    path = os.path.realpath(mkdtemp())

    try:
        os.chdir(path)
        with runez.Anchored(path):
            yield path

    finally:
        os.chdir(old_cwd)
        shutil.rmtree(path)
