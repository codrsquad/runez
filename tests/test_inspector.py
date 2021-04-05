import os
import sys

import pytest

import runez
from runez.inspector import auto_import_siblings, ImportTime
from runez.system import _R


class MockFrame(object):
    f_globals = None


def mock_package(package, **kwargs):
    mf = MockFrame()
    mf.f_globals = {"__package__": package}
    for key, value in kwargs.items():
        mf.f_globals["__%s__" % key] = value

    return mf


def importable_test_py_files(folder):
    """Finds all .py files in tests/ folder, used for auto-import validation"""
    for fname in os.listdir(folder):
        fpath = os.path.join(folder, fname)
        if os.path.isdir(fpath):
            for x in importable_test_py_files(fpath):
                yield x

        elif fname.endswith(".py"):
            yield fpath


def test_auto_import_siblings(monkeypatch):
    # Check that none of these invocations raise an exception
    assert not _R.is_actual_caller_frame(mock_package(None))
    assert not _R.is_actual_caller_frame(mock_package(""))
    assert not _R.is_actual_caller_frame(mock_package("_pydevd"))
    assert not _R.is_actual_caller_frame(mock_package("_pytest.foo"))
    assert not _R.is_actual_caller_frame(mock_package("pluggy.hooks"))
    assert not _R.is_actual_caller_frame(mock_package("runez"))
    assert not _R.is_actual_caller_frame(mock_package("runez.system"))

    assert _R.is_actual_caller_frame(mock_package("foo"))
    assert _R.is_actual_caller_frame(mock_package("runez.system", name="__main__"))

    with pytest.raises(ImportError):
        with monkeypatch.context() as m:
            m.setattr(runez.inspector, "find_caller_frame", lambda *_, **__: None)
            auto_import_siblings()

    with pytest.raises(ImportError):
        with monkeypatch.context() as m:
            m.setattr(runez.inspector, "find_caller_frame", lambda *_, **__: mock_package("foo", name="__main__"))
            auto_import_siblings()

    with pytest.raises(ImportError):
        with monkeypatch.context() as m:
            m.setattr(runez.inspector, "find_caller_frame", lambda *_, **__: mock_package(None))
            auto_import_siblings()

    with pytest.raises(ImportError):
        with monkeypatch.context() as m:
            m.setattr(runez.inspector, "find_caller_frame", lambda *_, **__: mock_package("foo"))
            auto_import_siblings()

    with pytest.raises(ImportError):
        with monkeypatch.context() as m:
            m.setattr(runez.inspector, "find_caller_frame", lambda *_, **__: mock_package("foo", file="/dev/null/foo"))
            auto_import_siblings()

    py_file_count = len(list(importable_test_py_files(runez.log.tests_path()))) - 1  # Remove one to not count tests/__init__.py itself
    imported = auto_import_siblings(package="tests")
    assert len(imported) == py_file_count

    imported = auto_import_siblings(skip=["tests.secondary"])
    assert len(imported) == py_file_count - 2
    assert "tests.conftest" in imported
    assert "tests.secondary" not in imported
    assert "tests.secondary.test_import" not in imported
    assert "tests.test_system" in imported

    monkeypatch.setenv("TOX_WORK_DIR", "some-value")
    imported = auto_import_siblings(skip=["tests.test_system", "tests.test_serialize"])
    assert len(imported) == py_file_count - 2

    assert "tests.conftest" in imported
    assert "tests.secondary" in imported
    assert "tests.secondary.test_import" in imported
    assert "tests.test_system" not in imported
    assert "tests.test_click" in imported
    assert "tests.test_serialize" not in imported


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
