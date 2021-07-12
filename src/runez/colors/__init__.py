"""
Simple coloring capabilities, without the need of bringing in further dependencies

Example usage:
    >>> from runez import blue
    >>> print(blue("hello"))
"""

from runez.system import DEV, short, Slotted, stringified, SYS_INFO, uncolored


class ActivateColors:
    """Context manager for temporarily overriding coloring"""

    def __init__(self, enable=True, flavor=None):
        if enable is True and DEV.current_test():
            # This allows to have easily reproducible tests (same color backend used in tests by default)
            enable = "testing"

        self.enable = enable
        self.flavor = flavor
        self.prev = None

    def __enter__(self):
        self.prev = ColorManager._activate_colors(self.enable, flavor=self.flavor)

    def __exit__(self, *_):
        ColorManager.backend, ColorManager.bg, ColorManager.fg, ColorManager.style = self.prev


class PlainBackend:
    """Default plain backend, ignoring colors"""

    color_count = 1
    name = "plain"

    def __repr__(self):
        return self.name

    def named_triplet(self):
        """Triplet of named bg, fg and style-s"""
        return NamedColors(), NamedColors(), NamedStyles()

    def adjusted_size(self, text, size=0):
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


class ColorManager:
    """Holds current global coloring backend and bg, fg color and style implementations"""

    backend = None  # type: PlainBackend
    bg = None  # type: NamedColors
    fg = None  # type: NamedColors
    style = None  # type: NamedStyles

    @classmethod
    def is_coloring(cls):
        """
        Returns:
            (bool): True if tty coloring is currently activated
        """
        return cls.backend.color_count > 1

    @classmethod
    def activate_colors(cls, enable=None, flavor=None):
        cls._activate_colors(enable=enable, flavor=flavor)
        return cls.is_coloring()

    @classmethod
    def adjusted_size(cls, text, size=0):
        """
        Args:
            text (str): Text to compute color adjusted padding size
            size (int): Desired padding size

        Returns:
            (int): `size`, adjusted to help take into account any color ANSI escapes
        """
        return cls.backend.adjusted_size(text, size)

    @classmethod
    def _activate_colors(cls, enable=None, flavor=None):
        """
        Args:
            enable (bool | PlainBackend.__class__ | None): Set colored output on or off
            flavor (str | None): Flavor to use (neutral, light or dark)
        """
        if enable is None:
            enable = SYS_INFO.terminal.is_stdout_tty

        prev = cls.backend, cls.bg, cls.fg, cls.style
        cls.backend = _detect_backend(enable, flavor=flavor)
        cls.bg, cls.fg, cls.style = cls.backend.named_triplet()
        return prev


class Renderable:
    """A render-able (color or style) named object"""

    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return self.name

    def __call__(self, text, size=None):
        """
        Allows for convenient call of the form:

        >>> import runez
        >>> print(runez.blue("foo"))
        """
        if size:
            text = short(text, size=size)

        else:
            text = stringified(text)

        if not text:
            return ""

        return self.rendered(text)

    def rendered(self, text):
        return text


class NamedRenderables(Slotted):
    def __init__(self, cls=None, params=None, **color_names):
        if params is None:
            params = {}

        colors = {}
        for key in self.__slots__:
            # Fill all slots, with default (plain) for non-specified ones
            color = color_names.pop(key, None)
            if color is None or cls is None:
                color = Renderable(key)

            else:
                args = color if isinstance(color, tuple) else [color]
                color = cls(key, *args, **params)

            colors[key] = color

        super().__init__(**colors)


class NamedColors(NamedRenderables):
    """Set of registered named colors"""

    __slots__ = ["black", "blue", "brown", "gray", "green", "orange", "plain", "purple", "red", "teal", "white", "yellow"]


class NamedStyles(NamedRenderables):
    """Set of registered named styles"""

    __slots__ = ["blink", "bold", "dim", "invert", "italic", "strikethrough", "underline"]


def cast_style(obj):
    """Cast 'obj' to a style, raise exception if that's not possible"""
    if isinstance(obj, Renderable):
        return obj

    if hasattr(obj, "__name__"):
        obj = obj.__name__

    result = ColorManager.style.get(obj)
    if result:
        return result

    raise ValueError("Unknown style '%s'" % obj)


def _detect_backend(enable, flavor=None):
    """Auto-detect best backend to use"""
    if isinstance(enable, type) and issubclass(enable, PlainBackend):
        return enable()

    if enable and isinstance(enable, PlainBackend):
        return enable

    if enable:
        from runez.colors import terminal

        if enable == "testing":
            return terminal.Ansi16Backend(flavor=flavor or "neutral")

        usable = terminal.usable_backends(flavor=flavor)
        if usable:
            return usable[0]

    return PlainBackend()
