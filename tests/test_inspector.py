import os
import sys

import pytest
from mock import MagicMock, patch

from runez.inspector import auto_import_siblings, ImportTime
from runez.system import _is_actual_caller_frame


def mock_package(package, **kwargs):
    globs = {"__package__": package}
    for key, value in kwargs.items():
        globs["__%s__" % key] = value

    return MagicMock(f_globals=globs)


def test_auto_import_siblings():
    # Check that none of these invocations raise an exception
    assert not _is_actual_caller_frame(mock_package(None))
    assert not _is_actual_caller_frame(mock_package(""))
    assert not _is_actual_caller_frame(mock_package("_pydevd"))
    assert not _is_actual_caller_frame(mock_package("_pytest.foo"))
    assert not _is_actual_caller_frame(mock_package("pluggy.hooks"))
    assert not _is_actual_caller_frame(mock_package("runez"))
    assert not _is_actual_caller_frame(mock_package("runez.system"))

    assert _is_actual_caller_frame(mock_package("foo"))
    assert _is_actual_caller_frame(mock_package("runez.system", name="__main__"))

    with pytest.raises(ImportError):
        with patch("runez.inspector.find_caller_frame", return_value=None):
            auto_import_siblings()

    with pytest.raises(ImportError):
        with patch("runez.inspector.find_caller_frame", return_value=mock_package("foo", name="__main__")):
            auto_import_siblings()

    with pytest.raises(ImportError):
        with patch("runez.inspector.find_caller_frame", return_value=mock_package(None)):
            auto_import_siblings()

    with pytest.raises(ImportError):
        with patch("runez.inspector.find_caller_frame", return_value=mock_package("foo")):
            auto_import_siblings()

    with pytest.raises(ImportError):
        with patch("runez.inspector.find_caller_frame", return_value=mock_package("foo", file="/dev/null/foo")):
            auto_import_siblings()

    with patch.dict(os.environ, {"TOX_WORK_DIR": "some-value"}, clear=True):
        imported = auto_import_siblings(skip=["tests.test_system", "tests.test_serialize"])
        assert len(imported) == 21

        assert "tests.conftest" in imported
        assert "tests.secondary" in imported
        assert "tests.secondary.test_import" in imported
        assert "tests.test_system" not in imported
        assert "tests.test_click" in imported
        assert "tests.test_serialize" not in imported

    imported = auto_import_siblings(skip=["tests.secondary"])
    assert len(imported) == 21
    assert "tests.conftest" in imported
    assert "tests.secondary" not in imported
    assert "tests.secondary.test_import" not in imported
    assert "tests.test_system" in imported


@pytest.mark.skipif(sys.version_info[:2] < (3, 7), reason="Available in 3.7+")
def test_importtime():
    """Verify that importing runez remains fast"""
    tos = ImportTime("os")
    tsys = ImportTime("sys")
    trunez = ImportTime("runez")
    assert "runez" in str(trunez)

    assert trunez.cumulative < 3 * tos.cumulative
    assert trunez.cumulative < 3 * tsys.cumulative

    assert trunez.elapsed < 3 * tos.elapsed
    assert trunez.elapsed < 3 * tsys.elapsed


def test_importtime_command(cli):
    cli.run("import-speed")
    assert cli.failed
    assert "Please specify module names, or use --all" in cli.logged

    cli.run("import-speed -i1 --all six wheel runez foo_no_such_module runez pkg_resources")
    assert cli.succeeded
    lines = cli.logged.stdout.contents().splitlines()
    assert len([s for s in lines if "runez" in s]) == 1
    assert len([s for s in lines if "foo_no_such_module" in s]) == 1
