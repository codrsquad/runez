"""
All public functions/classes are made available here.

Example usage (with this style, you can easily see all of your usages of runez by simply searching for `runez.`):

    import runez
    runez.copy("source", "dest")

Or (perhaps slightly harder to track runez usage, and also needlessly specific):

    from runez.file import copy
    copy("source", "dest")


DRYRUN mode:
    operations like copy(), delete() etc will not actually do their thing, but just log "Would ..." instead
    It's recommended to set DRYRUN only once at the start of your run via: runez.log.setup(dryrun=...)
"""

from runez import click, config, heartbeat, program, serialize
from runez.base import decode, Slotted, Undefined, UNSET
from runez.config import capped, from_json, to_boolean, to_bytesize, to_dict, to_int, to_number
from runez.context import CaptureOutput, CurrentFolder, TempFolder, TrackedOutput, verify_abort
from runez.convert import Anchored, flattened, formatted, quoted, represented_args, resolved_path, short, shortened
from runez.convert import affixed, camel_cased, entitled, get_words, snakified, wordified  # noqa, import order not useful here
from runez.convert import SANITIZED, SHELL, UNIQUE
from runez.file import copy, delete, first_line, get_conf, get_lines, move, symlink, touch, write
from runez.heartbeat import Heartbeat
from runez.logsetup import LogManager as log, LogSpec
from runez.path import basename, ensure_folder, parent_folder
from runez.program import check_pid, get_dev_folder, get_program_path, is_executable, is_younger, make_executable, run, which
from runez.represent import header
from runez.serialize import read_json, save_json, Serializable
from runez.system import abort, get_timezone, get_version, set_dryrun

__all__ = [
    "DRYRUN",
    "click", "config", "heartbeat", "logsetup", "program", "serialize",
    "decode", "Slotted", "Undefined", "UNSET",
    "capped", "from_json", "to_boolean", "to_bytesize", "to_dict", "to_int", "to_number",
    "CaptureOutput", "CurrentFolder", "TempFolder", "TrackedOutput", "verify_abort",
    "Anchored", "flattened", "formatted", "quoted", "represented_args", "resolved_path", "short", "shortened",
    "affixed", "camel_cased", "entitled", "get_words", "snakified", "wordified",
    "SANITIZED", "SHELL", "UNIQUE",
    "copy", "delete", "first_line", "get_conf", "get_lines", "move", "symlink", "touch", "write",
    "Heartbeat",
    "log", "LogSpec",
    "basename", "ensure_folder", "parent_folder",
    "check_pid", "get_dev_folder", "get_program_path", "is_executable", "is_younger", "make_executable", "run", "which",
    "header",
    "read_json", "save_json", "Serializable",
    "abort", "get_timezone", "get_version", "set_dryrun",
]

DRYRUN = False
