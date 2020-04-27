import argparse

import runez


def sized(text, size):
    fmt = "{:%s}" % runez.color.adjusted_size(text, size)
    return fmt.format(text)


def show_fgcolors(bg=runez.plain):
    longest_color_name = runez.color.fg.longest_name
    overhead = max(runez.color.fg.overhead, longest_color_name)
    for color in runez.color.fg:
        color_name = color.name
        text = color(color.name)
        if text[0] == "\033":
            i = text.index("m", 1)
            text = "%s %s" % (color_name, text[2:i])

        line = [bg(color(sized(text, overhead)))]
        for style in runez.color.style:
            text = "%s %s" % (style.name, color_name)
            line.append(sized(bg(style(color(text))), longest_color_name + len(style.name) + 2))

        print(" ".join(line))

    print("")


def main():
    parser = argparse.ArgumentParser(description="Show a coloring sample")
    parser.add_argument("--color", action="store_true", help="Use colors (on by default on ttys).")
    parser.add_argument("--no-color", action="store_true", help="Do not use colors (even if on tty).")
    parser.add_argument("--bg", help="Show bg variant(s) (comma-separated list of color names).")
    parser.add_argument("--flavor", help="Show specific flavor (neutral, light or dark).")
    args = parser.parse_args()

    enable_colors = runez.is_tty()
    if args.no_color:
        enable_colors = False

    elif args.color:
        enable_colors = True

    with runez.ActivateColors(enable=enable_colors, flavor=args.flavor):
        print("Backend: %s\n" % runez.color.backend)
        show_fgcolors()
        if args.bg:
            for name in runez.flattened(args.bg, split=","):
                color = runez.color.bg.get(name)
                if color is None:
                    print("Unknown color '%s'" % name)

                else:
                    show_fgcolors(bg=color)


if "__main__" in __name__:
    main()
