"""
Convenience methods for file/folder operations
"""

import os

from runez.system import _R, abort, LOG, resolved_path, short, UNSET


def basename(path, extension_marker=os.extsep):
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

        return result  # We have a basename starting with '.'

    return result


def ensure_folder(path, folder=False, fatal=True, logger=LOG.debug, dryrun=UNSET):
    """Ensure folder exists

    Args:
        path (str | None): Path to file or folder
        folder (bool): If True, 'path' refers to a folder (file assumed otherwise)
        fatal (bool | None): Abort execution on failure if True
        logger (callable | None): Logger to use
        dryrun (bool): Optionally override current dryrun setting

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
            return abort("Folder %s is not writable" % folder, return_value=-1, fatal=fatal, logger=logger)

        return 0

    if dryrun is UNSET:
        dryrun = _R.is_dryrun()

    if dryrun:
        LOG.debug("Would create %s", short(folder))
        return 1

    try:
        os.makedirs(folder)
        if logger:
            logger("Created folder %s", short(folder))

        return 1

    except Exception as e:
        return abort("Can't create folder %s" % short(folder), exc_info=e, return_value=-1, fatal=fatal, logger=logger)


def parent_folder(path, base=None):
    """Parent folder of `path`, relative to `base`

    Args:
        path (str | None): Path to file or folder
        base (str | None): Base folder to use for relative paths (default: current working dir)

    Returns:
        (str): Absolute path of parent folder
    """
    return path and os.path.dirname(resolved_path(path, base=base))
