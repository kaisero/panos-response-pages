"""The sanctioned-app handoff on the URL block page.

Every assertion here covers something that fails quietly: a redirect that arms on
a page it was never meant for, one that fires off a security block, a target the
page took from the blocked site rather than from config, or a feature that is
"off" and still costs bytes on every page of every theme.
"""

import copy
import json
import re
import unittest

from _paths import DATA
from panos_response_pages import redirect
from panos_response_pages.builder import load_themes
from panos_response_pages.config import load_config
from panos_response_pages.emit import strip_output
from panos_response_pages.errors import BuildError
from panos_response_pages.page import build_page
from panos_response_pages.palettes import load_palette
from panos_response_pages.validate import PAGE_TOKENS, WARN_BYTES, validate

THEMES = load_themes(DATA)
PALETTE = load_palette("cyber-orange", DATA / "palettes")
TEMPLATES = DATA / "templates"


def shipped():
    return load_config("contoso", DATA / "config")


def configured(**over):
    """The shipped config with two calm categories mapped to sanctioned apps."""
    cfg = shipped()
    cfg["redirect"]["enabled"] = True
    cfg["redirect"]["categories"] = {
        "social-networking": {"app": "Company Engage", "url": "https://engage.example.com/"},
        "streaming-media": {"app": "Company Video", "url": "https://video.example.com/"},
    }
    cfg["redirect"].update(over)
    return cfg


def render(cfg, page="url-block-page", theme=None):
    return strip_output(build_page(page, theme or THEMES[0], cfg, PALETTE, False, TEMPLATES))


def script_of(html):
    """The redirect script only -- the last <script> on the page."""
    return re.findall(r"<script>(.*?)</script>", html, re.S)[-1]


def map_of(html):
    return json.loads(re.search(r"var R=(\{.*?\});", script_of(html), re.S).group(1))


class TestOffByDefault(unittest.TestCase):
    def test_shipped_config_has_it_disabled_and_unmapped(self):
        """Opt-in means opt-in: shipping a populated table would redirect users
        the moment someone flipped the toggle to see what it did."""
        red = shipped()["redirect"]
        self.assertIs(red["enabled"], False)
        self.assertEqual(red["categories"], {})
        self.assertFalse(redirect.enabled(shipped()))

    def test_a_toggle_without_a_mapping_table_stays_off(self):
        cfg = shipped()
        cfg["redirect"]["enabled"] = True
        self.assertFalse(redirect.enabled(cfg))
        self.assertNotIn('id="rx"', render(cfg))

    def test_off_costs_nothing_in_any_theme_or_page(self):
        """The three slots must render empty, not blank-ish. A feature that is off
        and still ships CSS is the whole reason the byte budget keeps shrinking."""
        for theme in THEMES:
            for page in sorted(PAGE_TOKENS):
                html = render(shipped(), page, theme)
                for fragment in ('id="rx"', ".rx{", "rxg", "data-off"):
                    self.assertNotIn(fragment, html, f"{theme['name']}/{page} carries redirect {fragment}")

    def test_off_is_byte_identical_to_having_no_redirect_key_at_all(self):
        stripped = shipped()
        del stripped["redirect"]
        self.assertEqual(len(render(stripped).encode()), len(render(shipped()).encode()))


class TestOnlyTheUrlBlockPage(unittest.TestCase):
    def test_the_notice_renders_on_the_url_block_page(self):
        self.assertIn('id="rx"', render(configured()))

    def test_and_on_no_other_page(self):
        """Only this page has a <category/> token to key on, and the coach pages
        already carry a Continue action a countdown would race."""
        for page in sorted(PAGE_TOKENS):
            if page == redirect.PAGE:
                continue
            self.assertNotIn('id="rx"', render(configured(), page), f"{page} armed a redirect")

    def test_emit_is_empty_for_every_other_page(self):
        for page in sorted(PAGE_TOKENS):
            parts = redirect.emit(configured(), page)
            if page == redirect.PAGE:
                self.assertTrue(all(parts))
            else:
                self.assertEqual(parts, ("", "", ""))


class TestEveryTheme(unittest.TestCase):
    def test_every_shell_renders_the_notice_and_its_styles(self):
        """A style is a shell plus a theme and both are discovered by globbing, so
        a shell that never got the slots would build clean and ship nothing."""
        for theme in THEMES:
            html = render(configured(), theme=theme)
            self.assertIn('id="rx"', html, f"{theme['name']} has no notice markup")
            self.assertIn(".rx{", html, f"{theme['name']} has no notice CSS")
            self.assertIn("rxg", script_of(html), f"{theme['name']} has no redirect script")

    def test_it_uses_the_shell_palette_rather_than_its_own_colours(self):
        """Structural CSS only. A literal colour here would look wrong in five of
        the six themes and in every palette."""
        self.assertNotIn("#", redirect.CSS)

    def test_no_theme_is_pushed_over_the_warning_line(self):
        for theme in THEMES:
            html = render(configured(), theme=theme)
            size, errors, _warnings = validate(redirect.PAGE, theme["name"], html)
            self.assertEqual(errors, [], f"{theme['name']}: {errors}")
            self.assertLess(size, WARN_BYTES, f"{theme['name']} is {size} B with the redirect on")


class TestTimer(unittest.TestCase):
    def test_the_default_is_ten_seconds(self):
        self.assertEqual(redirect.DEFAULT_SECONDS, 10)
        self.assertEqual(shipped()["redirect"]["seconds"], 10)
        self.assertIn("var S=10,", script_of(render(configured())))

    def test_a_category_on_the_default_does_not_carry_its_own_copy(self):
        self.assertEqual(
            map_of(render(configured()))["social-networking"], ["Company Engage", "https://engage.example.com/"]
        )

    def test_a_category_can_override_it(self):
        cfg = configured()
        cfg["redirect"]["categories"]["social-networking"]["seconds"] = 3
        self.assertEqual(map_of(render(cfg))["social-networking"][2], 3)

    def test_the_default_itself_can_be_changed(self):
        self.assertIn("var S=25,", script_of(render(configured(seconds=25))))


class TestMessages(unittest.TestCase):
    def test_the_default_message_is_emitted_once_not_per_category(self):
        """It is the longest value in the table. Repeating it per category would
        cost more than the rest of the feature."""
        default = shipped()["redirect"]["message"]
        self.assertEqual(script_of(render(configured())).count(default[:20]), 1)

    def test_a_category_can_override_it(self):
        cfg = configured()
        cfg["redirect"]["categories"]["streaming-media"]["message"] = "Watch it on {app} instead."
        row = map_of(render(cfg))["streaming-media"]
        self.assertEqual(row[3], "Watch it on {app} instead.")
        self.assertEqual(row[2], 0, "a per-category message must not also pin the default seconds")

    def test_the_app_placeholder_is_substituted_in_the_browser(self):
        self.assertIn(".replace('{app}',n)", script_of(render(configured())))


class TestSafety(unittest.TestCase):
    def test_the_target_is_never_taken_from_the_url_token(self):
        """<url/> is chosen by whoever the user was trying to reach. A redirect
        built from it turns every firewall serving this page into an open
        redirector."""
        self.assertNotIn("<url/>", script_of(render(configured())))

    def test_it_will_not_hop_again_from_a_blocked_sanctioned_app(self):
        """The loop guard, and it checks EVERY target rather than this category's.
        A hop only ever targets something in this table, so every cycle passes
        through one of these hosts -- including cycles that never repeat a host,
        which a this-target-only check would follow forever."""
        self.assertIn(
            "for(var k in R){h.href=R[k][1];if(h.host===location.host)return}", script_of(render(configured()))
        )

    def test_it_checks_the_tone_the_category_map_resolved(self):
        self.assertIn("data-tone')!=='calm'", script_of(render(configured())))

    def test_the_countdown_pauses_in_a_background_tab(self):
        self.assertIn("if(document.hidden)return", script_of(render(configured())))

    def test_the_script_runs_after_the_category_lookup(self):
        """It reads the tone that lookup resolves. Reordered, the calm-only guard
        reads an attribute nobody has set yet and arms on every category."""
        html = render(configured())
        self.assertLess(html.index("var M="), html.index("var R="))


class TestConfigIsChecked(unittest.TestCase):
    def bad(self, message, mutate):
        cfg = configured()
        mutate(cfg)
        with self.assertRaises(BuildError) as caught:
            render(cfg)
        self.assertIn(message, str(caught.exception))

    def test_a_warn_or_critical_category_may_not_redirect(self):
        def mutate(cfg):
            cfg["redirect"]["categories"]["malware"] = {"app": "X", "url": "https://x.example.com/"}

        self.bad("only a calm category may redirect", mutate)

    def test_the_target_must_be_absolute_https(self):
        for url in ("http://plain.example.com/", "/relative", "drive.example.com"):
            self.bad(
                "must be an absolute https:// URL",
                lambda cfg, url=url: cfg["redirect"]["categories"]["streaming-media"].update(url=url),
            )

    def test_the_category_must_exist_in_the_category_map(self):
        def mutate(cfg):
            cfg["redirect"]["categories"]["nonesuch"] = {"app": "X", "url": "https://x.example.com/"}

        self.bad("is not in `categories`", mutate)

    def test_app_and_url_are_required(self):
        for key in ("app", "url"):
            self.bad(
                f"has no {key}",
                lambda cfg, key=key: cfg["redirect"]["categories"]["streaming-media"].update({key: "  "}),
            )

    def test_seconds_must_be_a_sane_whole_number(self):
        for value in (0, 61, -1):
            self.bad("expected 1-60 seconds", lambda cfg, v=value: cfg["redirect"].update(seconds=v))
        for value in ("10", 2.5, True):
            self.bad("whole number of seconds", lambda cfg, v=value: cfg["redirect"].update(seconds=v))

    def test_per_category_seconds_are_checked_too(self):
        self.bad(
            "expected 1-60 seconds",
            lambda cfg: cfg["redirect"]["categories"]["streaming-media"].update(seconds=99),
        )

    def test_the_default_message_may_not_be_blank(self):
        self.bad("redirect.message is empty", lambda cfg: cfg["redirect"].update(message="  "))

    def test_the_toggle_must_be_a_boolean(self):
        self.bad("must be true or false", lambda cfg: cfg["redirect"].update(enabled="yes"))

    def test_bad_config_fails_the_build_on_every_page_not_just_the_one(self):
        """Otherwise a typo is invisible until someone looks at the one page that
        renders it."""
        cfg = configured()
        cfg["redirect"]["categories"]["streaming-media"]["url"] = "http://nope.example.com/"
        with self.assertRaises(BuildError):
            render(cfg, "virus-block-page")

    def test_a_disabled_but_populated_table_is_still_checked(self):
        cfg = configured()
        cfg["redirect"]["enabled"] = False
        cfg["redirect"]["categories"]["malware"] = {"app": "X", "url": "https://x.example.com/"}
        with self.assertRaises(BuildError):
            render(cfg)


class TestMap(unittest.TestCase):
    def test_it_carries_only_the_categories_that_were_configured(self):
        self.assertEqual(sorted(map_of(render(configured()))), ["social-networking", "streaming-media"])

    def test_the_gloss_map_is_untouched(self):
        """The two tables are separate on purpose: one explains a block, the other
        offers a way out, and not every explained category has one."""
        cfg = configured()
        before = copy.deepcopy(cfg["categories"])
        render(cfg)
        self.assertEqual(cfg["categories"], before)


if __name__ == "__main__":
    unittest.main()
