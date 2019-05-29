"""
Convenience logging setup
"""

import logging
import os
import signal
import sys
import threading
from functools import partial
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler

try:
    # faulthandler is only available in python 3.3+
    import faulthandler

except ImportError:
    faulthandler = None

import runez.system
from runez.base import Slotted, ThreadGlobalContext, UNSET
from runez.config import to_bytesize, to_int
from runez.convert import flattened, formatted, represented_args, SANITIZED, UNIQUE
from runez.path import basename as get_basename, ensure_folder
from runez.program import get_dev_folder, get_program_path


LOG = logging.getLogger(__name__)
ORIGINAL_CF = logging.currentframe


class LoggingSnapshot(Slotted):
    """
    Take a snapshot of parts we're modifying in the 'logging' module, in order to be able to restore it as it was
    """

    __slots__ = ["_srcfile", "critical", "fatal", "error", "exception", "warning", "info", "debug"]

    def _seed(self):
        """Seed initial fields"""
        for name in self.__slots__:
            setattr(self, name, getattr(logging, name))

    def restore(self):
        for name in self.__slots__:
            setattr(logging, name, getattr(self, name))


class LogSpec(Slotted):
    """
    Settings to use, you can safely customize these (before calling runez.log.setup), for example:
        runez.log.setup(console_stream=sys.stdout)
    or
        runez.log.spec.set(console_stream=sys.stdout)
        runez.log.setup()
    or
        runez.log.spec.console_stream = sys.stdout
        runez.log.setup()
    """

    # See setup()'s docstring for meaning of each field
    __slots__ = [
        "appname",
        "basename",
        "console_format",
        "console_level",
        "console_stream",
        "context_format",
        "dev",
        "file_format",
        "file_level",
        "file_location",
        "locations",
        "rotate",
        "rotate_count",
        "timezone",
        "tmp",
    ]

    @property
    def argv(self):
        """str: Command line invocation, represented to show as greeting"""
        return represented_args(sys.argv)

    @property
    def pid(self):
        """str: Current process id represented to show as greeting"""
        return os.getpid()

    def usable_location(self):
        """
        Returns:
            str | None: First available usable location
        """
        if not self.should_log_to_file:
            return None
        if self.file_location is not None:
            # Custom location typically provided via --config CLI flag
            return self._auto_complete_filename(self.file_location)
        if self.locations:
            for location in self.locations:
                path = self._auto_complete_filename(location)
                if path:
                    return path

    @property
    def should_log_to_file(self):
        """
        Returns:
            bool: As per the spec, should we be logging to a file?
        """
        if not self.file_format:
            return False
        if self.file_location is not None:
            return bool(self.file_location)
        return bool(self.locations)

    def _auto_complete_filename(self, location):
        """
        Args:
            location (str | unicode | None): Location to auto-complete with {basename}, if it points to a folder

        Returns:
            str | None: {location}/{basename}
        """
        path = formatted(location, self, os.environ)
        if path:
            if os.path.isdir(path):
                filename = formatted(self.basename, self)
                if not filename:
                    return None
                path = os.path.join(path, filename)
            if path and ensure_folder(path, fatal=False, logger=LOG.debug, dryrun=False) >= 0:
                return path


class _ContextFilter(logging.Filter):
    """
    Optional logging filter allowing to inject key/value pairs to every log record.

    In order to activate this:
    - Mention %(context)s in your log format
    - Add key/value pairs via runez.log.context.add_global(), runez.log.context.add_threadlocal()
    """

    def __init__(self, context, name=""):
        """
        Args:
            context (ThreadGlobalContext): Associated context
            name (str | unicode): Passed through to parent
        """
        super(_ContextFilter, self).__init__(name=name)
        self.context = context

    def filter(self, record):
        """Determines if the record should be logged and injects context info into the record. Always returns True"""
        fmt = LogManager.spec.context_format
        if fmt:
            data = self.context.to_dict()
            if data:
                record.context = fmt % ",".join("%s=%s" % (key, val) for key, val in sorted(data.items()) if key and val)
            else:
                record.context = ""
        return True


class LogManager(object):
    """
    Global logging context managed by runez.
    There's only one, as multiple contexts would not be useful (logging setup is a global thing)
    """

    # Defaults used to initialize LogSpec instances
    # Use runez.log.override_spec() to change these defaults (do not change directly)
    _default_spec = LogSpec(
        appname=None,
        basename="{appname}.log",
        console_format="%(asctime)s %(levelname)s %(message)s",
        console_level=logging.WARNING,
        console_stream=sys.stderr,
        context_format="[[%s]] ",
        dev=None,
        file_format="%(asctime)s %(timezone)s %(context)s%(levelname)s - %(message)s",
        file_level=logging.DEBUG,
        file_location=None,
        locations=["{dev}/log/{basename}", "/logs/{appname}/{basename}", "/var/log/{basename}"],
        rotate=None,
        rotate_count=10,
        timezone=runez.system.get_timezone(),
        tmp=None,
    )

    # Spec defines how logs should be setup()
    # Best way to provide your spec is via: runez.log.setup(), for example:
    #   runez.log.setup(rotate="size:50m")
    spec = LogSpec(_default_spec)

    # Thread-local / global context
    context = ThreadGlobalContext(_ContextFilter)

    # Below fields should be read-only for outside users, do not modify these
    debug = None
    console_handler = None  # type: logging.StreamHandler | None
    file_handler = None  # type: logging.FileHandler | None # File we're currently logging to (if any)
    handlers = None  # type: list[logging.Handler] | None
    used_formats = None  # type: str | None
    faulthandler_signum = None  # type: int | None

    _lock = threading.RLock()
    _logging_snapshot = LoggingSnapshot()
    _shortcuts_fixed = False

    @classmethod
    def setup(
            cls,
            debug=UNSET,
            dryrun=UNSET,
            level=UNSET,
            clean_handlers=UNSET,
            greetings=UNSET,
            appname=UNSET,
            basename=UNSET,
            console_format=UNSET,
            console_level=UNSET,
            console_stream=UNSET,
            context_format=UNSET,
            dev=UNSET,
            file_format=UNSET,
            file_level=UNSET,
            file_location=UNSET,
            locations=UNSET,
            rotate=UNSET,
            rotate_count=UNSET,
            timezone=UNSET,
            tmp=UNSET,
    ):
        """
        Args:
            debug (bool): Enable debug level logging (overrides other specified levels)
            dryrun (bool): Enable dryrun
            level (int | None): Shortcut to set both `console_level` and `file_level` at once
            clean_handlers (bool): Remove any existing logging.root.handlers
            greetings (str | unicode | list[str | unicode] | None): Optional greetings message(s) to log
            appname (str | unicode | None): Program's base name, not used directly, just as reference for default 'basename'
            basename (str | unicode | None): Base name of target log file, not used directly, just as reference for default 'locations'
            console_format (str | unicode | None): Format to use for console log, use None to deactivate
            console_level (int | None): Level to use for console logging
            console_stream (TextIOWrapper | None): Stream to use for console log (eg: sys.stderr), use None to deactivate
            context_format (str | unicode | None): Format to use for contextual log, use None to deactivate
            dev (str | unicode | None): Custom folder to use when running from a development venv (auto-determined if None)
            file_format (str | unicode | None): Format to use for file log, use None to deactivate
            file_level (str | unicode | None): Level to use for file logging
            file_location (str | unicode | None): Desired custom file location (overrides {locations} search, handy as a --log cli flag)
            locations (list[str | unicode]|None): List of candidate folders for file logging (None: deactivate file logging)
            rotate (str | unicode | None): How to rotate log file (None: no rotation, "time:1d" time-based, "size:50m" size-based)
            rotate_count (int): How many rotations to keep
            timezone (str | unicode | None): Time zone, use None to deactivate time zone logging
            tmp (str | unicode | None): Optional temp folder to use (auto determined)
        """
        with cls._lock:
            if dryrun is not UNSET:
                if dryrun and (debug is None or debug is UNSET):
                    # Automatically turn debug on (if not explicitly specified) with dryrun,
                    # as many of the "Would ..." messages are at debug level
                    debug = True
                runez.system.set_dryrun(dryrun)

            if debug is not UNSET:
                cls.debug = debug

            cls.spec.set(
                appname=appname,
                basename=basename,
                console_format=console_format,
                console_level=console_level or level,
                console_stream=console_stream,
                context_format=context_format,
                dev=dev,
                file_format=file_format,
                file_level=file_level or level,
                file_location=file_location,
                locations=locations,
                rotate=rotate,
                rotate_count=rotate_count,
                timezone=timezone,
                tmp=tmp,
            )

            cls._auto_fill_defaults()

            if cls.debug:
                cls.spec.console_level = logging.DEBUG
                cls.spec.file_level = logging.DEBUG

            elif level:
                cls.spec.console_level = level
                cls.spec.file_level = level

            root_level = min(flattened([cls.spec.console_level, cls.spec.file_level], split=SANITIZED))
            if root_level and root_level != logging.root.level:
                logging.root.setLevel(root_level)

            if cls.handlers is None:
                cls.handlers = []

            cls._setup_handler("console")
            cls._setup_handler("file")
            cls._update_used_formats()
            cls._fix_logging_shortcuts()

            if clean_handlers:
                cls.clean_handlers()

            cls.greet(greetings)

    @classmethod
    def greet(cls, greetings, logger=LOG.debug):
        """
        Args:
            greetings (str | unicode | list[str | unicode] | None): Greetings message(s) to log
            logger (callable | None): Logger to use
        """
        if greetings and logger:
            for msg in flattened(greetings, split=SANITIZED):
                message = cls.formatted_greeting(msg)
                if message:
                    logger(message)

    @classmethod
    def clean_handlers(cls):
        """Remove all non-runez logging handlers"""
        for h in logging.root.handlers:
            if h is not cls.console_handler and h is not cls.file_handler:
                logging.root.removeHandler(h)

    @classmethod
    def reset(cls):
        """Reset logging as it was before setup(), no need to call this outside of testing, or some very special cases"""
        cls._disable_faulthandler()
        if cls.handlers is not None:
            for handler in cls.handlers:
                logging.root.removeHandler(handler)
            cls.handlers = None
        cls._logging_snapshot.restore()
        cls.context.reset()
        cls.spec = LogSpec(cls._default_spec)
        cls.debug = None
        cls.console_handler = None
        cls.file_handler = None
        cls.used_formats = None

    @classmethod
    def formatted_greeting(cls, greeting):
        if greeting:
            if cls.file_handler and cls.file_handler.baseFilename:
                location = cls.file_handler.baseFilename
            elif not cls.spec.should_log_to_file:
                location = "file log disabled"
            elif cls.spec.file_location:
                location = "{file_location} is not usable"
            else:
                location = "no usable locations from {locations}"
            return formatted(greeting, cls.spec, location=location, strict=False)

    @classmethod
    def silence(cls, *modules, **kwargs):
        """
        Args:
            *modules: Modules, or names of modules to silence (by setting their log level to WARNING or above)
            **kwargs: Pass as kwargs due to python 2.7, would be level=logging.WARNING otherwise
        """
        level = kwargs.pop("level", logging.WARNING)
        for mod in modules:
            name = mod.__name__ if hasattr(mod, "__name__") else mod
            logging.getLogger(name).setLevel(level)

    @classmethod
    def is_using_format(cls, markers, used_formats=None):
        """
        Args:
            markers (str | unicode): Space separated list of markers to look for
            used_formats (str | unicode): Formats to consider (default: cls.used_formats)

        Returns:
            (bool): True if any one of the 'markers' is seen in 'used_formats'
        """
        if used_formats is None:
            used_formats = cls.used_formats
        if not markers or not used_formats:
            return False
        return any(marker in used_formats for marker in flattened(markers, split=(" ", UNIQUE)))

    @classmethod
    def enable_faulthandler(cls, signum=signal.SIGUSR1):
        """
        Enable dumping thread stack traces when specified signals are received, similar to java's handling of SIGQUIT

        Note: this must be called from the surviving process in case of daemonization.
        Note that SIGQUIT does not work in all environments with a python process.

        :param int|None signum: Signal number to register for full thread stack dump (use None to disable)
        """
        with cls._lock:
            if not signum:
                cls._disable_faulthandler()
                return
            if not cls.file_handler or faulthandler is None:
                return
            cls.faulthandler_signum = signum
            dump_file = cls.file_handler.stream
            faulthandler.enable(file=dump_file, all_threads=True)
            faulthandler.register(signum, file=dump_file, all_threads=True, chain=False)

    @classmethod
    def override_spec(cls, **kwargs):
        """OVerride 'spec' and '_default_spec' with given values"""
        cls._default_spec.set(**kwargs)
        cls.spec.set(**kwargs)

    @classmethod
    def _update_used_formats(cls):
        cls.used_formats = None
        for handler in (cls.console_handler, cls.file_handler):
            if handler and handler.formatter and handler.formatter._fmt:
                cls.used_formats = "%s %s" % (cls.used_formats or "", handler.formatter._fmt)
                cls.used_formats = cls.used_formats.strip()

    @classmethod
    def _setup_handler(cls, name):
        fmt = _canonical_format(getattr(cls.spec, "%s_format" % name))
        level = getattr(cls.spec, "%s_level" % name)
        if name == "console":
            target = cls.spec.console_stream
        else:
            target = cls.spec.usable_location()

        existing = getattr(cls, "%s_handler" % name)
        if cls._is_equivalent_handler(existing, target, fmt, level):
            return

        if existing is not None:
            cls.handlers.remove(existing)
            logging.root.removeHandler(existing)

        if not target:
            return

        if name == "console":
            new_handler = logging.StreamHandler(target)

        else:
            new_handler = _get_file_handler(target, cls.spec.rotate, cls.spec.rotate_count)

        if fmt:
            new_handler.setFormatter(logging.Formatter(fmt))
        if level:
            new_handler.setLevel(level)

        setattr(cls, "%s_handler" % name, new_handler)
        logging.root.addHandler(new_handler)
        cls.handlers.append(new_handler)

    @classmethod
    def _is_equivalent_handler(cls, existing, target, fmt, level):
        """
        Args:
            existing (logging.Handler): Existing handler to examine
            target: Target for candidate new handler
            fmt: Format for candidate new handler
            level: Level for candidate new handler

        Returns:
            (bool): True if `existing` handler is equivalent to candidate new handler
        """
        if existing is None:
            return False

        if not existing.formatter or fmt != existing.formatter._fmt:
            return False

        if existing.level != level:
            return False

        if isinstance(existing, logging.FileHandler):
            return existing.baseFilename == target

        if isinstance(existing, logging.StreamHandler):
            return existing.stream == target

    @classmethod
    def _auto_fill_defaults(cls):
        """Late auto-filled missing defaults (caller's value kept if provided)"""
        if not cls.spec.appname:
            cls.spec.appname = get_basename(get_program_path())
        if not cls.spec.dev:
            cls.spec.dev = get_dev_folder()

    @classmethod
    def _disable_faulthandler(cls):
        if faulthandler and cls.faulthandler_signum:
            faulthandler.unregister(cls.faulthandler_signum)
            faulthandler.disable()
            cls.faulthandler_signum = None

    @classmethod
    def _fix_logging_shortcuts(cls):
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
        if cls.is_using_format("%(context)s"):
            cls.context.enable(True)
            for handler in cls.handlers:
                handler.addFilter(cls.context.filter)

        else:
            for handler in cls.handlers:
                handler.removeFilter(cls.context.filter)
            cls.context.enable(False)

        if cls.is_using_format("%(pathname)s %(filename)s %(funcName)s %(module)s"):
            logging._srcfile = cls._logging_snapshot._srcfile

        else:
            logging._srcfile = None

        logging.logProcesses = cls.is_using_format("%(process)d")
        logging.logThreads = cls.is_using_format("%(thread)d %(threadName)s")

        if cls._shortcuts_fixed:
            return
        cls._shortcuts_fixed = True

        def log(level, msg, *args, **kwargs):
            """Wrapper to make logging.info() etc report the right module %(name)"""
            name = sys._getframe(1).f_globals.get("__name__")
            logger = logging.getLogger(name)
            try:
                logging.currentframe = lambda: sys._getframe(4)
                logger.log(level, msg, *args, **kwargs)
            finally:
                logging.currentframe = ORIGINAL_CF

        def wrap(level, **kwargs):
            """Wrap corresponding logging shortcut function"""
            original = getattr(logging, logging.getLevelName(level).lower())
            f = partial(log, level, **kwargs)
            f.__doc__ = original.__doc__
            return f

        logging.critical = wrap(logging.CRITICAL)
        logging.fatal = logging.critical
        logging.error = wrap(logging.ERROR)
        logging.exception = partial(logging.error, exc_info=True)
        logging.warning = wrap(logging.WARNING)
        logging.info = wrap(logging.INFO)
        logging.debug = wrap(logging.DEBUG)
        logging.log = log


def _replace_and_pad(fmt, marker, replacement):
    """
    Args:
        fmt (str | unicode): Format to tweak
        marker (str | unicode): Marker to replace
        replacement (str | unicode): What to replace marker with

    Returns:
        (str): Resulting format, with marker replaced
    """
    if marker not in fmt:
        return fmt
    if replacement:
        return fmt.replace(marker, replacement)
    # Remove mention of 'marker' in 'fmt', including leading space (if present)
    fmt = fmt.replace("%s " % marker, marker)
    return fmt.replace(marker, "")


def _canonical_format(fmt):
    """
    Args:
        fmt (str | unicode | None): Format specification

    Returns:
        (str | None): Canonical version of format
    """
    if not fmt:
        return fmt
    return _replace_and_pad(fmt, "%(timezone)s", LogManager.spec.timezone)


def _get_file_handler(location, rotate, rotate_count):
    """
    Args:
        location (str | unicode | None): Log file path
        rotate (str | unicode | None): How to rotate, examples:
            time:midnight - Rotate at midnight
            time:15s - Rotate every 15 seconds
            time:2h - Rotate every 2 hours
            time:7d - Rotate every 7 days
            size:20m - Rotate every 20MB
            size:1g - Rotate every 1MB
        rotate_count (int): How many backups to keep

    Returns:
        (logging.FileHandler): Associated handler
    """
    if not rotate:
        return logging.FileHandler(location)

    kind, _, mode = rotate.partition(":")

    if not mode:
        raise ValueError("Invalid 'rotate' (missing kind): %s" % rotate)

    if kind == "time":
        if mode == "midnight":
            return TimedRotatingFileHandler(location, when="midnight", backupCount=rotate_count)

        timed = "shd"
        if mode[-1].lower() not in timed:
            raise ValueError("Invalid 'rotate' (unknown time spec): %s" % rotate)

        interval = to_int(mode[:-1])
        if interval is None:
            raise ValueError("Invalid 'rotate' (time range not an int): %s" % rotate)

        return TimedRotatingFileHandler(location, when=mode[-1], interval=interval, backupCount=rotate_count)

    if kind == "size":
        size = to_bytesize(mode)
        if size is None:
            raise ValueError("Invalid 'rotate' (size not a bytesize): %s" % rotate)

        return RotatingFileHandler(location, maxBytes=size, backupCount=rotate_count)

    raise ValueError("Invalid 'rotate' (unknown type): %s" % rotate)
