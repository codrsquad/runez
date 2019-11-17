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


# Allows for a clean `import *`
__all__ = [
    "activate_colors", "Color", "color_adjusted_size", "is_coloring", "is_tty", "uncolored",
    "blink", "bold", "dim", "invert", "italic", "strikethrough", "underline",
    "styles",
]


RE_ANSI_ESCAPE = re.compile("\x1b\\[[;\\d]*[A-Za-z]")


def activate_colors(enable):
    """
    Args:
        enable (bool | PlainBackend.__class__ | None): Set colored output on or off
    """
    global BACKEND
    if enable is None:
        enable = is_tty()

    BACKEND = detect_backend(enable)


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
    return sys.stdout.isatty() or "PYCHARM_HOSTED" in os.environ


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
    bg_offset = 40
    fg_offset = 30

    @classmethod
    def ansi16(cls, offset, r, g, b, use_bright):
        r = int(round(r / 255.0))
        g = int(round(g / 255.0)) << 1
        b = int(round(b / 255.0)) << 2
        code = (90 if use_bright else 30) + (r | g | b)
        return int(code) + offset - cls.fg_offset

    @classmethod
    def ansi256(cls, offset, r, g, b, use_bright):
        """Convert RGB to ANSI 256 color"""
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

        return "%s;5;%s" % (8 + offset, code)

    @classmethod
    def truecolor(cls, offset, r, g, b, use_bright):
        return "%s;2;%s;%s;%s" % (8 + offset, r, g, b)


class ColorFormat(object):
    def __init__(self, color, fmt):
        self.color = color
        if self.color.rgb is None:
            self.light = "{}"
            self.dark = "{}"

        else:
            offset = AnsiCode.bg_offset if color.rgb < 0 else AnsiCode.fg_offset
            rgb = abs(color.rgb)
            r = (rgb & 0xff0000) >> 16
            g = (rgb & 0xff00) >> 8
            b = rgb & 0xff

            base_fmt = "\033[{{start}}m{{{{}}}}\033[{end}m".format(end=offset + 9)
            self.light = base_fmt.format(start=fmt(offset, r, g, b, True))
            self.dark = base_fmt.format(start=fmt(offset, r, g, b, False))

    def __repr__(self):
        return "%s - %s" % (self.light, self.dark)


class Color(object):
    """Defines a color, with associated tty codes, plus a `name` that can potentially be used by other kinds of backends"""

    def __init__(self, name, rgb):
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

        if text == "":
            return ""

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
    priority = 10
    flavor = "dark"

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
    priority = 3
    ansi = "ansi16"

    @classmethod
    def colored(cls, text, color):
        ansi = getattr(color, cls.ansi)
        flavor = getattr(ansi, cls.flavor)
        return flavor.format(text)

    @classmethod
    def styled(cls, text, style):
        if text == "":
            return ""

        return style.fmt.format(text)


class Ansi256Backend(Ansi16Backend):
    priority = 2
    ansi = "ansi256"


class TrueColorBackend(Ansi16Backend):
    priority = 1
    ansi = "truecolor"


def mentions(value, *terms):
    for term in terms:
        if term in value:
            return term


def usable_backends(env):
    for env_var in ("COLORTERM", "TERM_PROGRAM", "TERM"):
        value = env.get(env_var)
        if value:
            value = value.lower()
            if mentions(value, "true", "24", "iterm", "hyper"):
                yield TrueColorBackend

            if mentions(value, "256", "8", "apple_"):
                yield Ansi256Backend


def detect_backend(enable, env=os.environ):
    """Auto-detect best backend to use"""
    if isinstance(enable, type) and issubclass(enable, PlainBackend):
        return enable

    if enable:
        usable = sorted(set(usable_backends(env)), key=lambda x: x.priority)
        if usable:
            return usable[0]

        return Ansi16Backend

    return PlainBackend


def detect_flavor(fgbg):
    if fgbg:
        _, _, bg = fgbg.partition(";")
        bg = to_int(bg, default=0)
        if bg > 6 and bg != 8:
            return "light"

        return "dark"


BACKEND = detect_backend(is_tty())
PlainBackend.flavor = detect_flavor(os.environ.get("COLORFGBG") or "dark")
