"""Layout details that broke once and must not break again.

Rules about MARKUP are asserted on the templates. Rules that involve the words
in the markup -- a label's position, a callout's guidance, a mail subject -- are
asserted on the BUILT pages: copy lives in `data/strings/*.json` now, so the
template carries a placeholder where the sentence used to be and a template-only
assertion has nothing left to find.
"""

import functools
import re
import unittest

from _build import deploy_dir, preview_dir
from _paths import DATA

SHELL = (DATA / "templates/shells/assist.html").read_text(encoding="utf-8")
PAGES = DATA / "templates/pages"

SECTION_RE = re.compile(r"<!--@([A-Z_]+)-->(.*?)<!--/@\1-->", re.S)

# The one page with no report BUTTON: its only a.btn is the search-settings
# link, and IT contact is an inline anchor inside its note. Named once so the
# counters below can DERIVE how many pages offer the button instead of carrying
# a hand-maintained number that stops being true when a page is added.
NO_REPORT_BUTTON = "safe-search-block-page"

# The label the shared `reportLabel` renders to in the base language. The built
# pages this suite reads are an English single-language build.
REPORT_LABEL = "Report to IT"


def slots(name):
    text = (PAGES / f"{name}.html").read_text(encoding="utf-8")
    return {k: v.strip() for k, v in SECTION_RE.findall(text)}


@functools.lru_cache(maxsize=1)
def built_pages():
    """Every built response page, as (path, html); portal pages excluded."""
    return tuple(
        (f, f.read_text(encoding="utf-8")) for f in sorted(deploy_dir().rglob("*.html")) if "portal" not in f.parts
    )


def built(*stems):
    """The built copies of the named pages, across every style and palette."""
    return [(f, text) for f, text in built_pages() if f.stem in stems]


def page_dirs():
    """The (style, palette) directories a build produces. Counters multiply by
    this rather than hardcoding a number, so adding a style widens the coverage
    instead of invalidating a count."""
    return {f.parent for f, _ in built_pages()}


class TestWarnline(unittest.TestCase):
    """.warnline is display:flex, which makes every inline child its own flex
    item. Bare text either side of a <strong> therefore laid out as separate
    columns, splitting one sentence into three. All text must sit in a single
    wrapping element."""

    WARNLINE_RE = re.compile(r'<p class="warnline">(.*?)</p>', re.S)

    def test_shell_reserves_one_flex_item_for_text(self):
        self.assertRegex(SHELL, r"\.warnline>span\s*\{[^}]*flex:1")
        self.assertRegex(SHELL, r"\.warnline>svg\s*\{[^}]*flex:none")

    def test_every_warnline_wraps_its_text_in_a_single_span(self):
        found = 0
        for page in PAGES.glob("*.html"):
            for body in self.WARNLINE_RE.findall(page.read_text(encoding="utf-8")):
                found += 1
                inner = body.replace("{{WARN_MARK}}", "").strip()
                self.assertTrue(
                    inner.startswith("<span>") and inner.endswith("</span>"),
                    f"{page.stem}: warnline text must be wrapped in one <span>, "
                    f"or flex will split the sentence -- got {inner[:70]!r}",
                )
                # exactly one span, no stray text outside it
                self.assertEqual(inner.count("<span>"), 1, page.stem)
        self.assertGreaterEqual(found, 1, "expected at least one warnline")

    def test_every_warnline_leads_with_the_warning_icon(self):
        for page in PAGES.glob("*.html"):
            for body in self.WARNLINE_RE.findall(page.read_text(encoding="utf-8")):
                self.assertTrue(
                    body.lstrip().startswith("{{WARN_MARK}}"), f"{page.stem}: warnline should open with the icon"
                )


class TestInfobox(unittest.TestCase):
    """The info callout shares the warnline's structure -- flex, so all text must
    live in one span or the sentence splits into columns."""

    INFOBOX_RE = re.compile(r'<p class="infobox">(.*?)</p>', re.S)

    BASE_RE = re.compile(r"\.infobox,\.warnline\{[^}]*\}")

    def test_both_callouts_share_one_treatment(self):
        """Info and warning are the same component with different meaning. The
        declarations are shared so the two cannot drift apart again."""
        base = self.BASE_RE.search(SHELL)
        self.assertIsNotNone(base, "callouts should share a single rule")
        self.assertIn("display:flex", base.group(0))
        self.assertRegex(SHELL, r"\.infobox>span,\.warnline>span\{[^}]*flex:1")
        self.assertRegex(SHELL, r"\.infobox>svg,\.warnline>svg\{[^}]*flex:none")

    def test_only_the_edge_and_icon_carry_severity(self):
        """The warning differs from the info box by colour of edge and icon, not
        by a different box. Body text stays on normal ink so it stays readable."""
        base = self.BASE_RE.search(SHELL).group(0)
        self.assertIn("color:var(--ik)", base, "callout text should use normal ink")
        self.assertNotIn("var(--tw)", base, "the shared base must be tone-independent")
        warn = re.search(r"(?m)^\.warnline\{[^}]*\}", SHELL).group(0)
        self.assertIn("border-left-color:var(--tt)", warn)
        self.assertRegex(SHELL, r"\.warnline>svg\{color:var\(--tt\)\}")

    def test_callout_prominence_does_not_vary_by_palette(self):
        """The accent wash is the ramp's 0 stop, which is a saturated peach in
        one brand and a pale cream in another. The derived surface tint plus a
        solid edge keeps the callout equally prominent everywhere."""
        base = self.BASE_RE.search(SHELL).group(0)
        self.assertIn("background:var(--sa)", base)
        self.assertRegex(base, r"border-left:\d+px solid var\(--at\)")
        self.assertNotIn("var(--aw)", base, "ramp-0 washes differ too much in lightness between brands")

    def test_every_infobox_wraps_its_text_in_a_single_span(self):
        """Same flex constraint as the warnline: bare text either side of a
        <strong> would lay out as separate columns."""
        found = 0
        for page in PAGES.glob("*.html"):
            for body in self.INFOBOX_RE.findall(page.read_text(encoding="utf-8")):
                found += 1
                inner = body.replace("{{INFO_MARK}}", "").strip()
                self.assertTrue(
                    inner.startswith("<span>") and inner.endswith("</span>"),
                    f"{page.stem}: info text must sit in one span -- got {inner[:70]!r}",
                )
                self.assertEqual(inner.count("<span>"), 1, page.stem)
        self.assertGreaterEqual(found, 1, "expected at least one info box")

    def test_credential_block_keeps_the_never_asks_guidance(self):
        """The one piece of advice on the highest-stakes page: we will never ask
        for your password on a page like this one.

        Asserted on the built page. The template holds {{T_EXTRA}}, so the
        sentence exists nowhere until the strings file and the markup are put
        together -- and a callout that quietly lost its copy is still a callout.
        """
        found = 0
        for f, text in built("credential-block-page"):
            found += 1
            boxes = self.INFOBOX_RE.findall(text)
            self.assertEqual(len(boxes), 1, f"{f}: expected exactly one info box")
            self.assertIn("never ask", boxes[0], f"{f}: the info box lost the 'never asks' guidance")
        self.assertEqual(found, len(page_dirs()), "not every build of credential-block-page was examined")

    def test_no_page_mixes_a_warnline_and_an_infobox(self):
        """Two stacked callouts read as competing alerts; each page should make
        one supplementary statement."""
        for page in PAGES.glob("*.html"):
            body = page.read_text(encoding="utf-8")
            self.assertFalse(
                self.INFOBOX_RE.search(body) and TestWarnline.WARNLINE_RE.search(body),
                f"{page.stem} carries both a warnline and an info box",
            )

    def test_every_infobox_leads_with_the_info_icon(self):
        for page in PAGES.glob("*.html"):
            for body in self.INFOBOX_RE.findall(page.read_text(encoding="utf-8")):
                self.assertTrue(body.lstrip().startswith("{{INFO_MARK}}"), page.stem)


class TestActionOrder(unittest.TestCase):
    COACH_PAGES = ("url-coach-text", "credential-coach-text")

    def test_continue_sits_left_of_report_on_both_coach_pages(self):
        """The primary action is Continue; reporting is the alternative.

        Asserted on the built page: the report label is {{T_REPORT_LABEL}} in
        the template, so there is no "Report to IT" in it to find a position
        for. `<pan_form/>` survives into the output untouched -- the firewall
        expands it at serve time -- so both landmarks are present there.
        """
        found = 0
        for f, text in built(*self.COACH_PAGES):
            found += 1
            self.assertIn("<pan_form/>", text, f"{f} should offer Continue")
            self.assertIn(f">{REPORT_LABEL}</a>", text, f"{f} should offer the report action")
            self.assertLess(
                text.index("<pan_form/>"),
                text.index(f">{REPORT_LABEL}</a>"),
                f"{f}: Continue must precede {REPORT_LABEL}",
            )
        self.assertEqual(found, len(self.COACH_PAGES) * len(page_dirs()), "not every coach page build was examined")


class TestActionStyling(unittest.TestCase):
    def test_report_to_it_is_a_button_on_every_page_that_offers_it(self):
        """It rendered as an underlined text link on url-coach-text, which read
        as prose rather than a control.

        On BUILT pages, and with a count. The label is a placeholder in the
        template now, so the old template-side loop skipped every page and
        passed while asserting nothing -- coverage in appearance only. The count
        is what makes that impossible to repeat: it is derived from the file
        listing rather than from the same `if` that decides whether to look, so
        a build where the label went missing fails here instead of going quiet.
        """
        examined = 0
        for f, text in built_pages():
            if f">{REPORT_LABEL}</a>" not in text:
                self.assertEqual(f.stem, NO_REPORT_BUTTON, f"{f}: no report button and it is not the page allowed one")
                continue
            examined += 1
            # The mailto body carries <url/> and <category/>, so the anchor's
            # attributes contain ">" -- match backwards from the label instead.
            idx = text.index(f">{REPORT_LABEL}</a>")
            opening = text.rindex("<a ", 0, idx)
            self.assertIn('class="btn"', text[opening:idx], f"{f}: {REPORT_LABEL} must be a full button")
        expected = len(built_pages()) - len(page_dirs())
        self.assertEqual(examined, expected, f"expected {expected} pages with a report button, examined {examined}")
        self.assertGreater(examined, 0, "the loop examined no pages at all")

    def test_no_underlined_action_style_remains(self):
        self.assertNotIn("btn-secondary", SHELL, "the underlined secondary style was retired")
        for page in PAGES.glob("*.html"):
            self.assertNotIn("btn-secondary", page.read_text(encoding="utf-8"), page.stem)


class TestIndicatorAndInjectedForm(unittest.TestCase):
    def test_indicator_is_in_the_production_shell(self):
        self.assertIn('<div class="ind">{{MARK}}</div>', SHELL)
        self.assertRegex(SHELL, r"\.hd\s+\.ind\s*\{[^}]*border-radius:50%")

    def test_indicator_stacks_on_mobile(self):
        mobile = SHELL[SHELL.index("@media(max-width:600px)") :]
        self.assertRegex(mobile, r"\.hd\{grid-template-columns:1fr")

    def test_mobile_actions_share_a_row(self):
        """`.btn{width:100%}` in the mobile block forced Continue and Report to IT
        onto separate rows even at 430px, where both fit comfortably."""
        mobile = SHELL[SHELL.index("@media(max-width:600px)") :]
        self.assertNotRegex(mobile, r"\.btn\{width:100%\}", "full-width buttons stack instead of sharing a row")
        self.assertRegex(mobile, r"\.acts>\.btn,\.acts>form\{flex:1")
        self.assertRegex(
            mobile, r"\.acts>form input\{width:100%\}", "the injected control must fill its flexed form wrapper"
        )


class TestMailto(unittest.TestCase):
    """The incident detail is carried once, in the data-* attributes.

    PAN-OS substitutes raw bytes, so the page cannot encode at serve time: a raw
    "&" in <url/> terminates a mailto body parameter and silently drops every
    field after it. The script therefore rebuilds the href from the rendered
    fact table with encodeURIComponent, which is the only place the encoding can
    happen correctly.

    The static href used to carry the same fields a second time, pre-encoded and
    ordered so a truncation lost only trailing text. It now carries the address
    alone -- the duplication was ~180 B per page of copy that had to be kept in
    step with the attributes by hand, and without the body there is nothing left
    to truncate. No-JS still reaches the right mailbox, with an empty message."""

    def _report_links(self):
        for page in PAGES.glob("*.html"):
            body = page.read_text(encoding="utf-8")
            if 'id="rep"' in body:
                start = body.index('id="rep"')
                # Bound on '">', not '>': the anchor's other attributes can still
                # hold a bare '>' in their copy, and cutting at the first one
                # would truncate the slice mid-tag.
                yield page.stem, body[body.rindex("<a ", 0, start) : body.index('">', body.index('href="', start)) + 2]

    def _mailto_sections(self):
        """The pre-filled mailto each page declares.

        It lives in its own section rather than in the anchor, because the anchor's
        href is now chosen at build time between this and a configured ticket URL.
        The <url/> ordering rule follows the mailto, not the anchor.
        """
        for page in PAGES.glob("*.html"):
            body = page.read_text(encoding="utf-8")
            m = re.search(r"<!--@CONTACT_MAILTO-->(.*?)<!--/@CONTACT_MAILTO-->", body, re.S)
            if m:
                yield page.stem, m.group(1)

    def test_every_report_link_carries_the_rebuild_attributes(self):
        # data-to is email-mode only -- it is an address, and a ticket URL has
        # none -- so the template carries {{CONTACT_TO}} and the build decides.
        # The other three ship in both modes: they are the page's incident
        # metadata, and what a ticket adapter will read.
        found = 0
        for name, tag in self._report_links():
            found += 1
            for attr in ("{{CONTACT_TO}}", "data-subject", "data-intro", "data-prompt"):
                self.assertIn(attr, tag, f"{name} missing {attr}")
        expected = len(list(PAGES.glob("*.html")))
        self.assertEqual(found, expected, "every page should offer a way to reach IT")

    def test_every_page_declares_a_mailto_section(self):
        """Email mode is the default, so a page without one has no href at all.
        page.py falls back to an empty string rather than raising."""
        declared = {name for name, _ in self._mailto_sections()}
        expected = {p.stem for p in PAGES.glob("*.html")}
        self.assertEqual(declared, expected, "every page needs a pre-filled mailto for email mode")

    def test_mailto_sections_are_single_line(self):
        """parse_sections strips the outer whitespace but not the interior, so a
        newline introduced by reformatting would land inside the href."""
        for name, mailto in self._mailto_sections():
            self.assertNotIn("\n", mailto.strip(), f"{name}: the mailto section must stay on one line")

    def test_the_static_href_carries_no_panos_tokens(self):
        """It is the address and nothing else, which is what makes the truncation
        hazard impossible rather than merely avoided.

        This used to be a rule about ORDER: the pre-filled href carried the
        user, the category and the address as body fields, a raw '&' in the
        substituted <url/> terminated the body parameter, and every field after
        it was silently dropped -- so <url/> had to come last. The fields now
        live only in the data-* attributes, which the script folds into the body
        with encodeURIComponent, so there is no body in the markup left to
        truncate. Asserting the absence is stronger than asserting the order:
        the ordering test could pass by a page simply having no <url/>.
        """
        found = 0
        for name, mailto in self._mailto_sections():
            found += 1
            self.assertNotRegex(
                mailto,
                r"<(user|url|category|ssurl|fname|appname)\s*/>",
                f"{name}: a PAN-OS token in the static href brings back the '&' truncation hazard",
            )
            self.assertNotIn("?", mailto, f"{name}: the static href should carry no query, only the address")
        self.assertEqual(found, len(list(PAGES.glob("*.html"))), "not every page was checked")

    def test_subjects_are_distinct_per_page(self):
        """A shared subject line makes two incidents one ticket thread.

        Asserted on the built pages, and WITHIN a build rather than across all
        of them: every page carries the same {{T_REPORT_SUBJECT}} placeholder in
        the template, so the subjects only differ once a language is substituted
        in -- and the same page built in seven styles is the same page, so its
        subject is expected to repeat across directories.

        `data-subject` is the only attribute of that name on a page, so it is
        matched directly rather than by first slicing out the anchor: the
        anchor's other attributes carry copy that can contain '>'.
        """
        subjects: dict[tuple[object, str], list[str]] = {}
        for f, text in built_pages():
            m = re.search(r'data-subject="([^"]*)"', text)
            self.assertIsNotNone(m, f"{f} carries no report subject")
            subjects.setdefault((f.parent, m.group(1)), []).append(f.stem)
        examined = sum(len(stems) for stems in subjects.values())
        self.assertEqual(examined, len(built_pages()), "not every built page was examined")
        dupes = {subject: sorted(stems) for (_dir, subject), stems in subjects.items() if len(stems) > 1}
        self.assertEqual(dupes, {}, f"pages share a mail subject, so tickets are indistinguishable: {dupes}")


class TestPreviewGallery(unittest.TestCase):
    """preview/index.html is generated by build.py and is the thing a reviewer
    actually looks at, so it gets the same scrutiny as the pages."""

    @classmethod
    def setUpClass(cls):
        cls.html = (preview_dir() / "index.html").read_text(encoding="utf-8")

    def _visible(self):
        """Markup with <style> and <script> stripped -- 'flex-direction' is not
        user-facing copy.

        Split rather than matched: a regexp over tags reads as a broken HTML
        sanitizer to code scanning, which is noise on markup this repo emitted
        itself -- and there is nothing here a regexp does better.
        """
        out = self.html
        for tag in ("style", "script"):
            parts = out.split(f"<{tag}>")
            out = parts[0] + "".join(p.partition(f"</{tag}>")[2] for p in parts[1:])
        return out

    def test_uses_preview_language_not_prototype(self):
        visible = self._visible().lower()
        for word in ("prototype", "direction"):
            self.assertNotIn(word, visible, f"the preview is not a design exploration: {word!r}")

    def test_style_selector_appears_exactly_when_there_is_a_choice(self):
        """The style is fixed at build time, so a one-option radiogroup is noise --
        but once a build produces several, every one of them has to be reachable
        or the gallery quietly hides a style from review."""
        import json

        themes = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((DATA / "themes").glob("*.json"))]
        if len(themes) == 1:
            self.assertNotIn('id="themegrp"', self.html)
        else:
            self.assertIn('id="themebtn"', self.html, "no style control was emitted")
            for theme in themes:
                self.assertIn(
                    f'data-value="{theme["name"]}"', self.html, f"{theme['name']} is built but not selectable"
                )

    def test_the_long_lists_do_not_grow_the_control_bar(self):
        """The chrome used to cost about 500 px of a 900 px viewport, most of it
        the page list wrapping onto three rows. The closed control is one line
        whatever a build produces -- its rows live in a popup that is hidden
        until opened -- so this is the rule that keeps the bar from creeping
        back: no page name may appear as a visible button in the bar itself."""
        self.assertIn('id="pagebtn"', self.html)
        self.assertNotRegex(self.html, r'<button role="radio" data-page="')

    def test_the_portal_frames_are_not_shrink_wrapped(self):
        """A portal page is a small card centred in min-height:100vh. Collapsing
        the frame to the card collapses the viewport it is centred in, so it
        loses the background it was designed to sit on and reads as a broken
        thumbnail. Block pages fill their frame and still shrink-wrap."""
        self.assertRegex(self.html, r"var FLOOR=\{desktop:\d{3},mobile:\d{3}\}")
        self.assertIn('i.setAttribute("data-min",FLOOR[kind])', self.html)

    def test_the_spliced_frames_still_carry_their_warning(self):
        """The one thing on this page that is not decoration: a spliced preview
        carries PAN-OS' own prefix and an inert CSRF token, and importing one
        breaks the portal."""
        self.assertIn("never importable", self.html)

    def test_every_control_is_labelled(self):
        """Two of the segmented controls dropped their visible caption to fit
        the bar on one line, so the label has to survive somewhere."""
        for group in ("Viewport", "Colour scheme"):
            self.assertIn(f'aria-label="{group}"', self.html)
        for ctl in ("Style", "Page"):
            self.assertIn(f"<span>{ctl}</span>", self.html)

    def test_takes_its_colours_from_the_palette(self):
        import json

        palette = json.loads((DATA / "palettes/cyber-orange.json").read_text(encoding="utf-8"))
        self.assertIn(palette["colors"]["accent"], self.html, "preview chrome should use the built palette's accent")
        self.assertIn(palette["colors"]["d_accent"], self.html)

    def test_frames_are_sized_to_their_content(self):
        """Fixed iframe heights made every page scroll inside its frame."""
        self.assertIn("function fit(", self.html)
        self.assertNotRegex(self.html, r"\.dev\.desktop iframe\{[^}]*height:\d+px")
        self.assertNotRegex(self.html, r"\.dev\.mobile iframe\{[^}]*height:\d+px")

    def test_embedded_pages_cannot_break_out_of_the_payload(self):
        self.assertNotIn("</script>", self.html[: self.html.rindex("</script>")])


if __name__ == "__main__":
    unittest.main()
