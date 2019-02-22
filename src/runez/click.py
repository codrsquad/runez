"""
Convenience commonly used click options:

    @runez.click.version()
    @runez.click.debug()
    @runez.click.dryrun("-n")  # If you wanted an extra `-n` flag to mean `--dryrun` as well
    @runez.click.log()
    def main(debug, dryrun, log, ...):
        ...
"""

from __future__ import absolute_import

import sys

try:
    import click

except ImportError:
    click = None

from runez.system import get_version


def debug(*args, **kwargs):
    """Show debugging information."""
    return option(debug, *args, is_flag=True, **kwargs)


def dryrun(*args, **kwargs):
    """Perform a dryrun."""
    return option(dryrun, *args, is_flag=True, **kwargs)


def log(*args, **kwargs):
    """Override log file location."""
    kwargs.setdefault("metavar", "PATH")
    kwargs.setdefault("show_default", False)
    return option(log, *args, **kwargs)


def version(*args, **kwargs):
    """Show the version and exit."""
    if hasattr(sys, "_getframe"):
        package = kwargs.pop("package", sys._getframe(1).f_globals.get("__package__"))
        if package:
            kwargs.setdefault("version", get_version(package))
    return click.version_option(*args, **kwargs)


def option(func, *args, **kwargs):
    """
    Args:
        func (function): Function defining this option
        *args: Optional extra short flag name
        **kwargs: Optional attr overrides provided by caller

    Returns:
        function: Click decorator
    """
    if click is None:
        return func

    def decorator(f):
        name = kwargs.pop("name", func.__name__.replace("_", "-"))
        kwargs.setdefault("help", func.__doc__)
        kwargs.setdefault("required", False)
        if not kwargs.get("is_flag"):
            kwargs.setdefault("show_default", True)
            kwargs.setdefault("metavar", name.replace("-", "_").upper())
            kwargs.setdefault("type", str)
        if not name.startswith("-"):
            name = "--%s" % name
        return click.option(name, *args, **kwargs)(f)

    return decorator
