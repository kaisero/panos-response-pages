"""Copy rules for the page templates.

Two classes of statement are forbidden because the response page has no way to
substantiate either: claims about whether data was transmitted, and claims that a
policy applies to all users. PAN-OS exposes no variable for either fact.

This lints the *templates*. build.py:audit_copy lints the *rendered output* using
the same phrase list. The duplication is deliberate — it catches a violation
introduced in config/_defaults.json, which never appears in a template.
"""

import json
import re
import unittest

from _paths import DATA

PAGES = sorted((DATA / "templates/pages").glob("*.html"))
CONFIG = DATA / "config/_defaults.json"

BANNED = [
    ("nothing you typed", "asserts data was not transmitted"),
    ("was not sent", "asserts data was not transmitted"),
    ("left your device", "asserts data was not transmitted"),
    ("for everyone", "asserts the policy applies to all users"),
    ("everybody", "asserts the policy applies to all users"),
    ("not just you", "asserts the policy applies to all users"),
]

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

    def test_user_field_row(self):
        for p in PAGES:
            text = p.read_text(encoding="utf-8")
            self.assertNotIn("Signed in as", text, f"{p.name} still uses 'Signed in as'")
            self.assertIn("<dt>User</dt><dd><user/></dd>", text, f"{p.name} missing the User fact row")

    def test_report_button_wording(self):
        for p in PAGES:
            text = p.read_text(encoding="utf-8")
            for old in ("Report this block to IT", "Report this to IT Security", "Report this instead"):
                self.assertNotIn(old, text, f"{p.name} still uses '{old}'")
            if p.stem in REPORT_PAGES:
                self.assertIn(">Report to IT</a>", text, f"{p.stem} is missing its 'Report to IT' action")

    def test_credential_block_headline(self):
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
