"""
Convenience methods for file/folder operations
"""

import logging
import os

from runez.convert import formatted, resolved_path, short
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
        return abort("Can't create folder %s: %s", short(folder), e, fatal=(fatal, -1))


def parent_folder(path, base=None):
    """
    :param str|None path: Path to file or folder
    :param str|None base: Base folder to use for relative paths (default: current working dir)
    :return str: Absolute path of parent folder of 'path'
    """
    return path and os.path.dirname(resolved_path(path, base=base))


def resolved_location(obj, custom_location=None, locations=None, basename=None):
    """
    :param obj: Object to expand formatting markers from, via formatted()
    :param str|None custom_location: Custom location to use (overrides further determination)
    :param list|None locations: Locations to try
    :param str|None basename: Filename to use if resolved location points to a folder
    :return str|None: Path to location to use, if it could be determined
    """
    if obj is not None:
        if custom_location is not None:
            # Custom location typically provided via --config CLI flag
            return _auto_complete_filename(obj, formatted(custom_location, obj), basename)
        if locations:
            for location in locations:
                path = _auto_complete_filename(obj, formatted(location, obj), basename)
                if path and ensure_folder(path, fatal=False, dryrun=False) >= 0:
                    return path


def _auto_complete_filename(obj, location, filename):
    if location:
        if filename is not None and os.path.isdir(location):
            filename = formatted(filename, obj)
            return filename and os.path.join(location, filename)
        return location
