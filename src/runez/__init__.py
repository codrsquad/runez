"""
Friendly misc/utils/convenience library
"""

from runez import click, config, heartbeat, program, prompt, schema, serialize, thread
from runez.base import abort, capped, decode, flattened, formatted, get_version, is_tty, quoted, represented_args, resolved_path, set_dryrun, short, shortened, stringified
from runez.base import AbortException, AdaptedProperty, Anchored, CaptureOutput, CurrentFolder, Slotted, TempArgv, TrackedOutput, Undefined
from runez.base import auto_import_siblings, class_descendants, current_test, find_parent_folder, first_meaningful_line, verify_abort
from runez.base import PY2, SANITIZED, SHELL, UNIQUE, UNSET, WINDOWS
from runez.colors import ActivateColors, ColorManager as color, is_coloring, uncolored
from runez.colors.named import black, blue, brown, gray, green, orange, plain, purple, red, teal, white, yellow
from runez.colors.named import blink, bold, dim, invert, italic, strikethrough, underline
from runez.config import from_json
from runez.convert import affixed, camel_cased, entitled, identifiers, snakified, wordified, words
from runez.convert import plural, represented_bytesize, represented_with_units
from runez.convert import to_boolean, to_bytesize, to_float, to_int, unitized
from runez.date import date_from_epoch, datetime_from_epoch, elapsed, local_timezone, represented_duration, \
    timezone, timezone_from_text, \
    to_date, to_datetime, to_epoch, to_epoch_ms, to_seconds
from runez.date import SECONDS_IN_ONE_DAY, SECONDS_IN_ONE_HOUR, SECONDS_IN_ONE_MINUTE, SECONDS_IN_ONE_YEAR, UTC
from runez.file import copy, delete, first_line, ini_to_dict, move, readlines, symlink, TempFolder, terminal_width, touch, write
from runez.heartbeat import Heartbeat
from runez.logsetup import LogManager as log, LogSpec
from runez.path import basename, ensure_folder, parent_folder
from runez.program import check_pid, dev_folder, is_executable, is_younger, make_executable, program_path
from runez.program import require_installed, run, which
from runez.prompt import ask_once
from runez.represent import align, header, indented, PrettyTable
from runez.serialize import json_sanitized, read_json, represented_json, save_json, Serializable
from runez.thread import thread_local_property, ThreadLocalSingleton

__all__ = [
    "DRYRUN",
    "click", "config", "heartbeat", "program", "prompt", "schema", "serialize", "thread",
    "abort", "capped", "decode", "flattened", "formatted", "get_version", "is_tty", "quoted", "represented_args", "resolved_path", "set_dryrun", "short", "shortened", "stringified",
    "AbortException", "AdaptedProperty", "Anchored", "CaptureOutput", "CurrentFolder", "Slotted", "TempArgv", "TrackedOutput", "Undefined",
    "auto_import_siblings", "class_descendants", "current_test", "find_parent_folder", "first_meaningful_line", "verify_abort",
    "PY2", "SANITIZED", "SHELL", "UNIQUE", "UNSET", "WINDOWS",
    "ActivateColors", "color", "is_coloring", "uncolored",
    "black", "blue", "brown", "gray", "green", "orange", "plain", "purple", "red", "teal", "white", "yellow",
    "blink", "bold", "dim", "invert", "italic", "strikethrough", "underline",
    "from_json",
    "affixed", "camel_cased", "entitled", "identifiers", "snakified", "wordified", "words",
    "plural", "represented_bytesize", "represented_with_units",
    "to_boolean", "to_bytesize", "to_float", "to_int", "unitized",
    "date_from_epoch", "datetime_from_epoch", "elapsed", "local_timezone", "represented_duration",
    "timezone", "timezone_from_text",
    "to_date", "to_datetime", "to_epoch", "to_epoch_ms", "to_seconds",
    "SECONDS_IN_ONE_DAY", "SECONDS_IN_ONE_HOUR", "SECONDS_IN_ONE_MINUTE", "SECONDS_IN_ONE_YEAR", "UTC",
    "copy", "delete", "first_line", "ini_to_dict", "move", "readlines", "symlink", "TempFolder", "terminal_width", "touch", "write",
    "Heartbeat",
    "log", "LogSpec",
    "basename", "ensure_folder", "parent_folder",
    "check_pid", "dev_folder", "is_executable", "is_younger", "make_executable", "program_path",
    "require_installed", "run", "which",
    "ask_once",
    "align", "header", "indented", "PrettyTable",
    "json_sanitized", "read_json", "represented_json", "save_json", "Serializable",
    "thread_local_property", "ThreadLocalSingleton",
]

DRYRUN = False


class system:
    # This is here for temporary backwars compatibility, because runez.system.AbortException was removed
    pass
