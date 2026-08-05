"""Which words a page uses, and in which language.

PAN-OS serves one page per type per vsys, so a firewall with German and English
speakers behind it cannot import two pages -- the choice has to happen in the
browser. Every configured language is compiled into the page and one is selected
at load time from navigator.languages.

Two-letter primary subtags only. `de-AT`, `de-CH` and `de-DE` all resolve to
`de`; regional variants as distinct COPY are deliberately not supported, because
the fallback chain and the case-canonicalisation rule they need are untested
weight that German does not exercise.
"""

from __future__ import annotations

import json
import pathlib
import re
from collections.abc import Mapping
from typing import Any

from panos_response_pages import contact
from panos_response_pages.errors import BuildError
from panos_response_pages.templates import substitute

# Two-letter primary subtag, lowercase. Anchored: "de-AT" must be refused
# loudly rather than silently truncated to a file that does not exist.
LANG_RE = re.compile(r"^[a-z]{2}$")

DEFAULT_LANG = "en"


def base_language(cfg: Mapping[str, Any]) -> str:
    """The language rendered as real text into the markup.

    This is what a browser with JavaScript disabled shows, and what every
    unmatched browser falls back to. It is never shipped in the runtime
    dictionary as well -- it is already in the page.
    """
    return str(cfg.get("baseLanguage", DEFAULT_LANG))


def languages(cfg: Mapping[str, Any]) -> list[str]:
    """Every language compiled into the page, base included."""
    return [str(x) for x in cfg.get("languages", [DEFAULT_LANG])]


def strings_path(lang: str, data_dir: pathlib.Path) -> pathlib.Path:
    return data_dir / "strings" / f"{lang}.json"


def check(cfg: Mapping[str, Any], data_dir: pathlib.Path) -> None:
    """Refuse a language configuration that cannot produce a correct page.

    Called before any page is built rather than at first use, so a bad config
    names the config key the author got wrong instead of surfacing as a KeyError
    from inside substitution.
    """
    langs = languages(cfg)
    base = base_language(cfg)

    if not langs:
        raise BuildError("`languages` is empty; it must list at least the base language")

    for lang in langs:
        if not LANG_RE.match(lang):
            raise BuildError(
                f"language '{lang}' is not a two-letter primary subtag. "
                "Regional variants are not supported: use 'de', which matches de-AT, de-CH and de-DE."
            )

    if base not in langs:
        raise BuildError(f"baseLanguage '{base}' is not in `languages` ({', '.join(langs)})")

    for lang in langs:
        path = strings_path(lang, data_dir)
        if not path.exists():
            raise BuildError(f"language '{lang}' is configured but {lang}.json is missing from {path.parent}")

    # A `translations` block for a language nothing compiles is copy the author
    # wrote and no user will ever read. Refused rather than ignored, and named as
    # a CONFIG problem: both lists live in the same file, either one could be the
    # one that is wrong, so the message says which two to reconcile instead of
    # pointing at a language file that has nothing to do with it.
    for lang in cfg.get("translations", {}):
        if lang not in langs:
            raise BuildError(
                f"`translations` has a block for '{lang}', which is not in `languages` ({', '.join(langs)}). "
                "Add it to `languages` or remove the block."
            )


# The one block a language may omit. Per-language category glosses are ~1800 B
# on the two pages that carry the category map; absent, a non-base language
# shows the translated defaultGloss/riskGloss for that category's TONE, which
# still varies severity and colour per category because the tone map itself is
# never translated and never duplicated.
OPTIONAL_BLOCKS = ("categories",)


def load(lang: str, data_dir: pathlib.Path) -> dict[str, Any]:
    path = strings_path(lang, data_dir)
    if not path.exists():
        raise BuildError(f"missing strings file: {path}")
    doc: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return doc


# Customer-authored copy: shipped in _defaults.json, overridable per customer,
# and therefore translatable only in the customer's own file. The strings files
# carry the shipped English of each one in `shared`, which is what a language the
# customer has not translated falls back to.
CONFIG_STRING_KEYS = ("defaultGloss", "riskGloss", "continueGrantText", "supportLabel")


def config_strings(cfg: Mapping[str, Any], doc: Mapping[str, Any], lang: str) -> dict[str, str]:
    """Customer-authored strings for one language.

    These four are the copy this project does NOT ship: a customer may rewrite
    any of them in their own config, so a translation of the shipped wording
    would be a translation of a sentence they no longer use. Their translations
    therefore live in the customer's file too -- data directories resolve as a
    whole tree, and putting a per-customer sentence in strings/<lang>.json would
    force a customer to fork the entire tree to translate it.

    Precedence mirrors config-over-defaults: the customer's `translations` block
    wins over the shipped strings file, and a key they have not translated falls
    back to it rather than to the base language.
    """
    shared = doc.get("shared", {})
    out = {k: str(shared[k]) for k in CONFIG_STRING_KEYS if k in shared}
    out.update({k: str(v) for k, v in cfg.get("translations", {}).get(lang, {}).items()})
    return out


def resolve(value: Any, values: Mapping[str, object]) -> Any:
    """Resolve {{PLACEHOLDER}}s inside copy, preserving the value's shape.

    Copy is data here, not template text, so it never passes through the
    template substitution pass -- and re.sub does not rescan its replacement, so
    a placeholder inside a translated value would otherwise survive verbatim.

    In the BASE language that surfaces loudly, as a BuildError from
    assert_resolved. In a non-base language it would not surface at all: the
    runtime dictionary is JSON handed to textContent, so a German user would
    simply read "{{COMPANY}}" off the page. That asymmetry is why this is
    applied to both paths rather than left to the template pass.
    """
    if isinstance(value, str):
        return substitute(value, values)
    if isinstance(value, list):
        return [resolve(v, values) for v in value]
    if isinstance(value, dict):
        return {k: resolve(v, values) for k, v in value.items()}
    return value


def page_values(doc: Mapping[str, Any], page: str, values: Mapping[str, object]) -> dict[str, str]:
    """The {{T_*}} values one page needs, flattened from the strings document.

    Fact labels are numbered rather than named. The runtime swaps them
    positionally against `dl dt` in document order, so the array IS the
    contract; giving the template names as well would create a second ordering
    that could silently disagree with it.
    """
    pages = doc.get("pages", {})
    if page not in pages:
        raise BuildError(f"strings document has no entry for page '{page}'")
    p = resolve(pages[page], values)
    shared = resolve(doc.get("shared", {}), values)
    # Most pages offer the same fallback ("... with the details above"), so it
    # lives in `shared` and is written once per language. The two pages that
    # want the user moving now -- a live credential submission, a malware hit --
    # say "straight away" instead, and carry their own pair. Overriding beats a
    # second shared key: the alternative names the variant rather than the page,
    # and a translator then has to work out which pages use which.
    contact_alt = p.get("contactAlt", shared["contactAlt"])
    out: dict[str, str] = {
        "T_TITLE": p["title"],
        "T_HEADLINE": p["headline"],
        "T_GLOSS": p["gloss"],
        "T_REPORT_LABEL": shared["reportLabel"],
        "T_REPORT_SUBJECT": p["report"]["subject"],
        "T_REPORT_INTRO": p["report"]["intro"],
        "T_REPORT_PROMPT": p["report"]["prompt"],
        "T_CONTACT_ALT1": contact_alt[0],
        "T_CONTACT_ALT2": contact_alt[1],
    }
    for i, label in enumerate(p["facts"], start=1):
        out[f"T_FACT{i}"] = label
    # A string when the slot is one run of prose, an array when the template
    # interrupts it with markup only the build can produce -- safe-search wraps
    # the contact anchor, whose href and data-* attributes are decided at build
    # time, in the middle of a sentence. Numbered like the fact labels and for
    # the same reason: the order IS the contract, and naming the fragments would
    # invent a second one that could disagree with it.
    extra = p.get("extra", "")
    if isinstance(extra, list):
        for i, part in enumerate(extra, start=1):
            out[f"T_EXTRA{i}"] = part
    else:
        out["T_EXTRA"] = extra
    # The report action is every page's first button and comes from `shared`.
    # A page that offers a second one -- safe-search sends the user to the search
    # engine's own settings -- names it here, because only that page has one.
    if "action2" in p:
        out["T_ACTION2_LABEL"] = p["action2"]
    return out


# Single-letter keys. This dictionary ships in every page of every style, so a
# descriptive key costs its own length x pages x styles x languages for nothing:
# the only reader is the emitted script twenty lines away.
def runtime_dict(cfg: Mapping[str, Any], page: str, data_dir: pathlib.Path) -> dict[str, dict[str, Any]]:
    """Per-page translations for every language EXCEPT the base one.

    The base language is already in the markup as real text; shipping it here as
    well would be the largest single waste in the design.
    """
    base = base_language(cfg)
    out: dict[str, dict[str, Any]] = {}
    for lang in languages(cfg):
        if lang == base:
            continue
        doc = load(lang, data_dir)
        # config_strings() is handed THIS language's own document, so the
        # fallback it applies when the customer has not translated a key is that
        # language's shipped wording rather than the base language's. For
        # `lang == base` it would return the strings-file value in place of the
        # customer's live config value -- which is why the loop skips the base
        # language above, and why that skip is load-bearing rather than an
        # optimisation.
        conf = config_strings(cfg, doc, lang)
        # Resolve placeholders inside the copy FIRST, and per language.
        #
        # This is the silent half of the bug resolve() exists for. page_values()
        # feeds the template pass, where an unresolved {{COMPANY}} eventually
        # trips assert_resolved and fails the build loudly. NOTHING here does:
        # this dictionary is JSON handed to textContent, so a stray placeholder
        # would be read off the page by a German user as literal braces, with no
        # error at build time and none on the firewall.
        #
        # CONTINUE_GRANT comes from `conf`, not from cfg: a non-base language
        # has its own translation of the duration, and resolving the German
        # string against the English value would put "15 minutes" inside a
        # German sentence.
        lang_values = {
            "COMPANY": cfg["company"],
            "SUPPORT_EMAIL": contact.email(cfg),
            "CONTINUE_GRANT": conf["continueGrantText"],
        }
        pages = doc.get("pages", {})
        if page not in pages:
            raise BuildError(f"{lang}.json has no entry for page '{page}'")
        p = resolve(pages[page], lang_values)
        shared = resolve(doc.get("shared", {}), lang_values)
        entry: dict[str, Any] = {
            "t": p["title"],
            "h": p["headline"],
            "g": p["gloss"],
            "f": list(p["facts"]),
            # A string when the slot is one run of prose, a list when the
            # template interrupts it with build-time markup. Kept in the shape
            # page_values() sees, for the same reason: the order IS the contract.
            "x": p.get("extra", ""),
            "rl": shared["reportLabel"],
            "rs": p["report"]["subject"],
            "ri": p["report"]["intro"],
            "rp": p["report"]["prompt"],
            # Mirrors page_values(): the two pages that want the user moving now
            # carry their own pair, and a page override has to win here too or
            # the swap would quietly replace "straight away" with the shared
            # wording the moment a language was selected.
            "ca": list(p.get("contactAlt", shared["contactAlt"])),
            "s": shared["severity"],
            "dg": conf["defaultGloss"],
            "rg": conf["riskGloss"],
        }
        # Only safe-search offers a second button, so only safe-search pays for
        # the key -- the dictionary carries what the page uses and nothing else.
        if "action2" in p:
            entry["a2"] = p["action2"]
        if "categories" in doc:
            entry["c"] = doc["categories"]
        out[lang] = entry
    return out


def flat_keys(doc: Mapping[str, Any], prefix: str = "") -> set[str]:
    """Every leaf path in a strings document.

    Lists are indexed rather than counted, so a German `facts` array one entry
    short names the missing position instead of reporting a length mismatch the
    translator then has to locate by eye.
    """
    out: set[str] = set()
    for key, value in doc.items():
        if not prefix and key in OPTIONAL_BLOCKS:
            continue
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            out |= flat_keys(value, f"{path}.")
        elif isinstance(value, list):
            out |= {f"{path}[{i}]" for i in range(len(value))}
        else:
            out.add(path)
    return out


def check_complete(cfg: Mapping[str, Any], data_dir: pathlib.Path) -> None:
    """Every configured language carries exactly the base language's key set.

    Exactly, not merely at least: an extra key is a typo or a stale entry, and
    either way it is a string that will never reach a page. Reported rather than
    ignored, because both are real mistakes that are invisible in the output.
    """
    base = base_language(cfg)
    want = flat_keys(load(base, data_dir))
    for lang in languages(cfg):
        if lang == base:
            continue
        got = flat_keys(load(lang, data_dir))
        missing = sorted(want - got)
        extra = sorted(got - want)
        if missing or extra:
            parts = []
            if missing:
                parts.append(f"missing {len(missing)} key(s):\n  " + "\n  ".join(missing))
            if extra:
                parts.append(f"unknown {len(extra)} key(s):\n  " + "\n  ".join(extra))
            raise BuildError(f"{lang}.json is out of step with {base}.json -- " + "; ".join(parts))
