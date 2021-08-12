"""
This module holds less often used conveniences, it is not available via `import runez`

Functions from this module must be explicitly imported, for example:

>>> from runez.inspector import auto_import_siblings
"""

import os
import sys
import time
from functools import wraps

from runez.convert import to_int
from runez.program import run
from runez.system import abort, find_caller_frame, py_mimic, SYS_INFO


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


class AutoInstall:
    """
    Decorator to trigger just-in-time pip installation of a requirement (if/when needed), example usage:

        from runez.inspector import AutoInstall

        @AutoInstall("requests")
        def fetch(url):
            import requests
            ...
    """

    def __init__(self, top_level, package_name=None):
        """Decorator creation"""
        self.top_level = top_level
        self.package_name = package_name or top_level

    def ensure_installed(self):
        """Ensure that self.top_level is installed (install it if need be)"""
        try:
            __import__(self.top_level)

        except ImportError:
            if not SYS_INFO.venv_bin_folder:
                abort("Can't auto-install '%s' outside of a virtual environment" % self.package_name)

            r = run(sys.executable, "-mpip", "install", self.package_name, dryrun=False)
            if r.failed:
                abort("Can't auto-install '%s': %s" % (self.package_name, r.full_output))

    def __call__(self, target):
        """Decorator invoked with decorated function 'target'"""
        @wraps(target)
        def inner(*args, **kwargs):
            self.ensure_installed()
            return target(*args, **kwargs)

        py_mimic(target, inner)
        return inner


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
