"""
Convenience methods for file/folder operations
"""

import logging
import os

from runez.convert import resolved_path, short
from runez.system import abort, is_dryrun


LOG = logging.getLogger(__name__)


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
