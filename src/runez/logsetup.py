# -*- encoding: utf-8 -*-

"""
Convenience logging setup
"""

import atexit
import logging
import os
import re
import signal
import sys
import threading
import time
from itertools import cycle
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler

try:
    # faulthandler is only available in python 3.3+
    import faulthandler
    from typing import List, Optional

except ImportError:
    faulthandler = None

from runez.convert import to_bytesize, to_int
from runez.date import local_timezone
from runez.file import basename as get_basename, parent_folder
from runez.system import _R, cached_property, find_caller_frame, flattened, LOG, quoted, short, Slotted, stringified
from runez.system import TERMINAL_INFO, ThreadGlobalContext, UNSET, WINDOWS


ORIGINAL_CF = logging.currentframe
RE_FORMAT_MARKERS = re.compile(r"{([a-z][a-z0-9_]*)}", re.IGNORECASE)
SPINNER_FPS = 10  # Animation overhead is ~0.1% at 10 FPS


def expanded(text, *args, **kwargs):
    """Generically expanded 'text': '{...}' placeholders are resolved from given objects / keyword arguments

    >>> expanded("{foo}", foo="bar")
    'bar'
    >>> expanded("{foo} {age}", {"age": 5}, foo="bar")
    'bar 5'

    Args:
        text (str): Text to format
        *args: Objects to extract values from (as attributes)
        **kwargs: Optional values provided as named args

    Returns:
        (str): '{...}' placeholders expanded from given `args` object's properties/fields, or as `kwargs`
    """
    if not text:
        return text

    if text.startswith("~"):
        text = os.path.expanduser(text)

    if "{" not in text:
        return text

    strict = kwargs.pop("strict", False)
    max_depth = kwargs.pop("max_depth", 3)
    objects = list(args) + [kwargs] if kwargs else args
    if not objects:
        return text

    definitions = {}
    markers = RE_FORMAT_MARKERS.findall(text)
    while markers:
        key = markers.pop()
        if key in definitions:
            continue

        val = _find_value(key, objects, max_depth)
        if strict and val is None:
            return None

        val = stringified(val) if val is not None else "{%s}" % key
        markers.extend(m for m in RE_FORMAT_MARKERS.findall(val) if m not in definitions)
        definitions[key] = val

    if not max_depth or not isinstance(max_depth, int) or max_depth <= 0:
        return text

    result = dict((k, _rformat(k, v, definitions, max_depth)) for k, v in definitions.items())
    return text.format(**result)


def formatted(message, *args, **kwargs):
    """
    Args:
        message (str): Message to format, support either the '%s' old method, or newer format() method

    Returns:
        (str): Formatted message
    """
    if not kwargs:
        if not args:
            return message

        if "%s" in message:
            try:
                return message % args

            except TypeError:
                pass

    try:
        return message.format(*args, **kwargs)

    except (IndexError, KeyError):
        return message


class ProgressHandler(logging.Handler):
    """Used to capture logging chatter and show it as progress"""

    level = logging.DEBUG

    @classmethod
    def handle(cls, record):
        """Intercept all log chatter and show it as progress message"""
        LogManager.progress.show(record.getMessage())

    @classmethod
    def emit(cls, record):
        """Not needed"""

    @classmethod
    def createLock(cls):
        """Not needed"""


class AsciiAnimation(object):
    """Contains a few progress spinner animation examples"""

    @classmethod
    def available_names(cls):
        """(list[str]): Available ascii animation names from this sample collection"""
        return sorted(k[3:] for k in dir(cls) if k.startswith("af_")) + ["off"]

    @classmethod
    def predefined(cls, name):
        """(AsciiFrames | None): Predefined animation with 'name', if any"""
        if name == "off":
            return AsciiFrames(None)

        if name in cls.available_names():
            return getattr(cls, "af_%s" % name)()

    @classmethod
    def af_dots(cls):
        """Dots going left and right"""
        return AsciiFrames(cls.symmetrical(["   ", ".  ", ".. ", "...", " ..", "  .", "   "]), fps=5)

    @classmethod
    def af_dotrot(cls):
        """Rotating dot"""
        return AsciiFrames(cls.circling_dots(), fps=5)

    @classmethod
    def af_dotrot2(cls):
        """2 rotating dots (one bigger, one smaller)"""
        chars = cycle(u"⣯⣷⣾⣽⣻⢿⡿⣟")
        return AsciiFrames(("%s%s" % (f, next(chars)) for f in cls.circling_dots()), fps=5)

    @classmethod
    def af_dotrot3(cls):
        """2 small rotating dots in opposite direction"""
        return AsciiFrames(cls.alternating_cycle(u"⡿⣟⣯⣷⣾⣽⣻⢿", size=2), fps=5)

    @classmethod
    def af_fill(cls):
        """Bar growing/shrinking vertically, then horizontally"""
        return AsciiFrames([" "] + cls.symmetrical(list(u"▁▂▃▄▅▆▇█")) + [" "] + cls.symmetrical(list(u"▏▎▍▌▋▊▉")))

    @classmethod
    def af_fill2(cls):
        """2 bars filling up and down"""
        return AsciiFrames(cls.travelling(cls.symmetrical(list(u"▁▂▃▄▅▆▇█")), 2))

    @classmethod
    def af_oh(cls):
        """Moving growing/shrinking O signal"""
        return AsciiFrames(cls.travelling(" .-oOOo-.", 3))

    @staticmethod
    def alternating_cycle(chars, size=2):
        """Rotate through characters in 'chars', in alternated direction, animation is 'size' characters wide"""
        alt = cycle((lambda: cycle(chars), lambda: cycle(reversed(chars))))
        cycles = [next(alt)() for _ in range(size)]
        return ("".join(next(c) for c in cycles) for _ in range(len(chars)))

    @classmethod
    def circling_dots(cls):
        return [u"▖ ", u"▗ ", u" ▖", u" ▗", u" ▝", u" ▘", u"▝ ", u"▘ "]

    @staticmethod
    def symmetrical(frames):
        """Frames followed by their reverse"""
        return frames + list(reversed(frames))

    @staticmethod
    def travelling(chars, size):
        """Animated 'chars', repeated 'size' times, moving left then right"""
        yield (["".join((" " * i, c, " " * (size - i - 1))) for c in chars] for i in range(size))
        if size > 2:
            yield (["".join((" " * (i + 1), c, " " * (size - i - 2))) for c in chars] for i in reversed(range(size - 2)))


class AsciiFrames(object):
    """Holds ascii animation frames, one-line animations of arbitrary size (should be playable in a loop for good visual effect)"""

    def __init__(self, frames, fps=SPINNER_FPS):
        """
        Args:
            frames: Frames composing the ascii animation
            fps (int): Desired frames per second
        """
        self.frames = flattened(frames, keep_empty=None) or None
        self.fps = fps
        self.animate_every = float(SPINNER_FPS) / fps
        self.countdown = 0.0
        self.index = 0

    def __repr__(self):
        return "off" if not self.frames else "%s frames" % len(self.frames)

    def next_frame(self):
        """
        Returns:
            (str): Next frame (infinite cycle across self.frames)
        """
        if self.frames:
            if self.countdown <= 0.1:
                self.countdown += self.animate_every
                self.index += 1
                if self.index >= len(self.frames):
                    self.index = 0

            self.countdown -= 1
            return self.frames[self.index]


class Progress(object):

    message_color = None
    spinner_color = None

    @cached_property
    def lock(self):
        return threading.Lock()

    @property
    def is_running(self):
        return self._thread is not None

    def show(self, message):
        if message:
            with self.lock:
                self._message = message

    def start(self, frames=UNSET, max_columns=140, message_color=None, spinner_color=None):
        """Start background thread if not already started

        Args:
            frames (AsciiFrames | None): Frames to use for spinner animation
            max_columns (int): Maximum number of terminal columns to use for progress line
            message_color (callable | None): Optional color to use for the message part
            spinner_color (callable | None): Optional color to use for the animated spinner
        """
        with self.lock:
            if frames is UNSET:
                frames = AsciiAnimation.predefined(os.environ.get("SPINNER")) or AsciiAnimation.af_dots()

            self.message_color = message_color
            self.spinner_color = spinner_color
            self._frames = frames or AsciiFrames(None)
            self._columns = TERMINAL_INFO.columns - 2
            if max_columns and max_columns > 0:
                self._columns = min(max_columns, self._columns)

            if self._thread is None:
                self._stderr_write = self._original_write(sys.stderr)
                if self._stderr_write is not None:
                    atexit.register(self.stop)
                    if not _R._runez_module().PY2:  # Can't replace 'write' in py2
                        sys.stderr.write = self._on_stderr
                        self._stdout_write = self._original_write(sys.stdout)
                        if self._stdout_write is not None:
                            sys.stdout.write = self._on_stdout

                    self._thread = threading.Thread(target=self._run, name="Progress")
                    self._thread.daemon = True
                    self._thread.start()
                    LogManager._auto_enable_progress_handler()
                    self._hide_cursor()

    def stop(self):
        with self.lock:
            if self._thread is not None:
                self._show_cursor()
                self._thread = None
                LogManager._auto_enable_progress_handler()
                if self._has_progress_line:
                    self._clear_line()

                if not _R._runez_module().PY2:  # Can't replace 'write' in py2
                    if self._stdout_write is not None:
                        sys.stdout.write = self._stdout_write
                        self._stdout_write = None

                    if self._stderr_write is not None:
                        sys.stderr.write = self._stderr_write
                        self._stderr_write = None

    _frames = None  # type: AsciiFrames # Frames to animate (set to None to stop animation)
    _thread = None  # type: Optional[threading.Thread] # Background daemon thread used to display progress
    _message = None  # type: Optional[str] # Message to be shown by background thread, on next run
    _columns = None  # type: int # Maximum number of columns to use for progress line
    _has_progress_line = False
    _stdout_write = None
    _stderr_write = None

    @staticmethod
    def _original_write(stream):
        if TERMINAL_INFO.isatty(stream):
            return stream.write

    def _clean_write(self, write, message):
        """Output 'message' using 'write' function, ensure any pending progress line is cleared first"""
        with self.lock:
            if self._has_progress_line:
                self._clear_line()
                self._has_progress_line = False

            write(message)

    def _on_stdout(self, message):
        self._clean_write(self._stdout_write, message)

    def _on_stderr(self, message):
        self._clean_write(self._stderr_write, message)

    def _hide_cursor(self):
        self._write("\033[?25l")

    def _show_cursor(self):
        self._write("\033[?25h")

    def _clear_line(self):
        self._write("\r\033[K")

    def _write(self, text):
        self._stderr_write(text)

    def _formatted_line(self, spin, spin_color, msg, msg_color):
        columns = self._columns
        if columns > 0 and (spin or msg):
            if spin:
                line = spin
                columns -= len(line)
                if spin_color:
                    line = spin_color(line)

            else:
                line = ""

            if msg:
                msg = short(_R._runez_module().uncolored(msg), size=columns)
                if msg_color:
                    msg = msg_color(msg)

                if line:
                    line += " "

                line += msg

            return line

    def _run(self):
        """Background thread handling progress reporting and animation"""
        try:
            sleep_delay = 1 / float(SPINNER_FPS)
            msg_fps = int(SPINNER_FPS / 2)  # Don't take any more than 2 messages per second
            msg_countdown = 0
            last_frame = last_message = current_message = None
            while self._thread:
                with self.lock:
                    if msg_countdown <= 0:
                        msg_countdown = msg_fps
                        current_message = self._message

                    current_frame = self._frames.next_frame()
                    if current_frame is not last_frame or current_message is not last_message:
                        last_frame = current_frame
                        last_message = current_message
                        line = self._formatted_line(current_frame, self.spinner_color, current_message, self.message_color)
                        if line:
                            self._clear_line()
                            self._write(line)
                            self._write("\r")
                            self._has_progress_line = True

                msg_countdown -= 1
                time.sleep(sleep_delay)

        finally:
            self.stop()


class TraceHandler(object):
    """
    Allows to optionally provide trace logging, typically activated by an env var, like:
        MY_APP_DEBUG=1 my-app ...
    """

    def __init__(self, prefix, stream=sys.stderr):
        self.prefix = prefix
        self.stream = stream

    def trace(self, message):
        """
        Args:
            message (str): Message to trace
        """
        if self.prefix:
            message = "%s%s" % (self.prefix, message)

        self.stream.write(message)
        if not message.endswith("\n"):
            self.stream.write("\n")

        self.stream.flush()


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
        "default_logger",
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
        return quoted(sys.argv)

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
            location (str | None): Location to auto-complete with {basename}, if it points to a folder

        Returns:
            (str | None): {location}/{basename}
        """
        path = expanded(location, self, os.environ, strict=True)
        if path:
            if os.path.isdir(path):
                filename = expanded(self.basename, self, strict=True)
                if not filename or not is_writable_folder(path):
                    return None

                return os.path.join(path, filename)

            parent = parent_folder(path)
            if not is_writable_folder(parent):
                try:
                    os.mkdir(parent)  # Create only one folder if possible (no mkdir -p)

                except OSError:
                    return None

            if is_writable_folder(parent):
                return path


def is_writable_folder(path):
    return path and os.path.isdir(path) and os.access(path, os.W_OK)


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


def default_log_locations():
    if WINDOWS:  # pragma: no cover
        return [os.path.join("{dev}", "log", "{basename}")]

    return ["{dev}/log/{basename}", "/logs/{appname}/{basename}", "/var/log/{basename}"]


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
        default_logger=LOG.debug,
        dev=None,
        file_format="%(asctime)s %(timezone)s [%(threadName)s] %(context)s%(levelname)s - %(message)s",
        file_level=logging.DEBUG,
        file_location=None,
        locations=default_log_locations(),
        rotate=None,
        rotate_count=10,
        timezone=local_timezone(),
        tmp=None,
    )

    # Spec defines how logs should be setup()
    # Best way to provide your spec is via: runez.log.setup(), for example:
    #   runez.log.setup(rotate="size:50m")
    spec = LogSpec(_default_spec)

    # Thread-local / global context
    context = ThreadGlobalContext(_ContextFilter)

    # Show progress, with animation
    progress = Progress()

    # Below fields should be read-only for outside users, do not modify these
    debug = False
    console_handler = None  # type: Optional[logging.StreamHandler]
    file_handler = None  # type: Optional[logging.FileHandler] # File we're currently logging to (if any)
    handlers = None  # type: Optional[List[logging.Handler]]
    tracer = None  # type: Optional[TraceHandler]
    used_formats = None  # type: Optional[str]
    faulthandler_signum = None  # type: Optional[int]

    _lock = threading.RLock()
    _logging_snapshot = LoggingSnapshot()

    @classmethod
    def set_debug(cls, debug):
        """Useful only as simple callback function, use runez.log.setup() for regular usage"""
        if debug is not UNSET:
            cls.debug = bool(debug)

        return cls.debug

    @classmethod
    def set_dryrun(cls, dryrun):
        """Useful only as simple callback function, use runez.log.setup() for regular usage"""
        _R.set_dryrun(dryrun)
        return _R.is_dryrun()

    @classmethod
    def set_file_location(cls, file_location):
        """Useful only as simple callback function, use runez.log.setup() for regular usage"""
        LogManager.spec.set(file_location=file_location)
        return cls.spec.file_location

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
        default_logger=UNSET,
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
            greetings (str | list[str] | None): Optional greetings message(s) to log
            appname (str | None): Program's base name, not used directly, just as reference for default 'basename'
            basename (str | None): Base name of target log file, not used directly, just as reference for default 'locations'
            console_format (str | None): Format to use for console log, use None to deactivate
            console_level (int | None): Level to use for console logging
            console_stream (io.TextIOBase | TextIO | None): Stream to use for console log (eg: sys.stderr), use None to deactivate
            context_format (str | None): Format to use for contextual log, use None to deactivate
            default_logger (callable | None): Default logger to use to trace operations such as runez.run() etc
            dev (str | None): Custom folder to use when running from a development venv (auto-determined if None)
            file_format (str | None): Format to use for file log, use None to deactivate
            file_level (int | None): Level to use for file logging
            file_location (str | None): Desired custom file location (overrides {locations} search, handy as a --log cli flag)
            locations (list[str]|None): List of candidate folders for file logging (None: deactivate file logging)
            rotate (str | None): How to rotate log file (None: no rotation, "time:1d" time-based, "size:50m" size-based)
            rotate_count (int): How many rotations to keep
            timezone (str | None): Time zone, use None to deactivate time zone logging
            tmp (str | None): Optional temp folder to use (auto determined)
        """
        with cls._lock:
            cls.set_debug(debug)
            cls.set_dryrun(dryrun)
            cls.spec.set(
                appname=appname,
                basename=basename,
                console_format=console_format,
                console_level=console_level or level,
                console_stream=console_stream,
                context_format=context_format,
                default_logger=default_logger,
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

            root_level = min(flattened([cls.spec.console_level, cls.spec.file_level], keep_empty=None))
            if root_level and root_level != logging.root.level:
                logging.root.setLevel(root_level)

            if cls.handlers is None:
                cls.handlers = []

            cls._setup_handler("console")
            cls._setup_handler("file")
            cls._auto_enable_progress_handler()
            cls._update_used_formats()
            cls._fix_logging_shortcuts()
            if clean_handlers:
                cls.clean_handlers()

            cls.greet(greetings)

    @classmethod
    def current_test(cls):
        """
        Returns:
            (str | None): Not empty if we're currently running a test (such as via pytest)
                          Actual value will be path to test_<name>.py file if user followed usual conventions,
                          otherwise path to first found test-framework module
        """
        import re

        regex = re.compile(r"^(.+\.|)(conftest|(test_|_pytest|unittest).+|.+_test)$")

        def is_test_frame(f):
            name = f.f_globals.get("__name__")
            if name and not name.startswith("runez"):
                return regex.match(name.lower()) and f.f_globals.get("__file__")

        return find_caller_frame(validator=is_test_frame)

    @staticmethod
    def dev_folder(*relative_path):
        """
        Args:
            *relative_path: Optional additional relative path to add

        Returns:
            (str | None): Path to development build folder (such as .venv, .tox etc), if we're currently running a dev build
        """
        folder = _find_parent_folder(sys.prefix, {"venv", ".venv", ".tox", "build"})
        if folder and relative_path:
            folder = os.path.join(folder, *relative_path)

        return folder

    @staticmethod
    def project_path(*relative_path):
        """
        Args:
            *relative_path: Optional additional relative path to add

        Returns:
            (str | None): Computed path, if we're currently running a dev build
        """
        path = _validated_project_path(LogManager.tests_path, LogManager.dev_folder)
        if path and relative_path:
            path = os.path.join(path, *relative_path)

        return path

    @staticmethod
    def tests_path(*relative_path):
        """
        Args:
            *relative_path: Optional additional relative path to add

        Returns:
            (str | None): Computed path, if we're currently running a test
        """
        path = _find_parent_folder(LogManager.current_test(), {"tests", "test"})
        if relative_path:
            path = os.path.join(path, *relative_path)

        return path

    @classmethod
    def greet(cls, greetings, logger=LOG.debug):
        """
        Args:
            greetings (str | list[str] | None): Greetings message(s) to log
            logger (callable | None): Logger to use
        """
        if greetings and logger:
            for msg in flattened(greetings, keep_empty=False):
                message = cls.formatted_greeting(msg)
                if message:
                    logger(message)

    @classmethod
    def clean_handlers(cls):
        """Remove all non-runez logging handlers"""
        for h in list(logging.root.handlers):
            if h is not cls.console_handler and h is not cls.file_handler and h is not ProgressHandler:
                logging.root.removeHandler(h)

    @classmethod
    def program_path(cls, path=None):
        """
        Args:
            path (str | None): Optional, path or name to consider (default: `sys.argv[0]`)

        Returns:
            (str): Path of currently running program
        """
        return path or sys.argv[0]

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
        cls.tracer = None
        cls.used_formats = None

    @classmethod
    def formatted_greeting(cls, greeting):
        if greeting:
            if cls.file_handler and cls.file_handler.baseFilename:
                location = cls.file_handler.baseFilename

            elif not cls.spec.should_log_to_file:
                location = "file log disabled"

            elif cls.spec.file_location:
                location = "given location '{file_location}' is not usable"

            else:
                location = "no usable locations from {locations}"

            return expanded(greeting, cls.spec, location=location)

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
            markers (str): Space separated list of markers to look for
            used_formats (str): Formats to consider (default: cls.used_formats)

        Returns:
            (bool): True if any one of the 'markers' is seen in 'used_formats'
        """
        if used_formats is None:
            used_formats = cls.used_formats

        if not markers or not used_formats:
            return False

        return any(marker in used_formats for marker in flattened(markers, split=" "))

    @classmethod
    def enable_faulthandler(cls, signum=getattr(signal, "SIGUSR1", None)):
        """Enable dumping thread stack traces when specified signals are received, similar to java's handling of SIGQUIT

        Note: this must be called from the surviving process in case of daemonization.

        Args:
            signum (int | None): Signal number to register for full thread stack dump (use None to disable)
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
    def enable_trace(cls, spec, prefix=":: ", stream=UNSET):
        """
        Args:
            spec (TraceHandler | str | bool | None):
            prefix (str | None): Prefix to use for trace messages
            stream: Where to trace (by default: current 'console_stream' if configured, otherwise sys.stderr)
        """
        if not spec or isinstance(spec, TraceHandler):
            cls.tracer = spec
            return

        cls.tracer = None
        if stream is UNSET:
            stream = cls.spec.console_stream or sys.stderr

        if stream:
            if isinstance(spec, bool):
                if spec and stream:
                    cls.tracer = TraceHandler(prefix, stream)

            elif os.environ.get(spec):
                cls.tracer = TraceHandler(prefix, stream)

    @classmethod
    def trace(cls, message, *args, **kwargs):
        """
        Args:
            message (str): Message to trace
        """
        if cls.tracer:
            message = formatted(message, *args, **kwargs)
            cls.tracer.trace(message)

    @classmethod
    def _auto_enable_progress_handler(cls):
        if cls.progress.is_running:
            if ProgressHandler not in logging.root.handlers:
                logging.root.handlers.append(ProgressHandler)

        elif ProgressHandler in logging.root.handlers:
            logging.root.handlers.remove(ProgressHandler)

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
            cls.spec.appname = get_basename(cls.program_path())

        if not cls.spec.dev:
            cls.spec.dev = cls.dev_folder()

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
        if cls.is_using_format("%(context)"):
            cls.context.enable(True)
            for handler in cls.handlers:
                handler.addFilter(cls.context.filter)

        else:
            for handler in cls.handlers:
                handler.removeFilter(cls.context.filter)

            cls.context.enable(False)

        if cls.is_using_format("%(pathname) %(filename) %(funcName) %(module)"):
            logging._srcfile = cls._logging_snapshot._srcfile

        else:
            logging._srcfile = None

        logging.logProcesses = cls.is_using_format("%(process)")
        logging.logThreads = cls.is_using_format("%(thread) %(threadName)")

        if not isinstance(logging.info, _LogWrap) and hasattr(sys, "_getframe"):
            logging.critical = _LogWrap(logging.CRITICAL)
            logging.fatal = logging.critical
            logging.error = _LogWrap(logging.ERROR)
            logging.exception = _LogWrap(logging.ERROR, exc_info=True)
            logging.warning = _LogWrap(logging.WARNING)
            logging.info = _LogWrap(logging.INFO)
            logging.debug = _LogWrap(logging.DEBUG)
            logging.log = _LogWrap.log


class _LogWrap(object):
    """Allows to correctly report caller file/function/line from convenience calls such as logging.info()"""

    def __init__(self, level, exc_info=None):
        self.level = level
        self.exc_info = exc_info
        self.__doc__ = getattr(logging, logging.getLevelName(level).lower()).__doc__

    @staticmethod
    def log(level, msg, *args, **kwargs):
        offset = kwargs.pop("_stack_offset", 1)
        name = sys._getframe(offset).f_globals.get("__name__")
        logger = logging.getLogger(name)
        try:
            logging.currentframe = lambda: sys._getframe(3 + offset)
            logger.log(level, msg, *args, **kwargs)

        finally:
            logging.currentframe = ORIGINAL_CF

    def __call__(self, msg, *args, **kwargs):
        kwargs.setdefault("exc_info", self.exc_info)
        kwargs.setdefault("_stack_offset", 2)
        self.log(self.level, msg, *args, **kwargs)


def _replace_and_pad(fmt, marker, replacement):
    """
    Args:
        fmt (str): Format to tweak
        marker (str): Marker to replace
        replacement (str): What to replace marker with

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
        fmt (str | None): Format specification

    Returns:
        (str | None): Canonical version of format
    """
    if not fmt:
        return fmt

    return _replace_and_pad(fmt, "%(timezone)s", LogManager.spec.timezone)


def _find_value(key, objects, max_depth):
    """Find a value for 'key' in any of the objects given as 'args'"""
    for obj in objects:
        v = _get_value(obj, key, max_depth)
        if v is not None:
            return v


def _get_value(obj, key, max_depth):
    """Get a value for 'key' from 'obj', if possible"""
    if obj is not None:
        if isinstance(obj, (list, tuple)):
            return _find_value(key, obj, max_depth - 1) if max_depth > 0 else None

        if hasattr(obj, "get"):
            return obj.get(key)

        return getattr(obj, key, None)


def _rformat(key, value, definitions, max_depth):
    m = RE_FORMAT_MARKERS.search(value)
    if not m:
        return value

    if max_depth > 1 and value and "{" in value:
        value = value.format(**definitions)
        return _rformat(key, value, definitions, max_depth=max_depth - 1)

    return value


def _find_parent_folder(path, basenames):
    if not path or len(path) <= 1:
        return None

    dirpath, basename = os.path.split(path)
    if basename and basename.lower() in basenames:
        return path

    return _find_parent_folder(dirpath, basenames)


def _validated_project_path(*funcs):
    for func in funcs:
        path = func()
        if path:
            path = os.path.dirname(path)
            if os.path.exists(os.path.join(path, "setup.py")) or os.path.exists(os.path.join(path, "project.toml")):
                return path


def _get_file_handler(location, rotate, rotate_count):
    """
    Args:
        location (str | None): Log file path
        rotate (str | None): How to rotate, examples:
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
