"""The docs are where the deployment gotchas are written down.

Every fact asserted here is one that cost someone real time to discover and that
nothing in the code can enforce. The README used to hold all of it; it now holds
the entry points and the docs site holds the rest, so both get checked.
"""

import re
import unittest

import pytest
import yaml

from _paths import DATA, ROOT

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

    def test_leads_with_the_live_preview(self):
        """What this project produces is pages. A visitor should be able to look
        at them before reading anything, from GitHub as well as from the site --
        and GitHub renders neither iframes nor relative site links, so the README
        needs the committed screenshot and an absolute URL."""
        self.assertIn("kaisero.github.io/panos-response-pages/preview/", README)
        self.assertIn("docs/assets/preview-beacon.png", README)


class TestPreviewIsPublished(unittest.TestCase):
    """The gallery ships with the docs site, generated at build time.

    Every assertion here guards a way this quietly stops working: a link that
    points nowhere, a screenshot that was never committed, or a generated tree
    that gets committed once and then shows visitors pages the templates no
    longer produce.
    """

    def test_the_home_page_embeds_and_links_it(self):
        text = page("index.md")
        self.assertIn("preview/index.html", text, "index.md does not link the preview")
        self.assertIn('id="rp-embed"', text, "index.md has no inline preview")
        for control in ('id="rp-page"', 'id="rp-scheme"', 'id="rp-frame"'):
            self.assertIn(control, text, f"inline preview is missing {control}")

    def test_the_embed_defaults_to_dark(self):
        """The pages support both schemes and the dark one is the less obvious
        of the two, so it is what a first-time reader is shown."""
        self.assertRegex(page("index.md"), r'id="rp-scheme"[^>]*\bchecked\b')
        # The word beside the switch is generated from :checked rather than
        # written by script, so it cannot come back disagreeing with the control
        # after a navigation restores the two independently.
        css = (DOCS / "assets" / "preview-embed.css").read_text(encoding="utf-8")
        self.assertIn("input:checked ~ .rp-switch-label::after", css)
        self.assertIn('content: "Dark"', css)

    def test_the_embed_script_is_not_inline(self):
        """navigation.instant swaps content in over XHR without re-executing
        inline <script>. Inline, the embed works on a hard load and is dead for
        anyone who arrives from another page in the site."""
        self.assertNotIn("<script", page("index.md"))
        config = yaml.safe_load((ROOT / "mkdocs.yml").read_text(encoding="utf-8"))
        self.assertIn("assets/preview-embed.js", config["extra_javascript"])
        self.assertIn("assets/preview-embed.css", config["extra_css"])
        self.assertIn("document$", (DOCS / "assets" / "preview-embed.js").read_text(encoding="utf-8"))

    def test_the_embed_offers_every_page(self):
        """The dropdown is a hand-written list in the embed script. A page added
        to the templates and not to that list is invisible on the home page, and
        nothing else would catch it."""
        js = (DOCS / "assets" / "preview-embed.js").read_text(encoding="utf-8")
        listed = set(re.findall(r'"([a-z0-9-]+(?:-page|-text))"', js))
        built = {p.stem for p in (ROOT / "src/panos_response_pages/data/templates/pages").glob("*.html")}
        self.assertEqual(built - listed, set(), "page template(s) missing from the home-page dropdown")
        self.assertEqual(listed - built, set(), "dropdown offers page(s) that no longer exist")

    def test_the_preview_links_open_outside_the_docs_shell(self):
        """navigation.instant swaps same-origin responses into the current page.
        The gallery is its own document with its own script; without a target it
        would be torn out of its shell and rendered as a docs page."""
        # Only real links -- the page also names out/preview/index.html in prose,
        # which is a path, not something anyone can click.
        links = re.findall(r"\]\(preview/index\.html\)(\{[^}]*\})?", page("index.md"))
        self.assertTrue(links, "no link to the preview in index.md")
        for attrs in links:
            self.assertIn('target="_blank"', attrs or "", "preview link is not opted out of instant loading")
        config = yaml.safe_load((ROOT / "mkdocs.yml").read_text(encoding="utf-8"))
        self.assertIn("attr_list", config["markdown_extensions"], "attr_list is what carries the target")

    def test_the_example_screenshot_is_committed(self):
        """Generated at build time it would be missing from GitHub, which never
        runs the build."""
        shot = DOCS / "assets" / "preview-beacon.png"
        self.assertTrue(shot.is_file(), "docs/assets/preview-beacon.png is missing")
        self.assertGreater(shot.stat().st_size, 10_000, "screenshot looks truncated")

    def test_the_gallery_itself_is_generated_not_committed(self):
        """The opposite rule to the screenshot, for the opposite reason: this one
        CAN be built by CI, so committing it only creates a copy that rots."""
        noxfile = (ROOT / "noxfile.py").read_text(encoding="utf-8")
        self.assertIn('PREVIEW_DEST = pathlib.Path("docs/preview")', noxfile)
        self.assertIn("_build_preview(session)", noxfile, "the docs session does not build the gallery")
        self.assertIn("docs/preview/", (ROOT / ".gitignore").read_text(encoding="utf-8"))

    def test_the_generated_gallery_is_excluded_from_codespell(self):
        """Two exclusions are needed, not one. codespell runs with
        pass_filenames: false, so it walks the working tree and gitignore does
        not reach it -- and the tree carries the captured minified jQuery, whose
        variable names read as typos. Without this, every commit made after a
        docs build fails on a directory nobody edited."""
        config = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        skip = re.search(r'^skip = "([^"]+)"', config, re.M)
        self.assertIsNotNone(skip, "codespell has no skip list")
        self.assertIn("./docs/preview", skip.group(1).split(","))


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

    def test_documents_the_override_timeout_key(self):
        """`continueGrantText` names a duration the page cannot check.

        The wording has to match the URL Admin Override timeout configured on the
        firewall, and nothing in the build knows what that is -- so the page can
        promise sixty minutes against a fifteen-minute policy and look correct.
        The docs are the only place that can say so.

        This assertion used to sit alongside one that `copy-rules.md` cited
        `BANNED_COPY`. That page has been removed; `styles.md` still mentions the
        constant in passing, but pointing this test at that mention would assert
        an aside while reading like it still guards the rules.
        """
        self.assertIn("continueGrantText", page("customising.md"))

    def test_documents_the_shell_contract(self):
        """A new shell that omits any of these builds clean and ships broken."""
        text = page("styles.md")
        for needle in ("{{SCRIPTS}}", "<dl>", 'id="gloss"', "data-force-scheme"):
            self.assertIn(needle, text, f"styles.md missing contract item: {needle}")

    def test_the_styles_table_lists_every_style(self):
        """Nothing else notices an undocumented style.

        The build discovers themes by glob, so a new one ships whether or not
        anyone writes it down -- and the counts in this file are prose, which
        goes stale silently. This is the one place that fails when it does.
        """
        # The first section only: later tables in this page list other things,
        # and a style is documented by appearing in the one at the top.
        intro = page("styles.md").split("\n## ")[0]
        listed = set(re.findall(r"^\| `([a-z0-9-]+)` \|", intro, re.M))
        shipped = {p.stem for p in (DATA / "themes").glob("*.json")}
        self.assertEqual(shipped - listed, set(), "style(s) shipped but not in the styles.md table")
        self.assertEqual(listed - shipped, set(), "styles.md lists style(s) that no longer exist")

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
