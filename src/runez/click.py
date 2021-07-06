"""
Convenience commonly used click options:

    @runez.click.version()
    @runez.click.debug()
    @runez.click.dryrun("-n")  # If you wanted an extra `-n` flag to mean `--dryrun` as well
    @runez.click.log()
    def main(debug, dryrun, log, ...):
        ...
"""

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
from runez.system import _R, find_caller_frame, flattened, get_version, stringified


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
    """Show debugging information."""
    attrs.setdefault("is_flag", True)
    attrs.setdefault("default", None)
    _auto_complete_callback(attrs, LogManager.set_debug)
    return option(debug, *args, **attrs)


def dryrun(*args, **attrs):
    """Perform a dryrun."""
    attrs.setdefault("is_flag", True)
    attrs.setdefault("default", None)
    attrs.setdefault("expose_value", False)
    _auto_complete_callback(attrs, LogManager.set_dryrun)
    return option(dryrun, *args, **attrs)


def log(*args, **attrs):
    """Override log file location."""
    attrs.setdefault("metavar", "PATH")
    attrs.setdefault("show_default", False)
    _auto_complete_callback(attrs, LogManager.set_file_location)
    return option(log, *args, **attrs)


def version(*args, **attrs):
    """Show the version and exit."""
    if "version" not in attrs:
        # Ensure 'version' is not None here, otherwise click gets runez version (instead of caller package's version)
        caller = find_caller_frame(validator=_R.frame_has_package)
        attrs["version"] = get_version(caller, default="")

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
    Conveniently re-arrage docstrings in click-decorated function in such a way that:
    - .help shows the first line of the docstring
    - .epilog shows the rest, with a \b separator if there is an empty line right after the 1st line

    Args:
        command (click.BaseCommand): Command to prettify (along with its sub-commands)
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
