import os
import sys
from unittest.mock import MagicMock, patch

import pytest

import runez
from runez.inspector import auto_import_siblings, AutoInstall, ImportTime


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


class SomeClass:
    @AutoInstall("bar")
    def needs_bar(self, msg):
        return "OK: %s" % msg


@AutoInstall("foo")
def needs_foo(msg):
    import foo  # noqa: F401

    return "OK: %s" % msg


def test_auto_install(logged, monkeypatch):
    # Verify that an already present req is a no-op
    AutoInstall("runez").ensure_installed()
    assert not logged

    # Verify failure to install raises abort exception
    with patch("runez.inspector.run", return_value=runez.program.RunResult("failed")):
        with pytest.raises(runez.system.AbortException):
            needs_foo("hello")
        assert "Can't auto-install 'foo': failed" in logged.pop()

    # Verify successful install exercises function call
    with patch("runez.inspector.run", return_value=runez.program.RunResult("OK", code=0)):
        with pytest.raises(ImportError):  # 2nd import attempt raises ImportError (in this case, because we're trying a mocked 'foo')
            needs_foo("hello")
        assert not logged

    # Full successful call
    with patch("runez.inspector.run", return_value=runez.program.RunResult("OK", code=0)):
        assert SomeClass().needs_bar("hello") == "OK: hello"
        assert not logged

    # Mocked successful import
    with patch.dict("sys.modules", foo=MagicMock()):
        with patch("runez.inspector.run", return_value=runez.program.RunResult("OK", code=0)):
            assert needs_foo("hello") == "OK: hello"
            assert not logged

    # Ensure auto-installation is refused unless we have a venv
    monkeypatch.setattr(runez.SYS_INFO, "venv_bin_folder", None)
    with pytest.raises(runez.system.AbortException):
        needs_foo("hello")
    assert "Can't auto-install 'foo' outside of a virtual environment" in logged.pop()


def test_diagnostics_command(cli):
    cli.run("--no-color", "diagnostics")
    assert cli.succeeded
    assert "platform : " in cli.logged
    assert "sys.executable : %s" % runez.short(sys.executable) in cli.logged


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

    cli.run("import-speed -i1 --all runez foo_no_such_module runez")
    assert cli.succeeded
    lines = cli.logged.stdout.contents().splitlines()
    assert len([s for s in lines if "runez" in s]) == 1
    assert len([s for s in lines if "foo_no_such_module" in s]) == 1


def test_passthrough(cli):
    cli.run("passthrough")
    assert cli.failed
    assert "Provide command to run" in cli.logged

    cli.run("passthrough", "echo", "hello")
    assert cli.succeeded
    assert "stdout:\nhello" in cli.logged
