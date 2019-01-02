"""
Convenience methods for executing programs
"""

import os
import subprocess  # nosec
import sys

from runez.base import decode, flattened, represented_args, short, State
from runez.log import abort, debug


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


def is_executable(path):
    """
    :param str|None path: Path to file
    :return bool: True if file exists and is executable
    """
    return path and os.path.isfile(path) and os.access(path, os.X_OK)


def make_executable(path, fatal=True):
    """
    :param str|None path: chmod file with 'path' as executable
    :param bool|None fatal: Abort execution on failure if True
    :return int: 1 if effectively done, 0 if no-op, -1 on failure
    """
    if is_executable(path):
        return 0

    if State.dryrun:
        debug("Would make %s executable", short(path))
        return 1

    if not os.path.exists(path):
        return abort("%s does not exist, can't make it executable", short(path), fatal=(fatal, -1))

    try:
        os.chmod(path, 0o755)  # nosec
        return 1

    except Exception as e:
        return abort("Can't chmod %s: %s", short(path), e, fatal=(fatal, -1))


def run(program, *args, **kwargs):
    """Run 'program' with 'args'"""
    args = flattened(args, unique=False)
    full_path = which(program)

    logger = kwargs.pop("logger", debug)
    fatal = kwargs.pop("fatal", True)
    dryrun = kwargs.pop("dryrun", State.dryrun)
    include_error = kwargs.pop("include_error", False)

    message = "Would run" if dryrun else "Running"
    message = "%s: %s %s" % (message, short(full_path or program), represented_args(args))
    if logger:
        logger(message)

    if dryrun:
        return message

    if not full_path:
        return abort("%s is not installed", short(program), fatal=fatal)

    stdout = kwargs.pop("stdout", subprocess.PIPE)
    stderr = kwargs.pop("stderr", subprocess.PIPE)
    args = [full_path] + args
    try:
        path_env = kwargs.pop("path_env", None)
        if path_env:
            kwargs["env"] = added_env_paths(path_env, env=kwargs.get("env"))
        p = subprocess.Popen(args, stdout=stdout, stderr=stderr, **kwargs)  # nosec
        output, err = p.communicate()
        output = decode(output)
        err = decode(err)
        if output is not None:
            output = output.strip()
        if err is not None:
            err = err.strip()

        if p.returncode and fatal is not None:
            note = ": %s\n%s" % (err, output) if output or err else ""
            message = "%s exited with code %s%s" % (short(program), p.returncode, note.strip())
            return abort(message, fatal=fatal)

        if include_error and err:
            output = "%s\n%s" % (output, err)
        return output and output.strip()

    except Exception as e:
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
