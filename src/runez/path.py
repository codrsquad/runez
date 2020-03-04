"""
Convenience methods for file/folder operations
"""

import logging
import os

from runez.convert import resolved_path, short
from runez.system import abort, find_caller_frame, is_dryrun


LOG = logging.getLogger(__name__)


def auto_import_siblings(folders=None, skip=None, auto_clean="TOX_WORK_DIR"):
    """
    Auto-import all sibling submodules from caller.
    This is handy for click command groups for example.
    It allows to avoid having to have a module that simply lists all sub-commands, just to ensure they are added to `main`.

    Example usage:
        my_cli.py:

            @click.group()
            def main(...):
                ...

            # Without this, one would have to ensure that all subcommands are imported somehow
            runez.auto_import_siblings()

        my_sub_command.py:

            from .my_cli import main

            @main.command():
            def foo(...):
                ...

    Args:
        folders (list | None): Folders to auto-import (default: folder of caller module)
        skip (list | set | None): Optional module names to skip importing
        auto_clean (str | bool | None): If True, auto-clean .pyc files
                                        If string: auto-clean .pyc files when corresponding env var is defined

    Returns:
        (list | None): List of imported modules, if any
    """
    if folders is None:
        caller = find_caller_frame(depth=1)
        if not caller:
            return None

        caller_path = caller.f_globals.get("__file__")
        if skip is None:
            skip = [basename(caller_path)]

        folders = [os.path.dirname(caller_path)]

    if not folders:
        return None

    import pkgutil

    imported = []
    for folder in folders:
        if folder and os.path.isdir(folder):
            if auto_clean is not None and not isinstance(auto_clean, bool):
                auto_clean = os.environ.get(auto_clean)

            if auto_clean:
                # Clean .pyc files so consecutive tox runs with distinct python2 versions don't get confused
                for root, dirs, files in os.walk(folder):
                    for fname in files:
                        if fname.endswith(".pyc"):  # pragma: no cover, only applicable for local development
                            try:
                                os.unlink(os.path.join(root, fname))

                            except OSError:
                                pass  # Delete is only needed in tox run, no need to fail if delete is not possible

            for loader, module_name, _ in pkgutil.walk_packages([folder]):
                if module_name not in skip:
                    imported.append(loader.find_module(module_name).load_module(module_name))

    return imported


def basename(path, extension_marker="."):
    """
    :param str|None path: Path to consider
    :param str|None extension_marker: Trim file extension based on specified character
    :return str: Basename part of path, without extension (if 'extension_marker' provided)
    """
    result = os.path.basename(path or "")
    if extension_marker:
        pre, _, post = result.rpartition(extension_marker)
        return pre or post

    return result


def ensure_folder(path, folder=False, fatal=True, logger=LOG.debug, dryrun=None):
    """
    :param str|None path: Path to file or folder
    :param bool folder: If True, 'path' refers to a folder (file otherwise)
    :param bool|None fatal: Abort execution on failure if True
    :param callable|None logger: Logger to use
    :param bool|None dryrun: If specified, override global is_dryrun()
    :return int: 1 if effectively done, 0 if no-op, -1 on failure
    """
    if not path:
        return 0

    if folder:
        folder = resolved_path(path)

    else:
        folder = parent_folder(path)

    if os.path.isdir(folder):
        if not os.access(folder, os.W_OK):
            return abort("Folder %s is not writable", folder, fatal=(fatal, -1), logger=logger)
        return 0

    if dryrun is None:
        dryrun = is_dryrun()

    if dryrun:
        LOG.debug("Would create %s", short(folder))
        return 1

    try:
        os.makedirs(folder)
        if logger:
            logger("Created folder %s", short(folder))

        return 1

    except Exception as e:
        return abort("Can't create folder %s: %s", short(folder), e, fatal=(fatal, -1), logger=logger)


def parent_folder(path, base=None):
    """
    :param str|None path: Path to file or folder
    :param str|None base: Base folder to use for relative paths (default: current working dir)
    :return str: Absolute path of parent folder of 'path'
    """
    return path and os.path.dirname(resolved_path(path, base=base))
