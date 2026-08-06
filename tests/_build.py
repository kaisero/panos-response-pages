"""One build, shared by every test that needs built output.

Five test classes each used to shell out to the build as a subprocess. That cost
five full builds per run, and -- more importantly -- meant coverage saw none of
the code they exercised, because the work happened in another interpreter. The
suite was thorough and the coverage number said 31%.
"""

import functools
import json
import pathlib
import shutil
import tempfile

from _paths import DATA
from panos_response_pages.builder import BuildResult, build_all

# The shipped default (`_defaults.json`), and so the palette every existing
# single-palette assertion meant before the matrix existed. Tests that only
# need *a* build read this one rather than picking arbitrarily.
DEFAULT_PALETTE = "cyber-orange"


def translated_strings(prefix: str = "de:") -> dict:
    """A stand-in translation of the shipped English document.

    The real de.json is a task of its own. Until it lands there is no language
    to compile, and a multi-language test that skipped until there was would
    leave the runtime unexercised for exactly as long as it was easiest to get
    wrong.

    Every leaf is PREFIXED rather than replaced, so {{COMPANY}} and
    {{CONTINUE_GRANT}} survive into the copy -- which is what makes the
    placeholder assertions mean anything. The key set is untouched, so the
    document also satisfies check_complete().
    """

    def walk(value):
        if isinstance(value, str):
            return prefix + value
        if isinstance(value, list):
            return [walk(v) for v in value]
        if isinstance(value, dict):
            return {k: walk(v) for k, v in value.items()}
        return value

    doc = walk(json.loads((DATA / "strings/en.json").read_text(encoding="utf-8")))
    doc["lang"] = "de"
    return doc


@functools.lru_cache(maxsize=1)
def built() -> tuple[pathlib.Path, BuildResult]:
    """Build everything once, into a temp directory.

    Deliberately not the repository's own out/: a test run must neither depend
    on nor clobber whatever the developer last built by hand.
    """
    out = pathlib.Path(tempfile.mkdtemp(prefix="panos-rp-tests-"))
    return out, build_all(DATA, out, preview=True)


@functools.lru_cache(maxsize=4)
def built_with_languages(languages: tuple[str, ...], base: str = "en") -> tuple[pathlib.Path, BuildResult]:
    """A build with a language set, against a COPY of the packaged data.

    The data directory is copied rather than written to: DATA is the installed
    package, `built()` memoises a build against it, and a config written in
    place would change what every other test in the session sees.

    Keyed on the language tuple so each set is built once, and passed a TUPLE
    for that reason -- lru_cache hashes its arguments, and a list raises
    TypeError. Cached separately from built(), whose single slot must keep
    holding the default build.

    A language with no strings/<lang>.json in the packaged tree gets the
    prefixed stand-in translated_strings() builds, written into the COPY.
    check_complete() refuses a configured language whose file is missing, so
    without this the helper would only work for languages that happen to have
    shipped yet -- and a test about theme opt-out would start failing for a
    reason that has nothing to do with theme opt-out.
    """
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="panos-rp-i18n-data-"))
    data = tmp / "data"
    shutil.copytree(DATA, data)
    for lang in languages:
        path = data / "strings" / f"{lang}.json"
        if not path.exists():
            path.write_text(json.dumps(translated_strings(f"{lang}:")), encoding="utf-8")
    cfg_path = data / "config" / "_defaults.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["languages"] = list(languages)
    cfg["baseLanguage"] = base
    cfg_path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")

    out = pathlib.Path(tempfile.mkdtemp(prefix="panos-rp-i18n-out-"))
    return out, build_all(data, out, preview=True)


@functools.lru_cache(maxsize=1)
def portal_pages() -> dict[tuple[str, str], str]:
    """Every portal page in every theme, as the firewall would receive it."""
    from _paths import DATA
    from panos_response_pages.builder import load_themes
    from panos_response_pages.config import load_config
    from panos_response_pages.palettes import load_palette
    from panos_response_pages.portal.page import build_portal_page

    cfg = load_config("contoso", DATA / "config")
    palette = load_palette("cyber-orange", DATA / "palettes")
    out: dict[tuple[str, str], str] = {}
    for theme in load_themes(DATA):
        for page in ("login", "home"):
            out[(theme["name"], page)] = build_portal_page(page, theme, cfg, palette, template_dir=DATA / "templates")
    return out


# The language swap, in full, exactly as it is emitted.
#
# A golden string rather than a set of substring assertions, because the block
# is JavaScript this suite cannot execute: there is no JS engine here, so the
# only thing a test can check is the bytes that go out. Substrings barely check
# those. Transposing S()'s arguments, indexing childNodes[1] instead of [2],
# testing x.length instead of x.pop, deleting the dl dt loop outright -- every
# one of those leaves a page that is visibly wrong in a browser and every one of
# them survives a suite that asserts on fragments.
#
# ONE assertion is enough for the whole build because this block is
# page-independent: it selects by DOM shape, never by page name, so all eleven
# pages in all seven shells emit these same 1098 bytes. That is asserted
# directly (test_the_language_block_is_the_same_bytes_on_every_page), so the
# claim cannot quietly stop being true.
#
# `en` is the base language the fixtures use; the loop's break literal is the
# one part of the block a different baseLanguage changes.
#
# WHEN THIS TEST FAILS: read the diff as a code review of the runtime, not as a
# stale expectation. Update it only once you can say what the new bytes do in a
# browser -- and check the byte cost, since every one of them ships on every
# page of every theme.
LANGUAGE_BLOCK = (
    # Pick a language. The base language STOPS the search: a browser that ranks
    # it above a compiled language must keep the page it was served.
    "LS=navigator.languages||[navigator.language||''],t,lk,i;"
    'for(i=0;i<LS.length;i++){lk=LS[i].slice(0,2).toLowerCase();if(lk=="en")break;if(T[lk]){t=T[lk];break}}'
    "if(t){"
    "var Q=function(s){return document.querySelector(s)};"
    # A sentence one child element splits into three nodes. `c` is passed only
    # where the middle node is copy rather than a build-time anchor.
    "var S=function(e,a,b,c){if(e&&e.childNodes.length>2){"
    "e.childNodes[0].nodeValue=a;e.childNodes[2].nodeValue=b;"
    "if(c!=null)e.childNodes[1].textContent=c;return 1}};"
    "document.documentElement.lang=lk;document.title=t.t;"
    "var H=Q('h1');if(H)H.textContent=t.h;"
    "var G0=Q('#gloss');if(G0)G0.textContent=t.g;"
    # Positional against `dl dt` in document order -- the same contract the
    # numbered {{T_FACT*}} placeholders are built on.
    "[].forEach.call(document.querySelectorAll('dl dt'),function(e,i){if(t.f[i])e.textContent=t.f[i]});"
    # The report button first, then any a.btn: three pages carry a PAN-OS token
    # the firewall expands into markup of its own before the report anchor.
    "var B=Q('a.btn#rep')||Q('a.btn');if(B)B.textContent=t.a2||t.rl;"
    "var R=Q('#rep');if(R){R.setAttribute('data-subject',t.rs);"
    "R.setAttribute('data-intro',t.ri);R.setAttribute('data-prompt',t.rp)}"
    "S(Q('.plain'),t.ca[0],t.ca[1]);"
    # A list-valued `extra` goes to the callout when the callout is itself the
    # split sentence (url-coach's <strong>), otherwise to the .note beneath it.
    "var X=Q('.infobox span,.warnline span'),x=t.x||'';"
    "if(x.pop){if(S(X,x[0],x[2],x[1]))X=0;else S(Q('.note'),x[1],x[2]);x=x[0]}"
    "if(X&&x)X.textContent=x;"
    # Only swapped when the pill says something: a calm page carries an empty
    # one, and writing a label into it would invent a severity.
    "var V=Q('.sev');if(V&&V.textContent)"
    "V.textContent=t.s[document.documentElement.getAttribute('data-tone')]||V.textContent;"
    "}"
)


def deploy_dir() -> pathlib.Path:
    return built()[0] / "deploy"


def preview_dir() -> pathlib.Path:
    return built()[0] / "preview"
