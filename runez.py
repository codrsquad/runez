"""
Convenience methods for file/process operations
"""

import io
import json
import logging
import os
import shutil
import subprocess  # nosec
import sys
import tempfile
import time

try:
    import StringIO
    StringIO = StringIO.StringIO

except ImportError:
    StringIO = io.StringIO

try:
    string_type = basestring  # noqa

except NameError:
    string_type = str
    unicode = str


LOG = logging.getLogger(__name__)
HOME = os.path.expanduser("~")
SYMBOLIC_TMP = "<tmp>"
DRYRUN = False
TEXT_THRESHOLD_SIZE = 16384  # Max size in bytes to consider a file a "text file"


class State:
    """Helps track state without using globals"""

    anchors = []  # Folder paths that can be used to shorten paths, via short()

    output = True  # print() warning/error messages (can be turned off when/if we have a logger to console for example)
    testing = False  # print all messages instead of logging (useful when running tests)
    logging = False  # Set to True if logging was setup


class CurrentFolder:
    """Context manager for changing the current working directory"""

    def __init__(self, destination, anchor=False):
        self.anchor = anchor
        self.destination = resolved_path(destination)

    def __enter__(self):
        self.current_folder = os.getcwd()
        os.chdir(self.destination)
        if self.anchor:
            add_anchors(self.destination)

    def __exit__(self, *_):
        os.chdir(self.current_folder)
        if self.anchor:
            pop_anchors(self.destination)


class Anchored:
    """Context manager for changing the current working directory"""

    def __init__(self, folder):
        self.folder = resolved_path(folder)

    def __enter__(self):
        add_anchors(self.folder)

    def __exit__(self, *_):
        pop_anchors(self.folder)


class TempFolder:
    """Context manager for obtaining a temp folder"""

    def __init__(self, anchor=True):
        self.anchor = anchor
        self.dryrun = DRYRUN
        self.tmp_folder = None

    def __enter__(self):
        self.tmp_folder = SYMBOLIC_TMP if self.dryrun else tempfile.mkdtemp()
        if self.anchor:
            add_anchors(self.tmp_folder)
        return self.tmp_folder

    def __exit__(self, *_):
        if self.anchor:
            pop_anchors(self.tmp_folder)
        if self.dryrun:
            debug("Would delete %s", self.tmp_folder)
        else:
            delete(self.tmp_folder)


class CaptureOutput:
    """
    Context manager allowing to temporarily grab stdout/stderr output.
    Output is captured and made available only for the duration of the context.

    Sample usage:

    with CaptureOutput() as output:
        # do something that generates output
        # output is available in 'output'
    """

    def __init__(self, stdout=True, stderr=True, anchors=None, dryrun=None):
        """
        :param bool stdout: Capture stdout
        :param bool stderr: Capture stderr
        :param str|list anchors: Optional paths to use as anchors for short()
        :param bool|None dryrun: Override dryrun (when explicitly specified, ie not None)
        """
        self.anchors = anchors
        self.dryrun = dryrun
        self.old_out = sys.stdout
        self.old_err = sys.stderr
        self.old_handlers = logging.root.handlers

        self.out_buffer = StringIO() if stdout else None

        if stderr:
            self.err_buffer = StringIO()
            self.handler = logging.StreamHandler(stream=self.err_buffer)
            self.handler.setLevel(logging.DEBUG)
            self.handler.setFormatter(logging.Formatter("%(levelname)s - %(message)s"))
        else:
            self.err_buffer = None
            self.handler = None

    def pop(self):
        """Current contents popped, useful for testing"""
        r = self.__repr__()
        if self.out_buffer:
            self.out_buffer.seek(0)
            self.out_buffer.truncate(0)
        if self.err_buffer:
            self.err_buffer.seek(0)
            self.err_buffer.truncate(0)
        return r

    def __repr__(self):
        result = ""
        if self.out_buffer:
            result += decode(self.out_buffer.getvalue())
        if self.err_buffer:
            result += decode(self.err_buffer.getvalue())
        return result

    def __enter__(self):
        if self.out_buffer:
            sys.stdout = self.out_buffer
        if self.err_buffer:
            sys.stderr = self.err_buffer
        if self.handler:
            logging.root.handlers = [self.handler]

        if self.anchors:
            add_anchors(self.anchors)

        if self.dryrun is not None:
            global DRYRUN
            (DRYRUN, self.dryrun) = (bool(self.dryrun), bool(DRYRUN))

        return self

    def __exit__(self, *args):
        sys.stdout = self.old_out
        sys.stderr = self.old_err
        self.out_buffer = None
        self.err_buffer = None
        logging.root.handlers = self.old_handlers

        if self.anchors:
            pop_anchors(self.anchors)

        if self.dryrun is not None:
            global DRYRUN
            DRYRUN = self.dryrun

    def __contains__(self, item):
        return item is not None and item in str(self)

    def __len__(self):
        return len(str(self))


class JsonSerializable:
    """
    Json serializable object
    """

    _path = None  # type: str # Path where this file should be stored, if any
    _source = None  # type: str # Where data came from

    def __repr__(self):
        return self._source or "no source"

    @classmethod
    def from_json(cls, path, fatal=True, logger=None):
        """
        :param str path: Path to json file
        :param bool|None fatal: Abort execution on failure if True
        :param callable|None logger: Logger to use
        :return cls: Deserialized object
        """
        result = cls()
        result.load(path, fatal=fatal, logger=logger)
        return result

    def set_from_dict(self, data, source=None):
        """
        :param dict data: Set this object from deserialized 'dict'
        :param source: Source where 'data' came from
        """
        if source:
            self._source = source
        if not data:
            return
        for key, value in data.items():
            key = key.replace("-", "_")
            if not hasattr(self, key):
                debug("%s is not an attribute of %s", key, self.__class__.__name__)
                continue
            attr = getattr(self, key)
            if attr is not None and not same_type(value, attr):
                debug(
                    "Wrong type '%s' for %s.%s in %s, expecting '%s'", type_name(value), type_name(self), key, self._source, type_name(attr)
                )
                continue
            setattr(self, key, value)

    def reset(self):
        """
        Reset all fields of this object to class defaults
        """
        for name in self.__dict__:
            if name.startswith("_"):
                continue
            attr = getattr(self, name)
            setattr(self, name, attr and attr.__class__())

    def to_dict(self):
        """
        :return dict: This object serialized to a dict
        """
        result = {}
        for name in self.__dict__:
            if name.startswith("_"):
                continue
            attr = getattr(self, name)
            result[name.replace("_", "-")] = attr.to_dict() if hasattr(attr, "to_dict") else attr
        return result

    def load(self, path=None, fatal=True, logger=None):
        """
        :param str|None path: Load this object from file with 'path' (default: self._path)
        :param bool|None fatal: Abort execution on failure if True
        :param callable|None logger: Logger to use
        """
        self.reset()
        if path:
            self._path = path
            self._source = short(path)
        if self._path:
            self.set_from_dict(read_json(self._path, default={}, fatal=fatal, logger=logger))

    def save(self, path=None, fatal=True, logger=None, sort_keys=True, indent=2):
        """
        :param str|None path: Save this serializable to file with 'path' (default: self._path)
        :param bool|None fatal: Abort execution on failure if True
        :param callable|None logger: Logger to use
        :param int indent: Indentation to use
        """
        data = self.to_dict()
        path = path or self._path
        return save_json(data, path, fatal=fatal, logger=logger, sort_keys=sort_keys, indent=indent)


def type_name(value):
    """
    :param value: Some object, or None
    :return str: Class name implementing 'value'
    """
    if value is None:
        return "None"
    if isinstance(value, string_type):
        return "str"
    return value.__class__.__name__


def same_type(t1, t2):
    """
    :return bool: True if 't1' and 't2' are of equivalent types
    """
    if isinstance(t1, string_type) and isinstance(t2, string_type):
        return True
    return type(t1) == type(t2)


def decode(value):
    """Python 2/3 friendly decoding of output"""
    if isinstance(value, bytes) and not isinstance(value, str):
        return value.decode("utf-8")
    return unicode(value)


def get_version(mod, default="0.0.0", fatal=True):
    """
    :param module|str mod: Module, or module name to find version for (pass either calling module, or its .__name__)
    :param str default: Value to return if version determination fails
    :param bool|None fatal: Abort execution on failure if True
    :return str: Determined version
    """
    name = mod
    if hasattr(mod, "__name__"):
        name = mod.__name__

    try:
        import pkg_resources
        return pkg_resources.get_distribution(name).version

    except Exception as e:
        return abort("Can't determine version for %s: %s", name, e, exc_info=e, fatal=(fatal, default))


def resolved_path(path, base=None):
    """
    :param str|None path: Path to resolve
    :param str|None base: Base path to use to resolve relative paths (default: current working dir)
    :return str: Absolute path
    """
    if not path or path.startswith(SYMBOLIC_TMP):
        return path
    path = os.path.expanduser(path)
    if base and not os.path.isabs(path):
        return os.path.join(resolved_path(base), path)
    return os.path.abspath(path)


def set_anchors(anchors):
    """
    :param str|list anchors: Optional paths to use as anchors for short()
    """
    State.anchors = sorted(flattened(anchors, unique=True), reverse=True)


def add_anchors(anchors):
    """
    :param str|list anchors: Optional paths to use as anchors for short()
    """
    set_anchors(State.anchors + [anchors])


def pop_anchors(anchors):
    """
    :param str|list anchors: Optional paths to use as anchors for short()
    """
    for anchor in flattened(anchors):
        if anchor in State.anchors:
            State.anchors.remove(anchor)


def short(path):
    """
    Example:
        short("examined /Users/joe/foo") => "examined ~/foo"

    :param path: Path to represent in its short form
    :return str: Short form, using '~' if applicable
    """
    if not path:
        return path

    path = str(path)
    if State.anchors:
        for p in State.anchors:
            if p:
                path = path.replace(p + "/", "")

    path = path.replace(HOME, "~")
    return path


def parent_folder(path, base=None):
    """
    :param str|None path: Path to file or folder
    :param str|None base: Base folder to use for relative paths (default: current working dir)
    :return str: Absolute path of parent folder of 'path'
    """
    return path and os.path.dirname(resolved_path(path, base=base))


def flatten(result, value, separator=None, unique=True):
    """
    :param list result: Flattened values
    :param value: Possibly nested arguments (sequence of lists, nested lists)
    :param str|None separator: Split values with 'separator' if specified
    :param bool unique: If True, return unique values only
    """
    if not value:
        # Convenience: allow to filter out --foo None easily
        if value is None and not unique and result and result[-1].startswith("-"):
            result.pop(-1)
        return
    if isinstance(value, (list, tuple, set)):
        for item in value:
            flatten(result, item, separator=separator, unique=unique)
        return
    if separator is not None and hasattr(value, "split") and separator in value:
        flatten(result, value.split(separator), separator=separator, unique=unique)
        return
    if not unique or value not in result:
        result.append(value)


def flattened(value, separator=None, unique=True):
    """
    :param value: Possibly nested arguments (sequence of lists, nested lists)
    :param str|None separator: Split values with 'separator' if specified
    :param bool unique: If True, return unique values only
    :return list: 'value' flattened out (leaves from all involved lists/tuples)
    """
    result = []
    flatten(result, value, separator=separator, unique=unique)
    return result


def quoted(text):
    """
    :param str text: Text to optionally quote
    :return str: Quoted if 'text' contains spaces
    """
    if text and " " in text:
        sep = "'" if '"' in text else '"'
        return "%s%s%s" % (sep, text, sep)
    return text


def represented_args(args, separator=" "):
    """
    :param list|tuple args: Arguments to represent
    :param str separator: Separator to use
    :return str: Quoted as needed textual representation
    """
    result = []
    if args:
        for text in args:
            result.append(quoted(short(text)))
    return separator.join(result)


def to_int(text, default=None):
    """
    :param text: Value to convert
    :param int|None default: Default to use if 'text' can't be parsed
    :return int:
    """
    try:
        return int(text)
    except (TypeError, ValueError):
        return default


def debug(message, *args, **kwargs):
    """Same as logging.debug(), but more convenient when testing"""
    if State.logging:
        LOG.debug(message, *args, **kwargs)
    if State.testing:
        print(message % args)


def info(message, *args, **kwargs):
    """
    Often, an info() message should be logged, but also shown to user (in the even where logging is not done to console)

    Example:
        info("...") => Will log if we're logging, but also print() if State.output is currently set
        info("...", output=False) => Will only log, never print
        info("...", output=True) => Will log if we're logging, and print
    """
    output = kwargs.pop("output", State.output)
    if State.logging:
        LOG.info(message, *args, **kwargs)
    if output or State.testing:
        print(message % args)


def warning(message, *args, **kwargs):
    """Same as logging.warning(), but more convenient when testing, similar to info()"""
    if State.logging:
        LOG.warning(message, *args, **kwargs)
    if State.output or State.testing:
        print("WARNING: %s" % (message % args))


def error(message, *args, **kwargs):
    """Same as logging.error(), but more convenient when testing, similar to info()"""
    if State.logging:
        LOG.error(message, *args, **kwargs)
    if State.output or State.testing:
        print("ERROR: %s" % (message % args))


def abort(*args, **kwargs):
    """
    Usage:
        return abort("...") => will sys.exit() by default
        return abort("...", fatal=True) => Will sys.exit()

        # Not fatal, but will log/print message:
        return abort("...", fatal=False) => Will return False
        return abort("...", fatal=(False, None)) => Will return None
        return abort("...", fatal=(False, -1)) => Will return -1

        # Not fatal, will not log/print any message:
        return abort("...", fatal=None) => Will return None
        return abort("...", fatal=(None, None)) => Will return None
        return abort("...", fatal=(None, -1)) => Will return -1

    :param args: Args passed through for error reporting
    :param kwargs: Args passed through for error reporting
    :return: kwargs["return_value"] (default: -1) to signify failure to non-fatal callers
    """
    code = kwargs.pop("code", 1)
    logger = kwargs.pop("logger", error if code else info)
    fatal = kwargs.pop("fatal", True)
    return_value = fatal
    if isinstance(fatal, tuple) and len(fatal) == 2:
        fatal, return_value = fatal
    if logger and fatal is not None and args:
        logger(*args, **kwargs)
    if fatal:
        sys.exit(code)
    return return_value


def ensure_folder(path, folder=False, fatal=True, logger=debug):
    """
    :param str|None path: Path to file or folder
    :param bool folder: If True, 'path' refers to a folder (file otherwise)
    :param bool|None fatal: Abort execution on failure if True
    :param callable|None logger: Logger to use
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

    if DRYRUN:
        debug("Would create %s", short(folder))
        return 1

    try:
        os.makedirs(folder)
        if logger:
            logger("Created folder %s", short(folder))
        return 1

    except Exception as e:
        return abort("Can't create folder %s: %s", short(folder), e, fatal=(fatal, -1))


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


def file_younger(path, age):
    """
    :param str|None path: Path to file
    :param int|float age: How many seconds to consider the file too old
    :return bool: True if file exists and is younger than 'age' seconds
    """
    try:
        return time.time() - os.path.getmtime(path) < age

    except (OSError, TypeError):
        return False


def check_pid(pid):
    """Check For the existence of a unix pid"""
    try:
        os.kill(pid, 0)
        return True
    except (OSError, TypeError):
        return False


def touch(path, fatal=True, logger=None):
    """
    :param str|None path: Path to file to touch
    :param bool|None fatal: Abort execution on failure if True
    :param callable|None logger: Logger to use
    """
    return write_contents(path, "", fatal=fatal, logger=logger)


def write_contents(path, contents, fatal=True, logger=None):
    """
    :param str|None path: Path to file
    :param str|None contents: Contents to write
    :param bool|None fatal: Abort execution on failure if True
    :param callable|None logger: Logger to use
    :return int: 1 if effectively done, 0 if no-op, -1 on failure
    """
    if not path:
        return 0

    if DRYRUN:
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


def read_json(path, default=None, fatal=True, logger=None):
    """
    :param str|None path: Path to file to deserialize
    :param dict|list|None default: Default if file is not present, or if it's not json
    :param bool|None fatal: Abort execution on failure if True
    :param callable|None logger: Logger to use
    :return dict|list: Deserialized data from file
    """
    if not path:
        return default

    path = resolved_path(path)
    if not path or not os.path.exists(path):
        if default is None:
            return abort("No file %s", short(path), fatal=(fatal, default))
        return default

    try:
        with io.open(path, "rt") as fh:
            data = json.load(fh)
            if default is not None and type(data) != type(default):
                return abort("Wrong type %s for %s, expecting %s", type(data), short(path), type(default), fatal=(fatal, default))
            if logger:
                logger("Read %s", short(path))
            return data

    except Exception as e:
        return abort("Couldn't read %s: %s", short(path), e, fatal=(fatal, default))


def save_json(data, path, fatal=True, logger=None, sort_keys=True, indent=2):
    """
    :param dict|list|None data: Data to serialize and save
    :param str|None path: Path to file where to save
    :param bool|None fatal: Abort execution on failure if True
    :param callable|None logger: Logger to use
    :param bool sort_keys: Save json with sorted keys
    :param int indent: Indentation to use
    """
    if data is None or not path:
        return 0

    try:
        path = resolved_path(path)
        ensure_folder(path, fatal=fatal, logger=None)
        if DRYRUN:
            debug("Would save %s", short(path))
            return 1

        if hasattr(data, "to_dict"):
            data = data.to_dict()

        with open(path, "wt") as fh:
            json.dump(data, fh, sort_keys=sort_keys, indent=indent)
            fh.write("\n")

        if logger:
            logger("Saved %s", short(path))

        return 1

    except Exception as e:
        return abort("Couldn't save %s: %s", short(path), e, fatal=(fatal, -1))


def copy(source, destination, adapter=None, fatal=True, logger=debug):
    """
    Copy source -> destination

    :param str|None source: Source file or folder
    :param str|None destination: Destination file or folder
    :param callable adapter: Optional function to call on 'source' before copy
    :param bool|None fatal: Abort execution on failure if True
    :param callable|None logger: Logger to use
    :return int: 1 if effectively done, 0 if no-op, -1 on failure
    """
    return _file_op(source, destination, _copy, adapter, fatal, logger)


def move(source, destination, adapter=None, fatal=True, logger=debug):
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


def symlink(source, destination, adapter=None, must_exist=True, fatal=True, logger=debug):
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
    return _file_op(source, destination, _symlink, adapter,  fatal, logger, must_exist=must_exist)


def _copy(source, destination):
    """Effective copy"""
    if os.path.isdir(source):
        shutil.copytree(source, destination, symlinks=True)
    else:
        shutil.copy(source, destination)

    shutil.copystat(source, destination)  # Make sure last modification time is preserved


def _move(source, destination):
    """Effective move"""
    shutil.move(source, destination)


def _symlink(source, destination):
    """Effective symlink"""
    os.symlink(source, destination)


def _file_op(source, destination, func, adapter, fatal, logger, must_exist=True):
    """
    Call func(source, destination)

    :param str|None source: Source file or folder
    :param str|None destination: Destination file or folder
    :param callable func: Implementation function
    :param callable adapter: Optional function to call on 'source' before copy
    :param bool|None fatal: Abort execution on failure if True
    :param callable|None logger: Logger to use
    :param bool must_exist: If True, verify that source does indeed exist
    :return int: 1 if effectively done, 0 if no-op, -1 on failure
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

    if DRYRUN:
        debug("Would %s %s %s %s", action, short(source), indicator, short(destination))
        return 1

    if must_exist and not os.path.exists(source):
        return abort("%s does not exist, can't %s to %s", short(source), action.title(), short(destination), fatal=(fatal, -1))

    try:
        # Delete destination, but ensure that its parent folder exists
        delete(destination, fatal=fatal, logger=None)
        ensure_folder(destination, fatal=fatal, logger=None)

        if logger:
            note = adapter(source, destination, fatal=fatal, logger=logger) if adapter else ""
            if logger:
                logger("%s %s %s %s%s", action.title(), short(source), indicator, short(destination), note)

        func(source, destination)
        return 1

    except Exception as e:
        return abort("Can't %s %s %s %s: %s", action, short(source), indicator, short(destination), e, fatal=(fatal, -1))


def delete(path, fatal=True, logger=debug):
    """
    :param str|None path: Path to file or folder to delete
    :param bool|None fatal: Abort execution on failure if True
    :param callable|None logger: Logger to use
    :return int: 1 if effectively done, 0 if no-op, -1 on failure
    """
    islink = path and os.path.islink(path)
    if not islink and (not path or not os.path.exists(path)):
        return 0

    if DRYRUN:
        debug("Would delete %s", short(path))
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


def make_executable(path, fatal=True):
    """
    :param str|None path: chmod file with 'path' as executable
    :param bool|None fatal: Abort execution on failure if True
    :return int: 1 if effectively done, 0 if no-op, -1 on failure
    """
    if is_executable(path):
        return 0

    if DRYRUN:
        debug("Would make %s executable", short(path))
        return 1

    if not os.path.exists(path):
        return abort("%s does not exist, can't make it executable", short(path), fatal=(fatal, -1))

    try:
        os.chmod(path, 0o755)  # nosec
        return 1

    except Exception as e:
        return abort("Can't chmod %s: %s", short(path), e, fatal=(fatal, -1))


def is_executable(path):
    """
    :param str|None path: Path to file
    :return bool: True if file exists and is executable
    """
    return path and os.path.isfile(path) and os.access(path, os.X_OK)


def which(program, ignore_own_venv=False):
    """
    :param str program: Program name to find via env var PATH
    :param bool ignore_own_venv: If True, do not resolve to executables in current venv
    :return str|None: Full path to program, if one exists and is executable
    """
    if not program:
        return None
    if os.path.isabs(program):
        return program if is_executable(program) else None
    for p in os.environ.get("PATH", "").split(":"):
        fp = os.path.join(p, program)
        if (not ignore_own_venv or not fp.startswith(sys.prefix)) and is_executable(fp):
            return fp
    return None


def run_program(program, *args, **kwargs):
    """Run 'program' with 'args'"""
    args = flattened(args, unique=False)
    full_path = which(program)

    logger = kwargs.pop("logger", debug)
    fatal = kwargs.pop("fatal", True)
    dryrun = kwargs.pop("dryrun", DRYRUN)
    include_error = kwargs.pop("include_error", False)

    message = "Would run" if dryrun else "Running"
    message = "%s: %s %s" % (message, short(full_path or program), represented_args(args))
    if logger:
        logger(message)

    if dryrun:
        return message

    if not full_path:
        return abort("%s is not installed", short(program), fatal=fatal)

    stdout = kwargs.pop("stdout", subprocess.PIPE)
    stderr = kwargs.pop("stderr", subprocess.PIPE)
    args = [full_path] + args
    try:
        path_env = kwargs.pop("path_env", None)
        if path_env:
            kwargs["env"] = added_env_paths(path_env, env=kwargs.get("env"))
        p = subprocess.Popen(args, stdout=stdout, stderr=stderr, **kwargs)  # nosec
        output, err = p.communicate()
        output = decode(output)
        err = decode(err)
        if output is not None:
            output = output.strip()
        if err is not None:
            err = err.strip()

        if p.returncode and fatal is not None:
            note = ": %s\n%s" % (err, output) if output or err else ""
            message = "%s exited with code %s%s" % (short(program), p.returncode, note.strip())
            return abort(message, fatal=fatal)

        if include_error and err:
            output = "%s\n%s" % (output, err)
        return output and output.strip()

    except Exception as e:
        return abort("%s failed: %s", short(program), e, exc_info=e, fatal=fatal)


def added_env_paths(env_vars, env=None):
    """
    :param dict env_vars: Env vars to customize
    :param dict env: Original env vars
    """
    if not env_vars:
        return None
    if not env:
        env = dict(os.environ)
    result = dict(env)
    for env_var, paths in env_vars.items():
        separator = paths[0]
        paths = paths[1:]
        current = env.get(env_var, "")
        current = [x for x in current.split(separator) if x]
        added = 0
        for path in paths.split(separator):
            if path not in current:
                added += 1
                current.append(path)
        if added:
            result[env_var] = separator.join(current)
    return result


def verify_abort(func, *args, **kwargs):
    """
    Convenient wrapper around functions that should exit or raise an exception

    Example:
        assert "Can't create folder" in verify_abort(ensure_folder, "/dev/null/foo")

    :param callable func: Function to execute
    :param args: Args to pass to 'func'
    :param Exception expected_exception: Type of exception that should be raised
    :param kwargs: Named args to pass to 'func'
    :return str: Chatter from call to 'func', if it did indeed raise
    """
    expected_exception = kwargs.pop("expected_exception", SystemExit)
    with CaptureOutput() as logged:
        try:
            func(*args, **kwargs)
            return None
        except expected_exception:
            return str(logged)
