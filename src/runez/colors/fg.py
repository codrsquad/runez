from runez.colors.terminal import Color


# Allows for a clean `import *`
__all__ = [
    "blue", "orange", "plain", "purple", "red", "teal", "yellow",
    "bold", "dim",
    "colors", "styles",
]

blue = Color("blue", 94)
orange = Color("orange", 33)
plain = Color("plain")
purple = Color("purple", 95)
red = Color("red", 91)
teal = Color("teal", 96)
yellow = Color("yellow", 93)

colors = [blue, orange, purple, red, teal, yellow]

bold = Color("bold", 1)
dim = Color("dim", 2)

styles = [bold, dim]
