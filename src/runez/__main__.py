"""
See some example behaviors of runez
"""

import argparse
import sys

import runez
from runez.inspector import ImportTime, run_cmds


def show_fgcolors(bg=runez.plain, border=None):
    print("")
    table = runez.PrettyTable("Color,Blink,Bold,Dim,Invert,Italic,Strikethrough,Underline", border=border)
    table.header.style = "bold"
    for color in runez.color.fg:
        color_name = color.name
        text = color(color.name)
        if text[0] == "\033":
            i = text.index("m", 1)
            text = "%s %s" % (color_name, text[2:i])

        line = [bg(color(text))]
        for style in runez.color.style:
            # text = "%s %s" % (style.name, color_name)
            line.append(bg(style(color(color_name))))

        table.add_row(line)

    print(table)


def cmd_colors():
    """Show a coloring sample"""
    parser = argparse.ArgumentParser(description="Show a coloring sample")
    parser.add_argument("--border", choices=runez.represent.NAMED_BORDERS, help="Use custom border.")
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
        show_fgcolors(border=args.border)
        if args.bg:
            for name in runez.flattened(args.bg, split=","):
                color = runez.color.bg.get(name)
                if color is None:
                    print("Unknown bg color '%s'" % name)

                else:
                    show_fgcolors(bg=color, border=args.border)


def cmd_import_speed():
    if sys.version_info[:2] >= (3, 7):
        pass

    parser = argparse.ArgumentParser(description="Show average import time of top-level python packages installed in this venv")
    parser.add_argument("--border", choices=runez.represent.NAMED_BORDERS, default="reddit", help="Use custom border.")
    parser.add_argument("name", nargs="+", help="Names of modules to show.")
    args = parser.parse_args()
    names = runez.flattened(args.name, split=",")
    times = []
    fastest = None
    slowest = None
    for name in names:
        t = ImportTime(name)
        times.append(t)
        if t.cumulative is None:
            continue

        if fastest is None or (t.cumulative < fastest.cumulative):
            fastest = t

        if slowest is None or t.cumulative > slowest.cumulative:
            slowest = t

    table = runez.PrettyTable("Module,Cumulative,Elapsed,Vs fastest,Note", border=args.border)
    for t in times:
        if t.cumulative is None:
            c = e = f = None

        else:
            factor = t.cumulative / fastest.cumulative
            c = runez.represented_duration(t.cumulative / 1000000, span=-2)
            e = runez.represented_duration(t.elapsed, span=-2)
            f = "x%.2f" % factor
            if t is fastest:
                f = ""

            elif t is slowest:
                f = runez.red(f)

            elif t.cumulative > fastest.cumulative * 2.9:
                f = runez.yellow(f)

        table.add_row(t.module_name, c, e, f, t.problem or "")

    print(table)


def main():
    run_cmds()


if __name__ == "__main__":
    main()
