"""The docs are where the deployment gotchas are written down.

Every fact asserted here is one that cost someone real time to discover and that
nothing in the code can enforce. The README used to hold all of it; it now holds
the entry points and the docs site holds the rest, so both get checked.
"""

import unittest

import pytest
import yaml

from _paths import ROOT

pytestmark = pytest.mark.unit

DOCS = ROOT / "docs"
README = (ROOT / "README.md").read_text(encoding="utf-8")


def page(name: str) -> str:
    return (DOCS / name).read_text(encoding="utf-8")


class TestReadme(unittest.TestCase):
    def test_shows_how_to_install_and_run(self):
        for needle in ("uv tool install", "panos-response-pages build", "out/deploy"):
            self.assertIn(needle, README, f"README missing: {needle}")

    def test_links_to_the_docs_site(self):
        self.assertIn("kaisero.github.io/panos-response-pages", README)

    def test_makes_no_stale_dependency_claim(self):
        """The project was stdlib-only and is not any more. The README must not
        still say so, and must not describe a build.py that no longer exists."""
        self.assertNotIn("standard library only", README)
        self.assertNotIn("python3 build.py", README)


class TestDocsSite(unittest.TestCase):
    def test_every_nav_entry_exists(self):
        nav = yaml.safe_load((ROOT / "mkdocs.yml").read_text(encoding="utf-8"))["nav"]
        for entry in nav:
            target = next(iter(entry.values()))
            self.assertTrue((DOCS / target).is_file(), f"nav points at missing page: {target}")

    def test_every_page_is_reachable_from_the_nav(self):
        """An unreferenced page builds fine and is invisible."""
        nav = yaml.safe_load((ROOT / "mkdocs.yml").read_text(encoding="utf-8"))["nav"]
        listed = {next(iter(e.values())) for e in nav}
        actual = {p.name for p in DOCS.glob("*.md")}
        self.assertEqual(actual - listed, set(), "page(s) not in the nav")

    def test_documents_the_copy_rules_and_their_source(self):
        text = page("copy-rules.md")
        self.assertIn("BANNED_COPY", text)
        self.assertIn("continueGrantText", page("customising.md"))

    def test_documents_the_shell_contract(self):
        """A new shell that omits any of these builds clean and ships broken."""
        text = page("styles.md")
        for needle in ("{{SCRIPTS}}", "<dl>", 'id="gloss"', "data-force-scheme"):
            self.assertIn(needle, text, f"styles.md missing contract item: {needle}")

    def test_documents_the_data_directory_resolution_order(self):
        text = page("index.md")
        self.assertIn("--config-dir", text)
        self.assertIn("~/.panos_response_pages", text)

    def test_cli_reference_covers_every_command(self):
        from panos_response_pages.cli import app

        text = page("cli.md")
        names = {c.name or c.callback.__name__ for c in app.registered_commands}
        for name in names:
            self.assertIn(name, text, f"cli.md does not mention the {name!r} command")
