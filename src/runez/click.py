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

try:
    import click

except ImportError:  # pragma: no cover, click used only if installed
    click = None

from runez.colors.terminal import activate_colors
from runez.config import use_cli
from runez.convert import flattened
from runez.logsetup import LogManager
from runez.system import actual_caller_frame, find_caller_frame, get_version


def command(help=None, width=140, **attrs):
    """Same as `@click.command()`, but with common settings (ie: "-h" for help, slightly larger help display)"""
    attrs = settings(help=help, width=width, **attrs)
    return click.command(**attrs)


def group(help=None, width=140, **attrs):
    """Same as `@click.group()`, but with common settings (ie: "-h" for help, slightly larger help display)"""
    attrs = settings(help=help, width=width, **attrs)
    return click.group(**attrs)


def color(*args, **attrs):
    """Use colors (on by default on ttys)"""
    attrs.setdefault("is_flag", "negatable")
    attrs.setdefault("default", None)
    attrs.setdefault("expose_value", False)
    auto_complete_callback(attrs, activate_colors)
    return option(color, *args, **attrs)


def config(*args, **attrs):
    """Override configuration"""
    attrs.setdefault("metavar", "KEY=VALUE")
    attrs.setdefault("multiple", True)
    auto_complete_callback(attrs, use_cli)
    return option(config, *args, **attrs)


def debug(*args, **attrs):
    """Show debugging information."""
    attrs.setdefault("is_flag", True)
    attrs.setdefault("default", None)
    auto_complete_callback(attrs, LogManager.set_debug)
    return option(debug, *args, **attrs)


def dryrun(*args, **attrs):
    """Perform a dryrun."""
    attrs.setdefault("is_flag", True)
    attrs.setdefault("default", None)
    auto_complete_callback(attrs, LogManager.set_dryrun)
    return option(dryrun, *args, **attrs)


def log(*args, **attrs):
    """Override log file location."""
    attrs.setdefault("metavar", "PATH")
    attrs.setdefault("show_default", False)
    auto_complete_callback(attrs, LogManager.set_file_location)
    return option(log, *args, **attrs)


def version(*args, **attrs):
    """Show the version and exit."""
    if "version" not in attrs:
        package = attrs.pop("package", None)
        if not package:
            package = find_caller_frame(frame_package)

        if package:
            attrs.setdefault("version", get_version(package))

    return click.version_option(*args, **attrs)


def settings(help=None, width=140, **attrs):
    """
    Args:
        help (list[str | unicode] | str | unicode | None): List of flags to show help, default: -h and --help
        width (int): Constrain help to
        **attrs:

    Returns:
        dict: Dict passable to @click.command() or @click.group()
    """
    if help is None:
        help = ["-h", "--help"]

    context_settings = attrs.pop("context_settings", {})
    context_settings["help_option_names"] = flattened(help, split=" ")
    context_settings["max_content_width"] = width

    return dict(context_settings=context_settings, **attrs)


def option(func, *args, **attrs):
    """
    Args:
        func (function): Function defining this option
        *args: Optional extra short flag name
        **attrs: Optional attr overrides provided by caller

    Returns:
        function: Click decorator
    """
    def decorator(f):
        name = attrs.pop("name", func.__name__.replace("_", "-"))
        negatable = None
        if attrs.get("is_flag") == "negatable":
            attrs["is_flag"] = True
            negatable = True

        attrs.setdefault("help", func.__doc__)
        attrs.setdefault("required", False)
        if not attrs.get("is_flag"):
            attrs.setdefault("show_default", True)
            attrs.setdefault("metavar", name.replace("-", "_").upper())
            attrs.setdefault("type", str)

        if not name.startswith("-"):
            if negatable:
                name = "--%s/--no-%s" % (name, name)

            else:
                name = "--%s" % name

        return click.option(name, *args, **attrs)(f)

    return decorator


def auto_complete_callback(attrs, func):
    if attrs.get("expose_value") is False and attrs.get("callback") is None:
        def _callback(ctx, param, value):
            func(value)
            return value

        attrs.setdefault("callback", _callback)


def frame_package(f):
    """
    Args:
        f (frame): Frame to inspect

    Returns:
        (str | None): Package name, if any
    """
    caller = actual_caller_frame(f)
    if caller:
        package = caller.f_globals.get("__package__")
        if package:
            return package
