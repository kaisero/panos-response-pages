"""Multi-language builds, and the promise that single-language builds are free.

The byte-identity assertion is the load-bearing one. `languages: ["en"]` must
produce exactly the bytes a build produced before this feature existed -- that
is what makes multi-language support cost nothing for every customer who does
not want it, and asserting it is how it stays true.

If this test fails, the change that broke it is wrong. Do NOT regenerate the
snapshot to make it pass.
"""

import hashlib
import json
import pathlib
import shutil
import tempfile
import unittest

import pytest

from _build import built
from _paths import DATA, ROOT
from panos_response_pages.builder import build_all
from panos_response_pages.errors import BuildError

pytestmark = pytest.mark.integration

SNAPSHOT = json.loads((ROOT / "tests/fixtures/byte-identity.json").read_text(encoding="utf-8"))


def broken_data_dir(strings=None, **over) -> pathlib.Path:
    """A copy of the shipped data directory, with `_defaults.json` overridden.

    A copy, never DATA itself: that tree is the installed package every other
    test builds from, and `_build.built()` caches one build of it for the whole
    run -- editing it in place would decide the outcome of tests that have
    nothing to do with languages.

    `strings` writes extra strings/<lang>.json documents, which is the only way
    to reach check_complete: it compares a language against the base language,
    so a language with no file at all fails the earlier existence rule instead.
    """
    root = pathlib.Path(tempfile.mkdtemp(prefix="panos-rp-i18n-")) / "data"
    shutil.copytree(DATA, root)
    path = root / "config" / "_defaults.json"
    cfg = json.loads(path.read_text(encoding="utf-8"))
    cfg.update(over)
    path.write_text(json.dumps(cfg), encoding="utf-8")
    for lang, doc in (strings or {}).items():
        (root / "strings" / f"{lang}.json").write_text(json.dumps(doc), encoding="utf-8")
    return root


def build(root: pathlib.Path) -> None:
    """Build `root` for its verdict only -- nothing is written and nothing kept."""
    build_all(root, root / "out", preview=False, write=False)


class TestABuildRunsTheLanguageValidators(unittest.TestCase):
    """Every rule i18n.check and i18n.check_complete enforce, exercised through
    a build.

    Deliberately through build_all rather than by calling the validator: that
    the validators work is already pinned by tests/test_i18n.py, and every one
    of these configurations passed the whole suite anyway -- because nothing in
    the build ever called them. What is under test here is the CALL SITE. A test
    that called check() directly would pass against the bug it exists to catch.
    """

    def test_a_base_language_outside_languages_fails_the_build(self):
        """The reported symptom: this used to fail incidentally, deep inside
        i18n.load(), with a bare `missing strings file:` and no mention of the
        key that was actually wrong."""
        with pytest.raises(BuildError) as err:
            build(broken_data_dir(baseLanguage="qq", languages=["en", "zz"]))
        message = str(err.value)
        assert "baseLanguage" in message
        assert "qq" in message

    def test_a_configured_language_with_no_strings_file_fails_the_build(self):
        with pytest.raises(BuildError) as err:
            build(broken_data_dir(baseLanguage="en", languages=["en", "zz"]))
        assert "zz.json" in str(err.value)

    def test_a_language_key_that_is_not_two_letters_fails_the_build(self):
        with pytest.raises(BuildError) as err:
            build(broken_data_dir(baseLanguage="en", languages=["en", "de-AT"]))
        assert "de-AT" in str(err.value)

    def test_an_empty_language_list_fails_the_build(self):
        with pytest.raises(BuildError) as err:
            build(broken_data_dir(baseLanguage="en", languages=[]))
        assert "languages" in str(err.value)

    def test_a_translations_block_for_an_unconfigured_language_fails_the_build(self):
        with pytest.raises(BuildError) as err:
            build(broken_data_dir(baseLanguage="en", languages=["en"], translations={"fr": {"defaultGloss": "x"}}))
        message = str(err.value)
        assert "fr" in message
        assert "translations" in message

    def test_a_language_missing_keys_fails_the_build(self):
        """Spec Decision 7 -- "a missing key is a build error" -- was simply not
        true of a build until the validator had a call site."""
        with pytest.raises(BuildError) as err:
            build(broken_data_dir(strings={"de": {"shared": {"reportLabel": "Melden"}}}, languages=["en", "de"]))
        message = str(err.value)
        assert "de.json" in message
        assert "missing" in message

    def test_a_language_with_an_unknown_key_fails_the_build(self):
        """The other half of `exactly`: an extra key is a typo or a stale entry,
        and either way it is a string no page will ever show."""
        doc = json.loads((DATA / "strings" / "en.json").read_text(encoding="utf-8"))
        doc["shared"]["nosuchkey"] = "x"
        with pytest.raises(BuildError) as err:
            build(broken_data_dir(strings={"de": doc}, languages=["en", "de"]))
        message = str(err.value)
        assert "de.json" in message
        assert "shared.nosuchkey" in message


class TestSingleLanguageIsFree(unittest.TestCase):
    def test_english_only_build_is_byte_identical(self):
        out, _result = built()
        checked = 0
        for key, want in SNAPSHOT.items():
            f = pathlib.Path(out) / "deploy" / key
            self.assertTrue(f.is_file(), f"{key} is missing from the build")
            got = hashlib.sha256(f.read_bytes()).hexdigest()
            self.assertEqual(got, want, f"{key} changed; single-language output must stay byte-identical")
            checked += 1
        self.assertEqual(checked, len(SNAPSHOT))

    def test_built_file_set_matches_snapshot_exactly(self):
        out, _result = built()
        deploy_dir = pathlib.Path(out) / "deploy"

        # Walk deploy dir and collect all .html files as snapshot-style keys
        built_files = set()
        for html_file in deploy_dir.rglob("*.html"):
            # Get relative path from deploy_dir and convert to posix-style key
            rel_path = html_file.relative_to(deploy_dir)
            key = rel_path.as_posix()
            built_files.add(key)

        snapshot_files = set(SNAPSHOT.keys())

        # Check for extras and missing
        extras = built_files - snapshot_files
        missing = snapshot_files - built_files

        if extras or missing:
            msg_parts = []
            if extras:
                msg_parts.append(f"Extra files in build: {sorted(extras)}")
            if missing:
                msg_parts.append(f"Missing files from build: {sorted(missing)}")
            self.fail("; ".join(msg_parts))

        self.assertEqual(built_files, snapshot_files)
