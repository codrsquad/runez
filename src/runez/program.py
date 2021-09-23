"""
Convenience methods for executing programs
"""

import errno
import fcntl
import os
import pty
import shutil
import struct
import subprocess  # nosec
import sys
import tempfile
import termios
from io import BytesIO
from select import select

from runez.convert import parsed_tabular, to_int
from runez.system import _R, abort, cached_property, decode, flattened, quoted, resolved_path, short, SYS_INFO, uncolored
from runez.system import UNSET, WINDOWS


DEFAULT_INSTRUCTIONS = {
    "darwin": "run: `brew install {program}`",
    "linux": "run: `apt install {program}`",
}
PS_FOLLOW = {
    "tmux": ("tmux", "display-message", "-p", "#{client_pid}"),
}


class PsInfo:
    """Summary info about a process, as given by `ps -f` command"""

    info = None  # type: dict # Info returned by `ps`

    def __init__(self, pid=None):
        """
        Args:
            pid (int | str): PID of process to get info for (default: current process)
        """
        self.pid = to_int(pid) or os.getpid()
        if self.pid:
            r = run("ps", "-f", self.pid, dryrun=False, fatal=False, logger=None)
            if r.succeeded:
                info = parsed_tabular(r.output)
                if info:
                    self.info = info[0]

    def __repr__(self):
        return "%s %s %s" % (self.pid, self.ppid, self.cmd)

    def __eq__(self, other):
        return isinstance(other, PsInfo) and self.pid == other.pid

    @classmethod
    def from_pid(cls, pid):
        """
        Args:
            pid (int | None): PID of process to get info for

        Returns:
            (PsInfo | None): Process info, if available
        """
        if pid:
            p = PsInfo(pid)
            if p.info is not None:
                return p

    @cached_property
    def cmd(self):
        """str: Reported CMD"""
        if self.info is not None:
            return self.info.get("CMD")

    @cached_property
    def cmd_basename(self):
        """str: Basename of CMD, if available"""
        cmd = self.cmd
        if cmd:
            cmd, _, rest = cmd.partition(" ")
            if os.path.isabs(cmd):
                # `ps` doesn't quote program paths
                if is_executable(cmd):
                    return os.path.basename(cmd)

                acc = cmd
                while rest:
                    more, _, rest = rest.partition(" ")
                    acc = "%s %s" % (acc, more)
                    if is_executable(acc):
                        return os.path.basename(acc)

        return cmd

    @cached_property
    def followed_parent(self):
        """
        Returns:
            (PsInfo | None): Parent process info (if any), special processes like tmux are followed through
        """
        if self.parent and self.parent.ppid == 1:
            follow_command = PS_FOLLOW.get(self.parent.cmd_basename)
            if follow_command:
                r = run(*follow_command, dryrun=False, fatal=False, logger=None)
                if r.succeeded:
                    p = PsInfo.from_pid(to_int(r.output))
                    if p:
                        return p

        return self.parent

    @cached_property
    def parent(self):
        """
        Returns:
            (PsInfo | None): Parent process info (if any)
        """
        if self.ppid:
            return PsInfo(self.ppid)

    @cached_property
    def ppid(self):
        """int: Reported parent PID"""
        if self.info is not None:
            return to_int(self.info.get("PPID"))

    @cached_property
    def uid(self):
        """int: Numerical UID as reported by ps"""
        if self.info is not None:
            uid = self.info.get("UID")
            if uid is not None:
                n = to_int(uid)
                if n is not None:
                    return n

                r = run("id", "-u", uid, dryrun=False, fatal=False, logger=None)
                if r.succeeded:
                    return to_int(r.output)

    @cached_property
    def userid(self):
        """str: Userid as reported by ps"""
        if self.info is not None:
            uid = self.info.get("UID")
            if uid is not None:
                n = to_int(uid)
                if n is None:
                    return uid

                r = run("id", "-un", uid, dryrun=False, fatal=False, logger=None)
                if r.succeeded:
                    return r.output

    def parent_list(self, follow=True):
        """
        Args:
            follow (bool): If True, try and follow special processes like tmux

        Returns:
            (list[PsInfo]): List of parent processes
        """
        p = self.followed_parent if follow else self.parent
        return [p] + p.parent_list(follow=follow) if p else []


def auto_shellify(args):
    if args and len(args) == 1 and hasattr(args[0], "split"):
        return args[0].split()

    return flattened(args, shellify=True)


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


def daemonize():
    """Daemonize this process, detach from parent

    Returns:
        (int | None): Child pid if returning in current process, None if in child (forked) process
    """
    child_pid = os.fork()
    if child_pid:  # 1st fork
        return child_pid

    os.setsid()  # Create new session
    if os.fork():  # pragma: no cover, 2nd fork
        os._exit(0)

    devnull_fd = os.open(os.devnull, os.O_RDWR)
    os.dup2(devnull_fd, sys.__stdin__.fileno())
    os.dup2(devnull_fd, sys.__stdout__.fileno())
    os.dup2(devnull_fd, sys.__stderr__.fileno())
    os.close(devnull_fd)


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
        fatal (type | bool | None): True: abort execution on failure, False: don't abort but log, None: don't abort, don't log
        logger (callable | bool | None): Logger to use, True to print(), False to trace(), None to disable log chatter
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


def run(
    program, *args, background=False, fatal=True, logger=UNSET, dryrun=UNSET, short_exe=UNSET,
    passthrough=False, path_env=None, strip="\r\n",
    stdout=subprocess.PIPE, stderr=subprocess.PIPE, **popen_args
):
    """Run 'program' with 'args'
    Args:
        program (str | pathlib.Path): Program to run (full path, or basename)
        *args: Command line args to call 'program' with
        background (bool): When True, background the spawned process (detach from console and current process)
        fatal (type | bool | None): True: abort execution on failure, False: don't abort but log, None: don't abort, don't log
        logger (callable | bool | None): Logger to use, True to print(), False to trace(), None to disable log chatter
        dryrun (bool): Optionally override current dryrun setting
        short_exe (str | bool | None): Try to log a compact representation of executable
        passthrough (bool | file | None): If True-ish, pass-through stderr/stdout in addition to capturing it
                                          as well as 'passthrough' itself if it has a write() function
        path_env (dict | None): Allows to inject PATH-like env vars, see `_added_env_paths()`
        strip (str | bool | None): If provided, `strip()` the captured output [default: strip "\n" newlines]
        stdout (int | IO[Any] | None): Passed-through to subprocess.Popen, [default: subprocess.PIPE]
        stderr (int | IO[Any] | None): Passed-through to subprocess.Popen, [default: subprocess.PIPE]
        **popen_args: Passed through to `subprocess.Popen`

    Returns:
        (RunResult): Run outcome, use .failed, .succeeded, .output, .error etc to inspect the outcome
    """
    if path_env:
        popen_args["env"] = _added_env_paths(path_env, env=popen_args.get("env"))

    args = flattened(args, shellify=True)
    full_path = which(program)
    result = RunResult(audit=RunAudit(full_path or program, args, popen_args))
    description = result.audit.run_description(short_exe=short_exe)
    if background:
        description += " &"

    abort_logger = None if logger is None else UNSET
    if logger is True or logger is print:
        # When logger is True, we just print() the message, so we may as well color it nicely
        description = _R.colored(description, "bold")

    if _R.hdry(dryrun, logger, "run: %s" % description):
        result.audit.dryrun = True
        result.exit_code = 0
        if stdout is not None:
            result.output = "[dryrun] %s" % description  # Properly simulate a successful run

        if stdout is not None:
            result.error = ""

        return result

    if not full_path:
        if program and os.path.basename(program) == program:
            result.error = "%s is not installed (PATH=%s)" % (short(program), short(os.environ.get("PATH")))

        else:
            result.error = "%s is not an executable" % short(program)

        return abort(result.error, return_value=result, fatal=fatal, logger=abort_logger)

    _R.hlog(logger, "Running: %s" % description)
    if background:
        child_pid = daemonize()
        if child_pid:
            result.pid = child_pid  # In parent process, we just report a successful run (we don't wait/check on background process)
            result.exit_code = 0
            return result

        fatal = False  # pragma: no cover, non-fatal mode in background process (there is no more console etc to report anything)

    with _WrappedArgs([full_path] + args) as wrapped_args:
        try:
            p, out, err = _run_popen(wrapped_args, popen_args, passthrough, fatal, stdout, stderr)
            result.output = decode(out, strip=strip)
            result.error = decode(err, strip=strip)
            result.pid = p.pid
            result.exit_code = p.returncode

        except Exception as e:
            if fatal:
                # Don't re-wrap with an abort(), let original stacktrace show through
                raise

            result.exc_info = e
            if not result.error:
                result.error = "%s failed: %s" % (short(program), repr(e) if isinstance(e, OSError) else e)

        if fatal and result.exit_code:
            base_message = "%s exited with code %s" % (short(program), result.exit_code)
            if passthrough and (result.output or result.error):
                exception = _R.abort_exception(override=fatal)
                if exception is SystemExit:
                    raise SystemExit(result.exit_code)

                if isinstance(exception, type) and issubclass(exception, BaseException):
                    raise exception(base_message)

            message = []
            if abort_logger is not None and not passthrough:
                # Log full output, unless user explicitly turned it off
                message.append("Run failed: %s" % description)
                if result.error:
                    message.append("\nstderr:\n%s" % result.error)

                if result.output:
                    message.append("\nstdout:\n%s" % result.output)

            message.append(base_message)
            abort("\n".join(message), code=result.exit_code, exc_info=result.exc_info, fatal=fatal, logger=abort_logger)

        if background:
            os._exit(result.exit_code)  # pragma: no cover, simply exit forked process (don't go back to caller)

        return result


def shell(*args, fatal=False, logger=False, dryrun=False):
    """Output of a quick shell command, same as run(), but doesn't log and returns output only (when available)

    Args:
        *args: Program and arguments to run
        fatal (type | bool | None): True: abort execution on failure, False: don't abort but log, None: don't abort, don't log
        logger (callable | bool | None): Logger to use, True to print(), False to trace(), None to disable log chatter
        dryrun (bool): Override current dryrun setting

    Returns:
        (str | None): Output (stdout) of command, if successful
    """
    r = run(*auto_shellify(args), fatal=fatal, logger=logger, dryrun=dryrun)
    if r.succeeded:
        return r.output


class RunAudit:
    """Provided as given by original code, for convenient reference"""

    def __init__(self, program, args, popen_args):
        """
        Args:
            program (str | pathlib.Path): Program as given by caller (or full path when available)
            args (list): Args given by caller
            popen_args (dict): Keyword args passed-through to subporcess.Popen()
        """
        self.program = str(program)
        self.args = args
        self.popen_args = popen_args
        self.dryrun = False  # Was this a dryrun?

    @staticmethod
    def shortened_program(program, args):
        if program and args:
            base = os.path.basename(program)
            if base in ("python", "python3"):
                if args[0] == "-m":
                    return args[1], args[2:]

                if args[0].startswith("-m"):
                    return args[0][2:], args[1:]

                if args[0].endswith("__main__.py"):
                    program = args[0]
                    program = os.path.dirname(os.path.abspath(program))
                    return os.path.basename(program), args[1:]

            elif SYS_INFO.venv_bin_folder and program.startswith(SYS_INFO.venv_bin_folder):
                return base, args

        return short(program), args

    def run_description(self, short_exe=UNSET):
        """
        Args:
            short_exe (str | bool | None): Try to log a compact representation of executable

        Returns:
            (str): Description for self.program run with self.args
        """
        program = self.program
        args = self.args
        if short_exe is UNSET and program and SYS_INFO.venv_bin_folder:
            short_exe = program.startswith(SYS_INFO.venv_bin_folder)

        if isinstance(short_exe, str):
            program = short_exe

        elif short_exe is True:
            program, args = self.shortened_program(program, args)

        else:
            program = short(program)

        return "%s %s" % (program, quoted(args)) if args and program else program


class RunResult:
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


def which(program, ignore_own_venv=False):
    """
    Args:
        program (str | pathlib.Path | None): Program name to find via env var PATH
        ignore_own_venv (bool): If True, do not resolve to executables in current venv

    Returns:
        (str | None): Full path to program, if one exists and is executable
    """
    if not program:
        return None

    program = str(program)
    if os.path.basename(program) != program:
        program = resolved_path(program)
        if WINDOWS:  # pragma: no cover
            return _windows_exe(program)

        return program if is_executable(program) else None

    for p in os.environ.get("PATH", "").split(os.pathsep):
        fp = os.path.join(p, program)
        if WINDOWS:  # pragma: no cover
            fp = _windows_exe(fp)

        if fp and (not ignore_own_venv or not SYS_INFO.venv_bin_folder or not fp.startswith(SYS_INFO.venv_bin_folder)):
            if is_executable(fp):
                return fp

    program = os.path.join(os.getcwd(), program)
    if is_executable(program):
        return program

    return None


def require_installed(program, instructions=None, platform=sys.platform):
    """Raise an exception if 'program' is not available on PATH, show instructions on how to install it

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


def _read_data(fd, length=1024):
    """Isolated as a function for test mocking"""
    return os.read(fd, length)


def _run_popen(args, popen_args, passthrough, fatal, stdout, stderr):
    """Run subprocess.Popen(), capturing output accordingly"""
    if not passthrough:
        p = subprocess.Popen(args, stdout=stdout, stderr=stderr, **popen_args)  # nosec
        if fatal is None and stdout is None and stderr is None:
            return p, None, None  # Don't wait on spawned process

        out, err = p.communicate()
        return p, decode(out), decode(err)

    # Capture output, but also let it pass-through as-is to the terminal
    stdout_r, stdout_w = pty.openpty()
    stderr_r, stderr_w = pty.openpty()
    stdout_buffer = BytesIO()
    stderr_buffer = BytesIO()
    term_size = struct.pack("HHHH", SYS_INFO.terminal.lines, SYS_INFO.terminal.columns, 0, 0)
    for fd in (stdout_r, stdout_w, stderr_r, stderr_w):
        fcntl.ioctl(fd, termios.TIOCSWINSZ, term_size)

    passthrough = getattr(passthrough, "stream", passthrough)  # Convenience support for things like logging handlers
    if not hasattr(passthrough, "write"):
        passthrough = None

    with subprocess.Popen(args, stdout=stdout_w, stderr=stderr_w, **popen_args) as p:  # nosec
        os.close(stdout_w)
        os.close(stderr_w)
        readable = [stdout_r, stderr_r]
        while readable:
            for fd in select(readable, [], [])[0]:
                try:
                    data = _read_data(fd)
                    if not data:
                        readable.remove(fd)
                        continue

                    text = decode(data)
                    _safe_write(passthrough, text)
                    if fd == stdout_r:
                        _safe_write(sys.stdout, text, flush=sys.stdout.buffer)
                        _safe_write(stdout_buffer, data)

                    else:
                        _safe_write(sys.stderr, text, flush=sys.stderr.buffer)
                        _safe_write(stderr_buffer, data)

                except OSError as e:
                    if e.errno != errno.EIO:  # On some OS-es, EIO means EOF
                        raise

                    readable.remove(fd)

    sys.stdout.flush()
    sys.stderr.flush()
    os.close(stdout_r)
    os.close(stderr_r)
    return p, uncolored(decode(stdout_buffer.getvalue())), uncolored(decode(stderr_buffer.getvalue()))


def _safe_write(target, data, flush=None):
    if target is not None and data is not None:
        try:
            target.write(data)
            if flush is not None:
                flush.flush()

        except Exception:  # nosec, don't consider run crashed if one of the channels we're passing through is failing
            pass


def _windows_exe(path):  # pragma: no cover
    if path:
        if os.path.isfile(path):
            return path

        for extension in (".exe", ".bat"):
            fpath = path
            if not fpath.lower().endswith(extension):
                fpath += extension

            if os.path.isfile(fpath):
                return fpath


class _WrappedArgs:
    """Context manager to temporarily work around https://youtrack.jetbrains.com/issue/PY-40692"""

    def __init__(self, args):
        self.args = args
        self.tmp_folder = None

    def __enter__(self):
        args = self.args
        if not WINDOWS and "PYCHARM_HOSTED" in os.environ and len(args) > 1 and "python" in args[0] and args[1][:2] in ("-m", "-X", "-c"):
            self.tmp_folder = os.path.realpath(tempfile.mkdtemp())
            wrapper = os.path.join(self.tmp_folder, "pydev-wrapper.sh")
            with open(wrapper, "wt") as fh:
                fh.write('exec "$@"\n')

            args = ["/bin/sh", wrapper] + args

        return args

    def __exit__(self, *_):
        if self.tmp_folder:
            shutil.rmtree(self.tmp_folder, ignore_errors=True)
