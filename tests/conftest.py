import pytest

import runez


TESTS = runez.parent_folder(__file__)
PROJECT = runez.parent_folder(TESTS)
INEXISTING_FILE = "/dev/null/foo/bar"

runez.State.testing = True


@pytest.fixture
def temp_base():
    with runez.TempFolder() as path:
        yield path
