"""
This module holds less often used conveniences, it is not available via `import runez`

Functions from this module must be explicitly imported, for example:

>>> from runez.inspector import auto_import_siblings
"""

import argparse
import os
import sys
import time

from runez.convert import to_int
from runez.logsetup import LogManager
from runez.program import run
from runez.render import PrettyTable
from runez.system import abort, find_caller_frame, first_line, TempArgv


def auto_import_siblings(package=None, auto_clean="TOX_WORK_DIR", skip=None):
    """Auto-import all sibling submodules from caller.

    This is handy for click command groups for example.
    It allows to avoid having to have a module that simply lists all sub-commands, just to ensure they are added to `main`.

    - ./my_cli.py::

        @click.group()
        def main(...):
            ...

        runez.auto_import_siblings()

    - ./my_sub_command.py::

        from .my_cli import main

        @main.command()  # The auto-import will trigger importing this without further ado
        def foo(...):
            ...

    Args:
        package (str | None): Name of package to import (default: caller's package)
        auto_clean (str | bool | None): If provided, auto-clean `.pyc`` files
        skip (list | None): Do not auto-import specified modules

    Returns:
        (list): List of imported modules, if any
    """
    if package:
        given = __import__(package)
        folder = getattr(given, "__file__", None)
        if folder:
            folder = os.path.dirname(os.path.abspath(folder))

    else:
        caller = find_caller_frame()
        if not caller:
            raise ImportError("Could not determine caller, can't auto-import")

        if caller.f_globals.get("__name__") == "__main__":
            raise ImportError("Calling auto_import_siblings() from __main__ is not supported: %s" % caller)

        package = caller.f_globals.get("__package__")
        if not package:
            raise ImportError("Could not determine caller's __package__, can't auto-import: %s" % caller)

        caller_path = caller.f_globals.get("__file__")
        if not caller_path:
            raise ImportError("Could not determine caller's __file__, can't auto-import: %s" % caller)

        folder = os.path.dirname(caller_path)

    if not folder or not os.path.isdir(folder):
        raise ImportError("%s.__file__ points to a non-existing directory, can't auto-import: %s" % (package, folder))

    if auto_clean is not None and not isinstance(auto_clean, bool):
        auto_clean = os.environ.get(auto_clean)

    if auto_clean:
        # Clean .pyc files so consecutive tox runs with distinct python2 versions don't get confused
        _clean_files(folder, ".pyc")

    import pkgutil

    imported = []
    for loader, module_name, _ in pkgutil.walk_packages([folder], prefix="%s." % package):
        if _should_auto_import(module_name, skip):
            __import__(module_name)
            imported.append(module_name)

    return imported


def auto_install(top_level, package_name=None):
    """
    Args:
        top_level (str): Name of top-level import that should be importable
        package_name (str | None): Name of pypi package to install (defaults to `top_level`)
    """
    package_name = package_name or top_level
    base_prefix = getattr(sys, "real_prefix", None) or getattr(sys, "base_prefix", sys.prefix)
    if sys.prefix == base_prefix:
        return abort("Can't auto-install '%s' outside of a virtual environments" % package_name)

    try:
        return __import__(top_level)

    except ImportError:
        r = run(sys.executable, "-mpip", "install", package_name, dryrun=False)
        if r.failed:
            return abort("Can't auto-install '%s': %s" % (package_name, r.full_output))

        return __import__(top_level)


def run_cmds(prog=None):
    """Handy way of running multi-commands with argparse

    If you don't have click, but would like to still have a quick multi-command entry point, you can use this.
    How it works:
    - Caller is automatically determined (from call stack), so no need to pass anything
    - All functions named `cmd_...` from caller are considered commands, and are invocable by name
    - All CLI args after command name are simply passed-through (command name removed)
    - Those functions should take no argument and should use `argparse` or equivalent as they would normally

    Example usage:
        from runez.inspector import run_cmds

        def cmd_foo():
            print("foo")

        def cmd_bar():
            print("bar")

        if __name__ == "__main__":
            run_cmds()

    Args:
        prog (str | None): The name of the program (default: sys.argv[0])
    """
    caller = find_caller_frame()
    f_globals = caller.f_globals
    available_commands = {}
    for name, func in f_globals.items():
        if len(name) > 4 and name.startswith("cmd_"):
            name = name[4:].replace("_", "-")
            available_commands[name] = func

    if not prog and f_globals.get("__name__") == "__main__":
        package = f_globals.get("__package__")
        if package:
            prog = "python -m%s" % package

    epilog = PrettyTable(2)
    epilog.header[0].style = "bold"
    for cmd, func in available_commands.items():
        epilog.add_row(" " + cmd, first_line(func.__doc__, default=""))

    epilog = "Available commands:\n%s" % epilog
    # noinspection PyTypeChecker
    parser = argparse.ArgumentParser(
        prog=prog,
        description=first_line(f_globals.get("__doc__"), default=""),
        epilog=epilog,
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("--debug", action="store_true", help="Show debug info.")
    parser.add_argument("command", choices=available_commands, metavar="command", help="Command to run.")
    parser.add_argument("args", nargs=argparse.REMAINDER, help="Passed-through to command")
    args = parser.parse_args()
    LogManager.setup(debug=args.debug)

    try:
        func = available_commands[args.command]
        with TempArgv(args.args):
            func()

    except KeyboardInterrupt:  # pragma: no cover
        sys.stderr.write("\nAborted\n")
        sys.exit(1)


class ImportTime:
    """Measure average import time of a given top-level package, works with 3.7+ only"""

    def __init__(self, module_name, iterations=3):
        self.module_name = module_name
        self.elapsed = None
        self.cumulative = None
        self.problem = None
        v = sys.version_info[:2]
        if v < (3, 7):
            v = "%s.%s" % (v[0], v[1])
            self.problem = "-Ximporttime is not available in python %s, can't measure import-time speed" % v
            return

        cumulative = 0
        started = time.time()
        for _ in range(iterations):
            c = self._get_importtime()
            if not c:
                return

            cumulative += c

        self.elapsed = (time.time() - started) / iterations
        self.cumulative = cumulative / iterations

    def __repr__(self):
        return "%s %.3g" % (self.module_name, self.elapsed or 0)

    def __lt__(self, other):
        if isinstance(other, ImportTime) and self.cumulative and other.cumulative:
            return self.cumulative < other.cumulative

    def _get_importtime(self):
        result = run(sys.executable, "-Ximporttime", "-c", "import %s" % self.module_name, fatal=None)
        if result.failed:
            lines = result.error.splitlines()
            self.problem = lines[-1] if lines else "-Ximporttime failed"
            return None

        cumulative = 0
        for line in result.error.splitlines():  # python -Ximporttime outputs to stderr
            c = to_int(line.split("|")[1])
            if c:
                cumulative = max(cumulative, c)

        return cumulative


def _clean_files(folder, extension):
    """Clean all files with `extension` from `folder`"""
    for root, dirs, files in os.walk(folder):
        for fname in files:
            if fname.endswith(extension):  # pragma: no cover, only applicable for local development
                try:
                    os.unlink(os.path.join(root, fname))

                except (OSError, IOError):
                    pass  # Delete is only needed in tox run, no need to fail if delete is not possible


def _should_auto_import(module_name, skip):
    """
    Args:
        module_name (str): Module being auto-imported
        skip (list | None): Modules to NOT auto-import

    Returns:
        (bool): True if we should auto-import `module_name`
    """
    if not module_name.endswith("_"):
        if skip and any(module_name.startswith(x) for x in skip):
            return False

        return True
