"""
Set of sample commands illustrating behaviors of runez
"""

import contextlib
import logging
import os
import sys
import time

import runez
from runez.ascii import AsciiAnimation
from runez.render import NAMED_BORDERS, PrettyTable


def cmd_colors():
    """Show a coloring sample"""
    parser = runez.cli.parser()
    parser.add_argument("--border", choices=NAMED_BORDERS, help="Use custom border.")
    parser.add_argument("--color", action="store_true", help="Use colors (on by default on ttys).")
    parser.add_argument("--no-color", action="store_true", help="Do not use colors (even if on tty).")
    parser.add_argument("--bg", help="Show bg variant(s) (comma-separated list of color names).")
    parser.add_argument("--flavor", help="Show specific flavor (neutral, light or dark).")
    args = parser.parse_args()

    enable_colors = None
    if args.no_color:
        enable_colors = False

    elif args.color:
        enable_colors = True

    with runez.ActivateColors(enable=enable_colors, flavor=args.flavor):
        print("Backend: %s" % runez.color.backend)
        _show_fgcolors(border=args.border)
        if args.bg:
            for name in runez.flattened(args.bg, split=","):
                color = runez.color.bg.get(name)
                if color is None:
                    print("Unknown bg color '%s'" % name)

                else:
                    _show_fgcolors(bg=color, border=args.border)


def cmd_diagnostics():
    """Show system diagnostics sample"""
    parser = runez.cli.parser()
    parser.add_argument("--border", default="colon", choices=NAMED_BORDERS, help="Use custom border.")
    parser.add_argument("--pyenv", default="PATH", help="Colon separated locations to examine for python installations")
    args = parser.parse_args()

    from runez.pyenv import PythonDepot

    locations = runez.flattened(args.pyenv, split=os.path.pathsep)
    depot = PythonDepot(*locations)
    available = depot.representation()
    print(PrettyTable.two_column_diagnostics(runez.SYS_INFO.diagnostics(), available, border=args.border))


def cmd_passthrough():
    """
    Capture pass-through test
    Run a program, capture its output as well as let it pass-through to stdout/stderr
    """
    parser = runez.cli.parser()
    _, unknown = parser.parse_known_args()

    unknown = runez.flattened(unknown, split=" ")
    if not unknown:
        sys.exit("Provide command to run")

    print(f"-- Running: {unknown}\n")
    r = runez.run(*unknown, fatal=False, passthrough=True)
    print(f"\n---- Captured: (exit code {r.exit_code}) ----")
    print(f"\nstdout:\n{r.output or runez.dim('-empty-')}")
    print(f"\nstderr:\n{r.error or runez.dim('-empty-')}")


def cmd_progress_bar():
    """Show a progress bar sample"""
    names = AsciiAnimation.available_names()
    parser = runez.cli.parser()
    parser.add_argument("--delay", "-d", type=float, default=100.0, help="Time in milliseconds to sleep between iterations.")
    parser.add_argument("--iterations", "-i", type=int, default=100, help="Number of iterations to run.")
    parser.add_argument("--log-every", "-l", type=int, default=5, help="Log a message every N iterations.")
    parser.add_argument("--spinner", "-s", choices=names, default=None, help="Pick spinner to use.")
    parser.add_argument("--sleep", type=float, default=None, help="Extra sleep when done, useful for inspecting animation a bit further.")
    parser.add_argument("--no-spinner", "-n", action="store_true", help="Useful to compare CPU usage with and without spinner.")
    parser.add_argument("--verbose", "-v", action="store_true", help="More chatty output.")
    parser.add_argument("name", nargs="*", help="Names of modules to show (by default: all).")
    args = parser.parse_args()

    process = None
    with contextlib.suppress(ImportError):
        import psutil

        process = psutil.Process(os.getpid())
        process.cpu_percent()

    runez.log.setup(console_format="%(levelname)s %(message)s", console_level=logging.INFO, trace="RUNEZ_DEBUG")
    if not args.no_spinner:
        runez.log.progress.start(frames=args.spinner, max_columns=40, spinner_color=runez.yellow)

    logger = logging.info if args.verbose else logging.debug
    for i in runez.ProgressBar(range(args.iterations)):
        i += 1
        if args.log_every and i % args.log_every == 0:
            logger("Running\niteration %s %s", runez.red(i), "-" * 50)
            logger = logging.debug

        else:
            runez.log.trace("At iteration %s" % i)

        if args.verbose and i % 10 == 0:
            print("iteration %s" % runez.bold(i))

        if i == 42:
            runez.log.progress.show("some progress msg")  # debug() and trace() messages don't appear any more after this
            for _ in runez.ProgressBar(range(10)):
                time.sleep(0.1)

        time.sleep(args.delay / 1000)

    msg = "done"
    if process:
        cpu_usage = ("%.2f" % process.cpu_percent()).rstrip("0")
        msg += " (%s%% CPU usage)" % cpu_usage

    print(msg)
    if args.sleep:
        runez.log.progress.show(msg)
        time.sleep(args.sleep)


def main():
    runez.cli.run_cmds()


def _show_fgcolors(bg=runez.plain, border=None):
    print("")
    table = PrettyTable("Color,Blink,Bold,Dim,Invert,Italic,Strikethrough,Underline", border=border)
    for color in runez.color.fg:
        color_name = color.name
        text = color(color.name)
        if text[0] == "\033":
            i = text.index("m", 1)
            text = "%s %s" % (color_name, text[2:i])

        line = [bg(color(text))]
        for style in runez.color.style:
            line.append(bg(style(color(color_name))))

        table.add_row(line)

    print(table)


if __name__ == "__main__":
    main()
