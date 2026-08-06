"""The sanctioned-app handoff on the URL block page.

Every assertion here covers something that fails quietly: a redirect that arms on
a page it was never meant for, one that fires off a security block, a target the
page took from the blocked site rather than from config, or a feature that is
"off" and still costs bytes on every page of every theme.
"""

import copy
import functools
import json
import pathlib
import re
import shutil
import subprocess
import tempfile
import unittest
from typing import ClassVar

from _build import translated_strings
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

# Styles that declare room for the notice. nyan does not -- see redirect.supported.
SUPPORTING = [t for t in THEMES if redirect.supported(t)]
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


@functools.lru_cache(maxsize=1)
def german_data_dir() -> pathlib.Path:
    """A copy of the shipped data directory with a second language in it.

    A copy, never DATA itself: that tree is the installed package the rest of the
    suite builds from, and a strings file written into it would decide the
    outcome of tests that have nothing to do with languages.
    """
    root = pathlib.Path(tempfile.mkdtemp(prefix="panos-rp-rx-lang-")) / "data"
    shutil.copytree(DATA, root)
    (root / "strings" / "de.json").write_text(json.dumps(translated_strings()), encoding="utf-8")
    return root


def german(translation, **over):
    """`configured()` with German compiled in and the notice translated."""
    cfg = configured(**over)
    cfg["languages"] = ["en", "de"]
    cfg["translations"] = {"de": {"redirect": translation}}
    return cfg


def render_german(cfg, theme=None):
    root = german_data_dir()
    return strip_output(build_page("url-block-page", theme or THEMES[0], cfg, PALETTE, False, root / "templates"))


def script_of(html):
    """The redirect script only.

    Found by its contents, not by position. It used to be "the last <script> on
    the page", which held until a shell appended one of its own after
    {{SCRIPTS}} -- nyan does, for the flight -- and every assertion about the
    redirect then ran against the wrong script and failed for the wrong reason.

    Split rather than matched: a regexp over <script> tags reads as a broken
    HTML sanitizer to code scanning (it misses <SCRIPT>, attributes, comments),
    and the alert is noise on a helper that only ever sees markup this repo
    emitted itself.

    `var R={` and not `var R=`: the language block declares a `var R=Q('#rep')`
    of its own, so on a multi-language page the looser test returns the CATEGORY
    script and every assertion below runs against the wrong one.
    """
    for block in html.split("<script>")[1:]:
        body = block.split("</script>")[0]
        if "var R={" in body:
            return body
    return ""


def map_of(html):
    return json.loads(re.search(r"var R=(\{.*?\});", script_of(html), re.S).group(1))


def lang_table(html):
    """The per-language notice table, or None when the build compiled one language."""
    found = re.search(r"var X=(\{.*?\})\[document\.documentElement\.lang\]", script_of(html), re.S)
    return json.loads(found.group(1)) if found else None


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
            parts = redirect.emit(configured(), page, SUPPORTING[0], data_dir=DATA)
            if page == redirect.PAGE:
                self.assertTrue(all(parts))
            else:
                self.assertEqual(parts, ("", "", ""))


class TestEveryTheme(unittest.TestCase):
    def test_every_supporting_shell_renders_the_notice_and_its_styles(self):
        """A style is a shell plus a theme and both are discovered by globbing, so
        a shell that never got the slots would build clean and ship nothing."""
        for theme in SUPPORTING:
            html = render(configured(), theme=theme)
            self.assertIn('id="rx"', html, f"{theme['name']} has no notice markup")
            self.assertIn(".rx{", html, f"{theme['name']} has no notice CSS")
            self.assertIn("rxg", script_of(html), f"{theme['name']} has no redirect script")

    def test_it_uses_the_shell_palette_rather_than_its_own_colours(self):
        """Structural CSS only. A literal colour here would look wrong in five of
        the six themes and in every palette."""
        self.assertNotIn("#", redirect.CSS)

    def test_a_style_that_does_not_declare_it_costs_nothing(self):
        """Opting out has to be as free as the feature being off, or the flag is
        just a switch for whether the page is broken."""
        for theme in [t for t in THEMES if not redirect.supported(t)]:
            html = render(configured(), theme=theme)
            for fragment in ('id="rx"', ".rx{", "rxg", "data-off"):
                self.assertNotIn(fragment, html, f"{theme['name']} opted out but carries {fragment}")

    def test_the_flag_is_honest_about_what_fits(self):
        """The point of the flag. `supported` is a claim in a JSON file that
        nothing else checks, and the cost of it being wrong is invisible: PAN-OS
        drops an oversize page and serves its own default, so the style looks
        like it was never imported rather than like it was too big.
        """
        for theme in SUPPORTING:
            html = render(configured(), theme=theme)
            size, errors, _warnings = validate(redirect.PAGE, html)
            self.assertEqual(errors, [], f"{theme['name']} claims redirect support: {errors}")
            self.assertLess(
                size,
                WARN_BYTES,
                f"{theme['name']} claims redirect support but is {size} B with the notice on "
                f'-- either shrink the style or drop "redirect" from its theme file',
            )

    def test_a_style_that_cannot_fit_it_has_not_claimed_it(self):
        """The other direction: a style opted out for a reason, and the reason is
        checkable. If this fails because the style now fits, delete it and set the
        flag -- do not delete it to make the suite green."""
        for theme in [t for t in THEMES if not redirect.supported(t)]:
            forced = dict(theme)
            forced["redirect"] = True
            size, _errors, _warnings = validate(redirect.PAGE, render(configured(), theme=forced))
            self.assertGreaterEqual(
                size,
                WARN_BYTES,
                f"{theme['name']} does not declare redirect support but fits at {size} B",
            )


class TestTimer(unittest.TestCase):
    def test_the_shipped_default_reaches_the_page(self):
        """Stated against the constant, not a literal: `DEFAULT_SECONDS == 10`
        cannot fail, and pinning the shipped config to a second copy of the
        number just means editing the default takes two edits."""
        self.assertEqual(shipped()["redirect"]["seconds"], redirect.DEFAULT_SECONDS)
        self.assertIn(f"var S={redirect.DEFAULT_SECONDS},", script_of(render(configured())))

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
        self.assertIn(".split('{app}').join(n)", script_of(render(configured())))


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

    def test_a_category_absent_from_the_map_is_calm_and_may_redirect(self):
        """`categories` lists the ones whose tone or copy differs, not all 90.

        An absent category already renders calm with defaultGloss in the browser,
        so refusing to build one here contradicted the page it was guarding: a
        customer redirecting a category that needs no tailored copy had to invent
        an entry for it just to satisfy the check.
        """
        cfg = configured()
        cfg["redirect"]["categories"]["nonesuch"] = {"app": "X", "url": "https://x.example.com/"}
        self.assertNotIn("nonesuch", cfg["categories"])

        table = json.loads(re.search(r"var R=(\{.*?\});", script_of(render(cfg))).group(1))
        self.assertIn("nonesuch", table)

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


class TestPreviewDemo(unittest.TestCase):
    """The gallery's Redirect toggle.

    It exists so the handoff can be evaluated before it is switched on, which
    means it deliberately ignores `redirect.enabled`. Everything here guards the
    consequence of that: a preview-only build that can never be mistaken for, or
    leak into, the bytes the firewall serves.
    """

    def demo(self, cfg=None, theme=None):
        return strip_output(
            build_page("url-block-page", theme or THEMES[0], cfg or shipped(), PALETTE, True, TEMPLATES, True)
        )

    def test_it_arms_on_a_config_that_has_not_enabled_it(self):
        """The whole point: `enabled` is false on every config until someone opts
        in, and a toggle that showed nothing until then would demonstrate the
        feature only to people who had already committed to it."""
        cfg = shipped()
        self.assertFalse(cfg["redirect"]["enabled"])
        self.assertFalse(cfg["redirect"]["categories"])
        self.assertIn('<div class="rx"', self.demo(cfg))

    def test_it_stands_in_a_calm_category_or_the_notice_could_never_show(self):
        """The sample category is command-and-control, which is critical, and the
        page refuses to forward anyone off a security block -- correctly. Without
        this substitution the demo would render a notice its own script hides."""
        self.assertIn(f'id="cat">{redirect.DEMO_CATEGORY}<', self.demo())
        self.assertIn(
            'id="cat">command-and-control<',
            build_page("url-block-page", THEMES[0], shipped(), PALETTE, True, TEMPLATES),
        )

    def test_a_configured_category_is_demonstrated_instead_of_the_built_in_one(self):
        """A customer who has mapped their own targets is shown theirs. The demo
        entry is a fallback for an empty table, not an override of a full one."""
        html = self.demo(configured())
        self.assertIn('id="cat">social-networking<', html)
        self.assertIn("Company Engage", html)
        self.assertNotIn(redirect.DEMO_APP["app"], html)

    def test_the_demo_category_gets_a_tone_and_a_gloss_of_its_own(self):
        """It is not one of the shipped `categories`, and a redirect on a category
        the map cannot resolve to `calm` is refused by the page's own guard."""
        cfg = redirect.demo_config(shipped())
        self.assertEqual(cfg["categories"][redirect.DEMO_CATEGORY]["tone"], "calm")
        self.assertIn(redirect.DEMO_CATEGORY, map_of(self.demo()))

    def test_it_loops_instead_of_navigating(self):
        """A srcdoc frame on file:// has nowhere to hand over to: navigating it
        would leave the gallery and need the network."""
        script = script_of(self.demo())
        self.assertIn("function go(){l=t;w()}", script)
        self.assertNotIn("location.replace", script)

    def test_everything_but_the_handover_is_the_script_that_ships(self):
        """Stay, Escape, the background-tab pause and the loop guard are not
        preview stand-ins -- a demo that reimplemented them would stop being
        evidence about the page that ships."""
        script = script_of(self.demo(configured()))
        for shipped_behaviour in ("document.hidden", "'Escape'", "h.host===location.host", "data-off"):
            self.assertIn(shipped_behaviour, script)

    def test_the_looping_build_can_never_be_a_deploy_build(self):
        """The one mistake that would ship a countdown that never hands over."""
        with self.assertRaises(BuildError):
            build_page("url-block-page", THEMES[0], configured(), PALETTE, False, TEMPLATES, True)

    def test_it_changes_nothing_for_any_other_page(self):
        """`redirect_demo` is ignored off the url-block page rather than being an
        error, so the builder can pass it without knowing which page it is on."""
        for page in sorted(set(PAGE_TOKENS) - {"url-block-page"}):
            with self.subTest(page=page):
                plain = build_page(page, THEMES[0], shipped(), PALETTE, True, TEMPLATES)
                self.assertEqual(build_page(page, THEMES[0], shipped(), PALETTE, True, TEMPLATES, True), plain)

    def test_it_does_not_mutate_the_config_the_other_pages_are_built_from(self):
        """The builder holds one config and builds nine pages from it afterwards.
        A demo that switched the redirect on in place would arm every one."""
        cfg = shipped()
        before = copy.deepcopy(cfg)
        self.demo(cfg)
        self.assertEqual(cfg, before)

    def test_every_supporting_theme_renders_it(self):
        for th in SUPPORTING:
            with self.subTest(theme=th["name"]):
                self.assertIn('<div class="rx"', self.demo(theme=th))

    def test_a_style_without_room_gets_no_demo_either(self):
        """The gallery must not offer a toggle whose On is a page the customer
        could never deploy -- the preview would be advertising a combination the
        firewall drops."""
        for th in [t for t in THEMES if not redirect.supported(t)]:
            with self.subTest(theme=th["name"]):
                self.assertNotIn('<div class="rx"', self.demo(theme=th))


class TestNoticeCopyEscaping(unittest.TestCase):
    """The announcement used to be concatenated into a single-quoted JS literal.

    It is "Stay" and plain English today, so nothing breaks -- but this is COPY,
    in a strings file a translator edits, and an apostrophe in it would emit
    syntactically broken JavaScript that Python cannot catch. Every string
    spliced into the script goes through json.dumps for that reason; this is
    what says so. Written against the strings document rather than a Python
    constant because that is where the words live now.
    """

    APOSTROPHES: ClassVar = {
        "go": "Let's go",
        "stay": "Don't go",
        "cancelled": "You're staying here.",
        "cancelledAnnounce": "Cancelled. You're staying here.",
        "announce": "You'll be sent to {app} in {n} seconds. Choose Don't go to stay.",
    }

    def data_dir_with(self, notice):
        root = pathlib.Path(tempfile.mkdtemp(prefix="panos-rp-rx-copy-")) / "data"
        shutil.copytree(DATA, root)
        path = root / "strings" / "en.json"
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc["shared"]["redirect"] = notice
        path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        return root

    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_an_apostrophe_anywhere_in_the_notice_copy_still_parses(self):
        root = self.data_dir_with(self.APOSTROPHES)
        html = strip_output(build_page("url-block-page", THEMES[0], configured(), PALETTE, False, root / "templates"))
        script = script_of(html)
        self.assertIn("You'll be sent to", script)
        self.assertIn("Don't go", html, "the base language's buttons are markup, not script")
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
            f.write(script)
            path = pathlib.Path(f.name)
        try:
            result = subprocess.run(  # noqa: S603
                ["node", "--check", str(path)],  # noqa: S607
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
        finally:
            path.unlink()


class TestTheNoticeActuallyArms(unittest.TestCase):
    """The two scripts run in sequence, against a DOM, and the notice un-hides.

    Every other test in this file asserts that markup and script are PRESENT.
    None of them ran the page. That gap shipped a redirect that never armed on
    any theme: category_js rewrites #cat's textContent to a friendly label
    before this script reads it, so the lookup missed and the notice -- which
    ships `hidden` -- silently stayed hidden. Nothing was missing from the page;
    the two halves simply disagreed about what #cat holds.

    Asserting on the observable end state, not on how the key is passed, so a
    future change to that mechanism is free as long as the notice still arms.
    """

    HARNESS = """
    const cat={textContent:RAW,attrs:{},setAttribute(k,v){this.attrs[k]=v},
               getAttribute(k){return k in this.attrs?this.attrs[k]:null}};
    const rx={hidden:true,attrs:{},setAttribute(k,v){this.attrs[k]=v}};
    const mk=()=>({textContent:'',hidden:false,style:{},href:'',
                   setAttribute(){},getAttribute(){return null},addEventListener(){}});
    const els={cat,rx,gloss:mk(),rxm:mk(),rxo:mk(),rxi:mk(),rxp:mk(),rxl:mk(),
               rxg:mk(),rxs:mk(),ts:mk(),rep:null};
    const root={attrs:{'data-tone':'calm'},setAttribute(k,v){this.attrs[k]=v},
                getAttribute(k){return this.attrs[k]||null}};
    global.document={getElementById:id=>(id in els?els[id]:null),querySelector:()=>null,
                     querySelectorAll:()=>[],documentElement:root,
                     createElement:()=>({href:'',host:'sanctioned.example'}),
                     addEventListener(){}};
    global.location={host:'blocked.example',replace(){}};
    global.setInterval=()=>1;global.clearInterval=()=>{};
    """

    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_the_notice_un_hides_for_a_mapped_category(self):
        for theme in SUPPORTING:
            with self.subTest(theme=theme["name"]):
                html = render(configured(), theme=theme)
                self.assertEqual(self._run(html, "social-networking")["hidden"], False)

    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_it_stays_hidden_for_a_category_that_is_not_mapped(self):
        """The other direction, or the test above would pass on a script that
        un-hid the notice unconditionally."""
        html = render(configured(), theme=SUPPORTING[0])
        self.assertEqual(self._run(html, "malware")["hidden"], True)

    def _run(self, html: str, category: str) -> dict:
        blocks = re.findall(r"<script>\(function\(\)\{(.*?)\}\)\(\);</script>", html, re.S)
        cat_js = next(b for b in blocks if "var M=" in b)
        rx_js = next(b for b in blocks if "var R=" in b)
        # Page order: the category script resolves the tone, then the redirect
        # script reads it. Running them the other way round would pass on the
        # very bug this exists to catch.
        script = (
            f"const RAW={json.dumps(category)};{self.HARNESS}"
            f"(function(){{{cat_js}}})();(function(){{{rx_js}}})();"
            "console.log(JSON.stringify({hidden:els.rx.hidden}));"
        )
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
            f.write(script)
            path = pathlib.Path(f.name)
        try:
            r = subprocess.run(["node", str(path)], capture_output=True, text=True, check=False)  # noqa: S603,S607
            self.assertEqual(r.returncode, 0, r.stderr)
            return json.loads(r.stdout.strip().splitlines()[-1])
        finally:
            path.unlink()


class TestTheNoticeIsTranslated(unittest.TestCase):
    """The notice is the last user-visible sentence no language path reached.

    A customer who enables the redirect and configures German used to get a
    German page with one English sentence in it: `redirect.message` is
    customer-authored copy, and the translatable-key tuple was flat, so neither
    it nor a per-category override could be named.

    Every fallback here is to the TRANSLATED default, never to English. A
    category whose override nobody translated is the case that matters: falling
    back to its English override would put an English sentence in a German page
    for exactly the categories a customer cared enough to write copy for.
    """

    DEFAULT_DE = "Weiterleitung zu {app} — die freigegebene Alternative."
    VIDEO_DE = "Sieh es auf {app} an."

    def test_a_single_language_build_carries_no_table(self):
        """The byte-identity promise, where this feature would break it: one
        language means the notice has nothing to select between."""
        script = script_of(render(configured()))
        self.assertIsNone(lang_table(render(configured())))
        self.assertNotIn("var X=", script)
        self.assertIn("m.textContent=(r[3]||D).split('{app}').join(n);", script)

    def test_the_default_notice_is_translated(self):
        table = lang_table(render_german(german({"message": self.DEFAULT_DE})))
        self.assertEqual(table["de"]["m"], self.DEFAULT_DE)

    def test_a_per_category_override_is_translated(self):
        cfg = german({"message": self.DEFAULT_DE, "categories": {"streaming-media": self.VIDEO_DE}})
        table = lang_table(render_german(cfg))
        self.assertEqual(table["de"]["c"], {"streaming-media": self.VIDEO_DE})

    def test_an_untranslated_category_takes_the_translated_default(self):
        """Not the English one. `social-networking` carries an English override
        here and no German one, so the German reader must get the German default
        sentence rather than the English override the config happens to hold."""
        cfg = german({"message": self.DEFAULT_DE})
        cfg["redirect"]["categories"]["social-networking"]["message"] = "Head over to {app} instead."
        html = render_german(cfg)
        self.assertNotIn("c", lang_table(html)["de"], "nothing was translated per category")
        self.assertIn("m.textContent=(X&&(X.c&&X.c[y]||X.m)||r[3]||D)", script_of(html))

    def test_a_translation_for_an_unmapped_category_is_not_shipped(self):
        """The table is keyed on `redirect.categories`, so a sentence for
        anything else has nothing to key on and would be bytes no page can
        reach -- on the one page already closest to the ceiling."""
        cfg = german({"message": self.DEFAULT_DE, "categories": {"nowhere": "Zu {app}."}})
        self.assertNotIn("nowhere", script_of(render_german(cfg)))

    def test_the_app_token_survives_translation(self):
        """`{app}` is substituted by this module, not by substitute(), so it is a
        different token syntax that resolve() and assert_resolved() both ignore.
        A German sentence that lost it renders a notice naming no application,
        and nothing in the build would say so."""
        cfg = german({"message": self.DEFAULT_DE, "categories": {"streaming-media": self.VIDEO_DE}})
        table = lang_table(render_german(cfg))
        self.assertIn("{app}", table["de"]["m"])
        self.assertIn("{app}", table["de"]["c"]["streaming-media"])

    def test_the_german_text_is_not_escaped_into_six_bytes_a_character(self):
        """This ships inside the one page that carries the notice, under the
        same ceiling as everything else on it."""
        self.assertIn("—", script_of(render_german(german({"message": self.DEFAULT_DE}))))

    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_a_german_browser_reads_the_translated_notice_with_the_app_named(self):
        """End to end, against a DOM: the language block picks German and sets
        documentElement.lang, then the notice reads it. The `{app}` assertion
        above proves the token reached the page; this proves it still resolves
        to the application name once it has."""
        cfg = german({"message": self.DEFAULT_DE, "categories": {"streaming-media": self.VIDEO_DE}})
        html = render_german(cfg)
        self.assertEqual(self._run(html, "streaming-media")["message"], "Sieh es auf Company Video an.")
        self.assertEqual(
            self._run(html, "social-networking")["message"],
            "Weiterleitung zu Company Engage — die freigegebene Alternative.",
            "an untranslated category fell back to English instead of to the translated default",
        )

    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_an_english_browser_still_reads_the_configured_notice(self):
        """The other direction. The swap is keyed on documentElement.lang, which
        the language block only assigns when it matched -- so a browser that
        matched nothing must keep the sentence the page was served with."""
        cfg = german({"message": self.DEFAULT_DE})
        got = self._run(render_german(cfg), "social-networking", lang="en")["message"]
        self.assertEqual(got, "Taking you to Company Engage — the approved alternative for this.")

    def _run(self, html: str, category: str, lang: str = "de") -> dict:
        return run_notice(self, html, category, lang)


def run_notice(test: unittest.TestCase, html: str, category: str, lang: str = "de") -> dict:
    """Run a built page's two scripts against the stub DOM and report the notice.

    Module level because two classes need it: the sentence and the furniture
    around it are swapped by the same script from the same table, and running
    them under two different harnesses would let the two drift.
    """
    blocks = re.findall(r"<script>\(function\(\)\{(.*?)\}\)\(\);</script>", html, re.S)
    cat_js = next(b for b in blocks if "var M=" in b)
    # `var R={`, for the reason script_of() gives: the language block has a
    # `var R=Q('#rep')` of its own, and this page carries both scripts.
    rx_js = next(b for b in blocks if "var R={" in b)
    # defineProperty, not assignment: `navigator` is a read-only accessor on
    # modern Node, so `global.navigator = {...}` fails SILENTLY and the page
    # would be selected against the host's own locale instead of this one.
    script = (
        f"const RAW={json.dumps(category)};"
        f"Object.defineProperty(global,'navigator',"
        f"{{value:{{languages:[{json.dumps(lang)}]}},configurable:true,writable:true}});"
        f"{TestTheNoticeActuallyArms.HARNESS}"
        f"(function(){{{cat_js}}})();(function(){{{rx_js}}})();"
        "console.log(JSON.stringify({hidden:els.rx.hidden,message:els.rxm.textContent,"
        "go:els.rxg.textContent,stay:els.rxs.textContent,cancelled:els.rxo.textContent,"
        "announce:els.rxl.textContent}));"
    )
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(script)
        path = pathlib.Path(f.name)
    try:
        r = subprocess.run(["node", str(path)], capture_output=True, text=True, check=False)  # noqa: S603,S607
        test.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        path.unlink()


class TestTheNoticeFurnitureIsTranslated(unittest.TestCase):
    """The other half of the notice: its two buttons, its cancelled line, and the
    two sentences a screen reader is read.

    Task 8b translated the MESSAGE and stopped. A German build then read "Sie
    werden zu Company Drive weitergeleitet" above buttons labelled "Go now" and
    "Stay", and read the whole English announcement out to a screen reader --
    half-translated output from a clean build, which is the failure this project
    exists to refuse. They are shipped copy, so they live in the strings document
    and ride the same table as the sentence.
    """

    DEFAULT_DE = "Weiterleitung zu {app} — die freigegebene Alternative."

    def test_the_base_language_words_are_markup(self):
        """The markup IS the base language, here as everywhere else: a browser
        with no JavaScript, and every browser that matches nothing, reads them."""
        html = render(configured())
        for word in ("Go now", "Stay", "Staying on this page."):
            self.assertIn(word, html, f"the notice lost its base-language {word!r}")

    def test_every_language_carries_the_furniture_translated_or_not(self):
        """Shipped copy, so it is there whether or not the customer wrote a
        sentence of their own -- otherwise a customer who enabled the redirect
        and translated nothing would get German copy under English buttons."""
        table = lang_table(render_german(german({})))
        self.assertEqual(table["de"]["g"], "de:Go now")
        self.assertEqual(table["de"]["s"], "de:Stay")
        self.assertEqual(table["de"]["o"], "de:Staying on this page.")
        self.assertNotIn("m", table["de"], "nobody translated the sentence")

    def test_a_single_language_build_carries_none_of_it(self):
        """The byte-identity rule this whole feature is built under: one language
        has nothing to select between, so it pays for no table and no swap."""
        script = script_of(render(configured()))
        self.assertNotIn("X.g", script)
        self.assertNotIn("var X=", script)

    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_a_german_browser_gets_german_buttons_and_announcement(self):
        html = render_german(german({"message": self.DEFAULT_DE}))
        got = run_notice(self, html, "social-networking")
        self.assertEqual(got["go"], "de:Go now")
        self.assertEqual(got["stay"], "de:Stay")
        self.assertEqual(got["cancelled"], "de:Staying on this page.")
        # The announcement is a sentence with two tokens, not a concatenation:
        # the app name and the countdown are values only the browser has, and a
        # translation has to be free to put them where its grammar wants.
        self.assertEqual(
            got["announce"],
            "de:You will be sent to Company Engage in 10 seconds. "
            "Choose Stay, or press Escape, to remain on this page.",
        )

    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_an_unmatched_browser_is_announced_the_base_language_sentence(self):
        """The other direction, and the token substitution with no table in play:
        a browser that matched nothing keeps the page it was served."""
        cfg = german({"message": self.DEFAULT_DE})
        got = run_notice(self, render_german(cfg), "social-networking", lang="en")
        self.assertEqual(
            got["announce"],
            "You will be sent to Company Engage in 10 seconds. Choose Stay, or press Escape, to remain on this page.",
        )
        self.assertEqual(got["go"], "", "the served markup was overwritten for a language nothing matched")


class TestTheReportLabelPrefersItsOwnButton(unittest.TestCase):
    """`Q('a.btn#rep')||Q('a.btn')`, pinned against the page that made it matter.

    The language block writes the report label into the first `a.btn` it finds.
    With the redirect on, the notice's "Go now" anchor is an `a.btn` and it comes
    FIRST in document order -- so the bare selector writes "Report to IT" into
    the Go button and leaves the real report button in the base language. This
    was a long comment and no test; it is a live combination, not a theoretical
    one, so it is asserted against a built page.
    """

    BTN_RE = re.compile(r"<a\b[^>]*\bclass=\"[^\"]*\bbtn\b[^\"]*\"[^>]*>")

    def buttons(self, html):
        """Every `a.btn` on the page, in document order -- what querySelector walks."""
        return self.BTN_RE.findall(html)

    def first(self, html, require_rep):
        """querySelector's answer for `a.btn#rep` (require_rep) or for `a.btn`."""
        for tag in self.buttons(html):
            if not require_rep or 'id="rep"' in tag:
                return tag
        return ""

    def html(self):
        cfg = german({"message": TestTheNoticeFurnitureIsTranslated.DEFAULT_DE})
        return render_german(cfg, theme=SUPPORTING[0])

    def test_the_bare_selector_would_hit_the_redirect_button(self):
        """The premise. If this ever fails because the notice moved below the
        actions, the comment in scripts.py is what needs re-reading -- not this."""
        html = self.html()
        self.assertGreater(len(self.buttons(html)), 1, "the page carries only one a.btn; nothing is being pinned")
        self.assertIn('id="rxg"', self.first(html, require_rep=False), "the redirect anchor is no longer first")

    def test_the_pinned_selector_hits_the_report_button(self):
        html = self.html()
        self.assertIn('id="rep"', self.first(html, require_rep=True))

    def test_the_page_emits_the_pinned_selector(self):
        """The two halves together: the selector the page ships is the one that
        picks the report button, and reverting it to `Q('a.btn')` would write the
        report label into the Go button on this exact page."""
        self.assertIn("var B=Q('a.btn#rep')||Q('a.btn');", self.html())


class TestPreviewDemoIsNotShipped(unittest.TestCase):
    def test_the_builder_writes_it_only_under_preview(self):
        import pathlib
        import tempfile

        from panos_response_pages.builder import build_all

        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp)
            build_all(data_dir=DATA, out_dir=out, theme=THEMES[0]["name"], palette_name="cyber-orange", preview=True)
            name = f"url-block-page{redirect.PREVIEW_SUFFIX}.html"
            self.assertTrue((out / "preview" / THEMES[0]["name"] / "cyber-orange" / name).is_file())
            self.assertFalse((out / "deploy" / THEMES[0]["name"] / "cyber-orange" / name).exists())

    def test_it_is_not_counted_as_a_page(self):
        """`results` is asserted against the length of PAGE_TOKENS elsewhere; a
        preview variant appearing there would be a page PAN-OS never serves."""
        import pathlib
        import tempfile

        from panos_response_pages.builder import build_all

        with tempfile.TemporaryDirectory() as tmp:
            r = build_all(
                data_dir=DATA,
                out_dir=pathlib.Path(tmp),
                theme=THEMES[0]["name"],
                palette_name="cyber-orange",
                preview=True,
            )
            self.assertEqual(sorted(x.page for x in r.results), sorted(set(PAGE_TOKENS)))


class TestStaleDataDirectory(unittest.TestCase):
    """A data directory copied out by `init` before the per-style flag existed.

    `datadir` prefers that copy over the packaged data, so every theme in it
    lacks the flag and the redirect turns itself off everywhere. The symptom is
    the notice simply not appearing, which reads as the feature being broken
    rather than as the directory being old -- so the build has to say so.
    """

    def stale_data_dir(self, tmp):
        """A copy of the packaged data with the flag stripped from every theme."""
        import shutil

        data = pathlib.Path(tmp) / "data"
        shutil.copytree(DATA, data)
        for path in (data / "themes").glob("*.json"):
            theme = json.loads(path.read_text())
            theme.pop("redirect", None)
            path.write_text(json.dumps(theme))
        cfg = json.loads((data / "config" / "_defaults.json").read_text())
        cfg["redirect"]["enabled"] = True
        cfg["redirect"]["categories"] = {
            "social-networking": {"app": "Company Engage", "url": "https://engage.example.com/"}
        }
        (data / "config" / "_defaults.json").write_text(json.dumps(cfg))
        return data

    def build_and_capture(self, data_dir):
        import logging
        import tempfile

        from panos_response_pages.builder import build_all

        with self.assertLogs("panos_response_pages", level=logging.WARNING) as caught:
            with tempfile.TemporaryDirectory() as out:
                build_all(data_dir=data_dir, out_dir=pathlib.Path(out), preview=False, palette_name="cyber-orange")
            return "\n".join(caught.output)

    def test_a_theme_with_no_flag_is_named_in_a_warning(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            logged = self.build_and_capture(self.stale_data_dir(tmp))
        for theme in THEMES:
            self.assertIn(theme["name"], logged, f"{theme['name']} lost the redirect silently")
        self.assertIn("init", logged, "the warning must say how to fix it")

    def test_a_deliberate_opt_out_is_not_warned_about(self):
        """nyan sets the flag to false on purpose. Warning about that would train
        everyone to ignore the warning that matters."""
        import logging
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            data = self.stale_data_dir(tmp)
            for path in (data / "themes").glob("*.json"):
                theme = json.loads(path.read_text())
                theme["redirect"] = theme["name"] != "nyan"
                path.write_text(json.dumps(theme))
            with tempfile.TemporaryDirectory() as out:
                from panos_response_pages.builder import build_all

                logger = logging.getLogger("panos_response_pages")
                with self.assertLogs(logger, level=logging.DEBUG) as caught:
                    logger.debug("marker")
                    build_all(data_dir=data, out_dir=pathlib.Path(out), preview=False, palette_name="cyber-orange")
        self.assertNotIn("no `redirect` flag", "\n".join(caught.output))


if __name__ == "__main__":
    unittest.main()
