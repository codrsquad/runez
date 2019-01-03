import io
import os

from runez.base import decode, short, State
from runez.log import abort, debug
from runez.path import ensure_folder


TEXT_THRESHOLD_SIZE = 16384  # Max size in bytes to consider a file a "text file"


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
            if '#' in line:
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

    if State.dryrun:
        action = "write %s bytes to" % len(contents) if contents else "touch"
        debug("Would %s %s", action, short(path))
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
