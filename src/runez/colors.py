"""
Simple coloring capabilities, without the need of bringing in further dependencies

Example usage:
    from runez import activate_colors, blue

    print(blue("hello"))
"""

import os
import sys

from runez.base import stringified
from runez.convert import shortened


# Allows for a clean `from runez.colors import *`
__all__ = ["blue", "bold", "dim", "plural", "red", "yellow"]


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

    def __call__(self, text, backend=None, shorten=None):
        if shorten:
            text = shortened(text, size=shorten)

        else:
            text = stringified(text)

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
        return stringified(text)


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


class Pluralizer:
    """Best-effort english plurals"""

    letter_based = {"f": "ves", "s": "ses", "x": "ces", "y": "ies"}
    suffix_based = {"man": "men"}
    word_based = {"person": "people"}

    @classmethod
    def find_letter_based(cls, singular):
        irregular = cls.letter_based.get(singular[-1])
        if irregular is not None:
            return 1, irregular

        if len(singular) > 1:
            irregular = cls.letter_based.get(singular[-2])
            if irregular is not None:
                return 2, irregular

    @classmethod
    def plural(cls, singular):
        irregular = cls.word_based.get(singular)
        if irregular:
            return irregular

        for suffix in cls.suffix_based:
            if singular.endswith(suffix):
                c = len(suffix)
                return "%s%s" % (singular[:-c], cls.suffix_based[suffix])

        irregular = cls.find_letter_based(singular)
        if irregular:
            return singular[:-irregular[0]] + irregular[1]

        return "%ss" % singular


def plural(countable, singular):
    """
    Args:
        countable: How many things there are (can be int, or something countable)
        singular: What is counted (example: "record", or "chair", etc...)

    Returns:
        (str): Rudimentary, best-effort plural of "<count> <name>(s)"
    """
    count = len(countable) if hasattr(countable, "__len__") else countable
    if count == 1:
        return "1 %s" % singular

    plural = Pluralizer.plural(singular)
    return "%s %s" % (count, plural)
