"""Severity signalling in the assist shell.

Scoped to assist on purpose. Every shell must render {{SEVERITY}} and must not
repaint the brand row or the primary action by tone -- that is the shared
contract, and tests/test_shells.py enforces it across all of them. How a shell
expresses severity is its own business: assist uses a pill in the brand row, and
what follows pins assist's version of it.

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

from _build import deploy_dir
from _paths import DATA

SHELL = (DATA / "templates/shells/assist.html").read_text(encoding="utf-8")


class TestAssistShell(unittest.TestCase):
    def test_brand_stays_on_accent(self):
        """The customer logo must not be recoloured by severity.

        The invariant is the absence of a tone token, not the presence of one
        specific accent token: --ac is the vivid fill and --at its text-safe
        variant, and either is fixed per palette.
        """
        brand = re.search(r"\.brand\s*\{[^}]*\}", SHELL)
        self.assertIsNotNone(brand, "no .brand rule found")
        rule = brand.group(0)
        for tone_token in ("var(--tone)", "var(--tt)", "var(--ti)", "var(--tw)"):
            self.assertNotIn(tone_token, rule, f"brand/logo must not vary with severity ({tone_token})")
        self.assertRegex(rule, r"color:var\(--a[ct]\)", "brand should use a fixed accent token")

    def test_primary_button_uses_the_palette_accent(self):
        """The action is the brand's, not the severity's: a Prisma-blue estate
        should not show an orange-red button because a category happens to be
        critical. Severity is carried by the pill and the warnline."""
        btn = re.search(r"\.btn\s*\{[^}]*\}", SHELL)
        self.assertIsNotNone(btn, "no .btn rule found")
        rule = btn.group(0)
        self.assertIn("background:var(--ac)", rule, "primary action should use the palette accent fill")
        self.assertNotIn("var(--tone)", rule, "primary action must not change colour with severity")

    def test_severity_is_still_visible_somewhere(self):
        """Removing tone from the button must not make severity invisible."""
        pill = re.search(r"\.brand\s+\.sev\s*\{[^}]*\}", SHELL)
        self.assertIsNotNone(pill)
        self.assertIn("var(--tt)", pill.group(0))
        warn = re.search(r"(?m)^\.warnline\{[^}]*\}", SHELL)
        self.assertIsNotNone(warn)
        self.assertIn("var(--tt)", warn.group(0), "the warning callout's edge should carry the severity colour")

    def test_no_text_sits_on_a_gradient(self):
        """A brand gradient runs 500 -> 1000, so it always ends at a tone no
        label can contrast against. It may only be used where there is no text."""
        for rule in re.findall(
            r"\.btn\s*\{[^}]*\}|\.sev[^{]*\{[^}]*\}"
            r"|\.warnline\s*\{[^}]*\}",
            SHELL,
        ):
            self.assertNotIn("gradient", rule, "text-bearing element must not use a gradient fill")

    def test_gradient_is_linear_only(self):
        """Radial and non-linear gradient variants are not used."""
        self.assertIn("linear-gradient(", SHELL)
        self.assertNotIn("radial-gradient", SHELL)
        self.assertNotIn("conic-gradient", SHELL)

    def test_severity_pill_beats_brand_span_specificity(self):
        """.brand span is (0,1,1); a bare .sev (0,1,0) would lose the cascade."""
        self.assertRegex(SHELL, r"\.brand\s+\.sev\s*\{", "severity pill must be scoped as '.brand .sev'")

    def test_empty_severity_pill_is_hidden(self):
        self.assertRegex(
            SHELL, r"\.sev:empty\s*\{[^}]*display:\s*none", "an empty pill must not render as a bare coloured chip"
        )

    def test_every_link_context_is_palette_coloured(self):
        """An unstyled <a> falls back to browser blue and breaks the palette."""
        for ctx in (".plain a", ".note a"):
            self.assertRegex(
                SHELL,
                re.escape(ctx).replace(r"\ ", r"\s*") + r"[^{]*\{[^}]*color:var\(--at\)",
                f"{ctx} must take the accent colour",
            )

    def test_shell_declares_the_pill(self):
        self.assertIn('<span class="sev"', SHELL)


class TestSeverityAtRuntime(unittest.TestCase):
    def _page(self, name):
        return (deploy_dir() / "assist" / f"{name}.html").read_text(encoding="utf-8")

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
