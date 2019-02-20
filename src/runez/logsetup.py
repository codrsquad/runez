"""
Convenience logging setup
"""

import inspect
import logging
import os
import signal
import sys
import threading
from functools import partial

try:
    # faulthandler is only available in python 3.3+
    import faulthandler

except ImportError:
    faulthandler = None

import runez.system
from runez.base import Slotted, ThreadGlobalContext, UNSET
from runez.convert import flattened, formatted
from runez.path import basename as get_basename, ensure_folder
from runez.program import get_dev_folder, get_program_path


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
    or
        runez.log.spec.console_stream = sys.stdout
    """

    __slots__ = [
        "level",  # Desired logging level (eg: logging.INFO)
        "custom_location",  # Desired custom file location (overrides {locations} search, handy as a --log cli flag)
        "console_stream",  # stream to use for console log (eg: sys.stderr), use None to deactivate
        "appname",  # Program's base name, not used directly, just as reference for default 'basename'
        "basename",  # Base name of target log file, not used directly, just as reference for default 'locations'
        "locations",  # List of candidate folders for file logging (None: deactivate file logging)
        "rotate",  # How to rotate log file (None: deactive, "1d" for daily rotation, "50m" for size based rotation etc)
        "console_format",  # Format to use for console log, use None to deactivate
        "file_format",  # Format to use for file log, use None to deactivate
        "context_format",  # Format to use for contextual log, use None to deactivate
        "timezone",  # Time zone, use None to deactivate time zone logging
        "dev",  # Custom folder to use when running from a development venv (auto-determined if None)
        "tmp",  # Optional temp folder to use (auto determined)
        "greeting",  # Optional greeting message to log right after runez.log.setup(), extra {pid} and {location} format markers provided
    ]

    def usable_location(self):
        """
        :return str|None: First available usable location
        """
        if self.custom_location is not None:
            # Custom location typically provided via --config CLI flag
            return self._auto_complete_filename(self.custom_location)
        if self.locations:
            for location in self.locations:
                path = self._auto_complete_filename(location)
                if path and ensure_folder(path, fatal=False, dryrun=False) >= 0:
                    return path

    @property
    def should_log_to_file(self):
        """
        :return bool: As per the spec, should we be logging to a file?
        """
        if self.custom_location is not None:
            return bool(self.custom_location)
        return bool(self.locations and self.file_format)

    def _auto_complete_filename(self, location):
        """
        :param str|None location: Location to auto-complete with {basename}, if it points to a folder
        :return str|None: {location}/{basename}
        """
        path = formatted(location, self)
        if path:
            if self.basename and os.path.isdir(path):
                filename = formatted(self.basename, self)
                return filename and os.path.join(path, filename)
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
        :param ThreadGlobalContext context: Associated context
        :param str name: Passed through to parent
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


class LogManager:
    """
    Global logging context managed by runez.
    There's only one, as multiple contexts would not be useful (logging setup is a global thing)
    """

    # Defaults used to initialize LogSpec instances
    # You shouldn't need to change these, but changing prior to calling runez.log.setup() will take effect
    # Use runez.log.override_spec() to change these defaults
    _default_spec = LogSpec(
        level=logging.INFO,
        custom_location=None,
        console_stream=sys.stderr,
        appname=get_basename(get_program_path()),
        basename="{appname}.log",
        locations=["{dev}/log/{basename}", "/logs/{appname}/{basename}", "/var/log/{basename}"],
        rotate=None,
        console_format="%(asctime)s %(levelname)s %(message)s",
        file_format="%(asctime)s %(timezone)s [%(threadName)s] %(context)s%(levelname)s - %(message)s",
        context_format="[[%s]] ",
        timezone=runez.system.get_timezone(),
        dev=None,
        tmp=None,
        greeting="{location}, {pid}",
    )

    # Spec defines how logs should be setup()
    # Best way to provide your spec is via: runez.log.setup(), for example:
    #   runez.log.setup(appname="my-app)
    spec = LogSpec(_default_spec)

    # Thread-local / global context
    context = ThreadGlobalContext(_ContextFilter)

    # Below fields should be read-only for outside users, do not modify these
    level = None  # Current severity level
    file_handler = None  # type: logging.FileHandler # File we're currently logging to (if any)
    handlers = None  # type: list[logging.StreamHandler]
    used_formats = None  # type: str
    faulthandler = faulthandler
    faulthandler_signum = None  # type: int

    _lock = threading.RLock()
    _logging_snapshot = LoggingSnapshot()

    @classmethod
    def setup(
            cls,
            debug=None,
            dryrun=None,
            level=UNSET,
            custom_location=UNSET,
            console_stream=UNSET,
            appname=UNSET,
            basename=UNSET,
            locations=UNSET,
            rotate=UNSET,
            console_format=UNSET,
            file_format=UNSET,
            context_format=UNSET,
            timezone=UNSET,
            dev=UNSET,
            tmp=UNSET,
            greeting=UNSET,
    ):
        """
        Args:
            debug (bool): Enable debug level logging (overrides `level`)
            dryrun (bool): Enable dryrun
            level (int): Desired logging level (eg: logging.INFO)
            custom_location (str|None): Desired custom file location (overrides {locations} search, handy as a --log cli flag)
            console_stream (TextIOWrapper|None): Stream to use for console log (eg: sys.stderr), use None to deactivate
            appname (str|None): Program's base name, not used directly, just as reference for default 'basename'
            basename (str|None): Base name of target log file, not used directly, just as reference for default 'locations'
            locations (list[str]|None): List of candidate folders for file logging (None: deactivate file logging)
            rotate (str|None): How to rotate log file (None: deactive, "1d" for daily rotation, "50m" for size based rotation etc)
            console_format (str|None): Format to use for console log, use None to deactivate
            file_format (str|None): Format to use for file log, use None to deactivate
            context_format (str|None): Format to use for contextual log, use None to deactivate
            timezone (str|None): Time zone, use None to deactivate time zone logging
            dev (str|None): Custom folder to use when running from a development venv (auto-determined if None)
            tmp (str|None): Optional temp folder to use (auto determined)
            greeting (str|None): Optional greeting message to log right after, extra {pid} and {location} format markers provided
        """
        with cls._lock:
            if cls.level is not None:
                raise Exception("Please call runez.log.setup() only once")

            if dryrun is not None:
                if dryrun and debug is None:
                    debug = True
                runez.system.set_dryrun(dryrun)

            cls.spec.set(
                level=level,
                custom_location=custom_location,
                console_stream=console_stream,
                appname=appname,
                basename=basename,
                locations=locations,
                rotate=rotate,
                console_format=console_format,
                file_format=file_format,
                context_format=context_format,
                timezone=timezone,
                dev=dev,
                tmp=tmp,
                greeting=greeting,
            )
            cls.level = logging.DEBUG if debug else cls.spec.level
            if logging.root.level != cls.level:
                logging.root.setLevel(cls.level)

            if cls.spec.dev is None:
                cls.spec.dev = get_dev_folder()

            hconsole = _get_handler(cls.level, logging.StreamHandler, cls.spec.console_format, cls.spec.console_stream)

            actual_location = cls.spec.usable_location()
            if actual_location:
                cls.file_handler = _get_handler(cls.level, logging.FileHandler, cls.spec.file_format, actual_location)

            cls.handlers = [h for h in (hconsole, cls.file_handler) if h is not None]

            cls.used_formats = " ".join(h.formatter._fmt for h in cls.handlers)

            if cls.is_using_format("%(context)s"):
                cls.context.enable()

            cls._fix_logging_shortcuts()

            if cls.context.filter:
                for handler in cls.handlers:
                    handler.addFilter(cls.context.filter)

            if cls.spec.greeting and cls.spec.should_log_to_file:
                pid = "pid %s" % os.getpid()
                message = "Logging to %s" % actual_location if actual_location else "No usable log locations from {locations}"
                message = formatted(cls.spec.greeting, cls.spec, pid=pid, location=message, strict=False)
                logging.getLogger(__name__).debug(message)

    @classmethod
    def silence(cls, *modules):
        """
        :param modules: Modules, or names of modules to silence, by setting their log level to WARNING
        """
        for mod in modules:
            name = mod.__name__ if hasattr(mod, "__name__") else mod
            logging.getLogger(name).setLevel(logging.WARNING)

    @classmethod
    def is_using_format(cls, markers, used_formats=None):
        """
        :param str markers: Space separated list of markers to look for
        :param str used_formats: Formats to consider (default: cls.used_formats)
        :return bool: True if any one of the 'markers' is seen in 'used_formats'
        """
        """"""
        if used_formats is None:
            used_formats = cls.used_formats
        if not markers or not used_formats:
            return False
        return any(marker in used_formats for marker in flattened(markers, separator=" ", unique=True))

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
    def override_root_level(cls, level):
        """This function is useful for testing, to temporarily set logging level to debug basically"""
        if level is not None:
            old_level = cls._default_spec.level
            if level != cls._default_spec.level:
                cls._default_spec.level = level
                cls.spec.level = level
            if level != logging.root.level:
                logging.root.setLevel(level)
            return old_level

    @classmethod
    def override_spec(cls, **kwargs):
        """OVerride 'spec' and '_default_spec' with given values"""
        cls._default_spec.set(**kwargs)
        cls.spec.set(**kwargs)

    @classmethod
    def _reset(cls):
        """Reset logging as it was before setup(), no need to call this outside of testing, or some very special cases"""
        cls._disable_faulthandler()
        if cls.handlers is not None:
            for handler in cls.handlers:
                logging.root.removeHandler(handler)
        cls._logging_snapshot.restore()
        cls.context.reset()
        cls.spec = LogSpec(cls._default_spec)
        cls.level = None
        cls.file_handler = None
        cls.handlers = None
        cls.used_formats = None

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
        if cls.is_using_format("%(pathname)s %(filename)s %(funcName)s %(module)s"):
            logging._srcfile = cls._logging_snapshot._srcfile
        else:
            logging._srcfile = None

        logging.logProcesses = cls.is_using_format("%(process)d")
        logging.logThreads = cls.is_using_format("%(thread)d %(threadName)s")

        def getframe():
            return sys._getframe(4)

        def log(level, msg, *args, **kwargs):
            """Wrapper to make logging.info() etc report the right module %(name)"""
            name = inspect.currentframe().f_back.f_globals["__name__"]
            logger = logging.getLogger(name)
            try:
                logging.currentframe = getframe
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


def _replace_and_pad(format, marker, replacement):
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
    # Remove mention of 'marker' in 'format', including leading space (if present)
    format = format.replace("%s " % marker, marker)
    return format.replace(marker, "")


def _get_handler(level, base, format, target):
    """
    :param type(logging.Handler) base: Handler implementation to use
    :param str|None format: Format to use
    :param str|None target: Target for handler
    :return logging.Handler|None:
    """
    if format and target:
        handler = base(target)
        handler.setFormatter(_get_formatter(format))
        handler.setLevel(level)
        logging.root.addHandler(handler)
        return handler


def _get_formatter(format):
    """
    :param str format: Format specification
    :return logging.Formatter: Associated logging formatter
    """
    format = _replace_and_pad(format, "%(timezone)s", LogManager.spec.timezone)
    return logging.Formatter(format)
