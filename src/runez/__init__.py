"""
Friendly misc/utils/convenience library
"""

from runez import click, colors, config, heartbeat, program, prompt, schema, serialize, thread
from runez.base import class_descendants, decode, PY2, Slotted, stringified, Undefined, UNSET
from runez.colors import bg, fg
from runez.colors.fg import black, blue, brown, gray, green, orange, plain, purple, red, teal, white, yellow
from runez.colors.terminal import activate_colors, Color, color_adjusted_size, is_coloring, is_tty, uncolored
from runez.colors.terminal import blink, bold, dim, invert, italic, strikethrough, underline
from runez.config import from_json
from runez.context import CaptureOutput, CurrentFolder, TrackedOutput, verify_abort
from runez.convert import Anchored, capped, flattened, formatted, plural, quoted, \
    represented_args, represented_bytesize, represented_with_units, \
    resolved_path, short, shortened
from runez.convert import affixed, camel_cased, entitled, get_words, snakified, wordified  # noqa, import order not useful here
from runez.convert import SANITIZED, SHELL, to_boolean, to_bytesize, to_float, to_int, UNIQUE, unitized
from runez.date import date_from_epoch, datetime_from_epoch, elapsed, get_local_timezone, represented_duration, \
    timezone, timezone_from_text, \
    to_date, to_datetime, to_epoch, to_epoch_ms, to_seconds
from runez.date import SECONDS_IN_ONE_DAY, SECONDS_IN_ONE_HOUR, SECONDS_IN_ONE_MINUTE, SECONDS_IN_ONE_YEAR, UTC
from runez.file import copy, delete, first_line, get_conf, get_lines, move, symlink, TempFolder, terminal_width, touch, write
from runez.heartbeat import Heartbeat
from runez.logsetup import LogManager as log, LogSpec
from runez.path import basename, ensure_folder, parent_folder
from runez.program import check_pid, get_dev_folder, get_program_path, is_executable, is_younger, make_executable
from runez.program import require_installed, run, which
from runez.prompt import ask_once
from runez.represent import header
from runez.serialize import json_sanitized, read_json, represented_json, save_json, Serializable
from runez.system import abort, auto_import_siblings, current_test, get_platform, get_version, set_dryrun, WINDOWS
from runez.thread import thread_local_property, ThreadLocalSingleton

__all__ = [
    "DRYRUN",
    "click", "colors", "config", "heartbeat", "logsetup", "program", "prompt", "schema", "serialize", "thread",
    "class_descendants", "decode", "PY2", "Slotted", "stringified", "Undefined", "UNSET",
    "bg", "fg",
    "black", "blue", "brown", "gray", "green", "orange", "plain", "purple", "red", "teal", "white", "yellow",
    "activate_colors", "Color", "color_adjusted_size", "is_coloring", "is_tty", "uncolored",
    "blink", "bold", "dim", "invert", "italic", "strikethrough", "underline",
    "from_json",
    "CaptureOutput", "CurrentFolder", "TrackedOutput", "verify_abort",
    "Anchored", "capped", "flattened", "formatted", "plural", "quoted",
    "represented_args", "represented_bytesize", "represented_with_units",
    "resolved_path", "short", "shortened",
    "affixed", "camel_cased", "entitled", "get_words", "snakified", "wordified",
    "SANITIZED", "SHELL", "to_boolean", "to_bytesize", "to_float", "to_int", "UNIQUE", "unitized",
    "date_from_epoch", "datetime_from_epoch", "elapsed", "get_local_timezone", "represented_duration",
    "timezone", "timezone_from_text",
    "to_date", "to_datetime", "to_epoch", "to_epoch_ms", "to_seconds",
    "SECONDS_IN_ONE_DAY", "SECONDS_IN_ONE_HOUR", "SECONDS_IN_ONE_MINUTE", "SECONDS_IN_ONE_YEAR", "UTC",
    "copy", "delete", "first_line", "get_conf", "get_lines", "move", "symlink", "TempFolder", "terminal_width", "touch", "write",
    "Heartbeat",
    "log", "LogSpec",
    "basename", "ensure_folder", "parent_folder",
    "check_pid", "get_dev_folder", "get_program_path", "is_executable", "is_younger", "make_executable",
    "require_installed", "run", "which",
    "ask_once",
    "header",
    "json_sanitized", "read_json", "represented_json", "save_json", "Serializable",
    "abort", "auto_import_siblings", "current_test", "get_platform", "get_version", "set_dryrun", "WINDOWS",
    "thread_local_property", "ThreadLocalSingleton",
]

DRYRUN = False
