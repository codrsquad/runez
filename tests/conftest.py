import os
import shutil
from tempfile import mkdtemp

import pytest

import runez


TESTS = runez.parent_folder(__file__)
PROJECT = runez.parent_folder(TESTS)
INEXISTING_FILE = "/dev/null/foo/bar"

runez.State.testing = True


@pytest.fixture
def temp_base():
    old_cwd = os.getcwd()
    path = mkdtemp()

    try:
        os.chdir(path)
        # Yielding abspath(".") to properly resolve for example symlinks on OSX temp paths
        yield os.path.abspath(".")

    finally:
        os.chdir(old_cwd)
        shutil.rmtree(path)
