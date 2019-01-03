"""
Convenience methods for file/folder operations
"""

import os
import shutil

from runez.base import short, State
from runez.log import abort, debug


SYMBOLIC_TMP = "<tmp>"


def copy(source, destination, adapter=None, fatal=True, logger=debug):
    """
    Copy source -> destination

    :param str|None source: Source file or folder
    :param str|None destination: Destination file or folder
    :param callable adapter: Optional function to call on 'source' before copy
    :param bool|None fatal: Abort execution on failure if True
    :param callable|None logger: Logger to use
    :return int: 1 if effectively done, 0 if no-op, -1 on failure
    """
    return _file_op(source, destination, _copy, adapter, fatal, logger)


def delete(path, fatal=True, logger=debug):
    """
    :param str|None path: Path to file or folder to delete
    :param bool|None fatal: Abort execution on failure if True
    :param callable|None logger: Logger to use
    :return int: 1 if effectively done, 0 if no-op, -1 on failure
    """
    islink = path and os.path.islink(path)
    if not islink and (not path or not os.path.exists(path)):
        return 0

    if State.dryrun:
        debug("Would delete %s", short(path))
        return 1

    if logger:
        logger("Deleting %s", short(path))

    try:
        if islink or os.path.isfile(path):
            os.unlink(path)
        else:
            shutil.rmtree(path)
        return 1

    except Exception as e:
        return abort("Can't delete %s: %s", short(path), e, fatal=(fatal, -1))


def ensure_folder(path, folder=False, fatal=True, logger=debug):
    """
    :param str|None path: Path to file or folder
    :param bool folder: If True, 'path' refers to a folder (file otherwise)
    :param bool|None fatal: Abort execution on failure if True
    :param callable|None logger: Logger to use
    :return int: 1 if effectively done, 0 if no-op, -1 on failure
    """
    if not path:
        return 0

    if folder:
        folder = resolved_path(path)

    else:
        folder = parent_folder(path)

    if os.path.isdir(folder):
        return 0

    if State.dryrun:
        debug("Would create %s", short(folder))
        return 1

    try:
        os.makedirs(folder)
        if logger:
            logger("Created folder %s", short(folder))

        return 1

    except Exception as e:
        return abort("Can't create folder %s: %s", short(folder), e, fatal=(fatal, -1))


def move(source, destination, adapter=None, fatal=True, logger=debug):
    """
    Move source -> destination

    :param str|None source: Source file or folder
    :param str|None destination: Destination file or folder
    :param callable adapter: Optional function to call on 'source' before copy
    :param bool|None fatal: Abort execution on failure if True
    :param callable|None logger: Logger to use
    :return int: 1 if effectively done, 0 if no-op, -1 on failure
    """
    return _file_op(source, destination, _move, adapter, fatal, logger)


def parent_folder(path, base=None):
    """
    :param str|None path: Path to file or folder
    :param str|None base: Base folder to use for relative paths (default: current working dir)
    :return str: Absolute path of parent folder of 'path'
    """
    return path and os.path.dirname(resolved_path(path, base=base))


def resolved_path(path, base=None):
    """
    :param str|None path: Path to resolve
    :param str|None base: Base path to use to resolve relative paths (default: current working dir)
    :return str: Absolute path
    """
    if not path or path.startswith(SYMBOLIC_TMP):
        return path

    path = os.path.expanduser(path)
    if base and not os.path.isabs(path):
        return os.path.join(resolved_path(base), path)

    return os.path.abspath(path)


def symlink(source, destination, adapter=None, must_exist=True, fatal=True, logger=debug):
    """
    Symlink source <- destination

    :param str|None source: Source file or folder
    :param str|None destination: Destination file or folder
    :param callable adapter: Optional function to call on 'source' before copy
    :param bool must_exist: If True, verify that source does indeed exist
    :param bool|None fatal: Abort execution on failure if True
    :param callable|None logger: Logger to use
    :return int: 1 if effectively done, 0 if no-op, -1 on failure
    """
    return _file_op(source, destination, _symlink, adapter,  fatal, logger, must_exist=must_exist)


def _copy(source, destination):
    """Effective copy"""
    if os.path.isdir(source):
        shutil.copytree(source, destination, symlinks=True)
    else:
        shutil.copy(source, destination)

    shutil.copystat(source, destination)  # Make sure last modification time is preserved


def _move(source, destination):
    """Effective move"""
    shutil.move(source, destination)


def _symlink(source, destination):
    """Effective symlink"""
    os.symlink(source, destination)


def _file_op(source, destination, func, adapter, fatal, logger, must_exist=True):
    """
    Call func(source, destination)

    :param str|None source: Source file or folder
    :param str|None destination: Destination file or folder
    :param callable func: Implementation function
    :param callable adapter: Optional function to call on 'source' before copy
    :param bool|None fatal: Abort execution on failure if True
    :param callable|None logger: Logger to use
    :param bool must_exist: If True, verify that source does indeed exist
    :return int: 1 if effectively done, 0 if no-op, -1 on failure
    """
    if not source or not destination or source == destination:
        return 0

    action = func.__name__[1:]
    indicator = "<-" if action == "symlink" else "->"
    psource = parent_folder(source)
    pdest = resolved_path(destination)
    if psource != pdest and psource.startswith(pdest):
        return abort(
            "Can't %s %s %s %s: source contained in destination", action, short(source), indicator, short(destination), fatal=(fatal, -1)
        )

    if State.dryrun:
        debug("Would %s %s %s %s", action, short(source), indicator, short(destination))
        return 1

    if must_exist and not os.path.exists(source):
        return abort("%s does not exist, can't %s to %s", short(source), action.title(), short(destination), fatal=(fatal, -1))

    try:
        # Delete destination, but ensure that its parent folder exists
        delete(destination, fatal=fatal, logger=None)
        ensure_folder(destination, fatal=fatal, logger=None)

        if logger:
            note = adapter(source, destination, fatal=fatal, logger=logger) if adapter else ""
            if logger:
                logger("%s %s %s %s%s", action.title(), short(source), indicator, short(destination), note)

        func(source, destination)
        return 1

    except Exception as e:
        return abort("Can't %s %s %s %s: %s", action, short(source), indicator, short(destination), e, fatal=(fatal, -1))
