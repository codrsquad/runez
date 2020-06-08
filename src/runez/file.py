import io
import os
import shutil
import tempfile
import time

from runez.convert import plural, represented_bytesize
from runez.system import _R, abort, Anchored, decode, resolved_path, short, SYMBOLIC_TMP, UNSET


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


def copy(source, destination, ignore=None, fatal=True, logger=UNSET, dryrun=UNSET):
    """Copy source -> destination

    Args:
        source (str | None): Source file or folder
        destination (str | None): Destination file or folder
        ignore (callable | list | str | None): Names to be ignored
        fatal (bool | None): True: abort execution on failure, False: don't abort but log, None: don't abort, don't log
        logger (callable | None): Logger to use, False to log errors only, None to disable log chatter
        dryrun (bool): Optionally override current dryrun setting

    Returns:
        (int): In non-fatal mode, 1: successfully done, 0: was no-op, -1: failed
    """
    return _file_op(source, destination, _copy, fatal, logger, dryrun, ignore=ignore)


def delete(path, fatal=True, logger=UNSET, dryrun=UNSET):
    """
    Args:
        path (str | None): Path to file or folder to delete
        fatal (bool | None): True: abort execution on failure, False: don't abort but log, None: don't abort, don't log
        logger (callable | None): Logger to use, False to log errors only, None to disable log chatter
        dryrun (bool): Optionally override current dryrun setting

    Returns:
        (int): In non-fatal mode, 1: successfully done, 0: was no-op, -1: failed
    """
    path = resolved_path(path)
    islink = path and os.path.islink(path)
    if not islink and (not path or not os.path.exists(path)):
        return 0

    if _R.hdry(dryrun, logger, "delete %s" % short(path)):
        return 1

    try:
        if islink or os.path.isfile(path):
            os.unlink(path)

        else:
            shutil.rmtree(path)

        _R.hlog(logger, "Deleted %s" % short(path))
        return 1

    except Exception as e:
        return abort("Can't delete %s" % short(path), exc_info=e, return_value=-1, fatal=fatal, logger=logger)


def ensure_folder(path, clean=False, fatal=True, logger=UNSET, dryrun=UNSET):
    """Ensure folder with 'path' exists

    Args:
        path (str | None): Path to file or folder
        clean (bool): True: If True, ensure folder is clean (delete any file/folder it may have)
        fatal (bool | None): True: abort execution on failure, False: don't abort but log, None: don't abort, don't log
        logger (callable | None): Logger to use, False to log errors only, None to disable log chatter
        dryrun (bool): Optionally override current dryrun setting

    Returns:
        (int): In non-fatal mode, >=1: successfully done, 0: was no-op, -1: failed
    """
    path = resolved_path(path)
    if not path:
        return 0

    if os.path.isdir(path):
        if not clean:
            return 0

        cleaned = 0
        for fname in os.listdir(path):
            cleaned += delete(os.path.join(path, fname), fatal=fatal, logger=False, dryrun=dryrun)

        if cleaned:
            msg = "%s from %s" % (plural(cleaned, "file"), short(path))
            if not _R.hdry(dryrun, logger, "clean %s" % msg):
                _R.hlog(logger, "Cleaned %s" % msg)

        return cleaned

    if _R.hdry(dryrun, logger, "create %s" % short(path)):
        return 1

    try:
        os.makedirs(path)
        _R.hlog(logger, "Created folder %s" % short(path))

        return 1

    except Exception as e:
        return abort("Can't create folder %s" % short(path), exc_info=e, return_value=-1, fatal=fatal, logger=logger)


def ini_to_dict(path, default=UNSET, keep_empty=False):
    """Contents of an INI-style config file as a dict of dicts: section -> key -> value

    Args:
        path (str | None): Path to file to parse
        default (dict | None): Object to return if conf couldn't be read
        keep_empty (bool): If True, keep definitions with empty values

    Returns:
        (dict): Dict of section -> key -> value
    """
    lines = readlines(path, default=None)
    if lines is None:
        return _R.hdef(default, "Couldn't read ini file '%s'" % short(path))

    result = {}
    section_key = None
    section = None
    for line in lines:
        line = line.strip()
        if "#" in line:
            i = line.index("#")
            line = line[:i].strip()

        if not line:
            continue

        if line.startswith("[") and line.endswith("]"):
            section_key = line.strip("[]").strip()
            section = result.get(section_key)
            continue

        if "=" not in line:
            continue

        if section is None:
            section = result[section_key] = {}

        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if keep_empty or (key and value):
            section[key] = value

    if not keep_empty:
        result = dict((k, v) for k, v in result.items() if k and v)

    return result


def is_younger(path, age, default=False):
    """
    Args:
        path (str): Path to file
        age (int | float): How many seconds to consider the file too old
        default (bool): Returned when file is not present

    Returns:
        (bool): True if file exists and is younger than 'age' seconds
    """
    try:
        if age > 0:
            return time.time() - os.path.getmtime(path) < age

    except (OSError, IOError, TypeError):
        return default


def parent_folder(path, base=None):
    """Parent folder of `path`, relative to `base`

    Args:
        path (str | None): Path to file or folder
        base (str | None): Base folder to use for relative paths (default: current working dir)

    Returns:
        (str): Absolute path of parent folder
    """
    return path and os.path.dirname(resolved_path(path, base=base))


def readlines(path, default=UNSET, first=None, errors=None):
    """
    Args:
        path (str | None): Path to file to read lines from
        default (list | None): Default if file is not present, or it could not be read
        first (int | None): Return only the 'first' lines when specified
        errors (str | None): Optional string specifying how encoding errors are to be handled

    Returns:
        (list): List of lines read, newlines and trailing spaces stripped
    """
    path = resolved_path(path)
    if not path or not os.path.exists(path):
        return _R.hdef(default, "No file %s" % short(path))

    try:
        result = []
        with io.open(path, errors=errors) as fh:
            if not first:
                first = -1

            for line in fh:
                if first == 0:
                    return result

                result.append(decode(line).rstrip())
                first -= 1

            return result

    except Exception as e:
        return _R.hdef(default, "Couldn't read %s" % short(path), e=e)


def move(source, destination, fatal=True, logger=UNSET, dryrun=UNSET):
    """Move `source` -> `destination`

    Args:
        source (str | None): Source file or folder
        destination (str | None): Destination file or folder
        fatal (bool | None): True: abort execution on failure, False: don't abort but log, None: don't abort, don't log
        logger (callable | None): Logger to use, False to log errors only, None to disable log chatter
        dryrun (bool): Optionally override current dryrun setting

    Returns:
        (int): In non-fatal mode, 1: successfully done, 0: was no-op, -1: failed
    """
    return _file_op(source, destination, _move, fatal, logger, dryrun)


def symlink(source, destination, must_exist=True, fatal=True, logger=UNSET, dryrun=UNSET):
    """Symlink `source` <- `destination`

    Args:
        source (str | None): Source file or folder
        destination (str | None): Destination file or folder
        must_exist (bool): If True, verify that source does indeed exist
        fatal (bool | None): True: abort execution on failure, False: don't abort but log, None: don't abort, don't log
        logger (callable | None): Logger to use, False to log errors only, None to disable log chatter
        dryrun (bool): Optionally override current dryrun setting

    Returns:
        (int): In non-fatal mode, 1: successfully done, 0: was no-op, -1: failed
    """
    return _file_op(source, destination, _symlink, fatal, logger, dryrun, must_exist=must_exist)


class TempFolder(object):
    """Context manager for obtaining a temp folder"""

    def __init__(self, anchor=True, dryrun=UNSET, follow=True):
        """
        Args:
            anchor (bool): If True, short-ify paths relative to used temp folder
            dryrun (bool): Optionally override current dryrun setting
            follow (bool): If True, change working dir to temp folder (and restore)
        """
        self.anchor = anchor
        self.dryrun = dryrun
        self.follow = follow
        self.old_cwd = None
        self.tmp_folder = None

    def __enter__(self):
        self.dryrun = _R.set_dryrun(self.dryrun)
        if not _R.is_dryrun():
            # Use realpath() to properly resolve for example symlinks on OSX temp paths
            self.tmp_folder = os.path.realpath(tempfile.mkdtemp())
            if self.follow:
                self.old_cwd = os.getcwd()
                os.chdir(self.tmp_folder)

        tmp = self.tmp_folder or SYMBOLIC_TMP
        if self.anchor:
            Anchored.add(tmp)

        return tmp

    def __exit__(self, *_):
        _R.set_dryrun(self.dryrun)
        if self.anchor:
            Anchored.pop(self.tmp_folder or SYMBOLIC_TMP)

        if self.old_cwd:
            os.chdir(self.old_cwd)

        if self.tmp_folder:
            shutil.rmtree(self.tmp_folder)


def touch(path, fatal=True, logger=UNSET, dryrun=UNSET):
    """Touch file with `path`

    Args:
        path (str | None): Path to file to touch
        fatal (bool | None): True: abort execution on failure, False: don't abort but log, None: don't abort, don't log
        logger (callable | None): Logger to use, False to log errors only, None to disable log chatter
        dryrun (bool): Optionally override current dryrun setting

    Returns:
        (int): In non-fatal mode, 1: successfully done, 0: was no-op, -1: failed
    """
    return write(path, None, fatal=fatal, logger=logger, dryrun=dryrun)


def write(path, contents, fatal=True, logger=UNSET, dryrun=UNSET):
    """Write `contents` to file with `path`

    Args:
        path (str | None): Path to file
        contents (str | None): Contents to write (only touch file if None)
        fatal (bool | None): True: abort execution on failure, False: don't abort but log, None: don't abort, don't log
        logger (callable | None): Logger to use, False to log errors only, None to disable log chatter
        dryrun (bool): Optionally override current dryrun setting

    Returns:
        (int): In non-fatal mode, 1: successfully done, 0: was no-op, -1: failed
    """
    if not path:
        return 0

    path = resolved_path(path)
    byte_size = represented_bytesize(len(contents), unit="bytes") if contents else ""
    if _R.hdry(dryrun, logger, lambda: "%s %s" % ("write %s to" % byte_size if byte_size else "touch", short(path))):
        return 1

    ensure_folder(parent_folder(path), fatal=fatal, logger=False, dryrun=dryrun)
    try:
        with io.open(path, "wt") as fh:
            if contents is None:
                os.utime(path, None)

            else:
                fh.write(decode(contents))

        _R.hlog(logger, "%s %s" % ("Wrote %s to" % byte_size if byte_size else "Touched", short(path)))
        return 1

    except Exception as e:
        return abort("Can't write to %s" % short(path), exc_info=e, return_value=-1, fatal=fatal, logger=logger)


def _copy(source, destination, ignore=None):
    """Effective copy"""
    if os.path.isdir(source):
        if os.path.isdir(destination):
            for fname in os.listdir(source):
                _copy(os.path.join(source, fname), os.path.join(destination, fname), ignore=ignore)

        else:
            if os.path.isfile(destination) or os.path.islink(destination):
                os.unlink(destination)

            shutil.copytree(source, destination, symlinks=True, ignore=ignore)

    else:
        shutil.copy(source, destination)

    shutil.copystat(source, destination)  # Make sure last modification time is preserved


def _move(source, destination):
    """Effective move"""
    shutil.move(source, destination)


def _symlink(source, destination):
    """Effective symlink"""
    os.symlink(source, destination)


def _file_op(source, destination, func, fatal, logger, dryrun, must_exist=True, ignore=None):
    """Call func(source, destination)

    Args:
        source (str | None): Source file or folder
        destination (str | None): Destination file or folder
        func (callable): Implementation function
        fatal (bool | None): True: abort execution on failure, False: don't abort but log, None: don't abort, don't log
        logger (callable | None): Logger to use, False to log errors only, None to disable log chatter
        dryrun (bool): Optionally override current dryrun setting
        must_exist (bool): If True, verify that source does indeed exist
        ignore (callable | list | str | None): Names to be ignored

    Returns:
        (int): In non-fatal mode, 1: successfully done, 0: was no-op, -1: failed
    """
    if not source or not destination or source == destination:
        return 0

    action = func.__name__[1:]
    indicator = "<-" if action == "symlink" else "->"
    description = "%s %s %s %s" % (action, short(source), indicator, short(destination))
    psource = parent_folder(source)
    pdest = resolved_path(destination)
    if psource != pdest and psource.startswith(pdest):
        message = "Can't %s: source contained in destination" % description
        return abort(message, return_value=-1, fatal=fatal, logger=logger)

    if _R.hdry(dryrun, logger, description):
        return 1

    if must_exist and not os.path.exists(source):
        message = "%s does not exist, can't %s to %s" % (short(source), action.lower(), short(destination))
        return abort(message, return_value=-1, fatal=fatal, logger=logger)

    try:
        # Ensure parent folder exists
        ensure_folder(parent_folder(destination), fatal=fatal, logger=False, dryrun=dryrun)
        _R.hlog(logger, lambda: "%s%s" % (description[0].upper(), description[1:]))
        if ignore is not None:
            if callable(ignore):
                func(source, destination, ignore=ignore)

            else:
                func(source, destination, ignore=lambda *_: ignore)

        else:
            func(source, destination)

        return 1

    except Exception as e:
        message = "Can't %s" % description
        return abort(message, exc_info=e, return_value=-1, fatal=fatal, logger=logger)
