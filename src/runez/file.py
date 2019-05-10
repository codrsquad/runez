import io
import logging
import os
import shutil

from runez.base import decode
from runez.convert import resolved_path, short
from runez.path import ensure_folder, parent_folder
from runez.system import abort, is_dryrun

LOG = logging.getLogger(__name__)
TEXT_THRESHOLD_SIZE = 16384  # Max size in bytes to consider a file a "text file"


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
    :param str|None path: Path to file or folder to delete
    :param bool|None fatal: Abort execution on failure if True
    :param callable|None logger: Logger to use
    :return int: 1 if effectively done, 0 if no-op, -1 on failure
    """
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


def first_line(path):
    """
    :param str|None path: Path to file
    :return str|None: First line of file, if any
    """
    try:
        with io.open(path, "rt", errors="ignore") as fh:
            return fh.readline().strip()

    except (IOError, TypeError):
        return None


def get_conf(path, fatal=True, keep_empty=False, default=None):
    """
    :param str|list|None path: Path to file, or lines to parse
    :param bool|None fatal: Abort execution on failure if True
    :param bool keep_empty: If True, keep definitions with empty values
    :param dict|list|None default: Object to return if conf couldn't be read
    :return dict: Dict of section -> key -> value
    """
    if not path:
        return default

    lines = path if isinstance(path, list) else get_lines(path, fatal=fatal, default=default)

    result = default
    if lines is not None:
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


def get_lines(path, max_size=TEXT_THRESHOLD_SIZE, fatal=True, default=None):
    """
    :param str|None path: Path of text file to return lines from
    :param int|None max_size: Return contents only for files smaller than 'max_size' bytes
    :param bool|None fatal: Abort execution on failure if True
    :param list|None default: Object to return if lines couldn't be read
    :return list|None: Lines from file contents
    """
    if not path or not os.path.isfile(path) or (max_size and os.path.getsize(path) > max_size):
        # Intended for small text files, pretend no contents for binaries
        return default

    try:
        with io.open(path, "rt", errors="ignore") as fh:
            return fh.readlines()

    except Exception as e:
        return abort("Can't read %s: %s", short(path), e, fatal=(fatal, default))


def move(source, destination, adapter=None, fatal=True, logger=LOG.debug):
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


def symlink(source, destination, adapter=None, must_exist=True, fatal=True, logger=LOG.debug):
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
    return _file_op(source, destination, _symlink, adapter, fatal, logger, must_exist=must_exist)


def touch(path, fatal=True, logger=None):
    """
    :param str|None path: Path to file to touch
    :param bool|None fatal: Abort execution on failure if True
    :param callable|None logger: Logger to use
    """
    return write(path, "", fatal=fatal, logger=logger)


def write(path, contents, fatal=True, logger=None):
    """
    :param str|None path: Path to file
    :param str|None contents: Contents to write
    :param bool|None fatal: Abort execution on failure if True
    :param callable|None logger: Logger to use
    :return int: 1 if effectively done, 0 if no-op, -1 on failure
    """
    if not path:
        return 0

    if is_dryrun():
        action = "write %s bytes to" % len(contents) if contents else "touch"
        LOG.debug("Would %s %s", action, short(path))
        return 1

    ensure_folder(path, fatal=fatal, logger=logger)
    if logger and contents:
        logger("Writing %s bytes to %s", len(contents), short(path))

    try:
        with io.open(path, "wt") as fh:
            if contents:
                fh.write(decode(contents))
            else:
                os.utime(path, None)
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
