import os
import sys

import pytest

import runez
from runez.inspector import auto_import_siblings


def importable_test_py_files(folder):
    """Finds all .py files in tests/ folder, used for auto-import validation"""
    for fname in os.listdir(folder):
        fpath = os.path.join(folder, fname)
        if os.path.isdir(fpath):
            for x in importable_test_py_files(fpath):
                yield x

        elif fname.endswith(".py"):
            yield fpath


def test_auto_import_siblings():
    # Check that none of these invocations raise an exception
    assert runez.system.find_caller(depth=100) is None
    caller = runez.system.find_caller(depth=1)  # Finds this test as caller
    assert str(caller) == "tests.test_inspector.test_auto_import_siblings"

    # Pretend we're calling auto_import_siblings() from a __main__
    caller.module_name = "__main__"
    assert caller.is_main
    with pytest.raises(ImportError):
        auto_import_siblings(caller=caller)

    # Pretend caller doesn't have a __package__
    caller.package_name = None
    caller.module_name = "foo"
    assert not caller.is_main
    with pytest.raises(ImportError):
        auto_import_siblings(caller=caller)

    py_file_count = len(list(importable_test_py_files(runez.DEV.tests_folder))) - 1  # Remove one to not count tests/__init__.py itself
    imported = auto_import_siblings()
    assert len(imported) == py_file_count

    imported = auto_import_siblings(skip=["tests.secondary"])
    assert len(imported) == py_file_count - 2
    assert "tests.conftest" in imported
    assert "tests.secondary" not in imported
    assert "tests.secondary.test_import" not in imported
    assert "tests.test_system" in imported

    imported = auto_import_siblings(skip=["tests.test_system", "tests.test_serialize"])
    assert len(imported) == py_file_count - 2

    assert "tests.conftest" in imported
    assert "tests.secondary" in imported
    assert "tests.secondary.test_import" in imported
    assert "tests.test_system" not in imported
    assert "tests.test_click" in imported
    assert "tests.test_serialize" not in imported


def test_diagnostics_command(cli):
    cli.run("--no-color", "diagnostics")
    assert cli.succeeded
    assert "platform : " in cli.logged
    assert "sys.executable : %s" % runez.short(sys.executable) in cli.logged


def test_passthrough(cli):
    cli.run("passthrough")
    assert cli.failed
    assert "Provide command to run" in cli.logged

    cli.run("passthrough", "echo", "hello")
    assert cli.succeeded
    assert "stdout:\nhello" in cli.logged
