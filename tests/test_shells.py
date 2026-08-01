"""The contract every shell must satisfy, checked against every shell.

A style is a shell plus a theme, and build.py discovers both by globbing. That
makes adding a style cheap, and it makes breaking one invisible: the build errors
only on *unknown* placeholders, never on a missing or misplaced one. A shell that
drops {{SEVERITY}}, wraps the facts in a <div> instead of a <dl>, or puts
{{SCRIPTS}} in <head> compiles clean, validates clean, and ships a page that is
quietly missing a third of its behaviour.

Everything asserted here is something that fails silently if it is wrong. Design
choices -- where the mark sits, how the callout is drawn, whether there is a
gradient -- are deliberately not asserted; those belong to the shell.
"""

import json
import re
import unittest

from _build import deploy_dir
from _paths import DATA

SHELLS = sorted((DATA / "templates/shells").glob("*.html"))

PLACEHOLDERS = (
    "TITLE",
    "HEADLINE",
    "GLOSS",
    "FACTS",
    "ACTIONS",
    "EXTRA",
    "MARK",
    "TONE",
    "SEVERITY",
    "COMPANY",
    "LOGO_SVG",
    "SCRIPTS",
    # Both empty on every page but the URL block one, and on every build that has
    # not opted in -- so a shell missing them builds clean and simply never shows
    # the handoff, in that one theme, for the one customer who turned it on.
    "REDIRECT_CSS",
    "REDIRECT",
)

# Selector/body pairs. At-rule wrappers (@media, @keyframes) contain nested
# braces, so they never match; their inner rules do, which is what we want.
RULE_RE = re.compile(r"([^{}]+)\{([^{}]*)\}")

# A text colour, not background-color / border-left-color / outline-color.
TEXT_COLOR_RE = re.compile(r"(?:^|[;{])\s*color:")

PLACEHOLDER_RE = re.compile(r"\{\{[A-Z_0-9]+\}\}")


def style_of(text):
    """The stylesheet, with {{PLACEHOLDERS}} flattened to a literal.

    Every rule in the token blocks is built from placeholders, and their braces
    are indistinguishable from CSS braces to a regex: left in place they end
    each rule body at the first '{{C_GROUND}}', so the blocks that matter most
    here parse as empty and every check over them passes vacuously.
    """
    css = re.search(r"<style>(.*?)</style>", text, re.S).group(1)
    return PLACEHOLDER_RE.sub("X", css)


def rules(css):
    return [(m.group(1).strip(), m.group(2)) for m in RULE_RE.finditer(css)]


def rule_body(css, selector):
    """The body of a rule whose selector is exactly `selector`."""
    for sel, body in rules(css):
        if sel.splitlines()[-1].strip() == selector:
            return body
    return None


def decls(body):
    """Split declarations on top-level ';' only.

    color-mix(in oklab,var(--gr) 88%,transparent) carries commas and would
    survive a naive split, but a nested ';' never appears -- what matters is
    that the property name is the text before the FIRST ':', not any later one.
    """
    out, depth, cur = [], 0, ""
    for ch in body:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == ";" and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    out.append(cur)
    return [d.strip() for d in out if d.strip()]


def prop(decl):
    return decl.split(":", 1)[0].strip()


def token_names(block):
    return set(re.findall(r"--([a-z0-9_]+)\s*:", block))


class ShellContract(unittest.TestCase):
    """Each test loops every shell so a new one cannot arrive unchecked."""

    @classmethod
    def setUpClass(cls):
        cls.shells = {p.stem: p.read_text(encoding="utf-8") for p in SHELLS}
        assert cls.shells, "no shells found"

    def each(self):
        for name, text in sorted(self.shells.items()):
            with self.subTest(shell=name):
                yield name, text, style_of(text)

    # ---- structure ---------------------------------------------------------

    def test_renders_every_placeholder(self):
        for name, text, _css in self.each():
            for ph in PLACEHOLDERS:
                self.assertIn(
                    f"{{{{{ph}}}}}",
                    text,
                    f"{name} never renders {{{{{ph}}}}} -- it would build clean and silently drop that content",
                )

    def test_declares_doctype_viewport_and_tone(self):
        for name, text, _css in self.each():
            self.assertTrue(
                text.lstrip().startswith("<!DOCTYPE html>"), f"{name}: missing doctype drops browsers into quirks mode"
            )
            self.assertIn("initial-scale=1", text, name)
            self.assertRegex(
                text,
                r'<html[^>]*data-tone="\{\{TONE\}\}"',
                f"{name}: the tone attribute must be on <html>, which is what the category script rewrites at runtime",
            )

    def test_facts_sit_inside_a_literal_dl(self):
        """The mailto rebuild is document.querySelectorAll('dl .f').

        A <div class="facts"> wrapper renders identically and then overwrites the
        working static href with one carrying no fields at all.
        """
        for name, text, _css in self.each():
            self.assertRegex(
                text, r"<dl[^>]*>\s*\{\{FACTS\}\}\s*</dl>", f"{name}: {{{{FACTS}}}} must be wrapped in a literal <dl>"
            )

    def test_gloss_element_is_addressable(self):
        """url-block-page and url-coach-text have their gloss rewritten per
        category; without the id they show the generic sentence forever."""
        for name, text, _css in self.each():
            self.assertRegex(text, r'id="gloss"[^>]*>\s*\{\{GLOSS\}\}', name)

    def test_scripts_come_after_the_content_they_touch(self):
        """The emitted script is a bare IIFE with no DOMContentLoaded guard. In
        <head> it silently loses the timestamp, the mailto rebuild, the gloss
        rewrite and the severity label."""
        for name, text, _css in self.each():
            at = text.index("{{SCRIPTS}}")
            for ph in ("FACTS", "ACTIONS", "EXTRA"):
                self.assertLess(text.index(f"{{{{{ph}}}}}"), at, f"{name}: {{{{SCRIPTS}}}} must follow {{{{{ph}}}}}")
            self.assertLess(at, text.index("</body>"), name)

    def test_extra_stays_with_the_actions(self):
        """{{EXTRA}} is the callout. It belongs in the same column/panel as the
        actions -- a shell that closes its panel first leaves the callout
        stranded on the bare background, or on an ambient field."""
        open_re = re.compile(r"<(div|main|section|header|aside)\b")
        close_re = re.compile(r"</(div|main|section|header|aside)>")
        for name, text, _css in self.each():
            span = text[text.index("{{ACTIONS}}") : text.index("{{EXTRA}}")]
            net = len(open_re.findall(span)) - len(close_re.findall(span))
            self.assertIn(
                net,
                (0, -1),
                f"{name}: {{{{EXTRA}}}} is {abs(net)} levels out from "
                f"{{{{ACTIONS}}}}; it should be a sibling of the action "
                f"row or share its container",
            )

    # ---- colour tokens -----------------------------------------------------

    def test_declares_all_four_token_blocks_with_matching_names(self):
        """The gallery forces a scheme with data-force-scheme, so the media query
        alone is not enough. Presence is not enough either: the real failure is a
        token declared in :root and forgotten in one dark block, which renders a
        light colour into a forced-dark preview and nowhere else.
        """
        for name, _text, css in self.each():
            root = re.search(r"(?m)^:root\{(.*?)\}", css, re.S)
            dark = re.search(r"@media\(prefers-color-scheme:dark\)\{:root\{(.*?)\}", css, re.S)
            forced = {k: re.search(rf"html\[data-force-scheme={k}\]\{{(.*?)\}}", css, re.S) for k in ("light", "dark")}
            self.assertIsNotNone(root, f"{name}: no :root token block")
            self.assertIsNotNone(dark, f"{name}: no prefers-color-scheme:dark block")
            for k, m in forced.items():
                self.assertIsNotNone(
                    m, f"{name}: no data-force-scheme={k} block; the preview gallery could not switch scheme"
                )

            names = {
                "dark media": token_names(dark.group(1)),
                "force-light": token_names(forced["light"].group(1)),
                "force-dark": token_names(forced["dark"].group(1)),
            }
            base = names["force-light"]
            for label, got in names.items():
                self.assertEqual(
                    got,
                    base,
                    f"{name}: the {label} block declares a different set "
                    f"of tokens ({sorted(got ^ base)} differ) -- one "
                    f"scheme would keep the other's value",
                )
            self.assertTrue(
                base <= token_names(root.group(1)),
                f"{name}: :root is missing {sorted(base - token_names(root.group(1)))}",
            )

    def test_declares_both_tone_overrides(self):
        for name, _text, css in self.each():
            for tone in ("warn", "crit"):
                self.assertRegex(
                    css, rf"html\[data-tone={tone}\]\{{", f"{name}: no {tone} override, so severity never shows"
                )

    def test_decoration_does_not_switch_scheme_outside_the_token_blocks(self):
        """A rule like .orb{opacity:.34} + a dark override in the media query has
        no way back to .34 when the gallery forces light on a dark-OS machine:
        the reviewer signs off dark tuning under a Light caption. Scheme-varying
        decoration must be a custom property declared in all four blocks."""
        for name, _text, css in self.each():
            for m in re.finditer(r"html\[data-force-scheme=(?:light|dark)\]\s+(\S[^{]*)\{", css):
                self.fail(
                    f"{name}: '{m.group(1).strip()}' is scheme-switched at the "
                    f"element; tokenise the value into the four :root blocks"
                )

    # ---- severity ----------------------------------------------------------

    def test_primary_action_carries_brand_not_severity(self):
        """Matched against the bare .btn rule only: assist deliberately tints the
        focus ring with --tt in 'a:focus-visible,.btn:focus-visible{...}'."""
        for name, _text, css in self.each():
            body = rule_body(css, ".btn")
            self.assertIsNotNone(body, f"{name}: no bare .btn rule")
            self.assertIn("background:var(--ac)", body, f"{name}: the action is the brand's, not the severity's")
            for tok in ("var(--tt)", "var(--tw)"):
                self.assertNotIn(tok, body, f"{name}: .btn must not vary with severity")

    def test_brand_row_is_never_repainted_by_severity(self):
        """Matched against the bare .brand rule only -- '.brand .sev' IS the
        severity pill and must contain tone tokens."""
        for name, _text, css in self.each():
            body = rule_body(css, ".brand")
            if body is None:
                continue  # a shell may have no brand row rule of its own
            for tok in ("var(--tt)", "var(--tw)"):
                self.assertNotIn(tok, body, f"{name}: a customer's mark must not be recoloured by block severity")

    def test_empty_severity_label_is_hidden_and_wins_the_cascade(self):
        """'.brand .sev' and '.sev:empty' are both (0,2,0), so only source order
        decides. Declared the wrong way round, every calm page ships a bare
        coloured chip -- with a green suite."""
        for name, _text, css in self.each():
            painted = -1
            for m in RULE_RE.finditer(css):
                sel, body = m.group(1), m.group(2)
                if ".sev" in sel and ":empty" not in sel and ("background:" in body or "color:" in body):
                    painted = max(painted, m.start())
            hide = [m for m in RULE_RE.finditer(css) if ".sev:empty" in m.group(1) and "display:none" in m.group(2)]
            self.assertTrue(hide, f"{name}: no .sev:empty{{display:none}} rule")
            if painted >= 0:
                self.assertGreater(
                    hide[-1].start(),
                    painted,
                    f"{name}: .sev:empty is declared before the rule "
                    f"that paints .sev; equal specificity means it "
                    f"loses and calm pages show an empty chip",
                )

    # ---- the markup pages actually emit ------------------------------------

    def test_styles_the_injected_panos_controls(self):
        """PAN-OS injects its own markup for <pan_form/> and <cookie/>. Unstyled
        it renders as a raw browser button beside a designed primary action."""
        for name, _text, css in self.each():
            self.assertRegex(css, r"\.acts[^{]*input\[type=submit\]", name)
            self.assertRegex(css, r"\.acts[^{]*button[^{]*\{", name)

    def test_long_values_can_shrink(self):
        """Only overflow-wrap:anywhere contributes to min-content sizing, which is
        what lets a 120-character URL fit a fixed sidebar track. break-word looks
        equivalent and overflows on every URL page."""
        for name, _text, css in self.each():
            body = rule_body(css, "dd")
            self.assertIsNotNone(body, f"{name}: no dd rule")
            self.assertIn("overflow-wrap:anywhere", body, name)

    def test_styles_every_class_the_pages_emit(self):
        for name, _text, css in self.each():
            for cls in (".plain", ".note", ".infobox", ".warnline"):
                self.assertIn(cls, css, f"{name}: pages emit {cls} and it is unstyled")

    def test_no_link_context_falls_back_to_browser_blue(self):
        for name, _text, css in self.each():
            for ctx in (".plain a", ".note a"):
                hit = [b for sel, b in rules(css) if ctx in sel and "color:var(--at)" in b]
                self.assertTrue(hit, f"{name}: {ctx} must take the accent colour")

    def test_has_a_mobile_breakpoint(self):
        for name, _text, css in self.each():
            self.assertIn("@media(max-width:600px)", css, name)

    def test_animation_respects_reduced_motion(self):
        for name, _text, css in self.each():
            if "@keyframes" in css:
                self.assertIn("prefers-reduced-motion", css, f"{name} animates but never opts out")

    # ---- colour / gradient rules -------------------------------------------

    def test_gradients_stay_off_text_bearing_components(self):
        """A brand gradient runs 500 -> 1000, so it always ends at a tone no label
        can contrast against. Scoped to the components that carry short text on a
        fill; body's border-image is a rule, not a text background."""
        for name, _text, css in self.each():
            self.assertNotIn("conic-gradient", css, f"{name}: conic gradients are not used")
            for sel, body in rules(css):
                if re.search(r"\.btn\b|\.sev\b|\.warnline\b", sel) and "gradient" in body:
                    self.fail(f"{name}: '{sel}' puts text on a gradient fill")

    def test_radial_gradients_are_texture_only(self):
        """Permitted as a fine repeating texture or a mask, never as a surface
        under text -- a 1.4px dot field is texture, a filled panel is not."""
        for name, _text, css in self.each():
            for sel, body in rules(css):
                if "radial-gradient" not in body:
                    continue
                self.assertNotRegex(body, TEXT_COLOR_RE, f"{name}: '{sel}' sets text on a radial gradient")
                self.assertTrue(
                    "background-size:" in body or "mask-image:" in body,
                    f"{name}: '{sel}' uses radial-gradient as a surface; "
                    f"it is allowed only as a repeating texture or a mask",
                )

    def test_color_mix_always_has_a_fallback(self):
        """color-mix is newer than the CSS this project assumes. Unsupported, the
        whole declaration is dropped -- so a translucent panel loses its
        background entirely and its text lands on whatever is behind it."""
        for name, _text, css in self.each():
            for sel, body in rules(css):
                ds = decls(body)
                for i, d in enumerate(ds):
                    if "color-mix(" not in d:
                        continue
                    self.assertGreater(i, 0, f"{name}: '{sel}' opens with color-mix and has no fallback")
                    self.assertEqual(
                        prop(ds[i - 1]),
                        prop(d),
                        f"{name}: '{sel}' -- {prop(d)} using color-mix must be preceded by a solid {prop(d)}",
                    )


class BuiltOutput(unittest.TestCase):
    """Guards that only mean anything against real build output."""

    @classmethod
    def setUpClass(cls):
        cls.themes = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((DATA / "themes").glob("*.json"))]
        from panos_response_pages.validate import PAGE_TOKENS

        cls.pages = sorted(PAGE_TOKENS)

    def test_every_theme_emits_every_page(self):
        """Counted before iterating: a theme that silently produced nothing would
        otherwise pass every per-file check by having no files."""
        root = deploy_dir()
        found = sorted(p.relative_to(root).as_posix() for p in root.glob("*/*.html"))
        want = sorted(f"{t['name']}/{p}.html" for t in self.themes for p in self.pages)
        self.assertEqual(found, want)

    def test_every_page_of_every_theme_stays_within_budget(self):
        for t in self.themes:
            for page in self.pages:
                path = deploy_dir() / t["name"] / f"{page}.html"
                size = len(path.read_bytes())
                with self.subTest(theme=t["name"], page=page):
                    self.assertLess(
                        size,
                        16000,
                        f"{t['name']}/{page} is {size} B, too close to "
                        f"the 17999 B ceiling -- <url/> expands at serve "
                        f"time",
                    )


if __name__ == "__main__":
    unittest.main()
