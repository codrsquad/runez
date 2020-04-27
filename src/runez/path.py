"""
Convenience methods for file/folder operations
"""

import logging
import os

from runez.convert import resolved_path, short
from runez.system import abort, is_dryrun


LOG = logging.getLogger(__name__)


def basename(path, extension_marker="."):
    """Base name of given `path`, ignoring extension if `extension_marker` is provided

    Args:
        path (str | None): Path to consider
        extension_marker (str | None): Also trim file extension, if marker provided

    Returns:
        (str): Basename part of path, without extension (if 'extension_marker' provided)
    """
    result = os.path.basename(path or "")
    if extension_marker:
        if extension_marker not in result:
            return result

        pre, _, post = result.rpartition(extension_marker)
        if pre:
            return pre

        return "%s%s" % (extension_marker, post)

    return result


def ensure_folder(path, folder=False, fatal=True, logger=LOG.debug, dryrun=None):
    """Ensure folder exists

    Args:
        path (str | None): Path to file or folder
        folder (bool): If True, 'path' refers to a folder (file assumed otherwise)
        fatal (bool | None): Abort execution on failure if True
        logger (callable | None): Logger to use
        dryrun (bool | None): If specified, override global is_dryrun()

    Returns:
         (int): 1 if effectively done, 0 if no-op, -1 on failure
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
    """Parent folder of `path`, relative to `base`

    Args:
        path (str | None): Path to file or folder
        base (str | None): Base folder to use for relative paths (default: current working dir)

    Returns:
        (str): Absolute path of parent folder
    """
    return path and os.path.dirname(resolved_path(path, base=base))
