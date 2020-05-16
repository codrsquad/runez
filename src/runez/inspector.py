import os

from runez.system import find_caller_frame


def auto_import_siblings(auto_clean="TOX_WORK_DIR", skip=None):
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
        auto_clean (str | bool | None): If provided, auto-clean `.pyc`` files
        skip (list | None): Do not auto-import specified modules

    Returns:
        (list): List of imported modules, if any
    """
    caller = find_caller_frame()
    if not caller:
        raise ImportError("Could not determine caller, can't auto-import")

    if caller.f_globals.get("__name__") == "__main__":
        raise ImportError("Calling auto_import_siblings() from __main__ is not supported: %s" % caller)

    caller_package = caller.f_globals.get("__package__")
    if not caller_package:
        raise ImportError("Could not determine caller's __package__, can't auto-import: %s" % caller)

    caller_path = caller.f_globals.get("__file__")
    if not caller_path:
        raise ImportError("Could not determine caller's __file__, can't auto-import: %s" % caller)

    folder = os.path.dirname(caller_path)
    if not os.path.isdir(folder):
        raise ImportError("Caller's __file__ points to a non-existing directory, can't auto-import: %s" % caller)

    if auto_clean is not None and not isinstance(auto_clean, bool):
        auto_clean = os.environ.get(auto_clean)

    if auto_clean:
        # Clean .pyc files so consecutive tox runs with distinct python2 versions don't get confused
        _clean_files(folder, ".pyc")

    import pkgutil

    imported = []
    for loader, module_name, _ in pkgutil.walk_packages([folder], prefix="%s." % caller_package):
        if _should_auto_import(module_name, skip):
            __import__(module_name)
            imported.append(module_name)

    return imported


def simplified_class_name(cls, root):
    """By default, root ancestor is ignored, common prefix/suffix is removed, and name is lowercase-d"""
    if cls is not root:
        name = cls.__name__
        root = getattr(root, "__name__", root)
        if name.startswith(root):
            name = name[len(root):]

        elif name.endswith(root):
            name = name[:len(root) + 1]

        return name.lower()


def class_descendants(ancestor, adjust=simplified_class_name, root=None):
    """
    Args:
        ancestor (type): Class to track descendants of
        root (type | str | None): Root ancestor, or ancestor name (defaults to `ancestor`), passed through to `adjust`
        adjust (callable): Function that can adapt each descendant, and return an optionally massaged name to represent it
                           If function returns None for a given descendant, that descendant is ignored in the returned map

    Returns:
        (dict): Map of all descendants, by optionally adjusted name
    """
    result = {}
    if root is None:
        root = ancestor
    name = adjust(ancestor, root)
    if name is not None:
        result[name] = ancestor
    _walk_descendants(result, ancestor, adjust, root)
    return result


def _clean_files(folder, extension):
    """Clean all files with `extension` from `folder`"""
    for root, dirs, files in os.walk(folder):
        for fname in files:
            if fname.endswith(extension):  # pragma: no cover, only applicable for local development
                try:
                    os.unlink(os.path.join(root, fname))

                except OSError:
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


def _walk_descendants(result, ancestor, adjust, root):
    for m in ancestor.__subclasses__():
        name = adjust(m, root)
        if name is not None:
            result[name] = m
        _walk_descendants(result, m, adjust, root)
