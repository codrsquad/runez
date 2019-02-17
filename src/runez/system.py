import logging
import time


class AbortException(Exception):
    """
    You can replace this with your preferred exception, for example:

        runez.base.AbortException = SystemExit
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
    logger = kwargs.pop("logger", logging.error if code else logging.info)
    fatal = kwargs.pop("fatal", True)
    return_value = fatal
    if isinstance(fatal, tuple) and len(fatal) == 2:
        fatal, return_value = fatal
    if logger and fatal is not None and args:
        logger(*args, **kwargs)
    if fatal:
        if isinstance(fatal, type) and issubclass(fatal, BaseException):
            raise fatal(code)
        if AbortException is not None:
            if isinstance(AbortException, type) and issubclass(AbortException, BaseException):
                raise AbortException(code)
            return AbortException(code)
    return return_value


def get_timezone():
    try:
        return time.tzname[0]
    except (IndexError, TypeError):
        return ""


def get_version(mod, default="0.0.0"):
    """
    :param module|str mod: Module, or module name to find version for (pass either calling module, or its .__name__)
    :param str default: Value to return if version determination fails
    :return str: Determined version
    """
    name = mod
    if hasattr(mod, "__name__"):
        name = mod.__name__

    try:
        import pkg_resources
        return pkg_resources.get_distribution(name).version

    except Exception as e:
        logging.warning("Can't determine version for %s: %s", name, e, exc_info=e)
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
