"""
Friendly misc/utils/convenience library
"""

from runez import click, config, date, file, program, serialize, system
from runez.colors import ActivateColors, ColorManager as color, uncolored
from runez.colors.named import black, blue, brown, gray, green, orange, plain, purple, red, teal, white, yellow
from runez.colors.named import blink, bold, dim, invert, italic, strikethrough, underline
from runez.config import from_json
from runez.convert import affixed, camel_cased, entitled, identifiers, snakified, wordified, words
from runez.convert import plural, represented_bytesize, represented_with_units
from runez.convert import to_boolean, to_bytesize, to_float, to_int, unitized
from runez.date import date_from_epoch, datetime_from_epoch, elapsed, local_timezone, represented_duration, \
    timezone, timezone_from_text, to_date, to_datetime, to_epoch, to_epoch_ms, to_seconds, UTC
from runez.file import basename, copy, delete, ensure_folder, move, parent_folder, readlines, symlink, TempFolder, touch, write
from runez.logsetup import LogManager as log
from runez.program import check_pid, is_executable, make_executable, run, terminal_width, which
from runez.serialize import read_json, represented_json, save_json, Serializable
from runez.system import abort, decode, expanded, flattened, quoted, short, stringified
from runez.system import AdaptedProperty, Anchored, CaptureOutput, CurrentFolder, Slotted, TempArgv, TrackedOutput, Undefined, UNSET
from runez.system import first_line, get_version, is_tty, PY2, resolved_path, WINDOWS

__all__ = [
    "DRYRUN",
    "click", "config", "date", "file", "program", "serialize", "system",
    "ActivateColors", "color", "uncolored",
    "black", "blue", "brown", "gray", "green", "orange", "plain", "purple", "red", "teal", "white", "yellow",
    "blink", "bold", "dim", "invert", "italic", "strikethrough", "underline",
    "from_json",
    "affixed", "camel_cased", "entitled", "identifiers", "snakified", "wordified", "words",
    "plural", "represented_bytesize", "represented_with_units",
    "to_boolean", "to_bytesize", "to_float", "to_int", "unitized",
    "date_from_epoch", "datetime_from_epoch", "elapsed", "local_timezone", "represented_duration",
    "timezone", "timezone_from_text", "to_date", "to_datetime", "to_epoch", "to_epoch_ms", "to_seconds", "UTC",
    "basename", "copy", "delete", "ensure_folder", "move", "parent_folder", "readlines", "symlink", "TempFolder", "touch", "write",
    "log",
    "check_pid", "is_executable", "make_executable", "run", "terminal_width", "which",
    "read_json", "represented_json", "save_json", "Serializable",
    "abort", "decode", "expanded", "flattened", "quoted", "short", "stringified",
    "AdaptedProperty", "Anchored", "CaptureOutput", "CurrentFolder", "Slotted", "TempArgv", "TrackedOutput", "Undefined", "UNSET",
    "first_line", "get_version", "is_tty", "PY2", "resolved_path", "WINDOWS",
]

DRYRUN = False
color.activate_colors()
