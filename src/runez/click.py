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

from runez.convert import flattened
from runez.system import get_version


def settings(epilog=None, help=None, width=140, **kwargs):
    """
    Args:
        epilog (str | None): Help epilog, defaults to __doc__ of caller module
        help (list[str] | str | None): List of flags to show help, default: -h and --help
        width (int): Constrain help to
        **kwargs:

    Returns:
        dict: Dict passable to @click.command() or @click.group()
    """
    if epilog is None:
        if hasattr(sys, "_getframe"):
            doc = sys._getframe(1).f_globals.get("__doc__")
            if doc:
                epilog = doc.strip()

    if help is None:
        help = ["-h", "--help"]

    return dict(
        epilog=epilog,
        context_settings=dict(help_option_names=flattened(help, split=" "), max_content_width=width),
        **kwargs
    )


def debug(*args, **kwargs):
    """Show debugging information."""
    kwargs.setdefault("is_flag", True)
    kwargs.setdefault("default", None)
    return option(debug, *args, **kwargs)


def dryrun(*args, **kwargs):
    """Perform a dryrun."""
    kwargs.setdefault("is_flag", True)
    kwargs.setdefault("default", None)
    return option(dryrun, *args, **kwargs)


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
