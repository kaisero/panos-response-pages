"""Data directory resolution.

Three rules, first hit wins. They are worth pinning because getting them wrong
is silent: the build succeeds against the wrong shells and nobody notices until
a customisation appears not to have taken effect.
"""

import pathlib
import shutil
import tempfile
import unittest
import unittest.mock

import pytest

from panos_response_pages import datadir

pytestmark = pytest.mark.unit


class TestResolution(unittest.TestCase):
    def setUp(self):
        self.saved = datadir.USER_DIR

    def tearDown(self):
        datadir.USER_DIR = self.saved

    def test_explicit_wins(self):
        target = pathlib.Path(tempfile.mkdtemp())
        path, reason = datadir.resolve(target)
        self.assertEqual(path, target)
        self.assertEqual(reason, "explicit")

    def test_explicit_expands_a_tilde(self):
        path, _ = datadir.resolve("~/nowhere-in-particular")
        self.assertTrue(path.is_absolute())

    def test_environment_is_used_when_no_flag_is_given(self):
        target = pathlib.Path(tempfile.mkdtemp())
        with unittest.mock.patch.dict("os.environ", {datadir.ENV_VAR: str(target)}):
            path, reason = datadir.resolve()
        self.assertEqual(path, target)
        self.assertEqual(reason, "environment")

    def test_falls_back_to_the_packaged_data(self):
        with (
            unittest.mock.patch.dict("os.environ", {}, clear=True),
            unittest.mock.patch.object(datadir, "USER_DIR", pathlib.Path("/nonexistent-xyz")),
        ):
            path, reason = datadir.resolve()
        self.assertEqual(reason, "packaged")
        self.assertEqual(path, datadir.PACKAGED)

    def test_the_packaged_data_is_complete(self):
        """A wheel missing any of these installs a tool that cannot build."""
        for sub in datadir.EXPECTED:
            self.assertTrue((datadir.PACKAGED / sub).is_dir(), f"packaged data has no {sub}/")

    def test_the_user_directory_is_preferred_over_the_package(self):
        target = pathlib.Path(tempfile.mkdtemp())
        with (
            unittest.mock.patch.dict("os.environ", {}, clear=True),
            unittest.mock.patch.object(datadir, "USER_DIR", target),
        ):
            path, reason = datadir.resolve()
        self.assertEqual(path, target)
        self.assertEqual(reason, "user")


def stale_data_dir() -> pathlib.Path:
    """A data directory as `init` produced them before the portal family existed."""
    target = pathlib.Path(tempfile.mkdtemp()) / "data"
    shutil.copytree(datadir.PACKAGED, target)
    shutil.rmtree(target / "templates" / "portal")
    shutil.rmtree(target / "fixtures")
    return target


class TestAStaleDataDirectory(unittest.TestCase):
    """resolve() takes the user tree whole, so a directory copied out before
    the portal family existed has neither of the things that family needs.

    The wrong behaviour here is refusing to build. The block pages in that
    directory are fine, and they would stop building for a family the user
    never asked for -- an upgrade breaking work that has nothing to do with it.
    """

    def test_the_portal_falls_back_to_the_packaged_data(self):
        self.assertEqual(datadir.portal_data(stale_data_dir()), datadir.PACKAGED)

    def test_a_current_data_directory_is_used_as_it_stands(self):
        fresh = pathlib.Path(tempfile.mkdtemp()) / "data"
        shutil.copytree(datadir.PACKAGED, fresh)
        self.assertEqual(datadir.portal_data(fresh), fresh)

    def test_the_fallback_says_what_is_missing_and_how_to_fix_it(self):
        """A silent fallback would be the worse bug: portal edits in the user
        directory would be ignored with nothing at all to show for it."""
        with self.assertLogs("panos_response_pages", level="WARNING") as caught:
            datadir.portal_data(stale_data_dir())
        message = "\n".join(caught.output)
        self.assertIn("templates/portal", message)
        self.assertIn("fixtures", message)
        self.assertIn("init --force", message)

    def test_both_families_still_build_from_it(self):
        from panos_response_pages import palettes
        from panos_response_pages.builder import build_all
        from panos_response_pages.validate import PAGE_TOKENS

        root = stale_data_dir()
        n_palettes = len(palettes.available(root / "palettes"))
        result = build_all(root, pathlib.Path(tempfile.mkdtemp()), theme="glass", preview=True)
        self.assertEqual(len(result.results), len(PAGE_TOKENS) * n_palettes)
        self.assertEqual(len(result.portal_results), 2 * n_palettes)
        self.assertFalse(result.failed)
