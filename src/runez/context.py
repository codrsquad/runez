"""
Convenience context managers
"""

import logging
import os
import shutil
import sys
import tempfile

try:
    import StringIO
    StringIO = StringIO.StringIO

except ImportError:
    from io import StringIO

from runez.base import decode, flattened, State
from runez.path import resolved_path, SYMBOLIC_TMP


class Anchored:
    """
    An "anchor" is a known path that we don't wish to show in full when printing/logging
    This allows to conveniently shorten paths, and show more readable relative paths
    """

    def __init__(self, folder):
        self.folder = resolved_path(folder)

    def __enter__(self):
        Anchored.add(self.folder)

    def __exit__(self, *_):
        Anchored.pop(self.folder)

    @classmethod
    def set(cls, anchors):
        """
        :param str|list anchors: Optional paths to use as anchors for short()
        """
        State.anchors = sorted(flattened(anchors, unique=True), reverse=True)

    @classmethod
    def add(cls, anchors):
        """
        :param str|list anchors: Optional paths to use as anchors for short()
        """
        cls.set(State.anchors + [anchors])

    @classmethod
    def pop(cls, anchors):
        """
        :param str|list anchors: Optional paths to use as anchors for short()
        """
        for anchor in flattened(anchors):
            if anchor in State.anchors:
                State.anchors.remove(anchor)


class CaptureOutput:
    """
    Context manager allowing to temporarily grab stdout/stderr output.
    Output is captured and made available only for the duration of the context.

    Sample usage:

    with CaptureOutput() as output:
        # do something that generates output
        # output is available in 'output'
    """

    def __init__(self, stdout=True, stderr=True, anchors=None, dryrun=None):
        """
        :param bool stdout: Capture stdout
        :param bool stderr: Capture stderr
        :param str|list anchors: Optional paths to use as anchors for short()
        :param bool|None dryrun: Override dryrun (when explicitly specified, ie not None)
        """
        self.anchors = anchors
        self.dryrun = dryrun
        self.old_out = sys.stdout
        self.old_err = sys.stderr
        self.old_handlers = logging.root.handlers

        self.out_buffer = StringIO() if stdout else None

        if stderr:
            self.err_buffer = StringIO()
            self.handler = logging.StreamHandler(stream=self.err_buffer)
            self.handler.setLevel(logging.DEBUG)
            self.handler.setFormatter(logging.Formatter("%(levelname)s - %(message)s"))
        else:
            self.err_buffer = None
            self.handler = None

    def pop(self):
        """Current contents popped, useful for testing"""
        r = self.__repr__()
        if self.out_buffer:
            self.out_buffer.seek(0)
            self.out_buffer.truncate(0)
        if self.err_buffer:
            self.err_buffer.seek(0)
            self.err_buffer.truncate(0)
        return r

    def __repr__(self):
        result = ""
        if self.out_buffer:
            result += decode(self.out_buffer.getvalue())
        if self.err_buffer:
            result += decode(self.err_buffer.getvalue())
        return result

    def __enter__(self):
        if self.out_buffer:
            sys.stdout = self.out_buffer
        if self.err_buffer:
            sys.stderr = self.err_buffer
        if self.handler:
            logging.root.handlers = [self.handler]

        if self.anchors:
            Anchored.add(self.anchors)

        if self.dryrun is not None:
            (State.dryrun, self.dryrun) = (bool(self.dryrun), bool(State.dryrun))

        return self

    def __exit__(self, *args):
        sys.stdout = self.old_out
        sys.stderr = self.old_err
        self.out_buffer = None
        self.err_buffer = None
        logging.root.handlers = self.old_handlers

        if self.anchors:
            Anchored.pop(self.anchors)

        if self.dryrun is not None:
            State.dryrun = self.dryrun

    def __contains__(self, item):
        return item is not None and item in str(self)

    def __len__(self):
        return len(str(self))


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
            Anchored.add(self.destination)

    def __exit__(self, *_):
        os.chdir(self.current_folder)
        if self.anchor:
            Anchored.pop(self.destination)


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
        self.dryrun = dryrun if dryrun is not None else State.dryrun
        self.old_cwd = os.getcwd() if follow else None
        self.tmp_folder = None

    def __enter__(self):
        if self.dryrun:
            self.tmp_folder = SYMBOLIC_TMP
        else:
            # Use realpath() to properly resolve for example symlinks on OSX temp paths
            self.tmp_folder = os.path.realpath(tempfile.mkdtemp())
            if self.old_cwd:
                os.chdir(self.tmp_folder)
        if self.anchor:
            Anchored.add(self.tmp_folder)
        return self.tmp_folder

    def __exit__(self, *_):
        if self.anchor:
            Anchored.pop(self.tmp_folder)
        if not self.dryrun:
            if self.old_cwd:
                os.chdir(self.old_cwd)
            if self.tmp_folder:
                shutil.rmtree(self.tmp_folder)


def verify_abort(func, *args, **kwargs):
    """
    Convenient wrapper around functions that should exit or raise an exception

    Example:
        assert "Can't create folder" in verify_abort(ensure_folder, "/dev/null/foo")

    :param callable func: Function to execute
    :param args: Args to pass to 'func'
    :param Exception expected_exception: Type of exception that should be raised
    :param kwargs: Named args to pass to 'func'
    :return str: Chatter from call to 'func', if it did indeed raise
    """
    expected_exception = kwargs.pop("expected_exception", SystemExit)
    with CaptureOutput() as logged:
        try:
            func(*args, **kwargs)
            return None
        except expected_exception:
            return str(logged)
