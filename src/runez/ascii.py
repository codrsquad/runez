import os
from itertools import cycle

from runez.system import flattened


class AsciiAnimation:
    """Contains a few progress spinner animation examples"""

    env_var = "SPINNER"  # Env var overriding which predefined spinner to use
    default = "dots"  # Default spinner to use

    @classmethod
    def available_names(cls, include_virtual=True):
        """(list[str]): Available ascii animation names from this sample collection"""
        return sorted(k[3:] for k in dir(cls) if k.startswith("af_")) + (["random", "off"] if include_virtual else [])

    @classmethod
    def predefined(cls, name):
        """(AsciiFrames | None): Predefined animation with 'name', if any"""
        if name == "off":
            return AsciiFrames(None)

        if name == "random":
            import random

            names = cls.available_names(include_virtual=False)
            n = len(names)
            n = max(0, min(n - 1, int(n * random.random())))
            name = names[n]

        if name in cls.available_names():
            return getattr(cls, "af_%s" % name)()

    @classmethod
    def from_spec(cls, spec):
        """
        Args:
            spec (AsciiFrames | callable | str | None): Possible reference to some frames, by predefined name or callable returning frames

        Returns:
            (AsciiFrames | None): Corresponding AsciiFrames object, if any
        """
        if callable(spec):
            spec = spec()

        if isinstance(spec, str):
            return cls.predefined(spec)

        if isinstance(spec, AsciiFrames):
            return spec

    @classmethod
    def from_specs(cls, *specs):
        """First usable frames from given specs"""
        for spec in specs:
            frames = cls.from_spec(spec)
            if frames:
                return frames

        return AsciiFrames(None)

    @classmethod
    def get_frames(cls, spec, default=None):
        """
        Args:
            spec (AsciiFrames | callable | str | None): What frame animation to use
            default (AsciiFrames | callable | str | None): Default

        Returns:
            (AsciiFrames): First found: from env var, then given 'spec', then 'default, finally 'cls.default'
        """
        if isinstance(spec, AsciiFrames):
            return spec

        return cls.from_specs(os.environ.get(cls.env_var or ""), spec, default, cls.default)

    @classmethod
    def af_dots(cls):
        """Dots going left and right"""
        return AsciiFrames(cls.symmetrical(["   ", ".  ", ".. ", "...", " ..", "  .", "   "]), fps=2)

    @classmethod
    def af_dotrot(cls):
        """Rotating dot"""
        return AsciiFrames(cls.circling_dots(), fps=5)

    @classmethod
    def af_dotrot2(cls):
        """2 rotating dots (one bigger, one smaller)"""
        chars = cycle("⣯⣷⣾⣽⣻⢿⡿⣟")
        return AsciiFrames(("%s%s" % (f, next(chars)) for f in cls.circling_dots()), fps=5)

    @classmethod
    def af_dotrot3(cls):
        """2 small rotating dots in opposite direction"""
        return AsciiFrames(cls.alternating_cycle("⡿⣟⣯⣷⣾⣽⣻⢿", size=2), fps=5)

    @classmethod
    def af_fill(cls):
        """Bar growing/shrinking vertically, then horizontally"""
        return AsciiFrames([" "] + cls.symmetrical(list("▁▂▃▄▅▆▇█")) + [" "] + cls.symmetrical(list("▏▎▍▌▋▊▉")))

    @classmethod
    def af_fill2(cls):
        """2 bars filling up and down"""
        return AsciiFrames(cls.travelling(cls.symmetrical(list("▁▂▃▄▅▆▇█")), 2))

    @classmethod
    def af_oh(cls):
        """Moving growing/shrinking O signal"""
        return AsciiFrames(cls.travelling(" .-oOOo-.", 3))

    @staticmethod
    def alternating_cycle(chars, size=2):
        """Rotate through characters in 'chars', in alternated direction, animation is 'size' characters wide"""
        alt = cycle((lambda: cycle(chars), lambda: cycle(reversed(chars))))
        cycles = [next(alt)() for _ in range(size)]
        return ("".join(next(c) for c in cycles) for _ in range(len(chars)))

    @classmethod
    def circling_dots(cls):
        return ["▖ ", "▗ ", " ▖", " ▗", " ▝", " ▘", "▝ ", "▘ "]

    @staticmethod
    def symmetrical(frames):
        """Frames followed by their reverse"""
        return frames + list(reversed(frames))

    @staticmethod
    def travelling(chars, size):
        """Animated 'chars', repeated 'size' times, moving left then right"""
        yield (["".join((" " * i, c, " " * (size - i - 1))) for c in chars] for i in range(size))
        if size > 2:
            yield (["".join((" " * (i + 1), c, " " * (size - i - 2))) for c in chars] for i in reversed(range(size - 2)))


class AsciiFrames:
    """Holds ascii animation frames, one-line animations of arbitrary size (should be playable in a loop for good visual effect)"""

    def __init__(self, frames, fps=10):
        """
        Args:
            frames: Frames composing the ascii animation
            fps (int): Desired frames per second
        """
        self.frames = flattened(frames, keep_empty=None) or None
        self.fps = fps
        self.index = 0

    def __repr__(self):
        return "off" if not self.frames else "%s frames" % len(self.frames)

    def next_frame(self):
        """
        Returns:
            (str): Next frame (infinite cycle across self.frames)
        """
        if self.frames:
            self.index += 1
            if self.index >= len(self.frames):
                self.index = 0

            return self.frames[self.index]
