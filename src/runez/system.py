import logging
import os
import sys


LOG = logging.getLogger(__name__)


class AbortException(Exception):
    """
    You can replace this with your preferred exception, for example:

        runez.system.AbortException = SystemExit
    """

    def __init__(self, code):
        self.code = code


def abort(*args, **kwargs):
    """
    Usage:
        return abort("...") => will sys.exit() by default
        return abort("...", fatal=True) => Will sys.exit()

        # Not fatal, but will log/print message:
        return abort("...", fatal=False) => Will return False
        return abort("...", fatal=(False, None)) => Will return None
        return abort("...", fatal=(False, -1)) => Will return -1

        # Not fatal, will not log/print any message:
        return abort("...", fatal=None) => Will return None
        return abort("...", fatal=(None, None)) => Will return None
        return abort("...", fatal=(None, -1)) => Will return -1

    :param args: Args passed through for error reporting
    :param kwargs: Args passed through for error reporting
    :return: kwargs["return_value"] (default: -1) to signify failure to non-fatal callers
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
            sys.stderr.write("%s\n" % formatted_string(*args))

    if fatal:
        if isinstance(fatal, type) and issubclass(fatal, BaseException):
            raise fatal(code)

        if AbortException is not None:
            if isinstance(AbortException, type) and issubclass(AbortException, BaseException):
                raise AbortException(code)

            return AbortException(code)

    return return_value


def auto_import_siblings(auto_clean="TOX_WORK_DIR", skip=None):
    """
    Auto-import all sibling submodules from caller.
    This is handy for click command groups for example.
    It allows to avoid having to have a module that simply lists all sub-commands, just to ensure they are added to `main`.

    Example usage:
        my_cli.py:

            @click.group()
            def main(...):
                ...

            # Without this, one would have to ensure that all subcommands are imported somehow
            runez.auto_import_siblings()

        my_sub_command.py:

            from .my_cli import main

            @main.command():
            def foo(...):
                ...

    Args:
        auto_clean (str | bool | None): If True, auto-clean .pyc files
                                        If string: auto-clean .pyc files when corresponding env var is defined
        skip (list | None): Do not auto-import specified modules

    Returns:
        (list): List of imported modules, if any
    """
    caller = find_caller_frame(depth=1)
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
        m = regex.match(name)
        if m:
            return f.f_globals.get("__file__")

    return find_caller_frame(test_frame, depth=2)


def actual_caller_frame(f):
    """Return `f` if it's a frame that looks like coming from actual caller (not runez itself, or an internal library package)"""
    if f.f_globals.get("__name__") == "__main__":
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


def formatted_string(*args):
    if not args:
        return ""

    message = args[0]
    if len(args) == 1:
        return message

    try:
        return message % args[1:]

    except TypeError:
        return message


def get_platform():
    return sys.platform


WINDOWS = get_platform().startswith("win")


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


# We have to import 'runez' late, can't import it right away at import time
_runez_module = None


def _get_runez():
    global _runez_module
    if _runez_module is None:
        import runez

        _runez_module = runez

    return _runez_module


def is_dryrun():
    return _get_runez().DRYRUN


def set_dryrun(dryrun):
    """
    :param bool dryrun: New value for runez.DRYRUN
    :return bool: Old value
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
