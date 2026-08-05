"""The sanctioned-app handoff on the URL block page.

When a blocked category has a company-sanctioned equivalent -- personal file
storage against the corporate drive, consumer webmail against corporate mail --
the page can say so and hand the user over after a countdown.

Opt-in, and off unless a customer both sets `redirect.enabled` and maps at least
one category. Nothing here reaches a page otherwise: the CSS, the markup and the
script are all empty strings, and a build with the feature off is byte-identical
to one from before it existed.

Three rules are enforced here rather than left to the config author, because each
of them fails in a way the author would not see:

* **Only a `calm` category may carry a redirect.** Checked at build time, and
  again in the browser against the tone the category map resolved. Automatically
  forwarding a user off a malware or phishing block is indefensible, and a typo
  in a tone must not be able to cause it. A category the map does not list is
  calm -- that map carries the ones that differ, not all 90 -- so it needs no
  entry to redirect.
* **The target is an absolute https URL from config.** Never `<url/>` -- that
  value is chosen by whoever the user was trying to reach, and a redirect built
  from it would make every firewall serving this page an open redirector.
* **At most one hop, ever.** A response page is served *as* the blocked site, so
  `location.host` is the host the user was refused. If that is the host of any
  sanctioned app in the table, this page is a blocked sanctioned app and the hop
  that landed the user here was ours -- so it does not hop again. A hop only ever
  targets something in this table, which means every cycle passes through one of
  these hosts, including cycles that never repeat a host. What it cannot prevent
  is the first hop into a blocked app: the target still has to be permitted by
  the policy that produced the block, and only policy can do that.
"""

from __future__ import annotations

import copy
import json
import pathlib
from collections.abc import Mapping
from typing import Any

from panos_response_pages import i18n
from panos_response_pages.errors import BuildError
from panos_response_pages.scripts import CATEGORY_KEY_ATTR

# Only this page. The other eight either have no <category/> token to key on, or
# already carry an action of their own that a countdown would race.
PAGE = "url-block-page"

DEFAULT_SECONDS = 10

# What the gallery's demo build is called, as a blob key and as a file beside the
# ordinary preview. A suffix rather than a tenth page: PAGE_TOKENS is the set of
# pages PAN-OS serves, and a preview-only variant is not one of them.
PREVIEW_SUFFIX = "-redirect"

# What the gallery demonstrates when a config maps nothing of its own. It is the
# worked example from `_defaults.json`, deliberately: someone who reaches for the
# config after seeing this in the preview finds the same names written down.
#
# `online-storage-and-backup` is not one of the shipped `categories`, so
# demo_config() contributes a tone and a gloss for it as well. Not for the tone,
# which would default to calm anyway, but for the GLOSS: the preview is what a
# reader judges the feature by, and the generic fallback sentence under a named
# sanctioned app reads like the config was half-finished.
DEMO_CATEGORY = "online-storage-and-backup"
DEMO_APP = {"app": "Company Drive", "url": "https://drive.example.com/"}
DEMO_GLOSS = "Personal file-storage services are not available on the company network."

# The notice's own copy -- the two buttons, the line that replaces the sentence
# when the user stays, and the two things a screen reader is told -- lives in the
# strings document under `shared.redirect`, and reaches this module through
# i18n.notice_strings() and i18n.redirect_strings(). It used to be four Python
# constants, which is the one place no language can reach: a German build read
# "Sie werden zu Company Drive weitergeleitet" above buttons labelled "Go now"
# and "Stay", and read the whole English sentence out to a screen reader.

# The notice itself. Structural only -- every colour comes from the shell's own
# custom properties, so a theme styles this by existing rather than by opting in.
#
# The countdown bar is an overlay on the border box, not a row inside it. In flow
# it sat one border in from the left and one up from the bottom, and the rounded
# corner clipped its left end, so the accent bar and the accent left border met
# in a notch. Sitting on the border box instead, under a clip with the same
# radius, the two are one continuous stroke turning the corner. `.rx` therefore
# cannot carry `overflow:hidden` -- that clips to the padding box, which is the
# inset the overlay exists to escape.
CSS = """
.rx{position:relative;margin:0 0 1.4rem;max-width:31rem;border:1px solid var(--aw);
border-left:3px solid var(--ac);border-radius:.5rem;background:var(--sa)}
.rx-b{display:flex;align-items:center;gap:.7rem;padding:.7rem .85rem;flex-wrap:wrap}
.rx-i{flex:none;width:1.9rem;height:1.9rem;border-radius:50%;background:var(--ac);color:var(--ai);
display:grid;place-items:center;font-style:normal;font-size:.8rem;font-weight:700;
font-variant-numeric:tabular-nums}
.rx-t{flex:1 1 12rem;min-width:0;font-size:.8rem;line-height:1.5;color:var(--ik)}
.rx-c{display:flex;gap:.5rem;align-items:center}
.rx-c .btn{min-height:2.2rem;padding:.4rem 1rem;font-size:.78rem;box-shadow:none}
.rx button{font:inherit;font-size:.76rem;min-height:2.2rem;padding:.4rem .9rem;border-radius:.45rem;
border:1px solid var(--aw);background:transparent;color:var(--im);cursor:pointer}
.rx-p{position:absolute;left:-3px;right:-1px;bottom:-1px;height:.5rem;border-radius:0 0 .5rem .5rem;
overflow:hidden;background:linear-gradient(var(--aw),var(--aw)) 0 100%/100% 3px no-repeat}
.rx-p span{position:absolute;left:0;bottom:0;height:3px;width:0;background:var(--ac);transition:width 1s linear}
.rx-sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.rx[data-off] .rx-p span{background:var(--if)}
.rx[data-off] .rx-i,.rx[data-off] .rx-c{display:none}
@media(prefers-reduced-motion:reduce){.rx-p span{transition:none}}
"""


# hidden until the script has decided the category qualifies: an unstyled notice
# flashing before the countdown starts is worse than no notice.
#
# The three words in here are the BASE language's, because the markup IS the base
# language -- the same rule the rest of the page is built on. Every other
# compiled language swaps them from the table in _script().
def _markup(notice: Mapping[str, str]) -> str:
    return f"""
<div class="rx" id="rx" hidden>
<div class="rx-b"><i class="rx-i" id="rxi" aria-hidden="true"></i>
<span class="rx-t"><span id="rxm"></span><span id="rxo" hidden>{notice["cancelled"]}</span>
<span class="rx-sr" id="rxl" role="status" aria-live="polite"></span></span>
<span class="rx-c"><a class="btn" id="rxg" href="#">{notice["go"]}</a>
<button type="button" id="rxs">{notice["stay"]}</button></span></div>
<div class="rx-p"><span id="rxp"></span></div>
</div>
"""


def _entries(cfg: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    red = cfg.get("redirect") or {}
    return red.get("categories") or {}


def enabled(cfg: Mapping[str, Any]) -> bool:
    """Both halves must be true: a toggle with no mapping table does nothing."""
    red = cfg.get("redirect") or {}
    return bool(red.get("enabled")) and bool(_entries(cfg))


def supported(theme: Mapping[str, Any]) -> bool:
    """Whether this style has room for the notice. Declared, not measured.

    The notice is a flat 3347 B and PAN-OS drops an oversize response page
    *silently* -- it serves its own default instead, so the failure looks like
    the page was never imported. nyan's URL block page is 15558 B before the
    notice, against a 17999 B ceiling, so it cannot have it.

    A per-theme flag rather than a size check at build time because the two
    answers are different: a size check would refuse the build for the customer
    who turned the redirect on, punishing them for a property of the style. The
    flag says up front which styles offer the feature, and the test suite holds
    the flag honest by measuring every style that claims it.
    """
    return bool(theme.get("redirect"))


def declares(theme: Mapping[str, Any]) -> bool:
    """Whether this theme file has an opinion about the redirect at all.

    `supported()` cannot tell "this style opted out" from "this theme file was
    written before the flag existed" -- both are falsey. The difference matters:
    the first is a decision, the second is a data directory copied out by `init`
    at some earlier version and never refreshed. `datadir` prefers that copy over
    the packaged data, so an old one silently turns the redirect off for every
    style, which looks like the feature is broken rather than like the directory
    is stale. The build warns on this; it does not warn on a deliberate `false`.
    """
    return "redirect" in theme


def demo_config(cfg: Mapping[str, Any]) -> dict[str, Any]:
    """`cfg` with the redirect forced on, for the gallery's Redirect toggle.

    PREVIEW ONLY. Never reaches a file under `deploy/`: the caller passes it
    solely to build the second url-block blob the toggle switches to.

    Forced rather than read, so the toggle demonstrates the feature to someone
    evaluating it -- including on the shipped config, where `categories` is empty
    and there is nothing real to show. A config that maps its own categories is
    shown its own, so what the preview demonstrates is the customer's copy and
    their target as soon as they write one; only the `enabled` flag is overridden.

    Deep-copied because the caller holds the live config and builds the other
    eight pages from it afterwards.
    """
    out = copy.deepcopy(dict(cfg))
    red = dict(out.get("redirect") or {})
    red.setdefault("seconds", DEFAULT_SECONDS)
    red.setdefault("message", "Taking you to {app} — the approved alternative for this.")
    red["enabled"] = True

    if not red.get("categories"):
        red["categories"] = {DEMO_CATEGORY: dict(DEMO_APP)}
        cats = dict(out.get("categories") or {})
        cats.setdefault(DEMO_CATEGORY, {"tone": "calm", "gloss": DEMO_GLOSS})
        out["categories"] = cats

    out["redirect"] = red
    return out


def demo_category(cfg: Mapping[str, Any]) -> str:
    """Which category the preview must render for the notice to arm.

    The page keys on the substituted `<category/>` value, and the sample one is
    `command-and-control` -- critical, which the redirect correctly refuses. So a
    demo build has to say which category it is standing in for, and the answer is
    the first mapped one rather than a constant: a customer who maps a category
    should see the preview arm on theirs.
    """
    return next(iter(_entries(cfg)), DEMO_CATEGORY)


def check(cfg: Mapping[str, Any]) -> None:
    """Fail the build on a redirect config that would misbehave silently."""
    red = cfg.get("redirect")
    if not red:
        return
    if not isinstance(red.get("enabled", False), bool):
        raise BuildError("redirect.enabled must be true or false")

    seconds = red.get("seconds", DEFAULT_SECONDS)
    _check_seconds(seconds, "redirect.seconds")
    if not str(red.get("message", "")).strip() and _entries(cfg):
        raise BuildError("redirect.message is empty; it is the fallback for every category")

    tones = {name: entry.get("tone") for name, entry in (cfg.get("categories") or {}).items()}
    for name, entry in _entries(cfg).items():
        where = f"redirect.categories.{name}"
        for key in ("app", "url"):
            if not str(entry.get(key, "")).strip():
                raise BuildError(f"{where} has no {key}")
        if not str(entry["url"]).startswith("https://"):
            raise BuildError(
                f"{where}.url must be an absolute https:// URL -- a relative or http target "
                "resolves against the blocked site, which is not ours"
            )
        # Absent means calm. `categories` carries the ones whose tone or copy
        # differs -- spelling all 90 out would blow the byte ceiling -- and the
        # browser already renders an unmapped category calm with defaultGloss.
        # Refusing one here would contradict the page this check guards.
        tone = tones.get(name, "calm")
        if tone != "calm":
            raise BuildError(
                f"{where} has tone '{tone}'; only a calm category may redirect. "
                "A user must not be forwarded off a warning or a security block."
            )
        if "seconds" in entry:
            _check_seconds(entry["seconds"], f"{where}.seconds")

    _check_translations(cfg)


def _check_translations(cfg: Mapping[str, Any]) -> None:
    """A language may not translate the per-category sentences and skip the default.

    The same rule as `redirect.message is empty; it is the fallback for every
    category`, one level down. The runtime's fallback chain is
    `X.c[y] || X.m || <English>`: with per-category sentences translated and no
    translated default, a category nobody wrote copy for falls out of the German
    branch entirely and lands on the English sentence -- inside a German page,
    for exactly the categories the customer did NOT single out.

    Checked against the mapped categories, like _langs() trims against them: a
    sentence for a category `redirect.categories` does not map is bytes no page
    can reach, so it cannot be what makes a missing default fatal.
    """
    entries = _entries(cfg)
    for lang, written in (cfg.get("translations") or {}).items():
        block = (written or {}).get("redirect") or {}
        if not str(block.get("message", "")).strip() and any(k in entries for k in block.get("categories") or {}):
            raise BuildError(
                f"translations.{lang}.redirect has per-category sentences but no `message`. "
                "It is the fallback for every category in that language: without it a category "
                f"nobody translated shows the English sentence inside a {lang} page."
            )


def _check_seconds(value: Any, where: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise BuildError(f"{where} must be a whole number of seconds")
    if not 1 <= value <= 60:
        raise BuildError(f"{where} is {value}; expected 1-60 seconds")


def _map(cfg: Mapping[str, Any]) -> dict[str, list[Any]]:
    """category -> [app, url] (+ seconds, + message) with defaults trimmed off.

    Trailing defaults are dropped rather than repeated: the message is the
    longest value in the table, and a customer who accepts the default one on
    every category should not pay for it once per category.
    """
    red = cfg["redirect"]
    default_seconds = red.get("seconds", DEFAULT_SECONDS)
    default_message = red["message"]
    out: dict[str, list[Any]] = {}
    for name, entry in _entries(cfg).items():
        row: list[Any] = [entry["app"], entry["url"]]
        seconds = entry.get("seconds", default_seconds)
        message = entry.get("message", default_message)
        if message != default_message:
            row += [0 if seconds == default_seconds else seconds, message]
        elif seconds != default_seconds:
            row.append(seconds)
        out[name] = row
    return out


def _langs(cfg: Mapping[str, Any], translations: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """language -> {furniture, m: default notice, c: {category: override}}, trimmed.

    Single-letter keys and absent-means-untranslated, for the same reason _map()
    drops trailing defaults: this rides on the one page that carries the notice,
    under the same byte ceiling as everything else on it.

    `m` and `c` are the CUSTOMER's sentences and are absent until they write
    them. The five furniture strings are shipped copy and are always here: they
    exist in every language whether or not the customer translated anything, and
    a language row carrying only them is what keeps "Go now" and "Stay" from
    sitting under a German sentence.

    Trimmed to the categories `redirect.categories` actually maps. The lookup is
    keyed on that table, so a sentence written for anything else has nothing to
    key on -- it would be bytes no page can reach.
    """
    entries = _entries(cfg)
    out: dict[str, dict[str, Any]] = {}
    for lang, block in translations.items():
        # KeyError is not reachable: i18n.redirect_strings() runs i18n.notice()
        # over every block it returns, which names the language and the key.
        row: dict[str, Any] = {
            "g": block["go"],
            "s": block["stay"],
            "o": block["cancelled"],
            "n": block["cancelledAnnounce"],
            "a": block["announce"],
        }
        message = str(block.get("message") or "")
        if message.strip():
            row["m"] = message
        cats = {k: str(v) for k, v in (block.get("categories") or {}).items() if k in entries and str(v).strip()}
        if cats:
            row["c"] = cats
        out[lang] = row
    return out


def _script(
    cfg: Mapping[str, Any],
    translations: Mapping[str, Mapping[str, Any]],
    notice: Mapping[str, str],
    *,
    loop: bool = False,
) -> str:
    red = cfg["redirect"]
    # Every language-aware fragment below is emitted ONLY when the page compiles
    # a second language. A single-language build has to be the bytes it was
    # before this existed, and there is nothing for it to select between.
    #
    # "a second language", not "a translated sentence": the notice's furniture is
    # shipped copy and exists in every language, so a customer who compiled German
    # and translated none of their own copy still gets German buttons.
    langs = _langs(cfg, translations)
    key = f"e.getAttribute('{CATEGORY_KEY_ATTR}')"
    # The category key is only named when something reads it twice. `y` and not
    # `k`: the loop guard below is a `for(var k in R)`, which is function-scoped
    # and leaves `k` bound to the last host in the table -- a translated notice
    # keyed on that would show the wrong category's sentence, or none.
    lookup = f"var y={key},r=R[y];" if langs else f"var r=R[{key}];"
    # ensure_ascii=False, unlike the tables above: this is the only value here
    # that is not English, and an escaped "a-umlaut" costs six bytes where the
    # character itself costs two, on the page with the least headroom.
    pick = (
        (
            "var X="
            + json.dumps(langs, separators=(",", ":"), ensure_ascii=False)
            # Set by the language block, which runs first and assigns it only
            # when it matched a compiled language. A browser that matched
            # nothing leaves the base language there, which is absent from this
            # table -- so it keeps the sentence the page was served with.
            + "[document.documentElement.lang]||0;"
        )
        if langs
        else ""
    )
    # Every fallback is to the TRANSLATED default, never to the English one: a
    # category whose override nobody translated would otherwise put an English
    # sentence into a German page for exactly the categories a customer cared
    # enough about to write their own copy for.
    #
    # `X.m` is what makes that true, and it is optional in the table -- so the
    # claim rests on _check_translations(), which refuses at BUILD time the one
    # config that reaches the English tail with a German `X` in hand: per-category
    # sentences translated, the default left behind. `r[3]||D` past a truthy `X`
    # is otherwise reachable only when the customer translated none of the notice
    # at all, where the English sentence is the only sentence there is.
    message = "X&&(X.c&&X.c[y]||X.m)||r[3]||D" if langs else "r[3]||D"
    # The furniture, swapped from the same table. Emitted only alongside it: a
    # single-language build has nothing to select between and pays nothing.
    furniture = "if(X){g.textContent=X.g;s.textContent=X.s;o.textContent=X.o}" if langs else ""
    # The two announcements. Sentences rather than concatenations now, because a
    # translation cannot reorder a concatenation: German puts the countdown
    # before the application name, and the {app}/{n} tokens are what let it.
    #
    # Parenthesised because the announce sentence is the receiver of a .split()
    # chain: without them the method would bind to the string literal alone and
    # the translated sentence would reach the page with its tokens intact.
    announce = "(" + ("X&&X.a||" if langs else "") + json.dumps(notice["announce"]) + ")"
    cancelled = "(" + ("X&&X.n||" if langs else "") + json.dumps(notice["cancelledAnnounce"]) + ")"
    # The one line that differs in a preview build. Shipped, reaching zero hands
    # the user over exactly once. In the gallery there is nobody to hand over --
    # the frame is a srcdoc iframe on file://, so navigating it would leave the
    # preview, need the network, and land on whatever drive.example.com resolves
    # to. Restarting instead keeps the countdown, Stay, Escape and Go now paths
    # byte-for-byte the ones that ship, and leaves the motion visible for as long
    # as a reviewer looks at it. Nothing in production loops; the gallery says so.
    go = "l=t;w()" if loop else "if(d)return;d=true;q();location.replace(u)"
    return (
        "<script>(function(){"
        "var R=" + json.dumps(_map(cfg), separators=(",", ":")) + ";"
        "var S=" + str(red.get("seconds", DEFAULT_SECONDS)) + ",D=" + json.dumps(red["message"]) + ";"
        "var e=document.getElementById('cat'),b=document.getElementById('rx');"
        "if(!e||!b)return;"
        # The attribute, not the text. category_js rewrites #cat's textContent to
        # a friendly label ("Online Storage and Backup") before this runs, so the
        # text no longer matches anything in R -- it parks the raw PAN-OS name in
        # CATEGORY_KEY_ATTR for exactly this lookup.
        + lookup
        # The tone the category map just resolved, not the one config claims: a
        # page repainted critical at runtime must not then forward anyone.
        + "if(!r||document.documentElement.getAttribute('data-tone')!=='calm')return;"
        "var u=r[1],h=document.createElement('a');"
        # The loop guard. A response page is served AS the blocked site, so
        # location.host is the host the user was refused. If that is the host of
        # any sanctioned app -- not merely this category's -- then this page is a
        # blocked sanctioned app, and the hop that landed the user here was ours.
        # Since a hop only ever targets something in this table, every cycle
        # passes through one of these hosts, so stopping here stops all of them.
        "for(var k in R){h.href=R[k][1];if(h.host===location.host)return}"
        "var n=r[0],t=r[2]||S,l=t,z,d=false;"
        "var m=document.getElementById('rxm'),o=document.getElementById('rxo');"
        "var i=document.getElementById('rxi'),p=document.getElementById('rxp');"
        "var v=document.getElementById('rxl'),g=document.getElementById('rxg');"
        "var s=document.getElementById('rxs');"
        + pick
        + furniture
        # split/join, not .replace(): .replace() only substitutes the first
        # occurrence, and when the second argument is a plain string it still
        # interprets $&, $', $` and $n as replacement patterns -- an app name
        # containing one of those would corrupt the message. split/join
        # replaces every occurrence and treats the app name as a literal.
        #
        # `{app}` is this module's own token, in its own syntax. substitute()
        # never sees it and assert_resolved() cannot miss it, so a translation
        # that drops it renders a notice naming no application with a clean
        # build behind it -- which is why the suite asserts it survives.
        + "m.textContent=("
        + message
        + ").split('{app}').join(n);g.href=u;b.hidden=false;"
        "function w(){i.textContent=l;p.style.width=((t-l)/t*100)+'%'}"
        "function q(){if(z){clearInterval(z);z=null}}"
        "function go(){" + go + "}"
        "function no(){if(d)return;d=true;q();b.setAttribute('data-off','1');"
        "m.hidden=true;o.hidden=false;v.textContent=" + cancelled + "}"
        "w();"
        # Announced once, as a sentence. The per-second number is aria-hidden --
        # a screen reader must not be read a countdown. Every string spliced into
        # this script goes through json.dumps, so copy that gains an apostrophe
        # -- or a translation that is nothing but apostrophes -- cannot emit
        # broken JavaScript.
        #
        # {n} as well as {app}: the countdown is a value only the browser has,
        # and a translation has to be free to put it wherever its grammar wants.
        "v.textContent=" + announce + ".split('{app}').join(n).split('{n}').join(t);"
        # A hidden tab pauses rather than counting: a background tab that
        # navigates itself is indistinguishable from a hijack.
        "z=setInterval(function(){if(document.hidden)return;l--;w();if(l<=0)go()},1000);"
        "g.addEventListener('click',function(x){x.preventDefault();go()});"
        "s.addEventListener('click',no);"
        "document.addEventListener('keydown',function(x){if(x.key==='Escape'||x.key==='Esc')no()});"
        "})();</script>"
    )


def emit(
    cfg: Mapping[str, Any],
    page: str,
    theme: Mapping[str, Any],
    *,
    data_dir: pathlib.Path,
    loop: bool = False,
) -> tuple[str, str, str]:
    """(css, markup, script) for this page. Three empty strings when it does not apply.

    Validation runs for every page and every style, not just the one that renders
    the notice, so a bad redirect config fails the build rather than quietly
    doing nothing on the one combination that would have shown it.

    `data_dir` is required rather than optional because the thing it buys is
    invisible when it is missing: without it the notice is the one sentence on a
    translated page still in the base language, and the page builds clean.

    `loop` is the gallery's demo build and must never be set for anything written
    under `deploy/` -- see `_script`.
    """
    check(cfg)
    if page != PAGE or not enabled(cfg) or not supported(theme):
        return "", "", ""
    # Read after the gate, not before: a single-language build resolves to an
    # empty mapping without opening a file, and every other page never asks.
    #
    # A style that opted out of the extra languages gets the empty mapping too.
    # Nothing on such a page ever assigns `documentElement.lang` -- the selector
    # that would is exactly what the opt-out drops -- so the notice's own
    # language table could only ever miss, and it would miss having spent its
    # bytes on the style that had none to spare. The two flags are independent
    # by design (nyan declares `"redirect": false` as well, so this branch is
    # unreachable from the shipped tree today), and independence is precisely
    # why the dependency has to be written down rather than assumed.
    translations = i18n.redirect_strings(cfg, data_dir) if i18n.enabled(theme) else {}
    # The base language's furniture. Read unconditionally, unlike the table
    # above: the markup renders these words on every build, translated or not.
    notice = i18n.notice_strings(cfg, data_dir)
    return CSS, _markup(notice), _script(cfg, translations, notice, loop=loop)
