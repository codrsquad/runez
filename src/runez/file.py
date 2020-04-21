import io
import logging
import os
import shutil
import tempfile

from runez.base import decode
from runez.convert import Anchored, resolved_path, short, SYMBOLIC_TMP, to_int
from runez.path import ensure_folder, parent_folder
from runez.system import abort, is_dryrun, set_dryrun

LOG = logging.getLogger(__name__)
TEXT_THRESHOLD_SIZE = 1048576  # Max size in bytes to consider a file a "text file"


def copy(source, destination, ignore=None, adapter=None, fatal=True, logger=LOG.debug):
    """Copy source -> destination

    Args:
        source (str | None): Source file or folder
        destination (str | None): Destination file or folder
        ignore (callable | list | str | None): Names to be ignored
        adapter (callable | None): Optional function to call on 'source' before copy
        fatal (bool | None): Abort execution on failure if True
        logger (callable | None): Logger to use

    Returns:
        (int): 1 if effectively done, 0 if no-op, -1 on failure
    """
    return _file_op(source, destination, _copy, adapter, fatal, logger, ignore=ignore)


def delete(path, fatal=True, logger=LOG.debug):
    """
    Args:
        path (str | None): Path to file or folder to delete
        fatal (bool | None): Abort execution on failure if True
        logger (callable | None): Logger to use

    Returns:
        (int): 1 if effectively done, 0 if no-op, -1 on failure
    """
    path = resolved_path(path)
    islink = path and os.path.islink(path)
    if not islink and (not path or not os.path.exists(path)):
        return 0

    if is_dryrun():
        LOG.debug("Would delete %s", short(path))
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


def first_line(path, default=None):
    """First line of file with `path`, if any

    Args:
        path (str | None): Path to file
        default (str | None): Default to return if file could not be read

    Returns:
        (str | None): First line of file, if any
    """
    try:
        with io.open(resolved_path(path), errors="ignore") as fh:
            return fh.readline().strip()

    except (IOError, TypeError, ValueError):
        return default


def ini_to_dict(data, keep_empty=False, default=None):
    """Contents of an INI-style config file as a dict of dicts: section -> key -> value

    Args:
        data (str | file | list | None): Path to file, or file object, or lines to parse
        keep_empty (bool): If True, keep definitions with empty values
        default (dict | None): Object to return if conf couldn't be read

    Returns:
        (dict): Dict of section -> key -> value
    """
    if not data:
        return default

    lines = readlines(data)
    if lines is None:
        return default

    result = {}
    section_key = None
    section = None
    for line in lines:
        line = decode(line).strip()
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


def readlines(data, max_size=TEXT_THRESHOLD_SIZE, default=None):
    """Tentatively read lines from `data`, if not possible, simply return `default`

    Args:
        data (str | file | list | None): Path to file, or file object to return lines from
        max_size (int | None): Return contents only for files smaller than 'max_size' bytes
        default (list | None): Object to return if lines couldn't be read

    Returns:
        (list | None): Lines from file contents
    """
    if not data:
        return default

    if isinstance(data, list):
        return data

    if hasattr(data, "readlines"):
        return data.readlines()

    path = resolved_path(data)
    if not os.path.isfile(path) or (max_size and os.path.getsize(path) > max_size):
        # Intended for small text files, pretend no contents for binaries
        return default

    try:
        with io.open(path) as fh:
            return fh.readlines()

    except Exception:
        return default


def move(source, destination, adapter=None, fatal=True, logger=LOG.debug):
    """Move `source` -> `destination`

    Args:
        source (str | None): Source file or folder
        destination (str | None): Destination file or folder
        adapter (callable): Optional function to call on 'source' before copy
        fatal (bool | None): Abort execution on failure if True
        logger (callable | None): Logger to use

    Returns:
        (int): 1 if effectively done, 0 if no-op, -1 on failure
    """
    return _file_op(source, destination, _move, adapter, fatal, logger)


def symlink(source, destination, adapter=None, must_exist=True, fatal=True, logger=LOG.debug):
    """Symlink `source` <- `destination`

    Args:
        source (str | None): Source file or folder
        destination (str | None): Destination file or folder
        adapter (callable): Optional function to call on 'source' before copy
        must_exist (bool): If True, verify that source does indeed exist
        fatal (bool | None): Abort execution on failure if True
        logger (callable | None): Logger to use

    Returns:
        (int): 1 if effectively done, 0 if no-op, -1 on failure
    """
    return _file_op(source, destination, _symlink, adapter, fatal, logger, must_exist=must_exist)


class TempFolder(object):
    """Context manager for obtaining a temp folder"""

    def __init__(self, anchor=True, dryrun=None, follow=True):
        """
        Args:
            anchor (bool): If True, short-ify paths relative to used temp folder
            dryrun (bool): Override dryrun (if provided)
            follow (bool): If True, change working dir to temp folder (and restore)
        """
        self.anchor = anchor
        self.dryrun = dryrun
        self.follow = follow
        self.old_cwd = None
        self.tmp_folder = None

    def __enter__(self):
        if self.dryrun is not None:
            self.dryrun = set_dryrun(self.dryrun)

        if not is_dryrun():
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
        if self.anchor:
            Anchored.pop(self.tmp_folder or SYMBOLIC_TMP)

        if self.old_cwd:
            os.chdir(self.old_cwd)

        if self.tmp_folder:
            shutil.rmtree(self.tmp_folder)

        if self.dryrun is not None:
            set_dryrun(self.dryrun)


def terminal_width(default=None):
    """Get the width (number of columns) of the terminal window.

    Args:
        default: Default to use if terminal width could not be determined

    Returns:
        (int): Determined terminal width, if possible
    """
    for func in (_tw_shutil, _tw_env):
        columns = func()
        if columns is not None:
            return columns

    return to_int(default)


def touch(path, fatal=True, logger=None):
    """Touch file with `path`

    Args:
        path (str | None): Path to file to touch
        fatal (bool | None): Abort execution on failure if True
        logger (callable | None): Logger to use

    Returns:
        (int): 1 if effectively done, 0 if no-op, -1 on failure
    """
    return write(path, None, fatal=fatal, logger=logger)


def write(path, contents, fatal=True, logger=None):
    """Write `contents` to file with `path`

    Args:
        path (str | None): Path to file
        contents (str | None): Contents to write (only touch file if None)
        fatal (bool | None): Abort execution on failure if True
        logger (callable | None): Logger to use

    Returns:
        (int): 1 if effectively done, 0 if no-op, -1 on failure
    """
    if not path:
        return 0

    path = resolved_path(path)
    if is_dryrun():
        action = "write %s bytes to" % len(contents) if contents else "touch"
        LOG.debug("Would %s %s", action, short(path))
        return 1

    ensure_folder(path, fatal=fatal, logger=logger)
    if logger and contents:
        logger("Writing %s bytes to %s", len(contents), short(path))

    try:
        with io.open(path, "wt") as fh:
            if contents is None:
                os.utime(path, None)

            else:
                fh.write(decode(contents))

        return 1

    except Exception as e:
        return abort("Can't write to %s: %s", short(path), e, fatal=(fatal, -1))


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


def _file_op(source, destination, func, adapter, fatal, logger, must_exist=True, ignore=None):
    """Call func(source, destination)

    Args:
        source (str | None): Source file or folder
        destination (str | None): Destination file or folder
        func (callable): Implementation function
        adapter (callable | None): Optional function to call on 'source' before copy
        fatal (bool | None): Abort execution on failure if True
        logger (callable | None): Logger to use
        must_exist (bool): If True, verify that source does indeed exist
        ignore (callable | list | str | None): Names to be ignored

    Returns:
        (int): 1 if effectively done, 0 if no-op, -1 on failure
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

    if is_dryrun():
        LOG.debug("Would %s %s %s %s", action, short(source), indicator, short(destination))
        return 1

    if must_exist and not os.path.exists(source):
        return abort("%s does not exist, can't %s to %s", short(source), action.title(), short(destination), fatal=(fatal, -1))

    try:
        # Ensure parent folder exists
        ensure_folder(destination, fatal=fatal, logger=None)

        if logger:
            note = adapter(source, destination, fatal=fatal, logger=logger) if adapter else ""
            if logger:
                logger("%s %s %s %s%s", action.title(), short(source), indicator, short(destination), note)

        if ignore is not None:
            if callable(ignore):
                func(source, destination, ignore=ignore)

            else:
                func(source, destination, ignore=lambda *_: ignore)

        else:
            func(source, destination)

        return 1

    except Exception as e:
        return abort("Can't %s %s %s %s: %s", action, short(source), indicator, short(destination), e, fatal=(fatal, -1))


def _tw_shutil():
    try:
        return shutil.get_terminal_size().columns

    except Exception:
        return None


def _tw_env():
    return to_int(os.environ.get("COLUMNS"))
