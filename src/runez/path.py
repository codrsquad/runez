"""
Convenience methods for file/folder operations
"""

import os

from runez.system import _R, abort, resolved_path, short, UNSET


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


def ensure_folder(path, fatal=True, logger=UNSET, dryrun=UNSET):
    """Ensure folder with 'path' exists

    Args:
        path (str | None): Path to file or folder
        fatal (bool | None): True: abort execution on failure, False: don't abort but log, None: don't abort, don't log
        logger (callable | None): Logger to use, or None to disable log chatter
        dryrun (bool): Optionally override current dryrun setting

    Returns:
        (int): In non-fatal mode, 1: successfully done, 0: was no-op, -1: failed
    """
    path = resolved_path(path)
    if not path or os.path.isdir(path):
        return 0

    if _R.hdry(dryrun, logger, "create %s" % short(path)):
        return 1

    try:
        os.makedirs(path)
        _R.hlog(logger, "Created folder %s" % short(path))
        return 1

    except Exception as e:
        return abort("Can't create folder %s" % short(path), exc_info=e, return_value=-1, fatal=fatal, logger=logger)


def parent_folder(path, base=None):
    """Parent folder of `path`, relative to `base`

    Args:
        path (str | None): Path to file or folder
        base (str | None): Base folder to use for relative paths (default: current working dir)

    Returns:
        (str): Absolute path of parent folder
    """
    return path and os.path.dirname(resolved_path(path, base=base))
