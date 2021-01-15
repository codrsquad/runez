# -*- encoding: utf-8 -*-
from itertools import cycle

from runez.system import flattened


SPINNER_FPS = 10  # Animation overhead is ~0.1% at 10 FPS


class AsciiAnimation(object):
    """Contains a few progress spinner animation examples"""

    @classmethod
    def available_names(cls):
        """(list[str]): Available ascii animation names from this sample collection"""
        return sorted(k[3:] for k in dir(cls) if k.startswith("af_")) + ["off"]

    @classmethod
    def predefined(cls, name):
        """(AsciiFrames | None): Predefined animation with 'name', if any"""
        if name == "off":
            return AsciiFrames(None)

        if name in cls.available_names():
            return getattr(cls, "af_%s" % name)()

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
        chars = cycle(u"⣯⣷⣾⣽⣻⢿⡿⣟")
        return AsciiFrames(("%s%s" % (f, next(chars)) for f in cls.circling_dots()), fps=5)

    @classmethod
    def af_dotrot3(cls):
        """2 small rotating dots in opposite direction"""
        return AsciiFrames(cls.alternating_cycle(u"⡿⣟⣯⣷⣾⣽⣻⢿", size=2), fps=5)

    @classmethod
    def af_fill(cls):
        """Bar growing/shrinking vertically, then horizontally"""
        return AsciiFrames([" "] + cls.symmetrical(list(u"▁▂▃▄▅▆▇█")) + [" "] + cls.symmetrical(list(u"▏▎▍▌▋▊▉")))

    @classmethod
    def af_fill2(cls):
        """2 bars filling up and down"""
        return AsciiFrames(cls.travelling(cls.symmetrical(list(u"▁▂▃▄▅▆▇█")), 2))

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
        return [u"▖ ", u"▗ ", u" ▖", u" ▗", u" ▝", u" ▘", u"▝ ", u"▘ "]

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


class AsciiFrames(object):
    """Holds ascii animation frames, one-line animations of arbitrary size (should be playable in a loop for good visual effect)"""

    def __init__(self, frames, fps=SPINNER_FPS):
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
