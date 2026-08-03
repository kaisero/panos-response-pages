"""Severity signalling in the assist shell.

Scoped to assist on purpose. Every shell must render {{SEVERITY}} and must not
repaint the brand row or the primary action by tone -- that is the shared
contract, and tests/test_shells.py enforces it across all of them. How a shell
expresses severity is its own business: assist uses a pill in the brand row, and
what follows pins assist's version of it.

Nothing here may restate a rule test_shells.py already loops over every shell:
an assist-only copy can only fail after the all-shells version already has, and
it makes the rule look like it lives in two places. If a rule belongs to every
shell, it belongs there.

A critical malware block must not look identical to a shopping block. The tone is
carried by a severity pill and the primary action only -- the customer logo and
brand row stay on the fixed accent, because a customer's mark must not be
repainted by severity.

The label is set by the same script that sets data-tone. Baking it from the
static TONE slot would be wrong: url-block-page declares TONE=calm but the
category script raises it to crit at runtime, which would leave an empty
coloured pill on the page.
"""

import re
import unittest

from _build import DEFAULT_PALETTE, deploy_dir
from _paths import DATA

SHELL = (DATA / "templates/shells/assist.html").read_text(encoding="utf-8")


class TestAssistShell(unittest.TestCase):
    def test_severity_is_still_visible_somewhere(self):
        """Removing tone from the button must not make severity invisible."""
        pill = re.search(r"\.brand\s+\.sev\s*\{[^}]*\}", SHELL)
        self.assertIsNotNone(pill)
        self.assertIn("var(--tt)", pill.group(0))
        warn = re.search(r"(?m)^\.warnline\{[^}]*\}", SHELL)
        self.assertIsNotNone(warn)
        self.assertIn("var(--tt)", warn.group(0), "the warning callout's edge should carry the severity colour")

    def test_severity_pill_beats_brand_span_specificity(self):
        """.brand span is (0,1,1); a bare .sev (0,1,0) would lose the cascade."""
        self.assertRegex(SHELL, r"\.brand\s+\.sev\s*\{", "severity pill must be scoped as '.brand .sev'")

    def test_shell_declares_the_pill(self):
        self.assertIn('<span class="sev"', SHELL)


class TestSeverityAtRuntime(unittest.TestCase):
    def _page(self, name):
        return (deploy_dir() / "assist" / DEFAULT_PALETTE / f"{name}.html").read_text(encoding="utf-8")

    def test_script_sets_the_label_alongside_data_tone(self):
        """url-block-page ships TONE=calm but is raised to crit at runtime; the
        label must move with it or the pill renders empty."""
        page = self._page("url-block-page")
        self.assertIn("setAttribute('data-tone',m[0])", page)
        self.assertIn("Security risk", page, "runtime label lookup missing from the emitted script")

    def test_statically_critical_page_ships_its_label(self):
        page = self._page("credential-block-page")
        self.assertIn('data-tone="crit"', page)
        self.assertIn("Security risk", page)

    def test_calm_page_ships_an_empty_pill(self):
        page = self._page("safe-search-block-page")
        self.assertIn('data-tone="calm"', page)
        self.assertIn('<span class="sev"></span>', page, "calm pages should emit an empty pill, hidden by .sev:empty")

    # The byte budget now lives in tests/test_shells.py, where it covers every
    # theme and all eight pages rather than five pages of one theme.


if __name__ == "__main__":
    unittest.main()
