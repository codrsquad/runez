"""
Friendly misc/utils/convenience library
"""

from runez import click, config, date, file, program, serialize, system
from runez.colors import ActivateColors, ColorManager as color, uncolored
from runez.colors.named import black, blue, brown, gray, green, orange, plain, purple, red, teal, white, yellow
from runez.colors.named import blink, bold, dim, invert, italic, strikethrough, underline
from runez.config import from_json
from runez.convert import affixed, camel_cased, entitled, identifiers, snakified, wordified, words
from runez.convert import parsed_tabular, to_boolean, to_bytesize, to_float, to_int, unitized
from runez.convert import plural, represented_bytesize, represented_with_units
from runez.date import date_from_epoch, datetime_from_epoch, elapsed, local_timezone, represented_duration, \
    timezone, timezone_from_text, to_date, to_datetime, to_epoch, to_epoch_ms, to_seconds, UTC
from runez.file import basename, copy, delete, ensure_folder, move, parent_folder, readlines, symlink, TempFolder, touch, write
from runez.logsetup import LogManager as log
from runez.program import check_pid, is_executable, make_executable, ps_info, run, which
from runez.serialize import read_json, represented_json, save_json, Serializable
from runez.system import abort, AdaptedProperty, cached_property, chill_property, PY2, Undefined, UNSET, WINDOWS
from runez.system import Anchored, CaptureOutput, CurrentFolder, Slotted, TempArgv, TrackedOutput
from runez.system import decode, flattened, joined, quoted, resolved_path, short, stringified, TERMINAL_INFO
from runez.system import FallbackChain, first_line, get_version, is_basetype, is_iterable, python_version

__all__ = [
    "DRYRUN",
    "click", "config", "date", "file", "program", "serialize", "system",
    "ActivateColors", "color", "uncolored",
    "black", "blue", "brown", "gray", "green", "orange", "plain", "purple", "red", "teal", "white", "yellow",
    "blink", "bold", "dim", "invert", "italic", "strikethrough", "underline",
    "from_json",
    "affixed", "camel_cased", "entitled", "identifiers", "snakified", "wordified", "words",
    "parsed_tabular", "to_boolean", "to_bytesize", "to_float", "to_int", "unitized",
    "plural", "represented_bytesize", "represented_with_units",
    "date_from_epoch", "datetime_from_epoch", "elapsed", "local_timezone", "represented_duration",
    "timezone", "timezone_from_text", "to_date", "to_datetime", "to_epoch", "to_epoch_ms", "to_seconds", "UTC",
    "basename", "copy", "delete", "ensure_folder", "move", "parent_folder", "readlines", "symlink", "TempFolder", "touch", "write",
    "log",
    "check_pid", "is_executable", "make_executable", "ps_info", "run", "which",
    "read_json", "represented_json", "save_json", "Serializable",
    "abort", "AdaptedProperty", "cached_property", "chill_property", "PY2", "Undefined", "UNSET", "WINDOWS",
    "Anchored", "CaptureOutput", "CurrentFolder", "Slotted", "TempArgv", "TrackedOutput",
    "decode", "flattened", "joined", "quoted", "resolved_path", "short", "stringified", "TERMINAL_INFO",
    "FallbackChain", "first_line", "get_version", "is_basetype", "is_iterable", "python_version",
]

DRYRUN = False
color.activate_colors()
