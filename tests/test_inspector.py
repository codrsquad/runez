import os

import pytest
from mock import MagicMock, patch

from runez.inspector import auto_import_siblings
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
        assert len(imported) == 22

        assert "tests.conftest" in imported
        assert "tests.secondary" in imported
        assert "tests.secondary.test_import" in imported
        assert "tests.test_system" not in imported
        assert "tests.test_click" in imported
        assert "tests.test_serialize" not in imported

    imported = auto_import_siblings(skip=["tests.secondary"])
    assert len(imported) == 22
    assert "tests.conftest" in imported
    assert "tests.secondary" not in imported
    assert "tests.secondary.test_import" not in imported
    assert "tests.test_system" in imported
