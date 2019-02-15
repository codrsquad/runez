"""
Convenience logging setup
"""

import logging
import os
import signal
import sys
import threading

try:
    # faulthandler is only available in python 3.3+
    import faulthandler

except ImportError:
    faulthandler = None

from runez.base import get_timezone, prop
from runez.path import basename as get_basename
from runez.program import get_program_path


class OriginalLogging:
    """Original logging state, before we made any changes"""

    __snapshot = None
    level = logging.root.level
    _srcfile = logging._srcfile
    critical = logging.critical
    fatal = logging.fatal
    error = logging.error
    exception = logging.exception
    warning = logging.warning
    info = logging.info
    debug = logging.debug

    def __init__(self):
        self.__snapshot = None

    def __enter__(self):
        self.__snapshot = {}
        for name, value in Settings.__dict__.items():
            if name.startswith("__") and name.endswith("__"):
                continue
            if not isinstance(value, classmethod):
                self.__snapshot[name] = value

    def __exit__(self, *_):
        SETUP.reset()
        if self.__snapshot:
            for name, value in self.__snapshot.items():
                setattr(Settings, name, value)
            for name in list(Settings.__dict__.keys()):
                if name.startswith("__") and not name.endswith("__"):
                    if name not in self.__snapshot:
                        delattr(Settings, name)


def add_global_context(**values):
    """Add 'values' to global logging context"""
    SETUP.context.add_global(**values)


def set_global_context(**values):
    """Set global logging context to 'values'"""
    SETUP.context.set_global(**values)


def add_thread_context(**values):
    """Add 'values' to current thread's logging context"""
    SETUP.context.add(**values)


def setup(debug=None, dryrun=None, custom_location=None):
    """
    :param bool|None debug: Enable debug level logging
    :param bool|None dryrun: Enable dryrun
    :param str|None custom_location: Optional custom location to use
    """
    SETUP.setup(debug, dryrun, custom_location)


def enable_faulthandler(self, signum=signal.SIGUSR1):
    """
    Enable dumping thread stack traces when specified signals are received, similar to java's handling of SIGQUIT

    Note: this must be called from the surviving process in case of daemonization.
    Note that SIGQUIT does not work in all environments with a python process.

    :param int signum: Signal number to register for full thread stack dump
    """
    SETUP.enable_faulthandler(signum)


class Settings:
    """
    Settings to use, you can safely customize these, for example:

        runez.log.Settings.console_stream = sys.stdout
    """

    basename = get_basename(get_program_path())
    filename = "{basename}.log"

    level = logging.INFO
    console_stream = sys.stderr
    folders = ["/logs/{basename}"]
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
        for k in list(cls.__dict__.keys()):
            if k.startswith("_"):
                continue
            if "{%s}" % k in text:
                values[k] = getattr(cls, k)
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
    def resolved_location(cls, custom_location=None):
        if custom_location:
            # Custom location typically provided via --config CLI flag
            custom_location = cls.formatted(custom_location)
            if os.path.isdir(custom_location):
                return os.path.join(custom_location, cls.formatted(cls.filename))
            return custom_location
        if cls.dev:
            # We're running from a dev environment
            return os.path.join(cls.dev, cls.formatted(cls.filename))
        if not cls.folders:
            # No folders configured
            return None
        for folder in cls.folders:
            location = cls.usable_folder(folder)
            if location:
                return os.path.join(location, cls.formatted(cls.filename))

    @classmethod
    def usable_folder(cls, folder):
        """
        :param str folder: Folder to examine
        :return str|None: 'folder', if it usable for logging
        """
        if not folder:
            return None
        folder = cls.formatted(folder)
        if os.path.isdir(folder):
            return folder if os.access(folder, os.W_OK) else None
        parent = os.path.dirname(folder)
        if not os.path.isdir(parent):
            return None
        try:
            if not os.path.isdir(folder):
                os.mkdir(folder)
            return folder
        except (IOError, OSError):
            return None

    @classmethod
    def is_using_format(cls, markers):
        """
        :param str markers: Space separated list of markers to look for
        :return bool:
        """
        if not markers:
            return False
        markers = markers.split()
        fmt = "%s %s" % (cls.console_format, cls.file_format)
        return any(marker in fmt for marker in markers)


class _LogSetup:
    """
    Tracks current setup
    """

    level = None  # Current severity level
    hconsole = None  # type: logging.StreamHandler
    hfile = None  # type: logging.StreamHandler # File we're currently logging to (if any)
    context = None  # type: _LogContext

    def __init__(self):
        self.lock = threading.RLock()

    def setup(self, debug, dryrun, custom_location):
        """
        :param bool debug: Enable debug level logging
        :param bool dryrun: Enable debug level logging
        :param str|None custom_location: Optional custom location to use
        """
        with self.lock:
            if self.context is not None:
                raise Exception("Please call runez.log.setup() only once")
            self.context = _LogContext(self)
            self.level = logging.DEBUG if debug else Settings.level or OriginalLogging.level
            logging.root.setLevel(self.level)
            self.hconsole = self.get_handler(logging.StreamHandler, Settings.console_format, Settings.console_stream)
            location = Settings.resolved_location(custom_location)
            self.hfile = self.get_handler(logging.FileHandler, Settings.file_format, location)
            if Settings.is_using_format("%(context)s"):
                self.context.enable()
            self.optimize()

    def reset(self):
        """Reset logging as it was before setup(), no need to call this outside of testing, or some very special cases"""
        if self.context is not None:
            self.context = None
            self.level = None
            if self.hconsole:
                logging.root.removeHandler(self.hconsole)
                self.hconsole = None
            if self.hfile:
                logging.root.removeHandler(self.hfile)
                self.hfile = None
            logging.root.setLevel(OriginalLogging.level)
            for name, value in OriginalLogging.__dict__.items():
                if not name.startswith("__") and hasattr(logging, name):
                    setattr(logging, name, value)

    def get_handler(self, base, format, target):
        """
        :param type(logging.Handler) base: Handler implementation to use
        :param str|None format: Format to use
        :param str|None target: Target for handler
        :return logging.Handler|None:
        """
        if format and target:
            handler = base(target)
            handler.setFormatter(self.get_formatter(format))
            handler.setLevel(self.level)
            logging.root.addHandler(handler)
            return handler

    def enable_faulthandler(self, signum):
        """
        :param int signum: Signal number to register for full thread stack dump
        """
        with self.lock:
            if not self.hfile or faulthandler is None:
                return
            dump_file = self.hfile.stream
            faulthandler.enable(file=dump_file, all_threads=True)
            faulthandler.register(signum, file=dump_file, all_threads=True, chain=False)

    def replace_and_pad(self, format, marker, replacement):
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

    def get_formatter(self, format):
        """
        :param str format: Format specification
        :return logging.Formatter: Associated logging formatter
        """
        format = self.replace_and_pad(format, "%(timezone)s", Settings.timezone)
        return logging.Formatter(format)

    def optimize(self):
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

        if not Settings.is_using_format("%(name)d"):
            return
        if Settings.is_using_format("%(pathname)s %(filename)s %(funcName)s %(module)s"):
            logging._srcfile = OriginalLogging._srcfile
        else:
            logging._srcfile = None
        logging.logProcesses = Settings.is_using_format("%(process)d")
        logging.logThreads = Settings.is_using_format("%(thread)d %(threadName)s")

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


class ContextFilter(logging.Filter):
    """
    Optional logging filter allowing to inject key/value pairs to every log record.

    In order to activate this:
    - Mention %(context)s in your log format
    - Add key/value pairs via stdlog.add_global_context(), stdlog.add_thread_context(), or configure(global_context={...})

    This filter renders %(context)s using the form.
    Modify ContextFilter.render if you'd like to customize it.
    """

    def filter(self, record):
        """Determines if the record should be logged and injects context info into the record. Always returns True"""
        record.context = self.render(SETUP.context.to_dict())
        return True

    def render(self, context):
        """Formats the context dictionary to string

        :param dict context: Current merged global + thread context
        :return str: Represented context
        """
        if context:
            return Settings.context_format % ",".join("%s=%s" % (key, val) for key, val in context.items() if key and val)
        return ""


class _LogContext:
    filter = None
    _thread = None
    _global = None

    def __init__(self, parent):
        """
        :param _LogSetup parent: Parent log setup object
        """
        self.parent = parent

    def to_dict(self):
        """
        :return dict: Combined global and thread-specific logging context
        """
        result = {}
        if self._global:
            result.update(self._global)
        if self._thread:
            result.update(getattr(self._thread, "context", {}))
        return result

    def enable(self):
        """Enable contextual logging"""
        if self.filter is None:
            self.filter = ContextFilter()
        if self.parent.hconsole:
            self.parent.hconsole.addFilter(self.filter)
        if self.parent.hfile:
            self.parent.hfile.addFilter(self.filter)

    def set(self, **values):
        """Set current thread's logging context to 'values'"""
        if self._thread is None:
            self._thread = threading.local()
        self._thread.context = values
        self.enable()

    def set_global(self, **values):
        """Set global logging context to 'values'"""
        self._global = values
        self.enable()

    def add(self, **values):
        """Add 'values' to current thread's logging context"""
        if self._thread is None:
            self._thread = threading.local()
        if getattr(self._thread, "context", None) is None:
            self._thread.context = {}
        self._thread.context.update(**values)
        self.enable()

    def add_global(self, **values):
        """Add 'values' to global logging context"""
        if self._global is None:
            self._global = {}
        self._global.update(**values)
        self.enable()

    def remove(self, name):
        """Remove entry with 'name' from current thread's context"""
        if self._thread is not None:
            c = getattr(self._thread, "context", None)
            if c and name in c:
                del c[name]

    def remove_global(self, name):
        """Remove entry with 'name' from global context"""
        if self._global and name in self._global:
            del self._global[name]

    def clear(self):
        """Clear current thread's context"""
        if self._thread is not None:
            self._thread.context = {}

    def clear_global(self):
        """Clear global context"""
        if self._global is not None:
            self._global = None


SETUP = _LogSetup()
