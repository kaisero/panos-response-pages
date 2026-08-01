"""A theme may pin its own palette. This is who wins when the sources disagree.

Order, first hit wins: --palette, then the customer's own config file, then the
theme's pin, then the shipped default.

The subtle rung is the customer file. `_defaults.json` ships a `palette`, and
`load_config` merges the customer document over it -- so the merged config always
carries one. Read naively, "config outranks the pin" means the pin never fires
and a style that owns its colour silently renders in someone else's. That is the
regression `customer_keys()` exists to prevent, and the fourth test here is the
one that would catch it coming back.
"""

import json
import pathlib
import shutil
import tempfile
import unittest

from _paths import DATA
from panos_response_pages.builder import build_all, format_report

# Any theme will do -- pinning is a property of the mechanism, not of nyan.
PINNED = "glass"


def data_dir(pin: str | None = "nyan", customer_palette: str | None = None) -> pathlib.Path:
    """A copy of the shipped data with a pin, and optionally a customer file."""
    root = pathlib.Path(tempfile.mkdtemp(prefix="panos-rp-pin-")) / "data"
    shutil.copytree(DATA, root)
    theme = root / "themes" / f"{PINNED}.json"
    doc = json.loads(theme.read_text(encoding="utf-8"))
    if pin:
        doc["palette"] = pin
    theme.write_text(json.dumps(doc), encoding="utf-8")
    if customer_palette:
        (root / "config" / "acme.json").write_text(json.dumps({"palette": customer_palette}), encoding="utf-8")
    return root


def palettes_used(root: pathlib.Path, **kwargs) -> dict[str, set[str]]:
    out = pathlib.Path(tempfile.mkdtemp(prefix="panos-rp-pin-out-"))
    result = build_all(root, out, preview=False, write=False, **kwargs)
    used: dict[str, set[str]] = {}
    for r in result.results:
        used.setdefault(r.theme, set()).add(r.palette)
    return used


class TestPalettePinning(unittest.TestCase):
    def test_a_pin_decides_when_nothing_else_speaks(self):
        used = palettes_used(data_dir())
        self.assertEqual(used[PINNED], {"nyan"}, "the theme's pin was ignored")

    def test_other_themes_are_untouched_by_one_theme_s_pin(self):
        used = palettes_used(data_dir())
        others = {name: p for name, p in used.items() if name != PINNED}
        self.assertTrue(others, "fixture built only one theme")
        for name, p in others.items():
            self.assertEqual(p, {"cyber-orange"}, f"{name} followed another theme's pin")

    def test_the_customer_s_own_config_outranks_the_pin(self):
        used = palettes_used(data_dir(customer_palette="prisma-blue"), customer="acme")
        self.assertEqual(used[PINNED], {"prisma-blue"}, "a customer's own choice must win")

    def test_the_shipped_default_does_not_outrank_the_pin(self):
        """_defaults.json sets a palette on every build. If that counted as a
        choice, the pin could never fire -- which is the whole failure mode."""
        used = palettes_used(data_dir())
        self.assertNotEqual(
            used[PINNED],
            {"cyber-orange"},
            "the default palette outranked the pin; only a customer's own file may",
        )

    def test_an_explicit_palette_outranks_everything(self):
        used = palettes_used(data_dir(customer_palette="prisma-blue"), customer="acme", palette_name="strata-yellow")
        for name, p in used.items():
            self.assertEqual(p, {"strata-yellow"}, f"{name} ignored --palette")

    def test_the_report_names_a_palette_the_build_did_not_select(self):
        out = pathlib.Path(tempfile.mkdtemp(prefix="panos-rp-pin-out-"))
        report = format_report(build_all(data_dir(), out, preview=False, write=False))
        self.assertIn(
            f"{PINNED} renders in its own palette: nyan",
            report,
            "a theme wearing a colour nobody selected must say so",
        )

    def test_no_pin_means_the_build_palette(self):
        used = palettes_used(data_dir(pin=None))
        for name, p in used.items():
            self.assertEqual(p, {"cyber-orange"}, f"{name} drifted off the build palette")


if __name__ == "__main__":
    unittest.main()
