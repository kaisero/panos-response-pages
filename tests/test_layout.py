"""Project layout invariants.

Only tracked paths are asserted here. The docs/prototype move is gitignored, so
asserting on it would make `git clone && test` fail forever.
"""

import json
import unittest

from _paths import DATA, ROOT


class TestLayout(unittest.TestCase):
    def test_no_prototype_html_in_project_root(self):
        stray = sorted(p.name for p in ROOT.glob("*.html"))
        self.assertEqual(stray, [], f"prototype HTML left in root: {stray}")

    def test_themes_and_shells_are_in_step(self):
        """A style is a shell plus a theme, and build.py discovers each by its own
        glob. A theme with no shell dies at build time; a shell with no theme is
        never built at all, which is the quiet half of the failure."""
        themes = sorted(p.stem for p in (DATA / "themes").glob("*.json"))
        shells = sorted(p.stem for p in (DATA / "templates/shells").glob("*.html"))
        self.assertEqual(themes, shells, "every shell needs a theme and every theme needs a shell")

    def test_every_theme_names_a_shell_that_exists(self):
        """A theme may point at another theme's shell in principle, so the name
        match above is not enough on its own."""
        for path in sorted((DATA / "themes").glob("*.json")):
            theme = json.loads(path.read_text(encoding="utf-8"))
            for key in ("name", "label", "shell"):
                self.assertIn(key, theme, f"{path.name} has no {key}")
            self.assertEqual(theme["name"], path.stem, f"{path.name} declares a different name")
            self.assertTrue(
                (DATA / "templates/shells" / f"{theme['shell']}.html").exists(),
                f"{path.name} names a shell that does not exist",
            )

    def test_a_template_exists_for_every_registered_page_type(self):
        """PAGE_TOKENS in build.py is the single source of truth for which page
        types this project handles; templates must track it exactly."""
        from panos_response_pages.validate import PAGE_TOKENS

        pages = sorted(p.stem for p in (DATA / "templates/pages").glob("*.html"))
        self.assertEqual(pages, sorted(PAGE_TOKENS), "templates and PAGE_TOKENS disagree")


if __name__ == "__main__":
    unittest.main()
