"""
See some example behaviors of runez
"""

import argparse
import os
import sys

import runez
from runez.inspector import ImportTime, run_cmds
from runez.render import NAMED_BORDERS, PrettyTable


def cmd_colors():
    """Show a coloring sample"""
    parser = argparse.ArgumentParser(description="Show a coloring sample")
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


def cmd_import_speed():
    """Show average import time of top-level python packages installed in this venv"""
    parser = argparse.ArgumentParser(description="Show average import time of top-level python packages installed in this venv")
    parser.add_argument("--all", action="store_true", help="Show all.")
    parser.add_argument("--border", choices=NAMED_BORDERS, default="reddit", help="Use custom border.")
    parser.add_argument("--iterations", "-i", type=int, default=3, help="Number of measurements to average.")
    parser.add_argument("name", nargs="*", help="Names of modules to show (by default: all).")
    args = parser.parse_args()
    names = []
    if args.name:
        names.extend(runez.flattened(args.name, split=","))

    if args.all:
        names.extend(_all_deps())

    if not names:
        sys.exit("Please specify module names, or use --all")

    names = sorted(runez.flattened(names, unique=True))
    times = []
    fastest = None
    slowest = None
    for name in names:
        t = ImportTime(name, iterations=args.iterations)
        times.append(t)
        if t.cumulative is None:
            continue

        if fastest is None or (t.cumulative < fastest.cumulative):
            fastest = t

        if slowest is None or t.cumulative > slowest.cumulative:
            slowest = t

    table = PrettyTable("Module,-X cumulative,Elapsed,Vs fastest,Note", border=args.border)
    table.header[3].align = "center"
    mid = _get_mid(times) or 0
    for t in times:
        if t.cumulative is None:
            c = e = f = None

        else:
            factor = t.elapsed / fastest.elapsed
            c = runez.represented_duration(t.cumulative / 1000000, span=-2)
            e = runez.represented_duration(t.elapsed, span=-2)
            f = "x%.2f" % factor
            if t is fastest:
                f = ""

            elif t is slowest:
                f = runez.red(f)

            elif t.elapsed and t.elapsed > mid:
                f = runez.orange(f)

        table.add_row(t.module_name, c, e, f, t.problem or "")

    print(table)


def _get_mid(times):
    times = [t for t in times if t.elapsed]
    if times:
        times = sorted(times, key=lambda x: -x.elapsed)  # Don't fail if no elapsed available
        return times[int(len(times) / 2)].elapsed


def main():
    run_cmds()


def _show_fgcolors(bg=runez.plain, border=None):
    print("")
    table = PrettyTable("Color,Blink,Bold,Dim,Invert,Italic,Strikethrough,Underline", border=border)
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


def _all_deps():
    """All dependencies in current venv"""
    import pkg_resources
    import sysconfig

    result = []
    base = sysconfig.get_path("purelib")
    ws = pkg_resources.WorkingSet([base])
    for dist in ws:
        if _is_interesting_dist(dist.key):
            top_level = _find_top_level(base, dist)
            if top_level:
                result.append(top_level)

    return result


# Usual dev libs that are not interesting for --all import times, they import ultra fast...
# They can always be stated as argument explicitly to show their import times anyway
DEV_LIBS = """
attrs coverage mock more-itertools packaging pip pluggy py pyparsing python-dateutil setuptools six wcwidth wheel zipp
binaryornot cookiecutter click future
"""
DEV_LIBS = set(runez.flattened(DEV_LIBS.splitlines(), split=" "))


def _is_interesting_dist(key):
    if key.startswith("pytest") or key.startswith("importlib"):
        return False

    return key not in DEV_LIBS


def _find_top_level(base, dist):
    name = dist.key.replace("-", "_").replace(".", "_")
    top_level = os.path.join(base, "%s-%s.dist-info" % (name, dist.version), "top_level.txt")
    for line in runez.readlines(top_level, default=[]):
        if not line.startswith("_") and line:
            return line


if __name__ == "__main__":
    main()
