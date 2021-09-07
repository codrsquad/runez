"""
Convenience commonly used click options:

    @runez.click.version()
    @runez.click.debug()
    @runez.click.dryrun("-n")  # If you wanted an extra `-n` flag to mean `--dryrun` as well
    @runez.click.log()
    def main(debug, dryrun, log, ...):
        ...
"""

import argparse
import errno
import logging
import os
import sys

try:
    import click

except ImportError:  # pragma: no cover, click used only if installed
    click = None

import runez.config
from runez.colors import ColorManager
from runez.convert import affixed
from runez.file import basename
from runez.logsetup import LogManager
from runez.system import find_caller, first_line, flattened, get_version, short, stringified, TempArgv, UNSET


class Cli:
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
            "Docstring used in --help"
            parser = runez.cli.parser()
            ...

        def cmd_bar():
            print("bar")

        if __name__ == "__main__":
            runez.cli.run_cmds()
    """

    color = ("--no-color",)
    debug = ("--debug", "-v")
    dryrun = ("--dryrun", "-n")
    version = ("--version", "-V")
    console_format = "%(levelname)s %(message)s"
    console_level = logging.INFO
    default_logger = UNSET
    log_locations = None
    _prog = None

    @classmethod
    def parser(cls, epilog=None, help=None, prog=None):
        """
        Args:
            epilog (str | None): Optional epilog
            help (str | None): Help to use (default: __doc__ of caller)
            prog (str | None): Name of the program (default: caller cmd_ function)

        Returns:
            (argparse.ArgumentParser): Parser with help auto-populated and well formatted
        """
        if not help or not prog:
            caller = find_caller()
            if caller:
                if not help and caller.function:
                    help = caller.function.__doc__

                if not prog:
                    prog = caller.function_name
                    if prog and prog.startswith("cmd_"):
                        prog = prog[4:]

        if prog and cls._prog and prog != cls._prog:
            prog = "%s %s" % (cls._prog, prog)

        return argparse.ArgumentParser(
            prog=prog or cls._prog,
            description=Cli.formatted_help(help),
            epilog=epilog,
            formatter_class=argparse.RawDescriptionHelpFormatter
        )

    @staticmethod
    def formatted_help(text):
        text = text and text.strip()
        if text:
            return "  %s" % "\n  ".join(x.strip() for x in text.splitlines())

    @classmethod
    def run_cmds(cls, prog=None):
        """To be called from one's main()

        Args:
            prog (str | None): The name of the program (default: sys.argv[0])
        """
        from runez.render import PrettyTable

        caller = find_caller()
        package = caller.package_name  # Will fail if no caller could be found (intentional)
        available_commands = {}
        for name, func in caller.globals(prefix="cmd_"):
            name = name[4:].replace("_", "-")
            available_commands[name] = func

        if not prog:
            if package:
                prog = "python -m%s" % package if caller.is_main else package

            elif caller.basename in ("__init__.py", "__main__.py"):
                prog = short(caller.folder)

        epilog = PrettyTable(2)
        epilog.header[0].style = "bold"
        for cmd, func in available_commands.items():
            epilog.add_row(" " + cmd, first_line(func.__doc__, default=""))

        epilog = "Available commands:\n%s" % epilog
        cls._prog = prog or package
        parser = cls.parser(epilog=epilog, help=caller.module_docstring, prog=prog)
        if cls.version and package:
            parser.add_argument(*cls.version, action="version", version=get_version(package), help="Show version and exit")

        if cls.color:
            parser.add_argument(*cls.color, action="store_true", help="Do not use colors (even if on tty)")

        if cls.debug:
            parser.add_argument(*cls.debug, action="store_true", help="Show debugging information")

        if cls.dryrun:
            parser.add_argument(*cls.dryrun, action="store_true", help="Perform a dryrun")

        parser.add_argument("command", choices=available_commands, metavar="command", help="Command to run")
        parser.add_argument("args", nargs=argparse.REMAINDER, help="Passed-through to command")
        args = parser.parse_args()
        if cls.console_format or hasattr(args, "debug") or hasattr(args, "dryrun"):
            LogManager.setup(
                debug=getattr(args, "debug", UNSET),
                dryrun=getattr(args, "dryrun", UNSET),
                console_format=cls.console_format,
                console_level=cls.console_level,
                default_logger=cls.default_logger,
                locations=cls.log_locations,
            )
        color = getattr(args, "no_color", None)
        if color is not None:
            ColorManager.activate_colors(enable=not color)

        try:
            func = available_commands[args.command]
            with TempArgv(args.args):
                func()

        except KeyboardInterrupt:  # pragma: no cover
            sys.stderr.write("\nAborted\n")
            sys.exit(1)


def command(help=None, width=140, **attrs):
    """Same as `@click.command()`, but with common settings (ie: "-h" for help, slightly larger help display)"""
    attrs = settings(help=help, width=width, **attrs)
    return click.command(**attrs)


def group(help=None, width=140, **attrs):
    """Same as `@click.group()`, but with common settings (ie: "-h" for help, slightly larger help display)"""
    attrs = settings(help=help, width=width, **attrs)
    return click.group(**attrs)


def border(*args, **attrs):
    # No docstring, as all the possible values are shown in --help, trivial to guess what this is
    from runez.render import NAMED_BORDERS  # Imported if used

    attrs.setdefault("default", "reddit")
    attrs.setdefault("type", click.Choice(NAMED_BORDERS))
    return option(border, *args, **attrs)


def color(*args, **attrs):
    """Use colors (on by default on ttys)"""
    attrs.setdefault("is_flag", "negatable")
    attrs.setdefault("default", None)
    attrs.setdefault("expose_value", False)
    _auto_complete_callback(attrs, ColorManager.activate_colors)
    return option(color, *args, **attrs)


def config(*args, **attrs):
    """Override configuration"""
    attrs.setdefault("metavar", "KEY=VALUE")
    attrs.setdefault("multiple", True)
    attrs.setdefault("expose_value", False)
    attrs.setdefault("callback", _ConfigOption(attrs))
    return option(config, *args, **attrs)


def debug(*args, **attrs):
    """Show debugging information"""
    attrs.setdefault("is_flag", True)
    attrs.setdefault("default", None)
    _auto_complete_callback(attrs, LogManager.set_debug)
    return option(debug, *args, **attrs)


def dryrun(*args, **attrs):
    """Perform a dryrun"""
    attrs.setdefault("is_flag", True)
    attrs.setdefault("default", None)
    attrs.setdefault("expose_value", False)
    _auto_complete_callback(attrs, LogManager.set_dryrun)
    return option(dryrun, *args, **attrs)


def log(*args, **attrs):
    """Override log file location"""
    attrs.setdefault("metavar", "PATH")
    attrs.setdefault("show_default", False)
    _auto_complete_callback(attrs, LogManager.set_file_location)
    return option(log, *args, **attrs)


def version(*args, **attrs):
    """Show the version and exit"""
    if "version" not in attrs:
        # Ensure 'version' is not None here, otherwise click gets runez version (instead of caller package's version)
        caller = find_caller(need_package=True)
        attrs["version"] = get_version(caller and caller.top_level, default="")

    return click.version_option(*args, **attrs)


def settings(help=None, width=140, **attrs):
    """
    Args:
        help (list[str] | str | None): List of flags to show help, default: -h and --help
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
        func: Function defining this option
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

        if func.__doc__:
            attrs.setdefault("help", func.__doc__)

        attrs.setdefault("required", False)
        if not name.startswith("-"):
            if negatable:
                name = "--%s/--no-%s" % (name, name)

            else:
                name = "--%s" % name

        return click.option(name, *args, **attrs)(f)

    return decorator


def prettify_epilogs(command, formatter=None):
    """
    Conveniently re-arrange docstrings in click-decorated function in such a way that:
    - .help shows the first line of the docstring
    - .epilog shows the rest, with a \b separator if there is an empty line right after the 1st line

    Args:
        command: Command to prettify (along with its sub-commands)
        formatter (callable | None): Optional formatter to invoke on each help/epilog string
    """
    if click is not None:
        if isinstance(command, click.Command):
            help = command.help
            if help:
                help = help.strip()
                if formatter is not None:
                    help = formatter(help)

                command.help = help

            epilog = command.epilog
            if epilog is None and help:
                lines = help.splitlines()
                first_line = lines.pop(0).strip() if lines else None
                if first_line and lines:
                    command.help = first_line
                    epilog = "\n".join(lines)
                    if not lines[0]:
                        epilog = "\b%s" % epilog

            if epilog:
                if formatter is not None:
                    epilog = formatter(epilog)

                command.epilog = epilog

        if isinstance(command, click.Group) and command.commands:
            for cmd in command.commands.values():
                prettify_epilogs(cmd, formatter=formatter)


def protected_main(main, debug_stacktrace=False, no_stacktrace=None):
    """Convenience wrapper for a click main() function

    Args:
        main (callable): 'main' function to invoke
        debug_stacktrace (bool): If True, show stack traces only with --debug runs
        no_stacktrace (list | None): Do not show stack trace for give Exception types
    """
    try:
        return main()

    except KeyboardInterrupt:
        sys.stderr.write(ColorManager.fg.red("\n\nAborted\n\n"))  # No need to show stack trace on a KeyboardInterrupt
        sys.exit(1)

    except NotImplementedError as e:
        msg = stringified(e) or "Not implemented yet"  # Convenience pretty-print of a `raise NotImplementedError(...)`
        sys.stderr.write(ColorManager.fg.red("\n%s\n\n" % msg))
        sys.exit(1)

    except Exception as e:
        if getattr(e, "errno", None) == errno.EPIPE:
            sys.exit(0)  # Broken pipe is OK, happens when output is piped to another command that closes input early, like `head`

        logger = logging.exception
        if (debug_stacktrace and not LogManager.debug) or (no_stacktrace and type(e) in no_stacktrace):
            logger = logging.error
            e = ColorManager.fg.red(e)

        logger(e)  # Ensure any uncaught exception gets properly logged
        sys.exit(1)


def _auto_complete_callback(attrs, func):
    if not attrs.get("expose_value", True) and attrs.get("callback") is None:

        def _callback(ctx, param, value):
            value = func(value)
            return value

        attrs["callback"] = _callback


class _ConfigOption:
    def __init__(self, attrs):
        self.adapter = attrs.pop("adapter", str.lower)
        self.default = attrs.pop("default", None)  # Defaults can't go via click, otherwise they always take precedence
        self.env = attrs.pop("env", None)
        self.name = "--%s" % attrs.get("name", "config")
        self.prefix = attrs.pop("prefix", None)
        self.propsfs = attrs.pop("propsfs", None)
        self.split = attrs.pop("split", None)
        self.set_global = not attrs.get("expose_value")

    def _get_values(self, value):
        value = flattened(value, split=self.split)
        values = [t.partition("=") for t in value if t]
        values = dict((k, v) for k, _, v in values)
        if self.prefix:
            values = dict((affixed(k, prefix=self.prefix), v) for k, v in values.items())

        return values

    def _add_dict(self, config, name, values):
        provider = runez.config.DictProvider(values, name=name)
        config.add(provider)
        return values

    def __call__(self, ctx, param, value):
        c = runez.config.Configuration()
        self._add_dict(c, self.name, self._get_values(value))

        if self.env:
            env_prefix = self.env if isinstance(self.env, str) else basename(sys.argv[0]).upper()
            if not env_prefix.endswith("_"):
                env_prefix += "_"

            values = {}
            for k, v in os.environ.items():
                if k.startswith(env_prefix):
                    k = k[len(env_prefix):]
                    if self.adapter is not None:
                        k = self.adapter(k)

                    values[k] = v

            self._add_dict(c, "%s* env vars" % env_prefix, values)

        if self.propsfs:
            folder = self.propsfs if isinstance(self.propsfs, str) else None
            c.add(runez.config.PropsfsProvider(folder))

        if self.default:
            self._add_dict(c, self.name + " default", self._get_values(self.default))

        if self.set_global:
            runez.config.CONFIG = c

        return c
