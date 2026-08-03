"""The sanctioned-app handoff on the URL block page.

Every assertion here covers something that fails quietly: a redirect that arms on
a page it was never meant for, one that fires off a security block, a target the
page took from the blocked site rather than from config, or a feature that is
"off" and still costs bytes on every page of every theme.
"""

import copy
import json
import pathlib
import re
import shutil
import subprocess
import tempfile
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


def script_of(html):
    """The redirect script only.

    Found by its contents, not by position. It used to be "the last <script> on
    the page", which held until a shell appended one of its own after
    {{SCRIPTS}} -- nyan does, for the flight -- and every assertion about the
    redirect then ran against the wrong script and failed for the wrong reason.
    """
    for block in re.findall(r"<script>(.*?)</script>", html, re.S):
        if "var R=" in block:
            return block
    return ""


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
            parts = redirect.emit(configured(), page, SUPPORTING[0])
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


class TestStayLabelEscaping(unittest.TestCase):
    """STAY_LABEL used to be concatenated straight into a single-quoted JS
    literal. It is "Stay" today, so nothing breaks -- but pure copy editing
    that gave it an apostrophe would emit syntactically broken JavaScript that
    Python cannot catch and nothing asserted against. It is now wrapped with
    json.dumps, as CANCELLED_ANNOUNCE already is a few lines above."""

    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_an_apostrophe_in_stay_label_still_produces_parseable_js(self):
        original = redirect.STAY_LABEL
        redirect.STAY_LABEL = "Don't go"
        try:
            script = script_of(render(configured()))
        finally:
            redirect.STAY_LABEL = original

        self.assertIn("Don't go", script)
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
