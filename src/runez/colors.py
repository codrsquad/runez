"""
Simple coloring capabilities, without the need of bringing in further dependencies

Example usage:
    from runez import activate_colors, blue

    print(blue("hello"))
"""

import os
import sys


def activate_colors(enable):
    """
    Args:
        enable (bool | None): Set colored output on or off, `None` means auto-determine depending on whether current stdout is a tty
    """
    global BACKEND
    if enable is None:
        enable = is_tty()
    BACKEND = TtyBackend if enable else PlainBackend


def is_coloring():
    """
    Returns:
        (bool): True if tty coloring is currently activated
    """
    return BACKEND is TtyBackend


def is_tty():
    """
    Returns:
        (bool): True if current stdout is a tty
    """
    return sys.stdout.isatty() or 'PYCHARM_HOSTED' in os.environ


class Color(object):
    """Defines a color, with associated tty codes, plus a `name` that can potentially be used by other kinds of backends"""

    def __init__(self, name, *tty_codes):
        self.name = name
        self.tty_fmt = "".join("\033[%dm" % c for c in tty_codes) + "%s\033[0m"  # codes + %s + reset

    def __call__(self, text, backend=None):
        text = str(text)
        if not text:
            return text
        if backend is None:
            backend = BACKEND
        return backend.colored(text, self)


class PlainBackend(object):
    """Default plain backend, ignoring colors"""

    @classmethod
    def colored(cls, text, color):
        """
        Args:
            text (str): Text to color
            color (Color): Color to use

        Returns:
            (str): Optionally colored text
        """
        return text


class TtyBackend(PlainBackend):
    """Color using usual tty escape codes"""

    @classmethod
    def colored(cls, text, color):
        return color.tty_fmt % text


BACKEND = TtyBackend if is_tty() else PlainBackend

blue = Color("blue", 94)
red = Color("red", 91)
yellow = Color("yellow", 93)

bold = Color("bold", 1)
dim = Color("dim", 2)
