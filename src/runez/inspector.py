"""
This module holds less often used conveniences, it is not available via `import runez`

Functions from this module must be explicitly imported, for example:

>>> from runez.inspector import auto_import_siblings
"""

import importlib
import sys
import time
from functools import wraps

from runez.convert import to_int
from runez.program import run
from runez.pyenv import get_current_version
from runez.system import abort_if, find_caller, py_mimic, SYS_INFO


def auto_import_siblings(skip=None, caller=None):
    """Auto-import all sibling submodules from caller.

    This is handy for click command groups for example.
    It allows to avoid having to have a module that simply lists all sub-commands, just to ensure they are added to `main`.

    - ./my_cli.py::

        from runez.inspector import auto_import_siblings

        @click.group()
        def main(...):
            ...

        auto_import_siblings()

    - ./my_sub_command.py::

        from .my_cli import main

        @main.command()  # The auto-import will trigger importing this without further ado
        def foo(...):
            ...

    Args:
        skip (list | None): Do not auto-import specified modules
        package (runez.system._CallerInfo | None): Caller info (for testing purposes)

    Returns:
        (list): List of imported modules, if any
    """
    if caller is None:
        caller = find_caller()

    if not caller or caller.is_main:
        raise ImportError("Calling auto_import_siblings() from __main__ is not supported: %s" % caller)

    if not caller.package_name or not caller.folder:
        raise ImportError("Could not determine caller's __package__ and __file__, can't auto-import: %s" % caller)

    import pkgutil

    imported = []
    for loader, module_name, _ in pkgutil.walk_packages([caller.folder], prefix="%s." % caller.package_name):
        if _should_auto_import(module_name, skip):
            importlib.import_module(module_name)
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
            importlib.import_module(self.top_level)

        except ImportError:
            abort_if(not SYS_INFO.venv_bin_folder, "Can't auto-install '%s' outside of a virtual environment" % self.package_name)
            r = run(sys.executable, "-mpip", "install", self.package_name, fatal=False, dryrun=False)
            abort_if(r.failed, "Can't auto-install '%s': %s" % (self.package_name, r.full_output))

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
        v = get_current_version()
        if v < 3.7:
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
