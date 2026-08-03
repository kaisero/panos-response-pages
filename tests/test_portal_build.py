"""Wiring the portal family into the build without disturbing the block pages.

Two families now come out of one `build`. The risks are all at the seam: a
portal import counted as a block page, a portal file swept up by a glob written
for block pages, a portal size reported against a limit it is not subject to,
or spliced preview bytes landing somewhere the import guards will walk.
"""

import pathlib
import tempfile
import unittest

import pytest

from _build import DEFAULT_PALETTE, built, deploy_dir, preview_dir
from _paths import DATA
from panos_response_pages import palettes
from panos_response_pages.builder import PORTAL_PAGES, PORTAL_PREVIEWS, build_all, format_report, load_themes
from panos_response_pages.portal.validate import MAX_ENCODED, SOFT_MAX
from panos_response_pages.validate import MAX_BYTES, PAGE_TOKENS

pytestmark = pytest.mark.integration

THEMES = [t["name"] for t in load_themes(DATA)]
PALETTES = palettes.available(DATA / "palettes")


class TestDeployLayout(unittest.TestCase):
    def test_every_theme_gets_both_imports_in_a_portal_subdirectory(self):
        for theme in THEMES:
            for page in PORTAL_PAGES:
                with self.subTest(theme=theme, page=page):
                    self.assertTrue((deploy_dir() / theme / DEFAULT_PALETTE / "portal" / f"{page}.html").is_file())

    def test_the_block_page_glob_still_sees_only_block_pages(self):
        """Three existing tests glob `deploy/*/ *.html` or list the theme
        directory. Flattening these to `portal-login.html` would put a second
        family inside both, and their failure would look like a block-page bug.
        """
        for theme in THEMES:
            found = sorted(p.stem for p in (deploy_dir() / theme / DEFAULT_PALETTE).glob("*.html"))
            with self.subTest(theme=theme):
                self.assertEqual(found, sorted(PAGE_TOKENS))


class TestResultsStayInTheirOwnFamily(unittest.TestCase):
    def test_portal_pages_are_not_in_results(self):
        result = built()[1]
        self.assertEqual(len(result.results), len(THEMES) * len(PALETTES) * len(PAGE_TOKENS))
        self.assertNotIn("login", {r.page for r in result.results})

    def test_portal_results_carry_both_lengths(self):
        result = built()[1]
        self.assertEqual(len(result.portal_results), len(THEMES) * len(PALETTES) * len(PORTAL_PAGES))
        for r in result.portal_results:
            with self.subTest(theme=r.theme, page=r.page):
                # base64 is 4/3 plus line breaks, so the encoded form is always
                # the larger number -- and the only one PAN-OS ever quotes.
                self.assertGreater(r.encoded, r.size)
                self.assertLessEqual(r.encoded, MAX_ENCODED)
                self.assertEqual(r.status, "ok")

    def test_a_failing_portal_import_fails_the_build(self):
        """`failed` gates the CLI's exit code. A portal error that did not
        reach it would exit 0 with the error printed above the summary."""
        result = built()[1]
        self.assertFalse(result.failed)
        result.portal_results[0].errors.append("invented")
        try:
            self.assertTrue(result.failed)
        finally:
            result.portal_results[0].errors.clear()


class TestReport(unittest.TestCase):
    def setUp(self):
        self.report = format_report(built()[1])

    def test_the_portal_table_quotes_the_portal_ceiling(self):
        self.assertIn(f"import ceiling {SOFT_MAX} B ({MAX_ENCODED} encoded)", self.report)

    def test_the_portal_table_shows_the_encoded_length(self):
        """The number PAN-OS says out loud when it refuses an import.

        The table is collapsed to one row per theme x palette -- the same shape
        as the block-page table -- so only the largest of the two imports for
        each combination gets a row; that is the one whose encoded length must
        appear.
        """
        self.assertIn("encoded", self.report)
        worst: dict[tuple[str, str], int] = {}
        sizes: dict[tuple[str, str], int] = {}
        for r in built()[1].portal_results:
            key = (r.theme, r.palette)
            if key not in sizes or r.size > sizes[key]:
                sizes[key] = r.size
                worst[key] = r.encoded
        for (theme, palette), encoded in worst.items():
            with self.subTest(theme=theme, palette=palette):
                self.assertIn(str(encoded), self.report)

    def test_the_two_ceilings_are_never_conflated(self):
        """MAX_BYTES is a serving-time limit for block pages. Reporting a
        portal import against it would read as 40% of a limit that does not
        apply, and would hide the one that does."""
        block, portal = self.report.split("portal import")
        self.assertIn(f"ceiling {MAX_BYTES} B", block)
        self.assertNotIn(str(MAX_BYTES), portal)

    def test_a_build_with_no_portal_results_omits_the_table(self):
        result = build_all(DATA, pathlib.Path(tempfile.mkdtemp()), theme="glass", preview=False, write=False)
        result.portal_results.clear()
        self.assertNotIn("portal import", format_report(result))


class TestPreview(unittest.TestCase):
    def test_every_theme_gets_all_six_spliced_surfaces(self):
        for theme in THEMES:
            found = sorted(p.stem for p in (preview_dir() / theme / DEFAULT_PALETTE / "portal").glob("*.html"))
            with self.subTest(theme=theme):
                self.assertEqual(found, sorted(PORTAL_PREVIEWS))

    def test_the_captured_asset_tree_is_written_where_the_prefixes_look_for_it(self):
        """Without jQuery the prefixes' ready handler never runs, and the login
        import ships its <img> with no src by design -- so a missing asset tree
        is an empty logo box in every preview, and it looks like the page's
        fault rather than the preview's."""
        self.assertTrue((preview_dir() / "portal" / "js" / "jquery.min.js").is_file())

    def test_the_previews_reach_the_tree_from_where_they_sit(self):
        page = (preview_dir() / "glass" / DEFAULT_PALETTE / "portal" / "login-default.html").read_text(encoding="utf-8")
        self.assertIn('src="../../../portal/js/jquery.min.js"', page)
        target = preview_dir() / "glass" / DEFAULT_PALETTE / "portal" / "../../../portal/js/jquery.min.js"
        self.assertTrue(target.resolve().is_file(), "the relative path does not resolve to the asset tree")

    def test_the_gallery_reaches_it_from_where_it_sits(self):
        """srcdoc frames resolve relative URLs against the gallery document,
        so the gallery's copy needs a different prefix from the files'."""
        gallery = (preview_dir() / "index.html").read_text(encoding="utf-8")
        self.assertIn('src=\\"portal/js/jquery.min.js\\"', gallery)
        self.assertTrue((preview_dir() / "portal" / "js" / "jquery.min.js").is_file())

    def test_the_gallery_offers_the_surfaces_and_the_login_states(self):
        gallery = (preview_dir() / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="stategrp"', gallery)
        for surface in ("portal:login", "portal:getsoftware", "portal:logout"):
            self.assertIn(f'<option value="{surface}"', gallery)
        for state in ("default", "error", "challenge", "changepw"):
            self.assertIn(f'data-state="{state}"', gallery)

    def test_no_spliced_output_lands_anywhere_deploy_can_see_it(self):
        """The hard rule, asserted against the filesystem rather than trusted.
        Every spliced file carries PAN-OS' prefix and a captured form; one of
        them under deploy/ would be uploaded by anyone globbing that tree."""
        for path in deploy_dir().rglob("*.html"):
            with self.subTest(path=str(path.relative_to(deploy_dir()))):
                text = path.read_text(encoding="utf-8")
                # The captured form's giveaway, and the guard validate_portal
                # trips on -- so its absence is what keeps `validate` usable.
                self.assertNotIn("csrf-token", text)
                self.assertNotIn(path.stem, PORTAL_PREVIEWS, "a preview file name under deploy/")
        for path in deploy_dir().rglob("portal/*.html"):
            with self.subTest(path=str(path.relative_to(deploy_dir()))):
                text = path.read_text(encoding="utf-8")
                # PAN-OS' prefix. An import carrying it would be a document,
                # which is the first thing validate_portal rejects.
                self.assertNotIn("function loadPage()", text)
                self.assertNotIn("<!DOCTYPE", text)


if __name__ == "__main__":
    unittest.main()
