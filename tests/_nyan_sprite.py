"""The nyan style's artwork: the pixel maps, and the compiler that ships them.

The shell cannot build this at runtime. The block pages have no bytes to spare
for a builder -- the draft that carried one reached 16,582 B on `url-block-page`,
over the suite's own limit -- so the artwork is compiled here and pasted into the
shell as one string, and `test_nyan_sprite.py` asserts the two have not drifted.

Six layers, because the animation is a frame swap and not a transform: the body
never moves, the legs alternate between two positions and the tail cycles
through three, the way the original's frames do. The shell shows one leg layer
and one tail layer at a time by animating `opacity` with `steps(1,end)`, which
is why each layer has to be its own group rather than one flattened picture.

Rectangle merging is not a nicety. One <rect> per pixel is ~11 kB, which fits no
ceiling here; merged and emitted as paths, all six layers come to about 1.7 kB.
Half of that saving is the occlusion pass described on `rectangles` -- without
it the black outline alone costs more than the cat it goes around.

To change the artwork: edit the maps, run this module, and paste what it prints
over the <svg> inside `.fly` in templates/shells/nyan.html.
"""

from __future__ import annotations

# The classic colours, not the style's ramp. Everything else on this page is
# palette-driven; the cat is a specific picture, and recolouring it to match a
# brand is what turned it into an anonymous blob the first time round.
#
# Three-digit hex throughout -- the shell carries this markup inline, where the
# short form is legal and saves three bytes on every path.
#
# The order is paint order, and `rectangles` depends on it: outline first, then
# the tart from the outside in, then the fur and the two details that sit on it.
PALETTE = {
    "k": "#000",  # outline
    "c": "#fc9",  # crust
    "f": "#f9c",  # frosting
    "d": "#f39",  # sprinkles
    "g": "#999",  # fur
    "p": "#f99",  # cheeks
    "w": "#fff",  # eye glint
}

# The canvas the layers are placed on, and the shell's viewBox.
WIDTH = 40
HEIGHT = 24

# Each layer is (x, y, rows): a map cropped to its own bounding box, and where
# that box sits on the canvas. Cropping keeps the maps readable -- a full 40x24
# grid per layer would be five screens of mostly dots -- and costs nothing, since
# the offset is folded into the path coordinates at compile time.
#
# '.' is transparent. The outlines are part of the maps rather than grown by
# code: this is artwork, and artwork is edited by looking at it.

# Pop tart and head. The sprinkle lattice is three rows of four, offset; the
# head carries ears, eyes with a glint, cheeks and the mouth.
BODY = (
    6,
    3,
    [
        ".kkkkkkkkkkkkkkkkkkkk...........",
        "kcccccccccccccccccccckkk.....kk.",
        "kcccccccccccccccccccckggk...kggk",
        "kccffffffffffffffffcckgggkkkgggk",
        "kccffddffddffddffddcckkgggggggk.",
        "kccffddffddffddffddcckgggggggggk",
        "kccffffffffffffffffcckggwkgwkggk",
        "kccffffddffddffddffcckppkkgkkpp.",
        "kccffffddffddffddffcckppkkgkkpp.",
        "kccffffffffffffffffcckgggggggggk",
        "kccffddffddffddffddcckggkgkgkggk",
        "kccffddffddffddffddcckgggkgkgggk",
        "kccffffffffffffffffcckkgggggggk.",
        "kccffffffffffffffffcck.kkkkkkk..",
        "kcccccccccccccccccccck..........",
        "kcccccccccccccccccccck..........",
        ".kkkkkkkkkkkkkkkkkkkk...........",
    ],
)

# Two leg positions. The front pair leads on one frame and trails on the other,
# which reads as a gallop at four frames a second and as nothing at all if only
# one of them ever ships.
LEGS = [
    (
        7,
        18,
        [
            ".kkk.......kkk......",
            "kgggk.kkk.kgggk.kkk.",
            "kgggkkgggkkgggkkgggk",
            "kgggkkgggkkgggkkgggk",
            ".kkk.kgggk.kkk.kgggk",
            "......kkk.......kkk.",
        ],
    ),
    (
        7,
        18,
        [
            "......kkk.......kkk.",
            ".kkk.kgggk.kkk.kgggk",
            "kgggkkgggkkgggkkgggk",
            "kgggkkgggkkgggkkgggk",
            "kgggk.kkk.kgggk.kkk.",
            ".kkk.......kkk......",
        ],
    ),
]

# Three tail positions: up, level, down. Cycled in order, so the tail sweeps
# rather than flicking between extremes.
TAILS = [
    (
        0,
        7,
        [
            "kk......",
            "ggkkk...",
            "gggggk..",
            "kkgggkk.",
            ".kgggggk",
            "..kkgggk",
            "...kgggk",
            "....kkk.",
        ],
    ),
    (
        0,
        12,
        [
            "kkkkkkk.",
            "gggggggk",
            "gggggggk",
            "kkgggggk",
            "..kkkkk.",
        ],
    ),
    (
        0,
        13,
        [
            "....kkk.",
            "...kgggk",
            "..kkgggk",
            "kkgggggk",
            "gggggkk.",
            "gggggk..",
            "kkkkk...",
        ],
    ),
]

LAYERS = [("", BODY)] + [(f"l{i}", m) for i, m in enumerate(LEGS)] + [(f"t{i}", m) for i, m in enumerate(TAILS)]

ORDER = list(PALETTE)
RANK = {char: i for i, char in enumerate(ORDER)}


def rectangles(rows: list[str], colour: str) -> list[tuple[int, int, int, int]]:
    """Greedy decomposition of one colour into (x, y, w, h) rectangles.

    Widest run first, then grown downward for as long as every row below
    matches. Not optimal -- optimal rectangle cover is expensive and these are
    tiny pictures -- but it turns ~500 pixels into ~40 rectangles.

    The occlusion is what makes it cheap rather than merely small. A rectangle
    may swallow pixels of any colour painted *later*, because that colour paints
    over them again; only transparent pixels and colours already laid down are
    barriers. So the tart's outline is one filled block with the crust dropped on
    top, not a 26-piece ring traced around it, and the head's outline is a block
    under the fur. `compile_svg` relies on PALETTE's order to make this hold, and
    `test_nyan_sprite.py` replays the paint to prove it is lossless.
    """
    h, w = len(rows), len(rows[0])
    rank = RANK[colour]

    def free(char: str) -> bool:
        return char != "." and RANK[char] >= rank

    used = [[False] * w for _ in range(h)]
    out: list[tuple[int, int, int, int]] = []
    for y in range(h):
        for x in range(w):
            if rows[y][x] != colour or used[y][x]:
                continue
            rw = 1
            while x + rw < w and free(rows[y][x + rw]) and not used[y][x + rw]:
                rw += 1
            rh = 1
            while y + rh < h and all(free(rows[y + rh][x + i]) and not used[y + rh][x + i] for i in range(rw)):
                rh += 1
            # Only this colour's own pixels are spent; the swallowed ones still
            # need their own rectangle when their turn comes.
            for j in range(rh):
                for i in range(rw):
                    if rows[y + j][x + i] == colour:
                        used[y + j][x + i] = True
            out.append((x, y, rw, rh))
    return out


def path_data(rects: list[tuple[int, int, int, int]], ox: int, oy: int) -> str:
    """Rectangles as one `d`, each subpath placed relative to the last.

    'z' returns the point to the subpath's start, so every hop is a delta from
    the previous rectangle's corner -- shorter than absolute coordinates, and
    shorter again when the delta is negative, because the minus sign doubles as
    the separator.
    """
    out = ""
    px = py = None
    for x, y, w, h in rects:
        cx, cy = x + ox, y + oy
        if px is None:
            out += f"M{cx} {cy}"
        else:
            dy = str(cy - py)
            out += f"m{cx - px}{'' if dy.startswith('-') else ' '}{dy}"
        out += f"h{w}v{h}h-{w}z"
        px, py = cx, cy
    return out


def paths(layer: tuple[int, int, list[str]]) -> str:
    """One <path> per colour present, in paint order, origin folded in."""
    ox, oy, rows = layer
    out = ""
    for char, hex_colour in PALETTE.items():
        rects = rectangles(rows, char)
        if not rects:
            continue
        out += f'<path fill="{hex_colour}" d="{path_data(rects, ox, oy)}"/>'
    return out


def compile_svg() -> str:
    """The artwork as it appears in the shell.

    Inline markup, not a data: URI. The legs and tail are animated by the page's
    own stylesheet, and CSS cannot reach inside a url() -- an SVG behind one is
    an isolated document. Inline it is also cheaper: no '%23' escaping, and the
    HTML parser supplies the SVG namespace, so no xmlns.
    """
    body = "".join(f'<g class="{cls}">{paths(m)}</g>' if cls else paths(m) for cls, m in LAYERS)
    return f'<svg class="ny" viewBox="0 0 {WIDTH} {HEIGHT}" shape-rendering="crispEdges">{body}</svg>'


if __name__ == "__main__":
    import sys

    svg = compile_svg()
    print(svg)
    print(f"\n{len(svg)} B", file=sys.stderr)
