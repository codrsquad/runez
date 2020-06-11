"""
Convenience methods for executing programs
"""

import os
import shutil
import subprocess  # nosec
import sys
import tempfile

from runez.convert import to_int
from runez.system import _R, abort, decode, flattened, LOG, quoted, short, UNSET, WINDOWS


DEFAULT_INSTRUCTIONS = {
    "darwin": "run: `brew install {program}`",
    "linux": "run: `apt install {program}`",
}


def check_pid(pid):
    """
    Args:
        pid (int | None): Pid to examine

    Returns:
        (bool): True if process with pid exists
    """
    if not pid:  # No support for kill pid 0, as that is not the intent of this function, and it's not cross platform
        return False

    if WINDOWS:  # pragma: no cover
        import ctypes

        kernel32 = ctypes.windll.kernel32
        SYNCHRONIZE = 0x100000
        process = kernel32.OpenProcess(SYNCHRONIZE, 0, pid)
        if process:
            kernel32.CloseHandle(process)
            return True

        return False

    try:
        os.kill(pid, 0)
        return True

    except (OSError, TypeError):
        return False


def is_executable(path):
    """
    Args:
        path (str | None): Path to file

    Returns:
        (bool): True if file exists and is executable
    """
    if WINDOWS:  # pragma: no cover
        return bool(_windows_exe(path))

    return path and os.path.isfile(path) and os.access(path, os.X_OK)


def make_executable(path, fatal=True, logger=UNSET, dryrun=UNSET):
    """
    Args:
        path (str): chmod file with 'path' as executable
        fatal (bool | None): True: abort execution on failure, False: don't abort but log, None: don't abort, don't log
        logger (callable | None): Logger to use, False to log errors only, None to disable log chatter
        dryrun (bool): Optionally override current dryrun setting

    Returns:
        (int): In non-fatal mode, 1: successfully done, 0: was no-op, -1: failed
    """
    if is_executable(path):
        return 0

    if _R.hdry(dryrun, logger, "make %s executable" % short(path)):
        return 1

    if not os.path.exists(path):
        return abort("%s does not exist, can't make it executable" % short(path), return_value=-1, fatal=fatal, logger=logger)

    try:
        os.chmod(path, 0o755)  # nosec
        _R.hlog(logger, "Made '%s' executable" % short(path))
        return 1

    except Exception as e:
        return abort("Can't chmod %s" % short(path), exc_info=e, return_value=-1, fatal=fatal, logger=logger)


def run(program, *args, **kwargs):
    """
    Run 'program' with 'args'

    Keyword Args:
        dryrun (bool): When True, do not really run but call logger("Would run: ...") instead [default: runez.DRYRUN]
        fatal (bool): If True: abort() on error [default: True]
        logger (callable | None): When provided, call logger("Running: ...") [default: LOG.debug]
        path_env (dict | None): Allows to inject PATH-like env vars, see `_added_env_paths()`
        stdout (int | IO[Any] | None): Passed-through to subprocess.Popen, [default: subprocess.PIPE]
        stderr (int | IO[Any] | None): Passed-through to subprocess.Popen, [default: subprocess.PIPE]

    Args:
        *args: Command line args to call 'program' with
        **kwargs: Passed through to `subprocess.Popen`

    Returns:
        (RunResult): Run outcome, use .failed, .succeeded, .output, .error etc to inspect the outcome
    """
    fatal = kwargs.pop("fatal", True)
    logger = kwargs.pop("logger", UNSET)
    dryrun = kwargs.pop("dryrun", UNSET)
    stdout = kwargs.pop("stdout", subprocess.PIPE)
    stderr = kwargs.pop("stderr", subprocess.PIPE)
    path_env = kwargs.pop("path_env", None)
    if path_env:
        kwargs["env"] = _added_env_paths(path_env, env=kwargs.get("env"))

    args = flattened(args, shellify=True)
    full_path = which(program)
    result = RunResult(audit=RunAudit(full_path or program, args, kwargs))
    description = "%s %s" % (short(full_path or program), quoted(args))
    if _R.hdry(dryrun, logger, "run: %s" % description):
        result.audit.dryrun = True
        result.exit_code = 0
        if stdout is not None:
            result.output = "[dryrun] %s" % description  # Properly simulate a successful run

        if stdout is not None:
            result.error = ""

        return result

    if not full_path:
        result.error = "%s is not installed" % short(program)
        return abort(result.error, return_value=result, fatal=fatal, logger=logger)

    _R.hlog(logger, "Running: %s" % description)
    with _WrappedArgs([full_path] + args) as wrapped_args:
        try:
            p = subprocess.Popen(wrapped_args, stdout=stdout, stderr=stderr, **kwargs)  # nosec
            if fatal is None and stdout is None and stderr is None:
                out, err = None, None  # Don't wait on spawned process

            else:
                out, err = p.communicate()

            result.output = decode(out, strip=True)
            result.error = decode(err, strip=True)
            result.pid = p.pid
            result.exit_code = p.returncode

        except Exception as e:
            if fatal:
                # Don't re-wrap with an abort(), let original stacktrace show through
                raise

            result.exc_info = e
            if not result.error:
                result.error = "%s failed: %s" % (short(program), e)

        if fatal and result.exit_code:
            if logger is not None:
                # Log full output, unless user explicitly turned it off
                message = ["Run failed: %s" % description]
                if result.error:
                    message.append("\nstderr:\n%s" % result.error)

                if result.output:
                    message.append("\nstdout:\n%s" % result.output)

                LOG.error("\n".join(message))

            message = "%s exited with code %s" % (short(program), result.exit_code)
            abort(message, code=result.exit_code, exc_info=result.exc_info, fatal=fatal, logger=logger)

        return result


class RunAudit(object):
    """Provided as given by original code, for convenient reference"""

    def __init__(self, program, args, kwargs):
        """
        Args:
            program (str): Program as given by caller (or full path when available)
            args (list): Args given by caller
            kwargs (dict): Keyword args passed-through to subporcess.Popen()
        """
        self.program = program
        self.args = args
        self.kwargs = kwargs
        self.dryrun = False  # Was this a dryrun?


class RunResult(object):
    """Holds result of a runez.run()"""

    def __init__(self, output=None, error=None, code=1, audit=None):
        """
        Args:
            output (str | None): Captured output (on stdout), if any
            error (str | None): Captured error output (on stderr), if any
            code (int): Exit code
            audit (RunAudit): Optional audit object recording what run this was related to
        """
        self.output = output
        self.error = error
        self.exit_code = code
        self.exc_info = None  # Exception that occurred during the run, if any
        self.pid = None  # Pid of spawned process, if any
        self.audit = audit

    def __repr__(self):
        return "RunResult(exit_code=%s)" % self.exit_code

    def __eq__(self, other):
        if isinstance(other, RunResult):
            return self.output == other.output and self.error == other.error and self.exit_code == other.exit_code

    def __bool__(self):
        return self.exit_code == 0

    @property
    def full_output(self):
        """Full output, error first"""
        if self.output is not None or self.error is not None:
            output = "%s\n%s" % (self.error or "", self.output or "")
            return output.strip()

    @property
    def failed(self):
        return self.exit_code != 0

    @property
    def succeeded(self):
        return self.exit_code == 0


def terminal_width(default=None):
    """Get the width (number of columns) of the terminal window.

    Args:
        default: Default to use if terminal width could not be determined

    Returns:
        (int): Determined terminal width, if possible
    """
    for func in (_tw_shutil, _tw_env):
        columns = func()
        if columns is not None:
            return columns

    return to_int(default)


def which(program, ignore_own_venv=False):
    """
    Args:
        program (str | None): Program name to find via env var PATH
        ignore_own_venv (bool): If True, do not resolve to executables in current venv

    Returns:
        (str | None): Full path to program, if one exists and is executable
    """
    if not program:
        return None

    if os.path.isabs(program):
        if WINDOWS:  # pragma: no cover
            return _windows_exe(program)

        return program if is_executable(program) else None

    for p in os.environ.get("PATH", "").split(os.pathsep):
        fp = os.path.join(p, program)
        if WINDOWS:  # pragma: no cover
            fp = _windows_exe(fp)

        if fp and (not ignore_own_venv or not fp.startswith(sys.prefix)) and is_executable(fp):
            return fp

    program = os.path.join(os.getcwd(), program)
    if is_executable(program):
        return program

    return None


def require_installed(program, instructions=None, platform=sys.platform):
    """Raise an expcetion if 'program' is not available on PATH, show instructions on how to install it

    Args:
        program (str): Program to check
        instructions (str | dict): Short instructions letting user know how to get `program` installed, example: `run: brew install foo`
                                   Extra convenience, specify:
                                   - None if `program` can simply be install via `brew install <program>`
                                   - A word (without spaces) to refer to "usual" package (brew on OSX, apt on Linux etc)
                                   - A dict with instructions per `sys.platform`
        platform (str | None): Override sys.platform (for testing instructions rendering)

    Returns:
        (bool): True if installed, False otherwise (when fatal=False)
    """
    if which(program) is None:
        if not instructions:
            instructions = DEFAULT_INSTRUCTIONS

        if isinstance(instructions, dict):
            instructions = _install_instructions(instructions, platform)

        message = "{program} is not installed"
        if instructions:
            if "\n" in instructions:
                message += ":\n- %s" % instructions

            else:
                message += ", %s" % instructions

        message = message.format(program=program)
        abort(message)


def _added_env_paths(env_vars, env=None):
    """
    Args:
        env_vars (dict): Env var customizations to apply
        env (dict | None): Original env vars (default: os.environ)

    Returns:
        (dict): Resulting merged env vars
    """
    if not env:
        env = os.environ

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


def _install_instructions(instructions_dict, platform):
    text = instructions_dict.get(platform)
    if not text:
        text = "\n- ".join("on %s: %s" % (k, v) for k, v in instructions_dict.items())

    return text


def _tw_shutil():
    try:
        return shutil.get_terminal_size().columns

    except Exception:
        return None


def _tw_env():
    return to_int(os.environ.get("COLUMNS"))


def _windows_exe(path):  # pragma: no cover
    if path:
        for extension in (".exe", ".bat"):
            fpath = path
            if not fpath.lower().endswith(extension):
                fpath += extension

            if os.path.isfile(fpath):
                return fpath


class _WrappedArgs(object):
    """Context manager to temporarily work around https://youtrack.jetbrains.com/issue/PY-40692"""

    def __init__(self, args):
        self.args = args
        self.tmp_folder = None

    def __enter__(self):
        args = self.args
        if not WINDOWS and "PYCHARM_HOSTED" in os.environ and len(args) > 1 and "python" in args[0] and args[1][:2] in ("-m", "-X"):
            self.tmp_folder = os.path.realpath(tempfile.mkdtemp())
            wrapper = os.path.join(self.tmp_folder, "pydev-wrapper.sh")
            with open(wrapper, "wt") as fh:
                fh.write('exec "$@"\n')

            args = ["/bin/sh", wrapper] + args

        return args

    def __exit__(self, *_):
        if self.tmp_folder:
            shutil.rmtree(self.tmp_folder)
