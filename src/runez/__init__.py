"""
All public functions/classes are made available here.

Example usage (with this style, you can easily see all of your usages of runez by simply searching for `runez.`):
    import runez
    runez.copy("source", "dest")

Or (perhaps slightly harder to track runez usage, and also needlessly specific):
    from runez.file import copy
    copy("source", "dest")

DRYRUN mode: operations like copy(), delete() etc will not actually do their thing, but just log "Would ..." instead
It's recommended to set DRYRUN only once at the start of your run via: runez.log.setup(dryrun=...)
"""

from runez import heartbeat, program, serialize
from runez.base import decode, prop, Slotted
from runez.context import CaptureOutput, CurrentFolder, TempFolder, verify_abort
from runez.convert import Anchored, flattened, formatted, quoted, represented_args, resolved_path, short, shortened, to_int
from runez.file import copy, delete, first_line, get_conf, get_lines, move, symlink, touch, write
from runez.heartbeat import Heartbeat
from runez.logsetup import LogManager as log, LogSpec
from runez.path import basename, ensure_folder, parent_folder
from runez.program import check_pid, get_dev_folder, get_program_path, is_executable, is_younger, make_executable, run, which
from runez.serialize import read_json, save_json, Serializable
from runez.system import abort, get_timezone, get_version, set_dryrun

__all__ = [
    "DRYRUN",
    "heartbeat", "logsetup", "program", "serialize",
    "decode", "prop", "Slotted",
    "CaptureOutput", "CurrentFolder", "TempFolder", "verify_abort",
    "Anchored", "flattened", "formatted", "quoted", "represented_args", "resolved_path", "short", "shortened", "to_int",
    "copy", "delete", "first_line", "get_conf", "get_lines", "move", "symlink", "touch", "write",
    "Heartbeat",
    "log", "LogSpec",
    "basename", "ensure_folder", "parent_folder",
    "check_pid", "get_dev_folder", "get_program_path", "is_executable", "is_younger", "make_executable", "run", "which",
    "read_json", "save_json", "Serializable",
    "abort", "get_timezone", "get_version", "set_dryrun",
]

DRYRUN = False
