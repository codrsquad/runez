"""
Convenience logging setup
"""

import logging
import os
import re
import signal
import sys
import threading

try:
    # faulthandler is only available in python 3.3+
    import faulthandler

except ImportError:
    faulthandler = None

from runez.base import flattened, get_timezone, prop, State
from runez.path import basename as get_basename, parent_folder
from runez.program import get_program_path


RE_FORMAT_MARKERS = re.compile(r"{([^}]*?)}")


def add_global_context(**values):
    """Add 'values' to global logging context"""
    Context.add_global_context(**values)


def set_global_context(**values):
    """Set global logging context to 'values'"""
    Context.set_global_context(**values)


def add_thread_context(**values):
    """Add 'values' to current thread's logging context"""
    Context.add_thread_context(**values)


def set_thread_context(**values):
    """Set thread logging context to 'values'"""
    Context.set_thread_context(**values)


def setup(debug=None, dryrun=None, location=None):
    """
    :param bool|None debug: Enable debug level logging
    :param bool|None dryrun: Enable dryrun
    :param str|None location: Optional custom location to use
    """
    Context.setup(debug, dryrun, location)


def enable_faulthandler(self, signum=signal.SIGUSR1):
    """
    Enable dumping thread stack traces when specified signals are received, similar to java's handling of SIGQUIT

    Note: this must be called from the surviving process in case of daemonization.
    Note that SIGQUIT does not work in all environments with a python process.

    :param int signum: Signal number to register for full thread stack dump
    """
    Context.enable_faulthandler(signum)


class Settings:
    """
    Settings to use, you can safely customize these, for example:

        runez.log.Settings.console_stream = sys.stdout
    """

    basename = get_basename(get_program_path())
    filename = "{basename}.log"

    level = logging.INFO
    console_stream = sys.stderr
    locations = ["{dev}/{filename}", "/logs/{basename}/{filename}", "/var/logs/{filename}"]
    rotate = None

    console_format = "%(asctime)s %(levelname)s %(message)s"
    file_format = "%(asctime)s %(timezone)s [%(threadName)s] %(context)s%(levelname)s - %(message)s"
    context_format = "[[%s]] "
    timezone = get_timezone()

    @prop
    def dev(cls):
        """
        :return str: Path to executable if running from a venv
        """
        return cls.find_dev(sys.prefix)

    @classmethod
    def formatted(cls, text):
        """
        :param str text: Text to format
        :return str: Attributes from this class are expanded if mentioned
        """
        if not text:
            return text
        values = {}
        markers = RE_FORMAT_MARKERS.findall(text)
        while markers:
            key = markers.pop()
            if key in values:
                continue
            val = getattr(cls, key, None)
            if val is None:
                return None
            markers.extend(m for m in RE_FORMAT_MARKERS.findall(val) if m not in values)
            values[key] = val
        for key, val in values.items():
            if '{' in val:
                values[key] = values[key].format(**values)
        return text.format(**values)

    @classmethod
    def find_dev(cls, path):
        """
        :param str path: Path to examine
        :return str|None: Path to development venv, if any
        """
        if not path or len(path) <= 4:
            return None
        dirpath, basename = os.path.split(path)
        if basename in ("venv", ".venv", ".tox"):
            return path
        return cls.find_dev(dirpath)

    @classmethod
    def resolved_location(cls, location=None):
        if location is not None:
            # Custom location typically provided via --config CLI flag
            location = cls.formatted(location)
            if os.path.isdir(location):
                return os.path.join(location, cls.formatted(cls.filename))
            return location
        if not cls.locations:
            # No locations configured
            return None
        for location in cls.locations:
            location = cls.usable_location(location)
            if location:
                return location

    @classmethod
    def usable_location(cls, location):
        """
        :param str location: Location to consider
        :return str|None: Full path if location is usable, None otherwise
        """
        location = cls.formatted(location)
        if not location:
            return None
        folder = parent_folder(location)
        if os.path.exists(folder):
            if os.path.isdir(folder):
                return location if os.access(folder, os.W_OK) else None
            return None
        parent = os.path.dirname(folder)
        if not os.path.isdir(parent):
            return None
        try:
            os.mkdir(folder)
            return location
        except (IOError, OSError):
            return None


def is_using_format(markers, used_formats):
    """
    :param str markers: Space separated list of markers to look for
    :param str used_formats: Formats to inspect
    :return bool: True if any one of the 'markers' is seen in 'used_formats'
    """
    if not markers or not used_formats:
        return False
    return any(marker in used_formats for marker in flattened(markers, separator=" ", unique=True))


class OriginalLogging:
    """
    Allows to isolate changes to logging setup.
    This should only be useful for testing (as in general, logging setup is a global thing)
    """

    level = logging.root.level
    _srcfile = logging._srcfile
    critical = logging.critical
    fatal = logging.fatal
    error = logging.error
    exception = logging.exception
    warning = logging.warning
    info = logging.info
    debug = logging.debug

    @classmethod
    def set_level(cls, level):
        """This function is useful for testing, to set logging level to debug basically"""
        if level is not None:
            old_level = OriginalLogging.level
            if level != OriginalLogging.level:
                OriginalLogging.level = level
            if level != logging.root.level:
                logging.root.setLevel(level)
            return old_level

    def __init__(self):
        self.__snapshot = None
        self.__level = self.level

    def __enter__(self):
        """Context manager to save and restore log setup, useful for testing"""
        self.__snapshot = {}
        for name, value in Settings.__dict__.items():
            if name.startswith("__") and name.endswith("__"):
                continue
            if not isinstance(value, classmethod):
                self.__snapshot[name] = value
        OriginalLogging.set_level(logging.DEBUG)
        if Settings.basename == "_jb_pytest_runner":
            Settings.basename = "pytest"
        return Context

    def __exit__(self, *_):
        if self.__snapshot:
            Context._reset()
            # Restore changes made to logging module
            OriginalLogging.set_level(self.__level)
            for name, value in OriginalLogging.__dict__.items():
                if not name.startswith("__") and hasattr(logging, name):
                    setattr(logging, name, value)
            # Restore changes made to Settings
            for name, value in self.__snapshot.items():
                setattr(Settings, name, value)
            for name in list(Settings.__dict__.keys()):
                if name.startswith("__") and not name.endswith("__"):
                    if name not in self.__snapshot:
                        delattr(Settings, name)


class Context:
    """
    Global logging context managed by runez.
    There's only one, as multiple contexts would not be useful (logging setup is a global thing)
    """

    lock = threading.RLock()
    level = None  # Current severity level
    hfile = None  # type: logging.FileHandler # File we're currently logging to (if any)
    handlers = None  # type: list[logging.StreamHandler]
    used_formats = None  # type: str
    faulthandler_signum = None  # type: int

    context_filter = None  # type: ContextFilter
    tpayload = None
    gpayload = None

    @classmethod
    def setup(cls, debug, dryrun, location):
        """
        :param bool debug: Enable debug level logging
        :param bool dryrun: Enable debug level logging
        :param str|None location: Optional custom location to use
        """
        with cls.lock:
            if cls.level is not None:
                raise Exception("Please call runez.log.setup() only once")
            if dryrun is not None:
                if dryrun and debug is None:
                    debug = True
                State.dryrun = dryrun
            cls.level = logging.DEBUG if debug else Settings.level or OriginalLogging.level
            logging.root.setLevel(cls.level)
            hconsole = cls.get_handler(logging.StreamHandler, Settings.console_format, Settings.console_stream)
            location = Settings.resolved_location(location)
            cls.hfile = cls.get_handler(logging.FileHandler, Settings.file_format, location)
            cls.handlers = [h for h in (hconsole, cls.hfile) if h is not None]
            cls.used_formats = " ".join(h.formatter._fmt for h in cls.handlers)

            if cls.is_using_format("%(context)s"):
                cls.enable_context_filtering()
            cls.optimize()
            if cls.context_filter:
                for handler in cls.handlers:
                    handler.addFilter(cls.context_filter)

    @classmethod
    def _reset(cls):
        """Reset logging as it was before setup(), no need to call this outside of testing, or some very special cases"""
        cls._disable_faulthandler()
        if cls.handlers is not None:
            for handler in cls.handlers:
                logging.root.removeHandler(handler)
        cls.level = None
        cls.hfile = None
        cls.handlers = None
        cls.used_formats = None
        cls.context_filter = None
        cls.tpayload = None
        cls.gpayload = None

    @classmethod
    def is_using_format(cls, markers):
        """Is current setup using any of the 'markers'?"""
        return is_using_format(markers, cls.used_formats)

    @classmethod
    def get_handler(cls, base, format, target):
        """
        :param type(logging.Handler) base: Handler implementation to use
        :param str|None format: Format to use
        :param str|None target: Target for handler
        :return logging.Handler|None:
        """
        if format and target:
            handler = base(target)
            handler.setFormatter(cls.get_formatter(format))
            handler.setLevel(cls.level)
            logging.root.addHandler(handler)
            return handler

    @classmethod
    def enable_faulthandler(cls, signum):
        """
        :param int|None signum: Signal number to register for full thread stack dump (use None to disable)
        """
        with cls.lock:
            if not signum:
                cls._disable_faulthandler()
                return
            if not cls.hfile or faulthandler is None:
                return
            cls.faulthandler_signum = signum
            dump_file = cls.hfile.stream
            faulthandler.enable(file=dump_file, all_threads=True)
            faulthandler.register(signum, file=dump_file, all_threads=True, chain=False)

    @classmethod
    def _disable_faulthandler(cls):
        if faulthandler and cls.faulthandler_signum:
            faulthandler.unregister(cls.faulthandler_signum)
            faulthandler.disable()
            cls.faulthandler_signum = None

    @classmethod
    def replace_and_pad(cls, format, marker, replacement):
        """
        :param str format: Format to tweak
        :param str marker: Marker to replace
        :param str replacement: What to replace marker with
        :return str: Resulting format, with marker replaced
        """
        if marker not in format:
            return format
        if replacement:
            return format.replace(marker, replacement)
        format = format.replace("%s " % marker, marker)
        return format.replace(marker, "")

    @classmethod
    def get_formatter(cls, format):
        """
        :param str format: Format specification
        :return logging.Formatter: Associated logging formatter
        """
        format = cls.replace_and_pad(format, "%(timezone)s", Settings.timezone)
        return logging.Formatter(format)

    @classmethod
    def optimize(cls):
        """
        Fix standard logging shortcuts to correctly report logging module.

        This is only useful if you:
        - actually use %(name) and care about it being correct
        - you would still like to use the logging.info() etc shortcuts

        So basically you'd like to write this:
            import logging
            logging.info("hello")

        Instead of this:
            import logging
            LOG = logging.getLogger(__name__)
            LOG.info("hello")
        """
        import inspect
        from functools import partial

        if not cls.is_using_format("%(name)d"):
            return
        if cls.is_using_format("%(pathname)s %(filename)s %(funcName)s %(module)s"):
            logging._srcfile = OriginalLogging._srcfile
        else:
            logging._srcfile = None
        logging.logProcesses = cls.is_using_format("%(process)d")
        logging.logThreads = cls.is_using_format("%(thread)d %(threadName)s")

        def log(level, msg, *args, **kwargs):
            """Wrapper to make logging.info() etc report the right module %(name)"""
            logging.getLogger(inspect.currentframe().f_back.f_globals["__name__"]).log(level, msg, *args, **kwargs)

        def wrap(level, **kwargs):
            """Wrap corresponding logging shortcut function"""
            if isinstance(level, int):
                original = getattr(logging, logging.getLevelName(level).lower())
                f = partial(log, level, **kwargs)
                f.__doc__ = original.__doc__
                return f
            f = partial(level, **kwargs)
            f.__doc__ = level.__doc__
            return f

        logging.critical = wrap(logging.CRITICAL)
        logging.fatal = logging.critical
        logging.error = wrap(logging.ERROR)
        logging.exception = partial(logging.error, exc_info=True)
        logging.warning = wrap(logging.WARNING)
        logging.info = wrap(logging.INFO)
        logging.debug = wrap(logging.DEBUG)

    @classmethod
    def enable_context_filtering(cls):
        """Enable contextual logging"""
        if cls.context_filter is None:
            cls.context_filter = ContextFilter()

    @classmethod
    def context_dict(cls):
        """
        :return dict: Combined global and thread-specific logging context
        """
        result = {}
        if cls.gpayload:
            result.update(cls.gpayload)
        if cls.tpayload:
            result.update(getattr(cls.tpayload, "context", {}))
        return result

    @classmethod
    def set_thread_context(cls, **values):
        """Set current thread's logging context to 'values'"""
        if cls.tpayload is None:
            cls.tpayload = threading.local()
        cls.tpayload.context = values
        cls.enable_context_filtering()

    @classmethod
    def set_global_context(cls, **values):
        """Set global logging context to 'values'"""
        cls.gpayload = values
        cls.enable_context_filtering()

    @classmethod
    def add_thread_context(cls, **values):
        """Add 'values' to current thread's logging context"""
        if cls.tpayload is None:
            cls.tpayload = threading.local()
        if getattr(cls.tpayload, "context", None) is None:
            cls.tpayload.context = {}
        cls.tpayload.context.update(**values)
        cls.enable_context_filtering()

    @classmethod
    def add_global_context(cls, **values):
        """Add 'values' to global logging context"""
        if cls.gpayload is None:
            cls.gpayload = {}
        cls.gpayload.update(**values)
        cls.enable_context_filtering()

    @classmethod
    def remove_thread_context(cls, name):
        """Remove entry with 'name' from current thread's context"""
        if cls.tpayload is not None:
            c = getattr(cls.tpayload, "context", None)
            if c and name in c:
                del c[name]

    @classmethod
    def remove_global_context(cls, name):
        """Remove entry with 'name' from global context"""
        if cls.gpayload and name in cls.gpayload:
            del cls.gpayload[name]

    @classmethod
    def clear_thread_context(cls):
        """Clear current thread's context"""
        if cls.tpayload is not None:
            cls.tpayload.context = {}

    @classmethod
    def clear_global_context(cls):
        """Clear global context"""
        if cls.gpayload is not None:
            cls.gpayload = None


def rendered_context(data):
    """
    :param dict data:
    :return str:
    """
    if data and Settings.context_format:
        return Settings.context_format % ",".join("%s=%s" % (key, val) for key, val in sorted(data.items()) if key and val)
    return ""


class ContextFilter(logging.Filter):
    """
    Optional logging filter allowing to inject key/value pairs to every log record.

    In order to activate this:
    - Mention %(context)s in your log format
    - Add key/value pairs via runez.log.add_global_context(), runez.log.add_thread_context()
    """

    def filter(self, record):
        """Determines if the record should be logged and injects context info into the record. Always returns True"""
        record.context = rendered_context(Context.context_dict())
        return True
