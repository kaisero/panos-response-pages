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


def enabled(theme: Mapping[str, Any]) -> bool:
    """Whether this style compiles the configured languages beyond the base one.

    Declared per style, not measured, for the same reason `redirect.supported`
    is: a measured check would refuse the BUILD for the customer who configured
    a second language, punishing them for a property of a style they may not
    even use. The flag says up front which styles carry the feature, and the
    suite holds it honest by measuring the ones that claim it.

    Opting out is not opting out of the page. An opted-out style still builds
    every page, still renders `baseLanguage` as real text, and is still measured
    against the ceiling -- it simply carries no dictionary and no selector. That
    is a smaller page in ONE language where the config asked for several, which
    is a real reduction in what the customer gets, so `format_report` prints it
    on that style's rows rather than letting it pass in silence.

    Absent means true. Six of the seven shipped styles have room, and a theme
    file written before the flag existed is one of them.
    """
    return bool(theme.get("i18n", True))


def shipped(cfg: Mapping[str, Any], theme: Mapping[str, Any]) -> list[str]:
    """The languages this style actually compiles, which is what the table shows.

    One place answers this, because two would eventually disagree -- and the way
    they would disagree is a report claiming a language the page does not carry.
    """
    return languages(cfg) if enabled(theme) else [base_language(cfg)]


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

# The one customer-authored key whose copy is a BLOCK rather than a string, and
# the only nesting this merge understands. The redirect notice has a default
# sentence and a per-category sentence that replaces it, so no flat key can name
# either -- and left untranslated they are the last user-visible copy a German
# page renders in English. The translated block mirrors the config block by name:
#
#   "translations": {"de": {"redirect": {"message": "...",
#                                        "categories": {"<category>": "..."}}}}
#
# `categories` maps a category straight to its sentence rather than repeating the
# config's `{"app", "url", "message"}` entry: `app` and `url` are not copy, and a
# translator handed a shape with them in it would be invited to change them.
#
# ONE level, for ONE key, deliberately. A general deep merge would have to answer
# what a list means and what a partially overridden leaf means, and neither
# question has a caller here. A second block key would be a second entry in this
# tuple; it would not be a rewrite.
CONFIG_STRING_BLOCKS = ("redirect",)


def config_strings(cfg: Mapping[str, Any], doc: Mapping[str, Any], lang: str) -> dict[str, Any]:
    """Customer-authored strings for one language.

    These are the copy this project does NOT ship: a customer may rewrite any of
    them in their own config, so a translation of the shipped wording would be a
    translation of a sentence they no longer use. Their translations therefore
    live in the customer's file too -- data directories resolve as a whole tree,
    and putting a per-customer sentence in strings/<lang>.json would force a
    customer to fork the entire tree to translate it.

    Precedence mirrors config-over-defaults: the customer's `translations` block
    wins over the shipped strings file, and a key they have not translated falls
    back to it rather than to the base language.

    A block key merges one level down rather than wholesale, so a customer who
    translates the notice's default sentence and none of its per-category
    overrides keeps whatever the other half of the block held -- the alternative
    makes translating one of the two silently discard the other.
    """
    shared = doc.get("shared", {})
    written = cfg.get("translations", {}).get(lang, {})
    out: dict[str, Any] = {k: str(shared[k]) for k in CONFIG_STRING_KEYS if k in shared}
    # str() on every flat value, and on none of the block ones: the same call
    # applied to a block would put the repr of a dict where a sentence belongs.
    out.update({k: str(v) for k, v in written.items() if k not in CONFIG_STRING_BLOCKS})
    for key in CONFIG_STRING_BLOCKS:
        block = {**(shared.get(key) or {}), **(written.get(key) or {})}
        # Absent rather than empty. Every reader treats presence as "this
        # language has a translation of it", and an empty block is one that
        # claims so while saying nothing.
        if block:
            out[key] = block
    return out


def redirect_strings(cfg: Mapping[str, Any], data_dir: pathlib.Path) -> dict[str, dict[str, Any]]:
    """The translated redirect notice, per language, base excluded.

    Same shape and same reasoning as runtime_dict(): the base language's notice
    is `redirect.message` itself -- the value the build writes into the script as
    its default -- so shipping a translation of it here as well would be a second
    copy of a sentence already on the page.

    Each language is resolved against its OWN strings document, so a key the
    customer has not translated falls back to that language's shipped wording
    rather than to the base language's.
    """
    base = base_language(cfg)
    out: dict[str, dict[str, Any]] = {}
    for lang in languages(cfg):
        if lang == base:
            continue
        block = config_strings(cfg, load(lang, data_dir), lang).get("redirect")
        if block:
            out[lang] = dict(block)
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


# The two fragments the CONTACT_ALT slot wraps its mailto anchor in. Named
# rather than written as `2` at both call sites: the number IS the template's
# shape, and a slot that grew a third fragment would have to change here.
CONTACT_ALT_PARTS = 2


def _contact_alt(page_block: Mapping[str, Any], shared: Mapping[str, Any], where: str) -> list[str]:
    """The pair of fragments either side of the contact address, for one page.

    Most pages offer the same fallback ("... with the details above"), so it
    lives in `shared` and is written once per language. The two pages that want
    the user moving now -- a live credential submission, a malware hit -- say
    "straight away" instead, and carry their own pair. Overriding beats a second
    shared key: the alternative names the variant rather than the page, and a
    translator then has to work out which pages use which.

    Every other failure in this module raises BuildError naming the page. This
    one used to raise a bare KeyError from the `shared` lookup, or -- worse -- a
    bare IndexError from the caller when an override carried one fragment
    instead of two, which names no file, no language and no page. The arity is
    checked here because a one-fragment override is not a missing key: it passes
    check_complete (the key exists), it passes empty_leaves (nothing is empty),
    and it is only wrong against the template, which this is the closest code
    to.
    """
    got = page_block.get("contactAlt") or shared.get("contactAlt")
    if not got:
        raise BuildError(f"strings document has no `contactAlt` for page '{where}', and none in `shared`")
    if len(got) != CONTACT_ALT_PARTS:
        raise BuildError(
            f"`contactAlt` for page '{where}' has {len(got)} fragment(s); "
            f"the template wraps its address in exactly {CONTACT_ALT_PARTS}"
        )
    return [str(x) for x in got]


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
    contact_alt = _contact_alt(p, shared, page)
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


# Portal copy lives in the SHELLS, identically in all seven, rather than in the
# page templates -- the reverse of the block-page family, where the shells carry
# no copy at all. That is a property of this family's split: PAN-OS fixes the
# file shape (page template) and the theme decides decoration (shell), and the
# words are decoration.
#
# `home` names no slot. Its import is script-only -- PAN-OS writes that body
# itself -- so its one piece of copy, the seven logout messages, reaches the page
# as a JS array rather than as markup, and there is no {{T_*}} for it to fill.
PORTAL_SLOTS = {
    "login": ("signIn", "getSoftware", "glossSignIn", "glossSoftware", "download", "otherPlatforms"),
    "home": (),
}


def portal_values(doc: Mapping[str, Any], surface: str, values: Mapping[str, object]) -> dict[str, str]:
    """The {{T_*}} values one portal import needs.

    Resolved against `values` for the same reason page_values() is: a portal
    string may carry {{COMPANY}} exactly as a block-page string may, and
    substitute() does not rescan its own replacement text.
    """
    block = doc.get("portal", {})
    if surface not in block:
        raise BuildError(f"strings document has no portal entry for '{surface}'")
    s = resolve(block[surface], values)
    out = {f"T_{k.upper()}": s[k] for k in PORTAL_SLOTS[surface]}
    if surface == "login":
        # The same split as contactAlt, and the same arity check: the shell owns
        # the anchor, so the sentence is two fragments either side of it, and a
        # one-fragment translation is an IndexError that names no file and no
        # key. CONTACT_ALT_PARTS because it IS the same number -- one anchor
        # inside one sentence -- not because the two slots are the same slot.
        note = s["note"]
        if len(note) != CONTACT_ALT_PARTS:
            raise BuildError(
                f"`note` for portal/{surface} has {len(note)} fragment(s); "
                f"the shell wraps its contact anchor in exactly {CONTACT_ALT_PARTS}"
            )
        out["T_NOTE1"], out["T_NOTE2"] = note[0], note[1]
    return out


def portal_runtime(
    cfg: Mapping[str, Any],
    surface: str,
    data_dir: pathlib.Path,
    values: Mapping[str, object],
) -> str:
    """The per-import language dictionary, as a JS object literal.

    '<' is escaped rather than left to json.dumps: portal/validate.py refuses a
    raw '<' anywhere in an import, because the observed failure is not an error
    on the firewall -- it is that <pan_form/> silently stops being substituted
    and the login form is lost entirely.

    Keys are spelled out rather than shortened to one letter as the block-page
    dictionary's are. That dictionary ships on eleven pages in seven styles
    across every palette; this one ships twice per style, so the same saving is
    two orders of magnitude smaller and not worth an unreadable emitted script.
    """
    base = base_language(cfg)
    out: dict[str, Any] = {}
    for lang in languages(cfg):
        if lang == base:
            continue
        doc = load(lang, data_dir)
        block = doc.get("portal", {})
        if surface not in block:
            raise BuildError(f"{lang}.json has no portal entry for '{surface}'")
        s = resolve(block[surface], values)
        if surface == "home":
            # A customer may have rewritten the seven messages in their own
            # config, in which case their translation of them wins -- the same
            # precedence config_strings() gives every other customer-authored
            # string. Read straight off the `translations` block rather than
            # through config_strings(), which str()s every value it does not know
            # and would put the repr of a list where seven sentences belong.
            written = cfg.get("translations", {}).get(lang, {}).get("logoutMessages")
            messages = resolve([str(m) for m in written], values) if written else list(s["logoutMessages"])
            out[lang] = {"lm": messages}
        else:
            out[lang] = s
    return json.dumps(out, separators=(",", ":"), ensure_ascii=False).replace("<", "\\u003c")


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
        # Not because an unresolved one would ship silently -- it would not.
        # assert_resolved() scans the WHOLE built page, the JSON inside <script>
        # included, so dropping these calls fails the build loudly:
        #
        #   BuildError: unresolved placeholder(s) in credential-block-page: COMPANY
        #
        # That message names the page, though, and nothing else: not the
        # language whose file carries the placeholder, not the key. The reason
        # to resolve here is the VALUES it resolves against. `lang_values` is
        # built from this language's own strings, so {{CONTINUE_GRANT}} in a
        # German sentence becomes "30 Minuten" rather than the English duration
        # the template pass would have substituted -- a page that builds clean,
        # reads as German, and states the wrong fact.
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
            # wording the moment a language was selected. Same helper, so a
            # German file with a one-fragment override fails naming the page
            # rather than shipping a sentence the runtime cannot swap.
            "ca": _contact_alt(p, shared, f"{lang}/{page}"),
            "s": shared["severity"],
            "dg": conf["defaultGloss"],
            "rg": conf["riskGloss"],
        }
        # Only safe-search offers a second button, so only safe-search pays for
        # the key -- the dictionary carries what the page uses and nothing else.
        if "action2" in p:
            entry["a2"] = p["action2"]
        # Resolved like every other value that leaves this function. It is copy
        # a translator writes, so it may carry {{COMPANY}} exactly as the page
        # blocks do, and assigning it raw made it the one copy value here that
        # reached a page unresolved -- failing the build with a message naming
        # the PAGE, which is the one thing about it that is not wrong.
        if "categories" in doc:
            entry["c"] = resolve(doc["categories"], lang_values)
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


# The one string that is deliberately empty: a calm page carries a pill with no
# words in it, and the runtime's `if(V&&V.textContent)` guard is built on that.
# Listed by exact path rather than by rule, so it stays a single documented
# exception instead of a hole any future empty string can fall through.
EMPTY_ALLOWED = frozenset({"shared.severity.calm"})


def empty_leaves(doc: Mapping[str, Any], prefix: str = "") -> list[str]:
    """Paths whose value is the empty string.

    An empty fragment is invisible to every other check in this module.
    check_complete() compares key SETS, and flat_keys() indexes list positions,
    so `"extra": ["", "Contact ", " and IT will look."]` has exactly the right
    keys in exactly the right places and is still broken: the template renders
    no text node for fragment 0, the sentence drops to two child nodes, and the
    runtime's S() -- which keys on childNodes.length>2 -- silently does nothing.
    The result is one sentence left in the base language on an otherwise
    translated page, with a clean build behind it.

    Empty, not blank: " " renders a text node and keeps the shape, and several
    fragments legitimately end in a space.
    """
    out: list[str] = []
    for key, value in doc.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            out += empty_leaves(value, f"{path}.")
        elif isinstance(value, list):
            out += [f"{path}[{i}]" for i, v in enumerate(value) if v == ""]
        elif value == "" and path not in EMPTY_ALLOWED:
            out.append(path)
    return out


def _refuse_empty(lang: str, doc: Mapping[str, Any]) -> None:
    """Names the language AND every key path, because the author fixing this has
    to find the string in a file they may not read."""
    blank = empty_leaves(doc)
    if blank:
        raise BuildError(
            f"{lang}.json has {len(blank)} empty string(s):\n  "
            + "\n  ".join(blank)
            + "\nAn empty fragment renders no text node, which collapses the sentence "
            "the runtime swaps and leaves it in the base language."
        )


def check_complete(cfg: Mapping[str, Any], data_dir: pathlib.Path) -> None:
    """Every configured language carries exactly the base language's key set,
    and no string in any of them is empty.

    Exactly, not merely at least: an extra key is a typo or a stale entry, and
    either way it is a string that will never reach a page. Reported rather than
    ignored, because both are real mistakes that are invisible in the output.

    The base language is checked for empty values too, and only for those: it
    defines the key set, so it cannot be out of step with itself -- but an empty
    fragment in the MARKUP collapses the three-node shape for every language at
    once, which is the worse version of the same bug.
    """
    base = base_language(cfg)
    base_doc = load(base, data_dir)
    want = flat_keys(base_doc)
    _refuse_empty(base, base_doc)
    for lang in languages(cfg):
        if lang == base:
            continue
        doc = load(lang, data_dir)
        _refuse_empty(lang, doc)
        got = flat_keys(doc)
        missing = sorted(want - got)
        extra = sorted(got - want)
        if missing or extra:
            parts = []
            if missing:
                parts.append(f"missing {len(missing)} key(s):\n  " + "\n  ".join(missing))
            if extra:
                parts.append(f"unknown {len(extra)} key(s):\n  " + "\n  ".join(extra))
            raise BuildError(f"{lang}.json is out of step with {base}.json -- " + "; ".join(parts))
