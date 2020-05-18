from runez.colors import ColorManager


# Colors
def black(text, size=None):
    return ColorManager.fg.black(text, size=size)


def blue(text, size=None):
    return ColorManager.fg.blue(text, size=size)


def brown(text, size=None):
    return ColorManager.fg.brown(text, size=size)


def gray(text, size=None):
    return ColorManager.fg.gray(text, size=size)


def green(text, size=None):
    return ColorManager.fg.green(text, size=size)


def orange(text, size=None):
    return ColorManager.fg.orange(text, size=size)


def plain(text, size=None):
    return ColorManager.fg.plain(text, size=size)


def purple(text, size=None):
    return ColorManager.fg.purple(text, size=size)


def red(text, size=None):
    return ColorManager.fg.red(text, size=size)


def teal(text, size=None):
    return ColorManager.fg.teal(text, size=size)


def white(text, size=None):
    return ColorManager.fg.white(text, size=size)


def yellow(text, size=None):
    return ColorManager.fg.yellow(text, size=size)


# Styles
def blink(text, size=None):
    return ColorManager.style.blink(text, size=size)


def bold(text, size=None):
    return ColorManager.style.bold(text, size=size)


def dim(text, size=None):
    return ColorManager.style.dim(text, size=size)


def invert(text, size=None):
    return ColorManager.style.invert(text, size=size)


def italic(text, size=None):
    return ColorManager.style.italic(text, size=size)


def strikethrough(text, size=None):
    return ColorManager.style.strikethrough(text, size=size)


def underline(text, size=None):
    return ColorManager.style.underline(text, size=size)
