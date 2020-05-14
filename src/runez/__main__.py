"""
See some example behaviors of runez
"""

import argparse

import runez


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


def main():
    runez.click.run_cmds()


if __name__ == "__main__":
    main()
