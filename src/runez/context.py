"""
Convenience context managers
"""

import os
import shutil
import sys
import tempfile

try:
    import StringIO

    StringIO = StringIO.StringIO

except ImportError:
    from io import StringIO

from runez.convert import Anchored, resolved_path, SYMBOLIC_TMP
from runez.system import AbortException, is_dryrun, set_dryrun


LOG_AUTO_CAPTURE = False
_LOG_CAPTURE_STACK = []


class CapturedStream(object):
    """Capture output to a stream by hijacking temporarily its write() function"""

    def __init__(self, name, target=None, buffer=None):
        self.name = name
        self.target = target
        if buffer is not None:
            self.buffer = StringIO(buffer.getvalue())
            self.name += "*"

        else:
            self.buffer = StringIO()

    @classmethod
    def emit(cls, caller, record):
        if _LOG_CAPTURE_STACK:
            buffer = _LOG_CAPTURE_STACK[-1]
            msg = caller.format(record)
            buffer.write(msg)
            buffer.write("\n")
            return True

    def __repr__(self):
        return self.contents()

    def __eq__(self, other):
        if isinstance(other, CapturedStream):
            return self.name == other.name and self.contents() == other.contents()
        return str(self).strip() == str(other).strip()

    def __contains__(self, item):
        return item is not None and item in self.contents()

    def __len__(self):
        return len(self.contents())

    def duplicate(self):
        return CapturedStream(self.name, buffer=StringIO(self.contents()))

    def contents(self):
        """
        Returns:
            str: Contents of `self.buffer`
        """
        return self.buffer.getvalue()

    def write(self, message):
        self.buffer.write(message)

    def capture(self):
        if self.target:
            self.original = self.target.write
            self.target.write = self.write

        elif self.name == "log":
            _LOG_CAPTURE_STACK.append(self.buffer)

    def restore(self):
        """Restore hijacked write() function"""
        if self.target:
            self.target.write = self.original

        elif self.name == "log":
            _LOG_CAPTURE_STACK.pop()

    def pop(self, strip=False):
        """Current content popped, useful for testing"""
        r = self.contents()
        self.clear()
        if r and strip:
            r = r.strip()
        return r

    def clear(self):
        """Clear captured content"""
        self.buffer.seek(0)
        self.buffer.truncate(0)


def _dupe(cap):
    """
    :param CapturedStream|None cap:
    :return CapturedStream|None: Duplicate of 'cap', if any
    """
    if cap is not None:
        return cap.duplicate()


class TrackedOutput(object):
    """
    Track captured output
    """

    def __init__(self, stdout, stderr, log):
        """
        :param CapturedStream|None stdout: Captured stdout
        :param CapturedStream|None stderr: Captured stderr
        :param CapturedStream|None log: Captured logging
        """
        self.stdout = stdout
        self.stderr = stderr
        self.log = log
        self.captured = [c for c in (self.stdout, self.stderr, self.log) if c is not None]

    def __repr__(self):
        return "\n".join("%s: %s" % (s.name, s) for s in self.captured)

    def __eq__(self, other):
        if isinstance(other, TrackedOutput):
            return self.stdout == other.stdout and self.stderr == other.stderr and self.log == other.log
        return str(self).strip() == str(other).strip()

    def __contains__(self, item):
        return any(item in s for s in self.captured)

    def __len__(self):
        return sum(len(s) for s in self.captured)

    def duplicate(self):
        return TrackedOutput(_dupe(self.stdout), _dupe(self.stderr), _dupe(self.log))

    def contents(self):
        return "".join(s.contents() for s in self.captured)

    def pop(self):
        """Current content popped, useful for testing"""
        r = self.contents()
        self.clear()
        return r

    def clear(self):
        """Clear captured content"""
        for s in self.captured:
            s.clear()


class CaptureOutput(TrackedOutput):
    """
    Context manager allowing to temporarily grab stdout/stderr output.
    Output is captured and made available only for the duration of the context.

    Sample usage:

    with CaptureOutput() as logged:
        # do something that generates output
        # output has been captured in 'logged'
    """

    def __init__(self, level=None, stdout=True, stderr=True, log=None, anchors=None, dryrun=None):
        """
        :param int|None level: Change logging level, if specified
        :param bool stdout: Capture stdout
        :param bool stderr: Capture stderr
        :param bool|None log: Capture pytest logging (if running in pytest), leave at None for auto-detect
        :param str|list anchors: Optional paths to use as anchors for short()
        :param bool|None dryrun: Override dryrun (when explicitly specified, ie not None)
        """
        stdout = CapturedStream("stdout", target=sys.stdout) if stdout else None
        stderr = CapturedStream("stderr", target=sys.stderr) if stderr else None
        if log is None:
            log = LOG_AUTO_CAPTURE
        log = CapturedStream("log") if log else None
        super(CaptureOutput, self).__init__(stdout, stderr, log)
        self.level = level
        self.anchors = anchors
        self.dryrun = dryrun

    def __enter__(self):
        for s in self.captured:
            s.capture()
        if self.anchors:
            Anchored.add(self.anchors)
        if self.dryrun is not None:
            self.dryrun = set_dryrun(self.dryrun)
        return self

    def __exit__(self, *args):
        for s in self.captured:
            s.restore()
        if self.anchors:
            Anchored.pop(self.anchors)
        if self.dryrun is not None:
            set_dryrun(self.dryrun)
        self.clear()


class CurrentFolder(object):
    """
    Context manager for changing the current working directory
    """

    def __init__(self, destination, anchor=False):
        self.anchor = anchor
        self.destination = resolved_path(destination)

    def __enter__(self):
        self.current_folder = os.getcwd()
        os.chdir(self.destination)
        if self.anchor:
            Anchored.add(self.destination)

    def __exit__(self, *_):
        os.chdir(self.current_folder)
        if self.anchor:
            Anchored.pop(self.destination)


class TempFolder(object):
    """
    Context manager for obtaining a temp folder
    """

    def __init__(self, anchor=True, dryrun=None, follow=True):
        """
        :param anchor: If True, short-ify paths relative to used temp folder
        :param dryrun: Override dryrun (if provided)
        :param follow: If True, change working dir to temp folder (and restore)
        """
        self.anchor = anchor
        self.dryrun = dryrun
        self.follow = follow
        self.old_cwd = None
        self.tmp_folder = None

    def __enter__(self):
        if self.dryrun is not None:
            self.dryrun = set_dryrun(self.dryrun)
        if not is_dryrun():
            # Use realpath() to properly resolve for example symlinks on OSX temp paths
            self.tmp_folder = os.path.realpath(tempfile.mkdtemp())
            if self.follow:
                self.old_cwd = os.getcwd()
                os.chdir(self.tmp_folder)
        tmp = self.tmp_folder or SYMBOLIC_TMP
        if self.anchor:
            Anchored.add(tmp)
        return tmp

    def __exit__(self, *_):
        if self.anchor:
            Anchored.pop(self.tmp_folder or SYMBOLIC_TMP)
        if self.old_cwd:
            os.chdir(self.old_cwd)
        if self.tmp_folder:
            shutil.rmtree(self.tmp_folder)
        if self.dryrun is not None:
            set_dryrun(self.dryrun)


def verify_abort(func, *args, **kwargs):
    """
    Convenient wrapper around functions that should exit or raise an exception

    Example:
        assert "Can't create folder" in verify_abort(ensure_folder, "/dev/null/not-there")

    :param callable func: Function to execute
    :param args: Args to pass to 'func'
    :param Exception expected_exception: Type of exception that should be raised
    :param kwargs: Named args to pass to 'func'
    :return str: Chatter from call to 'func', if it did indeed raise
    """
    expected_exception = kwargs.pop("expected_exception", AbortException)
    with CaptureOutput() as logged:
        try:
            func(*args, **kwargs)
            return None
        except expected_exception:
            return str(logged)
