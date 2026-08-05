"""Copy rules for the page templates.

Two classes of statement are forbidden because the response page has no way to
substantiate either: claims about whether data was transmitted, and claims that a
policy applies to all users. PAN-OS exposes no variable for either fact.

This lints the *templates*. build.py:audit_copy lints the *rendered output* using
the same phrase list. Duplicating the *pass* is deliberate — it catches a
violation introduced in config/_defaults.json, which never appears in a
template. Duplicating the *phrase list* would not be: a phrase added to
BANNED_COPY would then never be linted against the templates, silently. So the
list is imported, and only the pass is written twice.
"""

import json
import re
import unittest

from _paths import DATA
from panos_response_pages.validate import BANNED_COPY

PAGES = sorted((DATA / "templates/pages").glob("*.html"))
CONFIG = DATA / "config/_defaults.json"

BANNED = BANNED_COPY

# Every page carrying a report action. safe-search is excluded: its primary
# action is "Open search settings", and IT contact is a link in the note.
REPORT_PAGES = [
    "url-block-page",
    "url-coach-text",
    "credential-block-page",
    "credential-coach-text",
]


class TestCopy(unittest.TestCase):
    # Only slot content reaches the user. A page template's leading <!-- --> block
    # is developer documentation and may legitimately discuss the banned phrases.
    SECTION_RE = re.compile(r"<!--@([A-Z_]+)-->(.*?)<!--/@\1-->", re.S)

    def _sources(self):
        out = []
        for p in PAGES:
            slots = self.SECTION_RE.findall(p.read_text(encoding="utf-8"))
            out.append((p.name, "\n".join(body for _name, body in slots)))
        out.append((CONFIG.name, CONFIG.read_text(encoding="utf-8")))
        return out

    def test_no_unsubstantiated_claims(self):
        hits = []
        for name, text in self._sources():
            low = text.lower()
            for phrase, why in BANNED:
                if phrase in low:
                    hits.append(f"{name} '{phrase}' — {why}")
        self.assertEqual(hits, [], "unsubstantiated claims:\n  " + "\n  ".join(hits))

    @unittest.expectedFailure
    def test_user_field_row(self):
        """MIGRATING (Task 4-10): copy has left the templates, so this string is
        no longer there to match. The guard moves to the built output in Task 10,
        which removes this decorator -- and unittest reports an unexpected
        success if that happens before every page has migrated."""
        for p in PAGES:
            text = p.read_text(encoding="utf-8")
            self.assertNotIn("Signed in as", text, f"{p.name} still uses 'Signed in as'")
            self.assertIn("<dt>User</dt><dd><user/></dd>", text, f"{p.name} missing the User fact row")

    @unittest.expectedFailure
    def test_report_button_wording(self):
        """MIGRATING (Task 5-10): the report label is one shared string now, so
        the template carries {{T_REPORT_LABEL}} and not the words. The guard
        moves to the built output in Task 10, which removes this decorator."""
        for p in PAGES:
            text = p.read_text(encoding="utf-8")
            for old in ("Report this block to IT", "Report this to IT Security", "Report this instead"):
                self.assertNotIn(old, text, f"{p.name} still uses '{old}'")
            if p.stem in REPORT_PAGES:
                self.assertIn(">Report to IT</a>", text, f"{p.stem} is missing its 'Report to IT' action")

    @unittest.expectedFailure
    def test_credential_block_headline(self):
        """MIGRATING (Task 5-10): the title and headline live in en.json, so the
        template slots hold placeholders. The guard moves to the built output in
        Task 10, which removes this decorator."""
        text = (DATA / "templates/pages/credential-block-page.html").read_text(encoding="utf-8")
        self.assertIn("<!--@TITLE-->Credential submission blocked<!--/@TITLE-->", text)
        self.assertIn("<!--@HEADLINE-->Credential submission blocked<!--/@HEADLINE-->", text)

    def test_continue_grant_duration_comes_from_config(self):
        """The Continue timeout is admin-configurable; hardcoding it asserts a
        fact the page cannot know."""
        cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
        self.assertIn("continueGrantText", cfg)
        for name, body in self._sources():
            if name == CONFIG.name:
                continue
            self.assertNotIn("15 minutes", body, f"{name} hardcodes the Continue grant duration")
        coach = (DATA / "templates/pages/url-coach-text.html").read_text(encoding="utf-8")
        self.assertIn("{{CONTINUE_GRANT}}", coach, "url-coach-text should render the duration from config")


if __name__ == "__main__":
    unittest.main()
