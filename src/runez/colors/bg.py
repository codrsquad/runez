from runez.colors.terminal import Color


# Allows for a clean `import *`
__all__ = [
    "black", "blue", "brown", "gray", "green", "orange", "purple", "red", "teal", "white", "yellow",
    "colors",
]

black = Color("black", -0x000001)
blue = Color("blue", -0x0000ff)
brown = Color("brown", -0xa52a2a)
gray = Color("gray", -0xbebebe)
green = Color("green", -0xff00)
orange = Color("orange", -0xffa500)
purple = Color("purple", -0xa020f0)
red = Color("red", -0xff0000)
teal = Color("teal", -0x008080)
white = Color("white", -0xffffff)
yellow = Color("yellow", -0xffff00)

colors = [black, blue, brown, gray, green, orange, purple, red, teal, white, yellow]
