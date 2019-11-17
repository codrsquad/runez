"""
Simple coloring capabilities, without the need of bringing in further dependencies

Example usage:
    from runez import activate_colors, blue

    print(blue("hello"))
"""

import os
import re
import sys

from runez.base import stringified
from runez.convert import shortened, to_int
from runez.system import current_test


# Allows for a clean `import *`
__all__ = [
    "activate_colors", "Color", "color_adjusted_size", "is_coloring", "is_tty", "uncolored",
    "blink", "bold", "dim", "invert", "italic", "strikethrough", "underline",
    "styles",
]


RE_ANSI_ESCAPE = re.compile("\x1b\\[[;\\d]*[A-Za-z]")
BACKEND = None


def is_coloring():
    """
    Returns:
        (bool): True if tty coloring is currently activated
    """
    return BACKEND is not PlainBackend


def is_tty():
    """
    Returns:
        (bool): True if current stdout is a tty
    """
    return (sys.stdout.isatty() or "PYCHARM_HOSTED" in os.environ) and not current_test()


def uncolored(text):
    """
    Args:
        text (str | None): Text to remove ANSI colors from

    Returns:
        (str): Text without any ANSI color escapes
    """
    return RE_ANSI_ESCAPE.sub("", text or "")


def color_adjusted_size(text, size):
    """
    Args:
        text (str): Text to compute color adjusted padding size
        size (int): Desired padding size

    Returns:
        (int): `size`, adjusted to help take into account any color ANSI escapes
    """
    if text:
        size += len(text) - len(uncolored(text))

    return size


class AnsiCode(object):
    """Compute ANSI escape codes to use for a given RGB color"""
    bg_offset = 40
    fg_offset = 30

    @classmethod
    def enhanced(cls, r, g, b, ratio):
        """Enhanced color by 'ratio', allows to brighten/darken colors"""
        f, lm = (min, 255) if ratio > 1 else (max, 0)
        if ratio > 1:
            r = max(8, r)
            g = max(8, g)
            b = max(8, b)

        return f(lm, int(round(r * ratio))), f(lm, int(round(g * ratio))), f(lm, int(round(b * ratio)))

    @classmethod
    def ansi16(cls, offset, r, g, b, brighten):
        """Convert RGB to ANSI 16 color"""
        r = int(round(r / 255.0))
        g = int(round(g / 255.0)) << 1
        b = int(round(b / 255.0)) << 2
        code = (90 if brighten else 30) + (r | g | b)
        return int(code) + offset - cls.fg_offset

    @classmethod
    def ansi256(cls, offset, r, g, b, brighten):
        """Convert RGB to ANSI 256 color"""
        if brighten is not None:
            r, g, b = cls.enhanced(r, g, b, 2 if brighten else 0.7)

        if r == g == b:
            if r < 8:
                code = 16

            elif r > 248:
                code = 231

            else:
                code = round(((r - 8) / 247.0) * 24) + 232

        else:
            r = 36 * round(r / 255.0 * 5.0)
            g = 6 * round(g / 255.0 * 5.0)
            b = round(b / 255.0 * 5.0)
            code = 16 + r + g + b

        return "%s;5;%s" % (8 + offset, int(code))

    @classmethod
    def truecolor(cls, offset, r, g, b, brighten):
        """Convert RGB to ANSI true-color"""
        if brighten is not None:
            r, g, b = cls.enhanced(r, g, b, 1.25 if brighten else 0.8)

        return "%s;2;%s;%s;%s" % (8 + offset, r, g, b)


class ColorFormat(object):
    """Pre-computed color formatters for all supported flavors"""

    def __init__(self, color, fmt):
        self.color = color
        if self.color.rgb is None:
            # `plain` color: return text as-is (no coloring applied)
            self.neutral = "{}"
            self.light = "{}"
            self.dark = "{}"

        else:
            offset = AnsiCode.bg_offset if color.rgb < 0 else AnsiCode.fg_offset
            rgb = abs(color.rgb)
            r = (rgb & 0xff0000) >> 16
            g = (rgb & 0xff00) >> 8
            b = rgb & 0xff

            base_fmt = "\033[{{start}}m{{{{}}}}\033[{end}m".format(end=offset + 9)
            self.neutral = base_fmt.format(start=fmt(offset, r, g, b, None))
            self.light = base_fmt.format(start=fmt(offset, r, g, b, True))
            self.dark = base_fmt.format(start=fmt(offset, r, g, b, False))


class Color(object):
    """Defines a color, with associated tty codes, plus a `name` that can potentially be used by other kinds of backends"""

    def __init__(self, name, rgb):
        """
        Args:
            name (str): Color name (example: blue)
            rgb (int | None): RGB value (example: 0x0000ff)
        """
        self.name = name
        self.rgb = rgb
        self.ansi16 = ColorFormat(self, AnsiCode.ansi16)
        self.ansi256 = ColorFormat(self, AnsiCode.ansi256)
        self.truecolor = ColorFormat(self, AnsiCode.truecolor)

    def __repr__(self):
        return self.name

    def __call__(self, text, shorten=None):
        if shorten:
            text = shortened(text, size=shorten)

        return BACKEND.colored(text, self)


class Style(object):
    def __init__(self, name, start, end):
        self.name = name
        self.start = start
        self.end = end
        self.fmt = "\033[%sm{}\033[%sm" % (start, end)

    def __repr__(self):
        return self.name

    def __call__(self, text, shorten=None):
        if shorten:
            text = shortened(text, size=shorten)

        return BACKEND.styled(text, self)


blink = Style("blink", 5, 25)
bold = Style("bold", 1, 22)
dim = Style("dim", 2, 22)
invert = Style("invert", 7, 27)
italic = Style("italic", 3, 23)
strikethrough = Style("strikethrough", 9, 29)
underline = Style("underline", 4, 24)

styles = [blink, bold, dim, invert, italic, strikethrough, underline]


class PlainBackend(object):
    """Default plain backend, ignoring colors"""
    color_count = 1
    flavor = "neutral"

    @classmethod
    def colored(cls, text, color):
        """
        Args:
            text (str): Text to color
            color (Color): Color to use

        Returns:
            (str): Optionally colored text
        """
        return stringified(text)

    @classmethod
    def styled(cls, text, style):
        """
        Args:
            text (str): Text to color
            style (Style): Style to use

        Returns:
            (str): Optionally styled text
        """
        return stringified(text)


class Ansi16Backend(PlainBackend):
    """ANSI 16-color"""
    color_count = 16
    ansi = "ansi16"

    @classmethod
    def colored(cls, text, color):
        if color is None or text == "":
            return text

        ansi = getattr(color, cls.ansi)
        flavor = getattr(ansi, cls.flavor)
        return flavor.format(text)

    @classmethod
    def styled(cls, text, style):
        if style is None or text == "":
            return text

        return style.fmt.format(text)


class Ansi256Backend(Ansi16Backend):
    """ANSI 256-color"""
    color_count = 256
    ansi = "ansi256"


class TrueColorBackend(Ansi16Backend):
    """ANSI true-color"""
    color_count = 1 << 24
    ansi = "truecolor"


def mentions(value, *terms):
    """Do any of the `terms` mention `value`?"""
    for term in terms:
        if term in value:
            return term


def usable_backends(env):
    """
    Args:
        env (dict): Environemnt variables to inspect

    Returns:
        (list): List of usable backends, give `env`
    """
    result = {PlainBackend}
    if env:
        result.add(Ansi16Backend)
        for env_var in ("COLORTERM", "TERM_PROGRAM", "TERM"):
            value = env.get(env_var)
            if value:
                value = value.lower()
                if mentions(value, "true", "24", "iterm", "hyper"):
                    result.add(TrueColorBackend)

                elif mentions(value, "256", "8", "apple_"):
                    result.add(Ansi256Backend)

    return sorted(result, key=lambda x: -x.color_count)


def detect_flavor(bg):
    """
    Args:
        bg (str | None): Value of env var COLORFGBG

    Returns:
        (str): Flavor to use
    """
    if bg and ";" in bg:
        _, _, bg = bg.partition(";")
        bg = to_int(bg, default=None)
        if bg is not None:
            return "dark" if bg > 6 and bg != 8 else "light"

    return "neutral"


def detect_backend(enable, env):
    """Auto-detect best backend to use"""
    if isinstance(enable, type) and issubclass(enable, PlainBackend):
        return enable

    return usable_backends(enable and env)[0]


def activate_colors(enable, flavor=None, env=os.environ):
    """
    Args:
        enable (bool | PlainBackend.__class__ | None): Set colored output on or off
        flavor (str | None): Flavor to use (neutral, light or dark)
        env (dict): Env vars to use
    """
    global BACKEND
    if enable is None:
        enable = is_tty()
        if flavor is None and enable:
            flavor = detect_flavor(env.get("COLORFGBG"))

    if flavor:
        PlainBackend.flavor = flavor

    BACKEND = detect_backend(enable, env)


activate_colors(None)
