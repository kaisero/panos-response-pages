"""Copy rules for the words this project ships.

Two classes of statement are forbidden because the response page has no way to
substantiate either: claims about whether data was transmitted, and claims that a
policy applies to all users. PAN-OS exposes no variable for either fact.

This lints the *authored copy*: `data/strings/*.json`, which is where every word
a user reads now lives, plus `config/_defaults.json`, whose customer-facing
sentences never pass through a strings file. Every shipped language is linted,
not just the base one -- globbed rather than listed, so a language is covered the
day its file lands. build.py:audit_copy lints the *rendered output* using the
same phrase list. Duplicating the *pass* is deliberate: this one names the file
and runs without a build, and it reaches copy that a single-language build never
renders at all. Duplicating the *phrase list* would not be -- a phrase added to
BANNED_COPY would then never be linted here, silently. So the list is imported,
and only the pass is written twice.

The structural guards below assert on BUILT pages rather than on templates. The
templates carry {{T_*}} placeholders now, so a template is no longer a place a
sentence can be found; the built page is the first artefact where the words and
the markup are in the same file, which is what these rules are about.
"""

import functools
import json
import re
import unittest

from _build import deploy_dir
from _paths import DATA
from panos_response_pages.validate import BANNED_COPY

PAGES = sorted((DATA / "templates/pages").glob("*.html"))
CONFIG = DATA / "config/_defaults.json"
STRINGS = DATA / "strings"

BANNED = BANNED_COPY

# Every page carrying a report action. safe-search is excluded: its primary
# action is "Open search settings", and IT contact is a link in the note.
REPORT_PAGES = [
    "url-block-page",
    "url-coach-text",
    "credential-block-page",
    "credential-coach-text",
]


@functools.lru_cache(maxsize=1)
def built_pages():
    """Every built response page, as (path, html). Portal pages excluded --
    they are not response pages and carry none of this structure.

    Cached: a build is 364 files and half the assertions below walk all of
    them."""
    return tuple(
        (f, f.read_text(encoding="utf-8")) for f in sorted(deploy_dir().rglob("*.html")) if "portal" not in f.parts
    )


def page_dirs():
    """The (style, palette) directories a build produces.

    The counters below multiply by this rather than hardcoding a number: a new
    style or palette should widen the coverage, not silently invalidate a count.
    """
    return {f.parent for f, _ in built_pages()}


class TestCopy(unittest.TestCase):
    # Only slot content reaches the user. A page template's leading <!-- --> block
    # is developer documentation and may legitimately discuss the banned phrases.
    SECTION_RE = re.compile(r"<!--@([A-Z_]+)-->(.*?)<!--/@\1-->", re.S)

    def _sources(self):
        """The authored copy, by file.

        Whole files rather than extracted values: a strings document is copy
        from `{` to `}`, and slicing it to the keys this test knows about would
        stop linting the next key someone adds.
        """
        out = [(p.name, p.read_text(encoding="utf-8")) for p in sorted(STRINGS.glob("*.json"))]
        out.append((CONFIG.name, CONFIG.read_text(encoding="utf-8")))
        return out

    def _template_slots(self):
        """The page templates' slot bodies.

        Almost all copy has left these, but a template can still be given words
        directly -- and copy hardcoded here is copy no language can override.
        Kept for the rules that are about the MARKUP carrying a fact, which is
        the one thing a strings file cannot express.
        """
        out = []
        for p in PAGES:
            slots = self.SECTION_RE.findall(p.read_text(encoding="utf-8"))
            out.append((p.name, "\n".join(body for _name, body in slots)))
        return out

    def test_no_unsubstantiated_claims(self):
        hits = []
        for name, text in self._sources():
            low = text.lower()
            for phrase, why in BANNED:
                if phrase in low:
                    hits.append(f"{name} '{phrase}' — {why}")
        self.assertEqual(hits, [], "unsubstantiated claims:\n  " + "\n  ".join(hits))

    def test_every_shipped_language_is_linted(self):
        """The pass above is a loop over a glob and a list of phrases, and both
        were English-only once. Neither can say so about itself.

        The file set is walked from the DATA root rather than re-globbing the
        directory _sources() globs -- a strings document filed anywhere under
        the tree is copy that ships, and re-running the same glob would only
        prove the glob equals itself.

        The phrase list is checked for teeth on a non-English sentence. Nothing
        else here would notice the German entries being dropped from
        BANNED_COPY: the pass would still run over de.json, still find nothing,
        and still report success.
        """
        linted = {name for name, _ in self._sources()}
        shipped = {p.name for p in DATA.rglob("*.json") if p.parent.name == "strings"}
        self.assertIn("en.json", shipped, "the base language is not in the shipped tree")
        self.assertGreater(len(shipped), 1, "only one language ships; 'every language' cannot be a claim yet")
        self.assertEqual(linted, shipped | {CONFIG.name}, "a shipped document is not linted")

        # Marked for the same reason validate.py marks its own German entries:
        # an English misspelling dictionary reads these words as typos.
        german = "Ihre Eingabe wurde nicht übermittelt, und die Regel gilt für alle."  # codespell:ignore
        self.assertTrue(
            [phrase for phrase, _why in BANNED if phrase in german.lower()],
            "the phrase list has no German entry, so de.json ships copy this pass cannot fail",
        )

    def test_continue_grant_duration_comes_from_config(self):
        """The Continue timeout is admin-configurable; hardcoding it asserts a
        fact the page cannot know.

        Read out of the strings files as well as the templates: the sentence
        carrying the duration is copy now, so that is where it would be
        hardcoded -- and where the placeholder has to survive translation.

        A strings file is linted on its PAGE copy only. `shared.continueGrantText`
        is not copy about the duration, it IS the duration: the per-language
        value {{CONTINUE_GRANT}} falls back to when a customer who changed the
        setting has not translated it. That it still says what _defaults.json
        says is asserted in test_i18n.py, and this exemption depends on it."""
        cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
        self.assertIn("continueGrantText", cfg)
        strings = [(p.name, json.loads(p.read_text(encoding="utf-8"))) for p in sorted(STRINGS.glob("*.json"))]
        copy = [(name, json.dumps(doc["pages"], ensure_ascii=False)) for name, doc in strings]
        for name, body in self._template_slots() + copy:
            self.assertNotIn("15 minutes", body, f"{name} hardcodes the Continue grant duration")
        for name, doc in strings:
            # The slot is split into fragments around its <strong>, so the
            # placeholder is asserted against the reassembled sentence. "".join
            # is a no-op on the single-string shape, so this reads either.
            raw = doc["pages"]["url-coach-text"]["extra"]
            extra = "".join(raw) if isinstance(raw, list) else raw
            self.assertIn("{{CONTINUE_GRANT}}", extra, f"{name}: url-coach-text drops the configured duration")


class TestBuiltPagesIdentifyTheUser(unittest.TestCase):
    """Who was blocked is the one fact every page states.

    Asserted on the built page rather than the template because the label is
    translated now: the template carries {{T_FACTn}} and the strings file
    carries "User", and neither file on its own says that the two ended up in
    the same row. The built page is where they meet.
    """

    def test_every_built_page_carries_a_user_row(self):
        """The assertion is on the TOKEN and its row, not on the word 'User' --
        a German page says "Benutzer" and is just as correct."""
        found = 0
        for f, text in built_pages():
            found += 1
            self.assertRegex(text, r"<dt>[^<]+</dt><dd><user/></dd>", f"{f} has no user fact row")
        self.assertGreater(found, 0, "no built pages were examined")

    def test_no_page_reverted_to_the_prose_form(self):
        """`Signed in as <user/>` was the shape this replaced. It reads as a
        greeting rather than as a recorded fact, and it does not fit the fact
        table the report mail is rebuilt from."""
        for f, text in built_pages():
            self.assertNotIn("Signed in as", text, f"{f} still uses 'Signed in as'")


class TestBuiltPagesUseTheAgreedReportWording(unittest.TestCase):
    """One label, shared by every page that offers the action.

    It lives in `shared.reportLabel` now, so the retired wordings could only
    come back through a template hardcoding them -- which is exactly the failure
    this keeps watching for, and which only the built page can show.
    """

    RETIRED = ("Report this block to IT", "Report this to IT Security", "Report this instead")

    def test_report_button_wording(self):
        found = 0
        for f, text in built_pages():
            for old in self.RETIRED:
                self.assertNotIn(old, text, f"{f} still uses '{old}'")
            if f.stem in REPORT_PAGES:
                found += 1
                self.assertIn(">Report to IT</a>", text, f"{f} is missing its 'Report to IT' action")
        self.assertEqual(
            found,
            len(REPORT_PAGES) * len(page_dirs()),
            "not every build of every reporting page was examined",
        )


class TestBuiltCredentialBlockPage(unittest.TestCase):
    """The highest-stakes page in the set, pinned by its words.

    Its title and headline are the same sentence deliberately -- the tab and the
    page agree about what happened -- and the two used to drift apart. Asserted
    against en.json AND the built page: the strings file is where the wording is
    authored, the built page is proof it reached the markup.
    """

    HEADLINE = "Credential submission blocked"

    def test_credential_block_headline(self):
        doc = json.loads((STRINGS / "en.json").read_text(encoding="utf-8"))
        page = doc["pages"]["credential-block-page"]
        self.assertEqual(page["title"], self.HEADLINE)
        self.assertEqual(page["headline"], self.HEADLINE)
        found = 0
        for f, text in built_pages():
            if f.stem != "credential-block-page":
                continue
            found += 1
            self.assertIn(f"<title>{self.HEADLINE}</title>", text, f"{f} lost its title")
            self.assertIn(f"<h1>{self.HEADLINE}</h1>", text, f"{f} lost its headline")
        self.assertEqual(found, len(page_dirs()), "not every build of credential-block-page was examined")


if __name__ == "__main__":
    unittest.main()
