"""
Convenience methods for file/folder operations
"""

import os

from runez.base import abort, debug, short, State


SYMBOLIC_TMP = "<tmp>"


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
