"""Every palette must be legible in both schemes.

A vivid accent is not automatically usable. White on orange #FA582D is
3.23:1 and on the yellow it is 1.56:1 -- both unreadable. So each palette
separates the vivid *fill* from the *text* and *ink* colours used with it,
and this test holds all three to 4.5:1.
"""

import colorsys
import json
import pathlib
import shutil
import tempfile
import unittest

from _paths import DATA
from panos_response_pages.errors import BuildError
from panos_response_pages.palettes import load_palette

PALETTES = sorted((DATA / "palettes").glob("*.json"))

REQUIRED = [
    "ground",
    "surface",
    "surface_alt",
    "ink",
    "ink_muted",
    "ink_faint",
    "accent",
    "accent_ink",
    "accent_text",
    "accent_wash",
    "warn",
    "warn_ink",
    "warn_text",
    "warn_wash",
    "crit",
    "crit_ink",
    "crit_text",
    "crit_wash",
]

AA_NORMAL = 4.5


def _lin(c):
    c /= 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def luminance(hex_colour):
    h = hex_colour.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def contrast(a, b):
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


class TestPalettes(unittest.TestCase):
    def test_the_shipped_palettes_exist(self):
        names = sorted(p.stem for p in PALETTES)
        for expected in ("cyber-orange", "prisma-blue", "strata-yellow", "nyan"):
            self.assertIn(expected, names)

    def test_every_palette_declares_its_kind(self):
        """Brand palettes are the customer axis: any style may wear any of them.
        A style palette belongs to one shell and is pinned by it. The guards
        below differ by kind, so it is declared rather than guessed at."""
        for path in PALETTES:
            kind = json.loads(path.read_text(encoding="utf-8")).get("kind")
            self.assertIn(kind, ("brand", "style"), f"{path.stem} declares no kind")

    def test_palettes_match_their_declared_ramps(self):
        """Each palette declares a five-stop ramp. The 500 stop is the accent
        and must appear verbatim as the accent fill."""
        expected = {
            "cyber-orange": ["#FFBF9C", "#FF724D", "#FA582D", "#B23808", "#190000"],
            "strata-yellow": ["#FFF0CC", "#FFDE73", "#FFCB06", "#D69F25", "#261B01"],
            "prisma-blue": ["#D9F8FC", "#56D6F4", "#00C0E8", "#0196B3", "#001D2B"],
            "nyan": ["#FFE4F1", "#FF8FC4", "#FF4FA3", "#C81F6F", "#2A0A1C"],
        }
        for path in PALETTES:
            d = json.loads(path.read_text(encoding="utf-8"))
            want = expected[d["name"]]
            self.assertEqual(
                [d["_ramp"][k] for k in ("0", "250", "500", "750", "1000")],
                want,
                f"{d['name']} ramp drifted from its declared stops",
            )
            self.assertEqual(d["colors"]["accent"].lower(), want[2].lower(), f"{d['name']} accent must be the 500 stop")
            self.assertEqual(d["gradient"]["from"], want[2])
            self.assertEqual(d["gradient"]["to"], want[4], "gradients run 500 -> 1000, linear only")

    def test_every_palette_defines_every_token(self):
        for path in PALETTES:
            colours = json.loads(path.read_text(encoding="utf-8"))["colors"]
            for key in REQUIRED:
                self.assertIn(key, colours, f"{path.stem} missing '{key}'")
                self.assertIn("d_" + key, colours, f"{path.stem} missing 'd_{key}'")

    def test_dark_grounds_are_tinted_not_saturated(self):
        """Regression guard. Deriving the dark ground by mixing the ramp's 1000
        stop toward black preserved its saturation -- 91-100% at 4% lightness,
        which reads brown for yellow and muddy for the rest. A dark UI ground
        wants the brand hue as a whisper.

        Scoped to brand palettes, which is who that argument is about. A style
        palette's dark ground is artwork rather than a tinted neutral -- the sky
        IS the picture -- and it is worn by the one shell built around it."""
        for path in PALETTES:
            palette = json.loads(path.read_text(encoding="utf-8"))
            if palette.get("kind") == "style":
                continue
            c = palette["colors"]
            for key in ("d_ground", "d_surface", "d_surface_alt"):
                h = c[key].lstrip("#")
                r, g, b = (int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))
                _hue, light, sat = colorsys.rgb_to_hls(r, g, b)
                self.assertLessEqual(
                    sat,
                    0.22,
                    f"{path.stem}.{key} is {sat:.0%} saturated ({c[key]}) -- too heavily tinted for a dark ground",
                )
                self.assertLess(light, 0.22, f"{path.stem}.{key} is too light for a dark ground")

    def test_every_colour_is_a_hex_triplet(self):
        for path in PALETTES:
            for key, value in json.loads(path.read_text(encoding="utf-8"))["colors"].items():
                self.assertRegex(value, r"^#[0-9a-fA-F]{6}$", f"{path.stem}.{key}")

    def test_contrast_holds_in_both_schemes(self):
        failures = []
        for path in PALETTES:
            c = json.loads(path.read_text(encoding="utf-8"))["colors"]
            for prefix, scheme in (("", "light"), ("d_", "dark")):
                g = c[prefix + "ground"]
                pairs = [
                    ("body text on ground", c[prefix + "ink"], g),
                    ("muted text on ground", c[prefix + "ink_muted"], g),
                    # dt / .plain / .note all sit on the body ground, not on a
                    # surface -- measuring against `surface` hid a real failure.
                    ("faint text on ground", c[prefix + "ink_faint"], g),
                    ("faint text on surface_alt", c[prefix + "ink_faint"], c[prefix + "surface_alt"]),
                ]
                for tone in ("accent", "warn", "crit"):
                    pairs += [
                        (f"{tone} label on {tone} fill", c[f"{prefix}{tone}_ink"], c[f"{prefix}{tone}"]),
                        (f"{tone} text on ground", c[f"{prefix}{tone}_text"], g),
                        (f"{tone} text on {tone} wash", c[f"{prefix}{tone}_text"], c[f"{prefix}{tone}_wash"]),
                    ]
                for label, fg, bg in pairs:
                    ratio = contrast(fg, bg)
                    if ratio < AA_NORMAL:
                        failures.append(f"{path.stem} [{scheme}] {label}: {fg} on {bg} = {ratio:.2f}:1")
        self.assertEqual(failures, [], "contrast failures:\n  " + "\n  ".join(failures))


class TestFilenameIsAuthoritative(unittest.TestCase):
    """build_all keys everything -- `loaded`, `blobs[(theme, stem, page)]`,
    deploy/<style>/<stem>/ -- by the palette file's stem. build_gallery keys
    everything else -- blob_map, blobs-<name>.js, data-pal, data-palette -- by
    the JSON's own `name` field. A palette whose `name` disagrees with its
    filename used to produce either a raw KeyError deep in build_gallery, or a
    build that reported `ok` while silently writing a gallery with two rows for
    the same palette and no sidecar for the new one. Both are worse than
    refusing at load time, where there is still one file to point at.

    Built in a tempfile.TemporaryDirectory() copy of the packaged data dir
    rather than in place, so a bad fixture never touches the packaged data.
    """

    def _copy(self) -> pathlib.Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        data_dir = pathlib.Path(tmp.name) / "data"
        shutil.copytree(DATA, data_dir)
        return data_dir

    def test_a_mismatched_name_is_a_build_error(self):
        data_dir = self._copy()
        palette_dir = data_dir / "palettes"
        acme = json.loads((palette_dir / "cyber-orange.json").read_text(encoding="utf-8"))
        acme["name"] = "acme-brand"
        (palette_dir / "acme.json").write_text(json.dumps(acme), encoding="utf-8")

        with self.assertRaises(BuildError) as caught:
            load_palette("acme", palette_dir)
        message = str(caught.exception)
        self.assertIn("acme-brand", message)
        self.assertIn("acme", message)

    def test_a_matching_name_still_loads(self):
        data_dir = self._copy()
        palette_dir = data_dir / "palettes"
        acme = json.loads((palette_dir / "cyber-orange.json").read_text(encoding="utf-8"))
        acme["name"] = "acme"
        (palette_dir / "acme.json").write_text(json.dumps(acme), encoding="utf-8")

        loaded = load_palette("acme", palette_dir)
        self.assertEqual(loaded["name"], "acme")


if __name__ == "__main__":
    unittest.main()
