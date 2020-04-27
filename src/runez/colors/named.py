from runez.colors import ColorManager


# Colors
def black(text, shorten=None):
    return ColorManager.fg.black(text, shorten=shorten)


def blue(text, shorten=None):
    return ColorManager.fg.blue(text, shorten=shorten)


def brown(text, shorten=None):
    return ColorManager.fg.brown(text, shorten=shorten)


def gray(text, shorten=None):
    return ColorManager.fg.gray(text, shorten=shorten)


def green(text, shorten=None):
    return ColorManager.fg.green(text, shorten=shorten)


def orange(text, shorten=None):
    return ColorManager.fg.orange(text, shorten=shorten)


def plain(text, shorten=None):
    return ColorManager.fg.plain(text, shorten=shorten)


def purple(text, shorten=None):
    return ColorManager.fg.purple(text, shorten=shorten)


def red(text, shorten=None):
    return ColorManager.fg.red(text, shorten=shorten)


def teal(text, shorten=None):
    return ColorManager.fg.teal(text, shorten=shorten)


def white(text, shorten=None):
    return ColorManager.fg.white(text, shorten=shorten)


def yellow(text, shorten=None):
    return ColorManager.fg.yellow(text, shorten=shorten)


# Styles
def blink(text, shorten=None):
    return ColorManager.style.blink(text, shorten=shorten)


def bold(text, shorten=None):
    return ColorManager.style.bold(text, shorten=shorten)


def dim(text, shorten=None):
    return ColorManager.style.dim(text, shorten=shorten)


def invert(text, shorten=None):
    return ColorManager.style.invert(text, shorten=shorten)


def italic(text, shorten=None):
    return ColorManager.style.italic(text, shorten=shorten)


def strikethrough(text, shorten=None):
    return ColorManager.style.strikethrough(text, shorten=shorten)


def underline(text, shorten=None):
    return ColorManager.style.underline(text, shorten=shorten)
