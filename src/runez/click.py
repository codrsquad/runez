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

from runez.colors import ColorManager
from runez.config import use_cli
from runez.convert import first_meaningful_line, flattened
from runez.logsetup import LogManager
from runez.represent import PrettyTable
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
    auto_complete_callback(attrs, ColorManager.activate_colors)
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


def run_cmds(prog=None):
    """Handy way of running multi-commands with argparse

    If you don't have click, but would like to still have a quick multi-command entry point, you can use this.
    How it works:
    - Caller is automatically determined (from call stack), so no need to pass anything
    - All functions named `cmd_...` from caller are considered commands, and are invocable by name
    - All CLI args after command name are simply passed-through (command name removed)
    - Those functions should take no argument and should use `argparse` or equivalent as they would normally

    Example usage:
        import runez

        def cmd_foo():
            print("foo")

        def cmd_bar():
            print("bar")

        if __name__ == "__main__":
            runez.run_cmds()

    Args:
        prog (str | None): The name of the program (default: sys.argv[0])
    """
    import argparse
    import sys

    import runez

    caller = find_caller_frame(depth=2)
    f_globals = caller.f_globals
    available_commands = {}
    for name, func in f_globals.items():
        if len(name) > 4 and name.startswith("cmd_"):
            name = name[4:].replace("_", "-")
            available_commands[name] = func

    if prog is None and f_globals.get("__name__") == "__main__":
        package = f_globals.get("__package__")
        if package:
            prog = "python -m%s" % package

    epilog = PrettyTable()
    for cmd, func in available_commands.items():
        epilog.add_row(runez.bold(cmd), first_meaningful_line(func.__doc__, ""))

    epilog = runez.indented(epilog, indent=2)
    epilog = "Available commands:\n%s" % epilog
    # noinspection PyTypeChecker
    parser = argparse.ArgumentParser(
        prog=prog,
        description=first_meaningful_line(f_globals.get("__doc__")),
        epilog=epilog,
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("--debug", action="store_true", help="Show debug info.")
    parser.add_argument("command", choices=available_commands, metavar="command", help="Command to run.")
    parser.add_argument("args", nargs=argparse.REMAINDER, help="Passed-through to command")
    args = parser.parse_args()

    runez.log.setup(debug=args.debug)

    try:
        func = available_commands[args.command]
        with runez.TempArgv(args.args):
            func()

    except KeyboardInterrupt:  # pragma: no cover
        sys.stderr.write("\nAborted\n")
        sys.exit(1)
