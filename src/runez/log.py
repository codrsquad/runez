"""
Convenience logging
"""

import logging
import sys

from runez.base import State


LOG = logging.getLogger(__name__)


def debug(message, *args, **kwargs):
    """
    Same as logging.debug(), but more convenient when testing (prints as well, on top of logging)
    """
    if State.logging:
        LOG.debug(message, *args, **kwargs)

    if State.testing:
        print(message % args)


def info(message, *args, **kwargs):
    """
    Often, an info() message should be logged, but also shown to user (in the even where logging is not done to console)

    Example:
        info("...") => Will log if we're logging, but also print() if State.output is currently set
        info("...", output=False) => Will only log, never print
        info("...", output=True) => Will log if we're logging, and print
    """
    output = kwargs.pop("output", State.output)
    if State.logging:
        LOG.info(message, *args, **kwargs)
    if output or State.testing:
        print(message % args)


def warning(message, *args, **kwargs):
    """Same as logging.warning(), but more convenient when testing, similar to info()"""
    if State.logging:
        LOG.warning(message, *args, **kwargs)
    if State.output or State.testing:
        print("WARNING: %s" % (message % args))


def error(message, *args, **kwargs):
    """Same as logging.error(), but more convenient when testing, similar to info()"""
    if State.logging:
        LOG.error(message, *args, **kwargs)
    if State.output or State.testing:
        print("ERROR: %s" % (message % args))


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
    logger = kwargs.pop("logger", error if code else info)
    fatal = kwargs.pop("fatal", True)
    return_value = fatal
    if isinstance(fatal, tuple) and len(fatal) == 2:
        fatal, return_value = fatal
    if logger and fatal is not None and args:
        logger(*args, **kwargs)
    if fatal:
        sys.exit(code)
    return return_value
