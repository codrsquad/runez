import logging
import sys
import time


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


def get_timezone():
    """
    Returns:
        (str): Name of current timezone
    """
    try:
        return time.tzname[0]

    except (IndexError, TypeError):
        return ""


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

    try:
        import pkg_resources

        mname = name.partition(".")[0]
        return pkg_resources.get_distribution(mname).version

    except Exception as e:
        if logger:
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
