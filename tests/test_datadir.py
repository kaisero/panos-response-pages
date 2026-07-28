"""Data directory resolution.

Three rules, first hit wins. They are worth pinning because getting them wrong
is silent: the build succeeds against the wrong shells and nobody notices until
a customisation appears not to have taken effect.
"""

import pathlib
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
