"""
This module holds less often used conveniences, it is not available via `import runez`

Functions from this module must be explicitly imported, for example:

>>> from runez.inspector import auto_import_siblings
"""

import importlib

from runez.system import find_caller


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
    for _, module_name, _ in pkgutil.walk_packages([caller.folder], prefix="%s." % caller.package_name):
        if _should_auto_import(module_name, skip):
            importlib.import_module(module_name)
            imported.append(module_name)

    return imported


def _should_auto_import(module_name, skip):
    """
    Args:
        module_name (str): Module being auto-imported
        skip (list | None): Modules to NOT auto-import

    Returns:
        (bool): True if we should auto-import `module_name`
    """
    return not module_name.endswith("_") and not (skip and any(module_name.startswith(x) for x in skip))
