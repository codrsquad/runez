import os

from runez.colors import NamedColors, NamedStyles, PlainBackend, Renderable
from runez.convert import to_int


VALID_FLAVORS = {"dark", "light", "neutral"}


class AnsiCode:
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


class AnsiColor(Renderable):
    """Defines a color, with associated tty codes, plus a `name` that can potentially be used by other kinds of backends"""

    def __init__(self, name, rgb, ansi=None, flavor=None):
        """
        Args:
            name (str): Color name (example: blue)
            rgb (int | None): RGB value (example: 0x0000ff)
            ansi (str): Ansi codeset to use (ansi16, ansi256 or truecolor)
            flavor (str): Flavor to use (neutral, light or dark)
        """
        super().__init__(name)
        self.rgb = rgb
        fmt = getattr(AnsiCode, ansi)
        offset = AnsiCode.bg_offset if rgb < 0 else AnsiCode.fg_offset
        rgb = abs(rgb)
        r = (rgb & 0xFF0000) >> 16
        g = (rgb & 0xFF00) >> 8
        b = rgb & 0xFF
        base_fmt = "\033[{{start}}m{{{{}}}}\033[{end}m".format(end=offset + 9)
        brighten = None if flavor == "neutral" else flavor == "light"
        self.fmt = base_fmt.format(start=fmt(offset, r, g, b, brighten))

    def rendered(self, text):
        return self.fmt.format(text)


class AnsiStyle(Renderable):
    def __init__(self, name, start, end):
        super().__init__(name)
        self.start = start
        self.end = end
        self.fmt = "\033[%sm{}\033[%sm" % (start, end)

    def rendered(self, text):
        return self.fmt.format(text)


class Ansi16Backend(PlainBackend):
    """ANSI 16-color"""

    color_count = 16
    ansi = "ansi16"

    def __init__(self, flavor=None):
        """
        Args:
            flavor (str | None): Flavor to use (neutral, light or dark)
        """
        if flavor is None:
            flavor = detect_flavor(os.environ.get("COLORFGBG"))

        self.flavor = flavor if flavor in VALID_FLAVORS else "neutral"
        self.name = "%s %s" % (self.ansi, self.flavor)

    def named_triplet(self):
        """Triplet of named bg, fg and style-s"""
        bg = NamedColors(
            cls=AnsiColor,
            params=dict(ansi=self.ansi, flavor=self.flavor),
            black=-0x000001,
            blue=-0x0000FF,
            brown=-0xA52A2A,
            gray=-0xBEBEBE,
            green=-0xFF00,
            orange=-0xFFA500,
            purple=-0xA020F0,
            red=-0xFF0000,
            teal=-0x008080,
            white=-0xFFFFFF,
            yellow=-0xFFFF00,
        )
        fg = NamedColors(
            cls=AnsiColor,
            params=dict(ansi=self.ansi, flavor=self.flavor),
            black=0x000000,
            blue=0x0000FF,
            brown=0x850A0A,
            gray=0xBEBEBE,
            green=0xFF00,
            orange=0xEF9500,
            purple=0xA020F0,
            red=0xFF0000,
            teal=0x008080,
            white=0xFFFFFF,
            yellow=0xFFFF00,
        )
        style = NamedStyles(
            cls=AnsiStyle,
            blink=(5, 25),
            bold=(1, 22),
            dim=(2, 22),
            invert=(7, 27),
            italic=(3, 23),
            strikethrough=(9, 29),
            underline=(4, 24),
        )
        return bg, fg, style


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


def usable_backends(flavor=None):
    """
    Args:
        flavor (str | None): Flavor to use (neutral, light or dark)

    Returns:
        (list): List of usable backends
    """
    result = set()
    result.add(Ansi16Backend)
    for env_var in ("COLORTERM", "TERM_PROGRAM", "TERM"):
        value = os.environ.get(env_var)
        if value:
            value = value.lower()
            if mentions(value, "true", "24", "iterm", "hyper"):
                result.add(TrueColorBackend)

            elif mentions(value, "256", "8", "apple_"):
                result.add(Ansi256Backend)

    return [cls(flavor=flavor) for cls in sorted(result, key=lambda x: -x.color_count)]


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
