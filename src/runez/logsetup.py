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
# from logging.handlers import RotatingFileHandler

try:
    # faulthandler is only available in python 3.3+
    import faulthandler

except ImportError:
    faulthandler = None

import runez.system
from runez.base import Slotted, ThreadGlobalContext, UNSET
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
        "appname", "basename", "console_format", "console_stream", "context_format", "custom_location",
        "dev", "file_format", "greetings", "level", "locations", "rotate", "timezone", "tmp",
    ]

    @property
    def argv(self):
        """str: Command line invocation, represented to show as greeting"""
        return represented_args(sys.argv)

    @property
    def pid(self):
        """str: Current process id represented to show as greeting"""
        return "pid %s" % os.getpid()

    def usable_location(self):
        """
        Returns:
            str | None: First available usable location
        """
        if self.custom_location is not None:
            # Custom location typically provided via --config CLI flag
            return self._auto_complete_filename(self.custom_location)
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
        if self.custom_location is not None:
            return bool(self.custom_location)
        return bool(self.locations and self.file_format)

    def _auto_complete_filename(self, location):
        """
        Args:
            location (str | None): Location to auto-complete with {basename}, if it points to a folder

        Returns:
            str | None: {location}/{basename}
        """
        path = formatted(location, self)
        if path:
            if self.basename and os.path.isdir(path):
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
            name (str): Passed through to parent
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
        level=logging.INFO,
        custom_location=None,
        console_stream=sys.stderr,
        appname=get_basename(get_program_path()),
        basename="{appname}.log",
        locations=["{dev}/log/{basename}", "/logs/{appname}/{basename}", "/var/log/{basename}"],
        rotate=None,
        console_format="%(asctime)s %(levelname)s %(message)s",
        file_format="%(asctime)s %(timezone)s %(context)s%(levelname)s - %(message)s",
        context_format="[[%s]] ",
        timezone=runez.system.get_timezone(),
        dev=None,
        tmp=None,
        greetings="{actual_location}, {pid}",
    )

    # Spec defines how logs should be setup()
    # Best way to provide your spec is via: runez.log.setup(), for example:
    #   runez.log.setup(appname="my-app")
    spec = LogSpec(_default_spec)

    # Thread-local / global context
    context = ThreadGlobalContext(_ContextFilter)

    # Below fields should be read-only for outside users, do not modify these
    level = None  # Current severity level
    actual_location = None
    console_handler = None  # type: logging.StreamHandler
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
            debug=UNSET,
            dryrun=UNSET,
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
            greetings=UNSET,
    ):
        """
        Args:
            debug (bool): Enable debug level logging (overrides `level`)
            dryrun (bool): Enable dryrun
            level (int): Desired logging level (eg: logging.INFO)
            custom_location (str | None): Desired custom file location (overrides {locations} search, handy as a --log cli flag)
            console_stream (TextIOWrapper | None): Stream to use for console log (eg: sys.stderr), use None to deactivate
            appname (str | None): Program's base name, not used directly, just as reference for default 'basename'
            basename (str | None): Base name of target log file, not used directly, just as reference for default 'locations'
            locations (list[str]|None): List of candidate folders for file logging (None: deactivate file logging)
            rotate (str | None): How to rotate log file (None: deactive, "1d" for daily rotation, "50m" for size based rotation etc)
            console_format (str | None): Format to use for console log, use None to deactivate
            file_format (str | None): Format to use for file log, use None to deactivate
            context_format (str | None): Format to use for contextual log, use None to deactivate
            timezone (str | None): Time zone, use None to deactivate time zone logging
            dev (str | None): Custom folder to use when running from a development venv (auto-determined if None)
            tmp (str | None): Optional temp folder to use (auto determined)
            greetings (str | list[str] | None): Optional greetings message(s) to log, extra {actual_location} format markers provided
        """
        with cls._lock:
            if cls.level is not None:
                raise Exception("Please call runez.log.setup() only once")

            if dryrun is not UNSET:
                if dryrun and (debug is None or debug is UNSET):
                    # Automatically turn debug on (if not explicitly specified) with dryrun,
                    # as many of the "Would ..." messages are at debug level
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
                greetings=greetings,
            )
            cls.level = logging.DEBUG if debug else cls.spec.level
            if logging.root.level != cls.level:
                logging.root.setLevel(cls.level)

            if cls.spec.dev is None:
                cls.spec.dev = get_dev_folder()

            if cls.spec.console_stream and cls.spec.console_format:
                cls.console_handler = logging.StreamHandler(cls.spec.console_stream)
                cls._add_handler(cls.console_handler, cls.spec.console_format)

            if cls.spec.should_log_to_file:
                cls.actual_location = cls.spec.usable_location()
                if cls.actual_location:
                    if not cls.spec.rotate:
                        cls.file_handler = logging.FileHandler(cls.actual_location)
                    # else:
                    #     cls.file_handler = RotatingFileHandler(cls.actual_location, maxBytes=cls.spec.rotate, backupCount=1)
                    cls._add_handler(cls.file_handler, cls.spec.file_format)

            if cls.is_using_format("%(context)s"):
                cls.context.enable()

            cls._fix_logging_shortcuts()

            if cls.context.filter:
                for handler in cls.handlers:
                    handler.addFilter(cls.context.filter)

            if cls.spec.greetings:
                for msg in flattened(cls.spec.greetings, split=SANITIZED):
                    message = cls.formatted_greeting(msg)
                    if message:
                        LOG.debug(message)

    @classmethod
    def formatted_greeting(cls, greeting):
        if greeting:
            if cls.actual_location:
                message = "Logging to %s" % cls.actual_location
            elif cls.spec.custom_location:
                message = "Can't log to {custom_location}"
            elif not cls.spec.should_log_to_file:
                message = "Not logging to file"
            else:
                message = "No usable log locations from {locations}"
            return formatted(greeting, cls.spec, actual_location=message, strict=False)

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
        cls.actual_location = None
        cls.console_handler = None
        cls.file_handler = None
        cls.handlers = None
        cls.used_formats = None

    @classmethod
    def _add_handler(cls, handler, format):
        """
        Args:
            handler (logging.Handler): Handler to decorate
            format (str): Format to use
        """
        handler.setFormatter(_get_formatter(format))
        handler.setLevel(cls.level)
        logging.root.addHandler(handler)
        if cls.handlers is None:
            cls.handlers = []
        cls.used_formats = ("%s %s" % (cls.used_formats or "", format)).strip()
        cls.handlers.append(handler)

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


def _replace_and_pad(fmt, marker, replacement):
    """
    :param str fmt: Format to tweak
    :param str marker: Marker to replace
    :param str replacement: What to replace marker with
    :return str: Resulting format, with marker replaced
    """
    if marker not in fmt:
        return fmt
    if replacement:
        return fmt.replace(marker, replacement)
    # Remove mention of 'marker' in 'fmt', including leading space (if present)
    fmt = fmt.replace("%s " % marker, marker)
    return fmt.replace(marker, "")


def _get_formatter(fmt):
    """
    :param str fmt: Format specification
    :return logging.Formatter: Associated logging formatter
    """
    fmt = _replace_and_pad(fmt, "%(timezone)s", LogManager.spec.timezone)
    return logging.Formatter(fmt)
