"""
Convenience methods for executing programs
"""

import logging
import os
import subprocess  # nosec
import sys
import time

from runez.base import decode
from runez.convert import flattened, represented_args, SHELL, short
from runez.system import abort, AbortException, is_dryrun


LOG = logging.getLogger(__name__)
DEV_FOLDERS = ("venv", ".venv", ".tox", "build")


def check_pid(pid):
    """
    :param int pid: Pid to examine
    :return bool: True if process with pid exists
    """
    try:
        os.kill(pid, 0)
        return True

    except (OSError, TypeError):
        return False


def get_dev_folder(path=sys.prefix):
    """
    :param str path: Path to examine
    :return str|None: Path to development build folder, such as .venv, .tox etc, if any
    """
    if not path or len(path) <= 4:
        return None
    dirpath, basename = os.path.split(path)
    if basename in DEV_FOLDERS:
        return path
    return get_dev_folder(dirpath)


def get_program_path(path=None):
    """
    :return str: Path of currently running program
    """
    if path is None:
        path = sys.argv[0]
    return which(path) or path


def is_executable(path):
    """
    :param str|None path: Path to file
    :return bool: True if file exists and is executable
    """
    return path and os.path.isfile(path) and os.access(path, os.X_OK)


def is_younger(path, age):
    """
    :param str|None path: Path to file
    :param int|float age: How many seconds to consider the file too old
    :return bool: True if file exists and is younger than 'age' seconds
    """
    try:
        return time.time() - os.path.getmtime(path) < age

    except (OSError, TypeError):
        return False


def make_executable(path, fatal=True):
    """
    :param str|None path: chmod file with 'path' as executable
    :param bool|None fatal: Abort execution on failure if True
    :return int: 1 if effectively done, 0 if no-op, -1 on failure
    """
    if is_executable(path):
        return 0

    if is_dryrun():
        LOG.debug("Would make %s executable", short(path))
        return 1

    if not os.path.exists(path):
        return abort("%s does not exist, can't make it executable", short(path), fatal=(fatal, -1))

    try:
        os.chmod(path, 0o755)  # nosec
        return 1

    except Exception as e:
        return abort("Can't chmod %s: %s", short(path), e, fatal=(fatal, -1))


def run(program, *args, **kwargs):
    """
    Run 'program' with 'args'

    Special optional keyword arguments:
    - dryrun (bool): When True (defaults to runez.DRYRUN), do not really run but call logger("Would run: ...") instead

    - fatal (bool | None):
        - when program invocation succeeds:
            - return output if available (ie: if stdout/stderr were not explicitly provided as None)
            - return exit code otherwise
        - when program invocation fails:
            - with fatal=None: Return `None` on failure
            - with fatal=False: Return False on failure
            - with fatal=True: Raise AbortException(exit_code) on failure

    - include_error (bool): When True, include stderr contents in returned string

    - logger (callable | None): When provided (defaults to LOG.debug), call logger("Running: ...")

    - path_env (dict | None): Allows to inject PATH-like env vars, see `added_env_paths()`

    - stdout, stderr: Passed through to `subprocess.Popen`, when both are None causes this function to return exit code instead of output
    """
    args = flattened(args, split=SHELL)
    full_path = which(program)

    logger = kwargs.pop("logger", LOG.debug)
    fatal = kwargs.pop("fatal", True)
    dryrun = kwargs.pop("dryrun", is_dryrun())
    include_error = kwargs.pop("include_error", False)

    message = "Would run" if dryrun else "Running"
    message = "%s: %s %s" % (message, short(full_path or program), represented_args(args))
    if logger:
        logger(message)

    stdout = kwargs.pop("stdout", subprocess.PIPE)
    stderr = kwargs.pop("stderr", subprocess.PIPE)

    if dryrun:
        if stdout is None and stderr is None:
            return 0
        return message

    if not full_path:
        return abort("%s is not installed", short(program), fatal=fatal)

    args = [full_path] + args
    try:
        path_env = kwargs.pop("path_env", None)
        if path_env:
            kwargs["env"] = added_env_paths(path_env, env=kwargs.get("env"))
        p = subprocess.Popen(args, stdout=stdout, stderr=stderr, **kwargs)  # nosec
        output, err = p.communicate()
        output = decode(output, strip=True)
        err = decode(err, strip=True)

        if stdout is None and stderr is None:
            if p.returncode and fatal:
                return abort("%s exited with code %s" % (short(program), p.returncode), fatal=fatal, code=p.returncode)
            return p.returncode

        if p.returncode and fatal is not None:
            note = ": %s\n%s" % (err, output) if output or err else ""
            message = "%s exited with code %s%s" % (short(program), p.returncode, note.strip())
            return abort(message, fatal=fatal, code=p.returncode)

        if include_error and err:
            output = "%s\n%s" % (output, err)

        return output and output.strip()

    except Exception as e:
        if isinstance(e, AbortException):
            raise
        return abort("%s failed: %s", short(program), e, exc_info=e, fatal=fatal)


def which(program, ignore_own_venv=False):
    """
    :param str|None program: Program name to find via env var PATH
    :param bool ignore_own_venv: If True, do not resolve to executables in current venv
    :return str|None: Full path to program, if one exists and is executable
    """
    if not program:
        return None
    if os.path.isabs(program):
        return program if is_executable(program) else None
    for p in os.environ.get("PATH", "").split(":"):
        fp = os.path.join(p, program)
        if (not ignore_own_venv or not fp.startswith(sys.prefix)) and is_executable(fp):
            return fp
    program = os.path.join(os.getcwd(), program)
    if is_executable(program):
        return program
    return None


def added_env_paths(env_vars, env=None):
    """
    :param dict|None env_vars: Env vars to customize
    :param dict env: Original env vars
    """
    if not env_vars:
        return None

    if not env:
        env = dict(os.environ)

    result = dict(env)
    for env_var, paths in env_vars.items():
        separator = paths[0]
        paths = paths[1:]
        current = env.get(env_var, "")
        current = [x for x in current.split(separator) if x]

        added = 0
        for path in paths.split(separator):
            if path not in current:
                added += 1
                current.append(path)

        if added:
            result[env_var] = separator.join(current)

    return result
