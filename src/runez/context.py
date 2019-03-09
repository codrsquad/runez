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
from runez.system import AbortException, get_caller_name, is_dryrun, set_dryrun


LOG_AUTO_CAPTURE = False
_LOG_STACK = []
_STACKS = {"stdout": [], "stderr": [], "log": _LOG_STACK}


class CapturedStream(object):
    """Capture output to a stream by hijacking temporarily its write() function"""

    def __init__(self, caller, name, target=None):
        self.meta = {"caller": caller}
        self.name = name
        self.target = target
        self.buffer = StringIO()

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

    def write(self, message):
        stack = _STACKS[self.name]
        if stack:
            stack[-1].buffer.write(message)

    def contents(self):
        """
        Returns:
            str: Contents of `self.buffer`
        """
        return self.buffer.getvalue()

    def _start_capture(self):
        _STACKS[self.name].append(self)
        if self.target:
            self.meta["original"] = self.target.write
            self.target.write = self.write

    def _stop_capture(self):
        _STACKS[self.name].pop()
        if self.target:
            self.target.write = self.meta["original"]

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

    def contents(self):
        return "".join(s.contents() for s in self.captured)

    def pop(self):
        """Current content popped, useful for testing"""
        r = self.contents()
        self.clear()
        return r

    def clear(self):
        """Clear captured content"""
        assert True
        for s in self.captured:
            s.clear()


class CaptureOutput(object):
    """
    Context manager allowing to temporarily grab stdout/stderr/log output.
    Output is captured and made available only for the duration of the context.

    Sample usage:

    with CaptureOutput() as logged:
        # do something that generates output
        # output has been captured in `logged`, see `logged.stdout` etc
        assert "foo" in logged
        assert "bar" in logged.stdout
    """

    def __init__(self, level=None, stdout=True, stderr=True, log=None, anchors=None, dryrun=None):
        """
        :param int|None level: Change logging level, if specified
        :param bool stdout: Capture stdout
        :param bool stderr: Capture stderr
        :param bool|None log: Capture logging, leave at None to default to LOG_AUTO_CAPTURE
        :param str|list anchors: Optional paths to use as anchors for short()
        :param bool|None dryrun: Override dryrun (when explicitly specified, ie not None)
        """
        self.level = level
        self.stdout = stdout
        self.stderr = stderr
        self.log = LOG_AUTO_CAPTURE if log is None else log
        self.anchors = anchors
        self.dryrun = dryrun
        self.caller = get_caller_name()

    def __enter__(self):
        self.tracked = TrackedOutput(
            CapturedStream(self.caller, "stdout", sys.stdout) if self.stdout else None,
            CapturedStream(self.caller, "stderr", sys.stderr) if self.stderr else None,
            CapturedStream(self.caller, "log") if self.log else None,
        )

        for c in self.tracked.captured:
            c._start_capture()

        if self.anchors:
            Anchored.add(self.anchors)

        if self.dryrun is not None:
            self.dryrun = set_dryrun(self.dryrun)

        return self.tracked

    def __exit__(self, *args):
        for c in self.tracked.captured:
            c._stop_capture()

        if self.anchors:
            Anchored.pop(self.anchors)

        if self.dryrun is not None:
            set_dryrun(self.dryrun)


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
