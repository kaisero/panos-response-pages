"""The nyan style's artwork: a pixel map, and the compiler that ships it.

The shell cannot build this at runtime. The block pages have no bytes to spare
for a builder, and the portal family -- which shares this style's palette but
not its artwork -- could not run one at all: its home import carries no script,
and its login import rejects a raw '<' outside a tag, which every `i<n`
comparison is. So the artwork is compiled here and pasted into the shell as one
string, and `test_nyan_sprite.py` asserts the two have not drifted.

Rectangle merging is not a nicety. One <rect> per pixel is 10,935 B, which fits
no ceiling here; merged into the largest rectangles that share a colour and
emitted as paths, the same picture is under 1 KB.

To change the artwork: edit SPRITE, run this module, and paste what it prints
into the `.ny` background in templates/shells/nyan.html.
"""

from __future__ import annotations

# One character per pixel, '.' transparent. Kept as a literal map rather than
# drawn with arithmetic: this is artwork, and artwork is edited by looking at it.
SPRITE = [
    "........................................",
    "........................................",
    "........................................",
    "........................................",
    "........................................",
    "............................kkkkk.......",
    "...........................krrrrrk......",
    "..........................krbbbbbrk.....",
    "....................cc...krbbiiibbrk....",
    "........................krbbiiiiccbrk...",
    "........................krbiiiiicccrk...",
    "........................krbiiiiiicbrk...",
    "................c.......krbiiiiiiibrk...",
    "........................krbbiiiiibbrk...",
    ".........................krbbiiibbrk....",
    "......................cc..krbbbbbrk.....",
    "...........................krrrrrk......",
    "............................kkkkk.......",
    "........................................",
    "........................................",
    "........................................",
    "........................................",
    "........................................",
    "........................................",
]

# The ramp this style's palette is built from, so the artwork and the page agree
# without the artwork being able to read a custom property -- an SVG behind
# url() is an isolated document and inherits nothing.
PALETTE = {
    "k": "#2a0a1c",  # outline, the ramp's 1000 stop
    "r": "#c81f6f",  # rim, the 750 stop
    "b": "#ff4fa3",  # body, the accent itself
    "i": "#ff8fc4",  # inner, the 250 stop
    "c": "#ffe4f1",  # core and sparks, the 0 stop
}

WIDTH = len(SPRITE[0])
HEIGHT = len(SPRITE)


def rectangles(colour: str) -> list[tuple[int, int, int, int]]:
    """Greedy decomposition of one colour into (x, y, w, h) rectangles.

    Widest run first, then grown downward for as long as every row below matches.
    Not optimal -- optimal rectangle cover is expensive and this is a 40x24
    picture -- but it turns ~500 pixels into ~40 rectangles, which is the whole
    point.
    """
    used = [[False] * WIDTH for _ in range(HEIGHT)]
    out: list[tuple[int, int, int, int]] = []
    for y in range(HEIGHT):
        for x in range(WIDTH):
            if SPRITE[y][x] != colour or used[y][x]:
                continue
            w = 1
            while x + w < WIDTH and SPRITE[y][x + w] == colour and not used[y][x + w]:
                w += 1
            h = 1
            while y + h < HEIGHT and all(SPRITE[y + h][x + i] == colour and not used[y + h][x + i] for i in range(w)):
                h += 1
            for j in range(h):
                for i in range(w):
                    used[y + j][x + i] = True
            out.append((x, y, w, h))
    return out


def compile_svg() -> str:
    """The artwork as one SVG, one path per colour.

    Single-quoted attributes: this string is also assigned inside a CSS url(),
    and on the portal it sits in a file where the quoting has to stay simple.
    """
    paths = ""
    for char, hex_colour in PALETTE.items():
        rects = rectangles(char)
        if not rects:
            continue
        d = "".join(f"M{x} {y}h{w}v{h}h-{w}z" for x, y, w, h in rects)
        paths += f"<path fill='{hex_colour}' d='{d}'/>"
    return f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 {WIDTH} {HEIGHT}'>{paths}</svg>"


def data_uri() -> str:
    """The artwork as it appears in the shells.

    Only '#' is escaped. Left raw it ends the URL and the artwork loses its
    colours; everything else survives a CSS url() as written, and every '<' in
    the result is followed by a letter or a slash, which is what keeps the
    portal's raw-'<' guard satisfied.
    """
    return compile_svg().replace("#", "%23")


if __name__ == "__main__":
    import sys

    uri = data_uri()
    print(f'url("data:image/svg+xml,{uri}") center/contain no-repeat')
    print(f"\n{len(uri)} B", file=sys.stderr)
