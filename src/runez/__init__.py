"""
Friendly misc/utils/convenience library
"""

from runez import ascii, click, config, date, file, program, serialize, system
from runez.colors import ActivateColors, ColorManager as color
from runez.colors.named import black, blue, brown, gray, green, orange, plain, purple, red, teal, white, yellow
from runez.colors.named import blink, bold, dim, invert, italic, strikethrough, underline
from runez.convert import affixed, camel_cased, entitled, identifiers, snakified, wordified, words
from runez.convert import parsed_tabular, to_boolean, to_bytesize, to_float, to_int, unitized
from runez.convert import plural, represented_bytesize, represented_with_units
from runez.date import date_from_epoch, datetime_from_epoch, elapsed, local_timezone, represented_duration, \
    timezone, timezone_from_text, to_date, to_datetime, to_epoch, to_epoch_ms, to_seconds, UTC
from runez.file import basename, checksum, ensure_folder, parent_folder, readlines, TempFolder, to_path, touch, write
from runez.file import compress, copy, decompress, delete, filesize, ls_dir, move, symlink
from runez.logsetup import LogManager as log, ProgressBar
from runez.program import check_pid, is_executable, make_executable, PsInfo, run, shell, which
from runez.serialize import from_json, read_json, represented_json, save_json, Serializable
from runez.system import abort, abort_if, AdaptedProperty, cached_property, uncolored, Undefined, UNSET, wcswidth, WINDOWS
from runez.system import Anchored, CaptureOutput, CurrentFolder, Slotted, TempArgv, TrackedOutput
from runez.system import capped, decode, DEV, flattened, joined, quoted, resolved_path, short, stringified, SYS_INFO
from runez.system import first_line, get_version, is_basetype, is_iterable, ltattr

__all__ = [
    "DRYRUN",
    "ascii", "click", "config", "date", "file", "program", "serialize", "system",
    "ActivateColors", "color",
    "black", "blue", "brown", "gray", "green", "orange", "plain", "purple", "red", "teal", "white", "yellow",
    "blink", "bold", "dim", "invert", "italic", "strikethrough", "underline",
    "affixed", "camel_cased", "entitled", "identifiers", "snakified", "wordified", "words",
    "parsed_tabular", "to_boolean", "to_bytesize", "to_float", "to_int", "unitized",
    "plural", "represented_bytesize", "represented_with_units",
    "date_from_epoch", "datetime_from_epoch", "elapsed", "local_timezone", "represented_duration",
    "timezone", "timezone_from_text", "to_date", "to_datetime", "to_epoch", "to_epoch_ms", "to_seconds", "UTC",
    "basename", "checksum", "ensure_folder", "parent_folder", "readlines", "TempFolder", "to_path", "touch", "write",
    "compress", "copy", "decompress", "delete", "filesize", "ls_dir", "move", "symlink",
    "log", "ProgressBar",
    "check_pid", "is_executable", "make_executable", "PsInfo", "run", "shell", "which",
    "from_json", "read_json", "represented_json", "save_json", "Serializable",
    "abort", "abort_if", "AdaptedProperty", "cached_property", "uncolored", "Undefined", "UNSET", "wcswidth", "WINDOWS",
    "Anchored", "CaptureOutput", "CurrentFolder", "Slotted", "TempArgv", "TrackedOutput",
    "capped", "decode", "DEV", "flattened", "joined", "quoted", "resolved_path", "short", "stringified", "SYS_INFO",
    "first_line", "get_version", "is_basetype", "is_iterable", "ltattr"
]

DRYRUN = False
color.activate_colors()
colored = color.colored
cli = click.Cli  # Handy way of running multi-commands with argparse
