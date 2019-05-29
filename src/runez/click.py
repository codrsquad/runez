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


def command(epilog=None, help=None, width=140, **attrs):
    """Same as `@click.command()`, but with common settings (ie: "-h" for help, epilog, slightly larger help display)"""
    if epilog is None:
        epilog = _get_caller_doc()
    attrs = settings(epilog=epilog, help=help, width=width, **attrs)
    return click.command(**attrs)


def group(epilog=None, help=None, width=140, **attrs):
    """Same as `@click.group()`, but with common settings (ie: "-h" for help, epilog, slightly larger help display)"""
    if epilog is None:
        epilog = _get_caller_doc()
    attrs = settings(epilog=epilog, help=help, width=width, **attrs)
    return click.group(**attrs)


def config(*args, **attrs):
    """Override configuration"""
    attrs.setdefault("metavar", "KEY=VALUE")
    attrs.setdefault("multiple", True)
    return option(config, *args, **attrs)


def debug(*args, **attrs):
    """Show debugging information."""
    attrs.setdefault("is_flag", True)
    attrs.setdefault("default", None)
    return option(debug, *args, **attrs)


def dryrun(*args, **attrs):
    """Perform a dryrun."""
    attrs.setdefault("is_flag", True)
    attrs.setdefault("default", None)
    return option(dryrun, *args, **attrs)


def log(*args, **attrs):
    """Override log file location."""
    attrs.setdefault("metavar", "PATH")
    attrs.setdefault("show_default", False)
    return option(log, *args, **attrs)


def version(*args, **attrs):
    """Show the version and exit."""
    if "version" not in attrs:
        if hasattr(sys, "_getframe"):
            package = attrs.pop("package", sys._getframe(1).f_globals.get("__package__"))
            if package:
                attrs.setdefault("version", get_version(package))
    return click.version_option(*args, **attrs)


def settings(epilog=None, help=None, width=140, **attrs):
    """
    Args:
        epilog (str | unicode | None): Help epilog, defaults to __doc__ of caller module
        help (list[str | unicode] | str | unicode | None): List of flags to show help, default: -h and --help
        width (int): Constrain help to
        **attrs:

    Returns:
        dict: Dict passable to @click.command() or @click.group()
    """
    if epilog is None:
        epilog = _get_caller_doc()

    if help is None:
        help = ["-h", "--help"]

    context_settings = attrs.pop("context_settings", {})
    context_settings["help_option_names"] = flattened(help, split=" ")
    context_settings["max_content_width"] = width

    return dict(epilog=epilog, context_settings=context_settings, **attrs)


def option(func, *args, **attrs):
    """
    Args:
        func (function): Function defining this option
        *args: Optional extra short flag name
        **attrs: Optional attr overrides provided by caller

    Returns:
        function: Click decorator
    """
    if click is None:
        return func

    def decorator(f):
        name = attrs.pop("name", func.__name__.replace("_", "-"))
        attrs.setdefault("help", func.__doc__)
        attrs.setdefault("required", False)
        if not attrs.get("is_flag"):
            attrs.setdefault("show_default", True)
            attrs.setdefault("metavar", name.replace("-", "_").upper())
            attrs.setdefault("type", str)
        if not name.startswith("-"):
            name = "--%s" % name
        return click.option(name, *args, **attrs)(f)

    return decorator


def _get_caller_doc(caller_depth=2):
    if hasattr(sys, "_getframe"):
        doc = sys._getframe(caller_depth).f_globals.get("__doc__")
        if doc:
            return doc.strip()
