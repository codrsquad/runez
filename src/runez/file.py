import io
import os
import shutil
import tempfile
import time

from runez.path import ensure_folder, parent_folder
from runez.system import _LateImport, abort, Anchored, decode, LOG, resolved_path, short, SYMBOLIC_TMP, UNSET


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

    if _LateImport.is_dryrun():
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


def ini_to_dict(data, keep_empty=False, default=None):
    """Contents of an INI-style config file as a dict of dicts: section -> key -> value

    Args:
        data (str | file | TextIO | list | None): Path to file, or file object, or lines to parse
        keep_empty (bool): If True, keep definitions with empty values
        default (dict | None): Object to return if conf couldn't be read

    Returns:
        (dict): Dict of section -> key -> value
    """
    if not data:
        return default

    result = {}
    try:
        section_key = None
        section = None
        for line in readlines(data):
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

    except (OSError, IOError):
        return default

    if not keep_empty:
        result = dict((k, v) for k, v in result.items() if k and v)

    return result


def is_younger(path, age):
    """
    Args:
        path (str): Path to file
        age (int | float): How many seconds to consider the file too old

    Returns:
        (bool): True if file exists and is younger than 'age' seconds
    """
    try:
        return time.time() - os.path.getmtime(path) < age

    except (OSError, IOError, TypeError):
        return False


def readlines(data, first=None, errors=None, fatal=UNSET, logger=UNSET):
    """Yield the `first` N lines from `data`

    Args:
        data (str | file | TextIO | list): Path to file, or object to return lines from
        first (int | None): Return only the 'first' lines when specified
        errors (str | None): Optional string specifying how encoding errors are to be handled
        fatal (bool): If True: abort() on error, if UNSET: pass-through original exception
        logger (callable | None): Logger to use to report crashes
    """
    try:
        if isinstance(data, list):
            for line in _readlines(data, first):
                yield line

            return

        if hasattr(data, "readline"):
            for line in _readlines(data, first):
                yield line

            return

        path = resolved_path(data)
        with io.open(path, errors=errors) as fh:
            for line in _readlines(fh, first):
                yield line

    except Exception as e:
        if fatal is UNSET:
            raise

        if fatal:
            abort("Can't readlines() from %s: %s", short(data), e, fatal=fatal, logger=logger)


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
            self.dryrun = _LateImport.set_dryrun(self.dryrun)

        if not _LateImport.is_dryrun():
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
            _LateImport.set_dryrun(self.dryrun)


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
    if _LateImport.is_dryrun():
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

    if _LateImport.is_dryrun():
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


def _readlines(data, first):
    if not first:
        first = -1

    for line in data:
        line = decode(line).rstrip()
        if first == 0:
            return

        first -= 1
        yield line
