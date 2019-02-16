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

import runez.logging
import runez.state
from runez.base import State
from runez.path import resolved_path, SYMBOLIC_TMP


class Anchored:
    """
    An "anchor" is a known path that we don't wish to show in full when printing/logging
    This allows to conveniently shorten paths, and show more readable relative paths
    """

    def __init__(self, folder):
        self.folder = resolved_path(folder)

    def __enter__(self):
        runez.state.Anchored.add(self.folder)

    def __exit__(self, *_):
        runez.state.Anchored.pop(self.folder)


class CapturedStream:
    """Capture output to a stream by hijacking temporarily its write() function"""

    _shared = None

    def __init__(self, name, target):
        self.name = name
        self.target = target
        if target is None:
            self.buffer = CapturedStream._shared._buffer
        else:
            self.buffer = StringIO()

    @classmethod
    def log_intercept(cls):
        if cls._shared:
            return cls("log", None)

    def __repr__(self):
        return "%s: %s" % (self.name, self.contents())

    def __eq__(self, other):
        if isinstance(other, CapturedStream):
            return self.name == other.name
        return str(self).strip() == str(other).strip()

    def __contains__(self, item):
        return item is not None and item in self.contents()

    def __len__(self):
        return len(self.contents())

    def contents(self):
        return self.buffer.getvalue()

    def capture(self):
        if self.target:
            self.original = self.target.write
            self.target.write = self.buffer.write
        else:
            self._shared._is_capturing = True

    def restore(self):
        """Restore hijacked write() function"""
        if self.target:
            self.target.write = self.original
        else:
            self._shared._is_capturing = False
        self.clear()

    def pop(self):
        """Current content popped, useful for testing"""
        r = self.contents()
        self.clear()
        return r

    def clear(self):
        """Clear captured content"""
        self.buffer.seek(0)
        self.buffer.truncate(0)


class CaptureOutput:
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
        self.level = level
        self.stdout = CapturedStream("stdout", sys.stdout) if stdout else None
        self.stderr = CapturedStream("stderr", sys.stderr) if stderr else None
        if log is None:
            log = bool(CapturedStream._shared)
        self.log = CapturedStream.log_intercept() if log else None
        self.captured = [c for c in (self.stdout, self.stderr, self.log) if c is not None]
        self.anchors = anchors
        self.dryrun = dryrun
        self._old_level = None

    def __enter__(self):
        self._old_level = runez.logging.OriginalLogging.set_level(self.level)
        for s in self.captured:
            s.capture()
        if self.anchors:
            runez.state.Anchored.add(self.anchors)
        if self.dryrun is not None:
            (State.dryrun, self.dryrun) = (bool(self.dryrun), bool(State.dryrun))
        return self

    def __exit__(self, *args):
        runez.logging.OriginalLogging.set_level(self._old_level)
        for s in self.captured:
            s.restore()
        if self.anchors:
            runez.state.Anchored.pop(self.anchors)
        if self.dryrun is not None:
            State.dryrun = self.dryrun

    def __repr__(self):
        return "".join(str(s) for s in self.captured)

    def __eq__(self, other):
        if isinstance(other, CaptureOutput):
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
        for s in self.captured:
            s.clear()


class CurrentFolder:
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
            runez.state.Anchored.add(self.destination)

    def __exit__(self, *_):
        os.chdir(self.current_folder)
        if self.anchor:
            runez.state.Anchored.pop(self.destination)


class TempFolder:
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
            (State.dryrun, self.dryrun) = (bool(self.dryrun), bool(State.dryrun))
        if not State.dryrun:
            # Use realpath() to properly resolve for example symlinks on OSX temp paths
            self.tmp_folder = os.path.realpath(tempfile.mkdtemp())
            if self.follow:
                self.old_cwd = os.getcwd()
                os.chdir(self.tmp_folder)
        tmp = self.tmp_folder or SYMBOLIC_TMP
        if self.anchor:
            runez.state.Anchored.add(tmp)
        return tmp

    def __exit__(self, *_):
        if self.anchor:
            runez.state.Anchored.pop(self.tmp_folder or SYMBOLIC_TMP)
        if self.old_cwd:
            os.chdir(self.old_cwd)
        if self.tmp_folder:
            shutil.rmtree(self.tmp_folder)
        if self.dryrun is not None:
            State.dryrun = self.dryrun


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
    expected_exception = kwargs.pop("expected_exception", runez.base.AbortException)
    with CaptureOutput() as logged:
        try:
            func(*args, **kwargs)
            return None
        except expected_exception:
            return str(logged)
