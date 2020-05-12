import logging
import os
import sys


LOG = logging.getLogger(__name__)
WINDOWS = sys.platform.startswith("win")


class AbortException(Exception):
    """Raised when calls fail, in runez functions with argument `fatal=True`.

    You can replace this with your preferred exception, for example:

    >>> import runez
    >>> runez.system.AbortException = SystemExit
    """

    def __init__(self, code):
        self.code = code


def abort(*args, **kwargs):
    """General wrapper for optionally fatal calls

    >>> from runez import abort
    >>> abort("foo")  # Raises AbortException
    foo
    runez.system.AbortException: 1
    >>> abort("foo", fatal=True) # Raises AbortException
    foo
    runez.system.AbortException: 1
    >>> # Not fatal, but will log/print message:
    >>> abort("foo", fatal=False)  # Returns False
    foo
    False
    >>> abort("foo", fatal=(False, None))  # Returns None
    foo
    >>> abort("foo", fatal=(False, -1)) # Returns -1
    foo
    -1
    >>> # Not fatal, will not log/print any message:
    >>> abort("foo", fatal=None)  # Returns None
    >>> abort("foo", fatal=(None, None))  # Returns None
    >>> abort("foo", fatal=(None, -1))  # Returns -1
    -1

    Args:
        *args: Args passed through for error reporting
        **kwargs: Args passed through for error reporting

    Returns:
        kwargs["return_value"] (default: -1) to signify failure to non-fatal callers
    """
    code = kwargs.pop("code", 1)
    logger = kwargs.pop("logger", LOG.error if code else LOG.info)
    fatal = kwargs.pop("fatal", True)
    return_value = fatal

    if isinstance(fatal, tuple) and len(fatal) == 2:
        fatal, return_value = fatal

    if logger and fatal is not None and args:
        if logging.root.handlers:
            logger(*args, **kwargs)

        else:
            sys.stderr.write("%s\n" % _formatted_string(*args))

    if fatal:
        if isinstance(fatal, type) and issubclass(fatal, BaseException):
            raise fatal(code)

        if AbortException is not None:
            if isinstance(AbortException, type) and issubclass(AbortException, BaseException):
                raise AbortException(code)

            return AbortException(code)

    return return_value


def auto_import_siblings(auto_clean="TOX_WORK_DIR", skip=None):
    """Auto-import all sibling submodules from caller.

    This is handy for click command groups for example.
    It allows to avoid having to have a module that simply lists all sub-commands, just to ensure they are added to `main`.

    - ./my_cli.py::

        @click.group()
        def main(...):
            ...

        runez.auto_import_siblings()

    - ./my_sub_command.py::

        from .my_cli import main

        @main.command()  # The auto-import will trigger importing this without further ado
        def foo(...):
            ...

    Args:
        auto_clean (str | bool | None): If provided, auto-clean `.pyc`` files
        skip (list | None): Do not auto-import specified modules

    Returns:
        (list): List of imported modules, if any
    """
    caller = find_caller_frame()
    if not caller:
        raise ImportError("Could not determine caller, can't auto-import")

    if caller.f_globals.get("__name__") == "__main__":
        raise ImportError("Calling auto_import_siblings() from __main__ is not supported: %s" % caller)

    caller_package = caller.f_globals.get("__package__")
    if not caller_package:
        raise ImportError("Could not determine caller's __package__, can't auto-import: %s" % caller)

    caller_path = caller.f_globals.get("__file__")
    if not caller_path:
        raise ImportError("Could not determine caller's __file__, can't auto-import: %s" % caller)

    folder = os.path.dirname(caller_path)
    if not os.path.isdir(folder):
        raise ImportError("Caller's __file__ points to a non-existing directory, can't auto-import: %s" % caller)

    if auto_clean is not None and not isinstance(auto_clean, bool):
        auto_clean = os.environ.get(auto_clean)

    if auto_clean:
        # Clean .pyc files so consecutive tox runs with distinct python2 versions don't get confused
        _clean_files(folder, ".pyc")

    import pkgutil

    imported = []
    for loader, module_name, _ in pkgutil.walk_packages([folder], prefix="%s." % caller_package):
        if should_auto_import(module_name, skip):
            __import__(module_name)
            imported.append(module_name)

    return imported


def should_auto_import(module_name, skip):
    """
    Args:
        module_name (str): Module being auto-imported
        skip (list | None): Modules to NOT auto-import

    Returns:
        (bool): True if we should auto-import `module_name`
    """
    if not module_name.endswith("_"):
        if skip and any(module_name.startswith(x) for x in skip):
            return False

        return True


def current_test():
    """
    Returns:
        (str): Not empty if we're currently running a test (such as via pytest)
               Actual value will be path to test_<name>.py file if user followed usual conventions,
               otherwise path to first found test-framework module
    """
    import re
    regex = re.compile(r"^(.+\.|)(conftest|(test_|_pytest\.|unittest\.).+|.+_test)$")

    def test_frame(f):
        name = f.f_globals.get("__name__").lower()
        if not name.startswith("runez"):
            return regex.match(name) and f.f_globals.get("__file__")

    return find_caller_frame(test_frame)


def actual_caller_frame(f):
    """Return `f` if it's a frame that looks like coming from actual caller (not runez itself, or an internal library package)"""
    name = f.f_globals.get("__name__")
    if name and "__main__" in name:
        return f

    package = f.f_globals.get("__package__")
    if package and not package.startswith("_") and package.partition(".")[0] not in ("importlib", "pluggy", "runez"):
        return f


def find_caller_frame(validator=actual_caller_frame, depth=2, maximum=None):
    """
    Args:
        validator (callable): Function that will decide whether a frame is suitable, and return value of interest from it
        depth (int): Depth from top of stack where to start
        maximum (int | None): Maximum depth to scan

    Returns:
        (frame): First frame found
    """
    if hasattr(sys, "_getframe"):
        while not maximum or depth <= maximum:
            try:
                f = sys._getframe(depth)
                value = validator(f)
                if value is not None:
                    return value

                depth = depth + 1

            except ValueError:
                return None


def find_parent_folder(path, basenames):
    """
    Args:
        path (str): Path to examine, first parent folder with basename in `basenames` is returned (case insensitive)
        basenames (set): List of acceptable basenames (must be lowercase)

    Returns:
        (str | None): Path to first containing folder of `path` with one of the `basenames`
    """
    if not path or len(path) <= 1:
        return None

    dirpath, basename = os.path.split(path)
    if basename and basename.lower() in basenames:
        return path

    return find_parent_folder(dirpath, basenames)


def get_version(mod, default="0.0.0", logger=LOG.warning):
    """
    Args:
        mod (module | str): Module, or module name to find version for (pass either calling module, or its .__name__)
        default (str): Value to return if version determination fails
        logger (callable | None): Logger to use to report inability to determine version

    Returns:
        (str): Determined version
    """
    name = mod
    if hasattr(mod, "__name__"):
        name = mod.__name__

    if not name:
        return default

    module_name = name
    try:
        import pkg_resources

        module_name = name.partition(".")[0]
        return pkg_resources.get_distribution(module_name).version

    except Exception as e:
        if logger and module_name != "tests":
            logger("Can't determine version for %s: %s", name, e, exc_info=e)

        return default


def is_dryrun():
    """
    Returns:
        (bool): Same as runez.DRYRUN, but as a function (and with late import)
    """
    return _get_runez().DRYRUN


def is_tty():
    """
    Returns:
        (bool): True if current stdout is a tty
    """
    return (sys.stdout.isatty() or "PYCHARM_HOSTED" in os.environ) and not current_test()


def set_dryrun(dryrun):
    """Set runez.DRYRUN, and return its previous value (useful for context managers)

    Args:
        dryrun (bool): New value for runez.DRYRUN

    Returns:
        (bool): Old value
    """
    r = _get_runez()
    old = r.DRYRUN
    r.DRYRUN = bool(dryrun)
    return old


def _clean_files(folder, extension):
    """Clean all files with `extension` from `folder`"""
    for root, dirs, files in os.walk(folder):
        for fname in files:
            if fname.endswith(extension):  # pragma: no cover, only applicable for local development
                try:
                    os.unlink(os.path.join(root, fname))

                except OSError:
                    pass  # Delete is only needed in tox run, no need to fail if delete is not possible


def _formatted_string(*args):
    if not args:
        return ""

    message = args[0]
    if len(args) == 1:
        return message

    try:
        return message % args[1:]

    except TypeError:
        return message


# We have to import 'runez' late when running in runez itself (because runez.__init__ imports everything to expose it)
_runez_module = None


def _get_runez():
    global _runez_module
    if _runez_module is None:
        import runez

        _runez_module = runez

    return _runez_module
