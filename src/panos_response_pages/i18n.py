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
import unicodedata
from collections.abc import Mapping, Sequence
from typing import Any, Literal

from panos_response_pages import contact, logs
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


# The language's own display name, in English, as a top-level key of its strings
# document -- "English", "German", not "en" and "de".
#
# In the strings file rather than in a table here because check_complete()
# enforces exact key parity: a language physically cannot ship without supplying
# its own display name, and there is no second list to fall out of step with the
# first. `lang` is already a top-level metadata key, so this is not a new shape.
#
# Read only by the preview gallery. runtime_dict() emits a fixed set of short
# keys and page_values() reads named ones, so this key reaches no built page --
# which is what makes it free for every customer who never opens the gallery.
NAME_KEY = "name"


def display_name(lang: str, data_dir: pathlib.Path) -> str:
    """What the gallery's Language control calls this language.

    Falls back to the code rather than raising: an out-of-step file is already
    excluded by previewable(), and a data directory predating this key would
    otherwise fail a build over a string only the preview reads.
    """
    return str(load(lang, data_dir).get(NAME_KEY) or lang)


def previewable(cfg: Mapping[str, Any], data_dir: pathlib.Path) -> list[str]:
    """Every language the gallery may offer, base language first.

    EVERY shipped strings file, not `languages` -- the shipped default is
    `languages: ["en"]`, so a config-driven list would be empty on a default
    build and nobody could look at the German that ships in this tree. The
    Redirect toggle shows an opt-in feature a config has not enabled for exactly
    the same reason, and like that toggle this is preview-only: build_page
    refuses the list on a deploy build.

    A file whose key set is out of step with the base language is left out, and
    SAID SO. It would reach runtime_dict() as a KeyError naming a template key
    rather than the file, and a half-written translation nobody has configured
    yet must not be able to fail a build that is otherwise correct -- so this is
    a warning and not a BuildError. But dropping it in silence is the shape of
    failure this project exists to refuse: the file is in the tree, its author
    expects to find it in the dropdown, and the only symptom is a language that
    is not offered. check_complete() raises on exactly the same comparison for a
    language the config turned on; this is that message, one severity down,
    because a gallery convenience must not be able to stop a build.
    """
    base = base_language(cfg)
    out = [base]
    want = flat_keys(load(base, data_dir))
    for path in sorted(strings_path(base, data_dir).parent.glob("*.json")):
        lang = path.stem
        if lang == base or not LANG_RE.match(lang):
            continue
        got = flat_keys(load(lang, data_dir))
        if got == want:
            out.append(lang)
            continue
        _warn_out_of_step(lang, base, sorted(want - got), sorted(got - want))
    return out


def _warn_out_of_step(lang: str, base: str, missing: Sequence[str], extra: Sequence[str]) -> None:
    """Name the file, name what is out of step, and name the consequence.

    Every key path, as check_complete() prints them: whoever fixes this has to
    find the string in a file they may not read, and a count alone sends them
    looking for it by eye.
    """
    parts = []
    if missing:
        parts.append(f"missing {len(missing)} key(s):\n  " + "\n  ".join(missing))
    if extra:
        parts.append(f"unknown {len(extra)} key(s):\n  " + "\n  ".join(extra))
    logs.get().warning(
        "%s.json is out of step with %s.json -- %s\nIt is left out of the preview gallery's Language "
        "control, because a page built from it would be missing copy. Nothing else is affected: "
        "`languages` in the config decides what a firewall serves.",
        lang,
        base,
        "; ".join(parts),
    )


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
            # The remedy, not just the diagnosis. `languages` defaults to
            # ["en"], so a data directory copied out by `init` before the
            # strings tree existed fails this for EVERY build and every page --
            # and the message on its own reads like a typo in a config key the
            # author never wrote. Naming `init --force` is the difference
            # between a five-second fix and a hunt through a config file that
            # is not wrong.
            raise BuildError(
                f"language '{lang}' is configured but {lang}.json is missing from {path.parent}. "
                "A data directory made before this release has no strings/ at all: refresh it with "
                "`panos-response-pages init --force` (back up your config/ first)."
            )

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


# The notice's own furniture: two button labels, the line that replaces the
# sentence when the user stays, and the two things a screen reader is told. All
# five are SHIPPED copy, so they live in the strings document like every other
# word this project writes -- and not, as they did, in Python constants that no
# language can reach. A German page used to read "Sie werden zu ... weitergeleitet"
# above buttons labelled "Go now" and "Stay", with the whole English sentence read
# out to a screen reader underneath.
#
# They sit inside `shared.redirect`, which is also the block a customer translates
# their own `message` into -- one block, merged one level by config_strings(), so a
# language ends up with the shipped furniture and the customer's sentence together.
#
# `announce` carries {app} and {n}: the app name and the countdown are values only
# the browser has. Same token syntax as `redirect.message`, and for the same
# reason -- this module's own, substituted by redirect.py rather than by
# substitute().
NOTICE_KEYS = ("go", "stay", "cancelled", "cancelledAnnounce", "announce")


def notice(block: Mapping[str, Any], where: str) -> dict[str, str]:
    """The five notice strings out of a `redirect` block, or a named failure.

    Checked rather than indexed because the caller splices these into markup and
    into a JS string literal: a missing key reaches the page as the word
    "undefined" on a button, which is a clean build and a broken page. `where` is
    the file the reader has to open -- the strings document, never the config,
    since this is copy no customer authors.
    """
    missing = [k for k in NOTICE_KEYS if not str(block.get(k, "")).strip()]
    if missing:
        raise BuildError(
            f"{where} has no `shared.redirect` copy for the notice: {', '.join(missing)}. "
            "A data directory made before this release predates the block: refresh it with "
            "`panos-response-pages init --force` (back up your config/ first)."
        )
    return {k: str(block[k]) for k in NOTICE_KEYS}


def notice_strings(cfg: Mapping[str, Any], data_dir: pathlib.Path) -> dict[str, str]:
    """The BASE language's notice furniture, which is what the markup renders."""
    lang = base_language(cfg)
    doc = load(lang, data_dir)
    return notice(doc.get("shared", {}).get("redirect") or {}, f"{lang}.json")


def redirect_strings(cfg: Mapping[str, Any], data_dir: pathlib.Path) -> dict[str, dict[str, Any]]:
    """The translated redirect notice, per language, base excluded.

    Same shape and same reasoning as runtime_dict(): the base language's notice
    is `redirect.message` itself -- the value the build writes into the script as
    its default -- so shipping a translation of it here as well would be a second
    copy of a sentence already on the page.

    Each language is resolved against its OWN strings document, so a key the
    customer has not translated falls back to that language's shipped wording
    rather than to the base language's.

    Every non-base language gets an entry now, whether or not the customer wrote
    one: the furniture is shipped copy and exists in every language, so there is
    always something to swap even where the sentence itself is untranslated.
    """
    base = base_language(cfg)
    out: dict[str, dict[str, Any]] = {}
    for lang in languages(cfg):
        if lang == base:
            continue
        block = config_strings(cfg, load(lang, data_dir), lang).get("redirect") or {}
        notice(block, f"{lang}.json")
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


def portal_dicts(
    cfg: Mapping[str, Any],
    surface: str,
    data_dir: pathlib.Path,
    values: Mapping[str, object],
    langs: Sequence[str] | None = None,
) -> dict[str, Any]:
    """The per-import language dictionary, one entry per non-base language.

    Split out of portal_runtime() so the preview gallery can carry these
    dictionaries beside the frames rather than inside them: it hands one back to
    an import that was built with none, and needs the object, not the literal.

    Keys are spelled out rather than shortened to one letter as the block-page
    dictionary's are. That dictionary ships on eleven pages in seven styles
    across every palette; this one ships twice per style, so the same saving is
    two orders of magnitude smaller and not worth an unreadable emitted script.

    `langs` overrides which languages are compiled, exactly as runtime_dict's
    does and for the same reason: absent -- every deploy build -- it is
    `languages(cfg)`, the only honest answer for an import a firewall serves,
    and the preview gallery passes previewable() so a reviewer can look at a
    language the config has not turned on yet.
    """
    base = base_language(cfg)
    out: dict[str, Any] = {}
    for lang in languages(cfg) if langs is None else langs:
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
    return out


def portal_runtime(
    cfg: Mapping[str, Any],
    surface: str,
    data_dir: pathlib.Path,
    values: Mapping[str, object],
    langs: Sequence[str] | None = None,
) -> str:
    """portal_dicts(), as the JS object literal an import carries.

    '<' is escaped rather than left to json.dumps: portal/validate.py refuses a
    raw '<' anywhere in an import, because the observed failure is not an error
    on the firewall -- it is that <pan_form/> silently stops being substituted
    and the login form is lost entirely.
    """
    dicts = portal_dicts(cfg, surface, data_dir, values, langs)
    return json.dumps(dicts, separators=(",", ":"), ensure_ascii=False).replace("<", "\\u003c")


# Single-letter keys. This dictionary ships in every page of every style, so a
# descriptive key costs its own length x pages x styles x languages for nothing:
# the only reader is the emitted script twenty lines away.
def runtime_dict(
    cfg: Mapping[str, Any],
    page: str,
    data_dir: pathlib.Path,
    langs: Sequence[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Per-page translations for every language EXCEPT the base one.

    The base language is already in the markup as real text; shipping it here as
    well would be the largest single waste in the design.

    `langs` overrides which languages are compiled. Absent -- every deploy build
    -- it is `languages(cfg)`, which is the only honest answer for a page a
    firewall serves. The preview gallery passes previewable() instead, so a
    reviewer can look at a language the config has not turned on yet.
    """
    base = base_language(cfg)
    out: dict[str, dict[str, Any]] = {}
    for lang in languages(cfg) if langs is None else langs:
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


# Angle brackets in copy. Both of them, and anywhere in the string: this is not a
# tag parser and must not read like one.
#
# Copy leaves this module down two paths, and the character breaks both:
#
# * As MARKUP, in the base language. `<strong>` renders, which is why the rule
#   cannot be "escape it" -- the base language would then show the escape.
# * As JSON inside an inline <script>, in every other language. json.dumps
#   escapes neither '<' nor a PAN-OS substitution token, so `<user/>` in a German
#   gloss survives the build, survives validate() -- the token IS legal on that
#   page -- and is expanded by the FIREWALL at serve time, inside a JS string
#   literal. A username of the shape `ACME\ukaiser` then reads as \u, and node
#   says what a browser says:
#
#       SyntaxError: Invalid Unicode escape sequence
#
#   which kills the entire page script: no language swap, no friendly category
#   label, no data-c for the redirect to key on, no timestamp, no mailto rebuild.
#   A clean build, a green validate, and a page that looks plausible.
#
# The fix is never innerHTML -- that makes every string in every language file an
# injection surface. It is to split the string around the element and let the
# TEMPLATE own the tag, which is what `contactAlt` does around its anchor and
# url-coach's info box does around its <strong>.
#
# The portal family already refuses a raw '<' anywhere in an import (_RAW_LT).
# This is the block-page half of the same rule, moved off the shipped tree --
# where a test enforced it -- and into the build, where it also covers the
# `init`-forked data directory that is the documented way to add a language.
MARKUP_CHARS = ("<", ">")

# What to do about it, for copy that is a SENTENCE around an element.
SPLIT_REMEDY = "Split the string around the element and let the template own the tag, as `contactAlt` does."

# The same rule, one document over: the customer-authored copy that lives in the
# CONFIG rather than in a strings file, and reaches the very same <script>.
#
# * `defaultGloss` and `riskGloss` are json.dumps'd straight into the category
#   selector -- see scripts.py::category_js, where they become `d` and `r`.
# * every `categories.<name>.gloss` is a value in that selector's compact map.
# * `redirect.message`, and each `redirect.categories.<name>.message` and `app`,
#   are json.dumps'd into the notice's script -- see redirect.py::_script, where
#   they become `D` and the rows of `R`.
#
# None of that depends on a second language being configured: these values are in
# the script of a single-language build too, which is what makes this wider than
# the strings-file rule it sits beside. Reproduced with `<user/>` in
# `defaultGloss` on the shipped English config -- a clean build, a green
# validate, and `node --check` on the served page saying
#
#     SyntaxError: Invalid Unicode escape sequence
#
# NAMED keys, never a walk of the config document. Most of that document is not
# copy and must keep its angle brackets: `logoSvg`, `marks.*` and
# `portalLogoSvg` are deliberately SVG markup, and the `_`-prefixed
# documentation keys in _defaults.json are prose about `<lang>` and `<user/>`.
# A walk would refuse every build there is.
CONFIG_COPY_KEYS = ("defaultGloss", "riskGloss")

# The copy inside one `redirect.categories` entry. `url` is deliberately absent:
# it is a destination rather than copy, and its rules -- absolute https, nothing
# that breaks out of an href -- belong with redirect.check's other url rules.
REDIRECT_COPY_KEYS = ("message", "app")

# These reach the page through textContent, never through substitution, so there
# is no tag here that would have rendered and nothing to split around.
CONFIG_REMEDY = (
    "These values are written into the page as text, never as markup, so there is no tag to keep: "
    "remove it and say the same thing in words."
)


def config_copy(cfg: Mapping[str, Any]) -> dict[str, Any]:
    """Just the config values that are copy, in the config's own shape.

    A sub-document rather than a flat list because markup_leaves() walks a
    document and reports the path it walked, and the path is the whole point:
    `redirect.categories.online-storage-and-backup.message` is what the author
    has to open their config and find.
    """
    out: dict[str, Any] = {k: cfg[k] for k in CONFIG_COPY_KEYS if isinstance(cfg.get(k), str)}
    cats = {
        name: {"gloss": entry["gloss"]}
        for name, entry in (cfg.get("categories") or {}).items()
        if isinstance(entry, Mapping) and isinstance(entry.get("gloss"), str)
    }
    if cats:
        out["categories"] = cats
    red = cfg.get("redirect")
    if isinstance(red, Mapping):
        block: dict[str, Any] = {"message": red["message"]} if isinstance(red.get("message"), str) else {}
        rows = {
            name: {k: entry[k] for k in REDIRECT_COPY_KEYS if isinstance(entry.get(k), str)}
            for name, entry in (red.get("categories") or {}).items()
            if isinstance(entry, Mapping)
        }
        rows = {name: row for name, row in rows.items() if row}
        if rows:
            block["categories"] = rows
        if block:
            out["redirect"] = block
    return out


def markup_leaves(doc: Mapping[str, Any], prefix: str = "") -> list[str]:
    """Paths whose value carries an angle bracket. Same walk as empty_leaves()."""
    out: list[str] = []
    for key, value in doc.items():
        path = f"{prefix}{key}"
        if isinstance(value, Mapping):
            out += markup_leaves(value, f"{path}.")
        elif isinstance(value, list):
            out += [f"{path}[{i}]" for i, v in enumerate(value) if _has_markup(v)]
        elif _has_markup(value):
            out.append(path)
    return out


def _has_markup(value: Any) -> bool:
    return isinstance(value, str) and any(c in value for c in MARKUP_CHARS)


def _refuse_markup(where: str, doc: Mapping[str, Any], prefix: str = "", *, remedy: str = SPLIT_REMEDY) -> None:
    """Names the source AND every key path, like _refuse_empty: whoever fixes
    this has to find the string in a file they may not read.

    `remedy` is the last line only. The diagnosis is one rule and reads the same
    wherever the string came from; what to DO about it differs, because config
    copy is never markup on any page and has no element to be split around.
    """
    bad = markup_leaves(doc, prefix)
    if bad:
        raise BuildError(
            f"{where} has {len(bad)} string(s) containing '<' or '>':\n  "
            + "\n  ".join(bad)
            + "\nCopy reaches every non-base language as JSON inside a <script>. A tag renders there "
            "as literal angle brackets, and a PAN-OS token such as <user/> is expanded by the firewall "
            "at serve time -- inside a JS string literal, where a username like ACME\\ukaiser reads as "
            "an invalid \\u escape and kills the whole page script.\n" + remedy
        )


# Unicode normalisation form. NFC is what every editor, browser and HTTP client
# produces by default and what every shipped strings file already is -- which is
# exactly why nothing noticed that nothing enforced it.
#
# The failure this refuses is a file re-saved in NFD. macOS is the environment
# where it happens without anyone choosing it: the filesystem normalises FILE
# NAMES to a decomposed form, and a handful of editors and shell pipelines carry
# the same habit into file CONTENT. A decomposed file is invisible to a reader:
#
# * It looks identical in a terminal and in a diff -- the combining mark renders
#   on top of the base letter, which is what a combining mark is for.
# * It passes check_complete's key parity: the keys are ASCII.
# * It passes empty_leaves: nothing is empty.
# * It passes markup_leaves: there is no angle bracket.
# * It passes json.loads, it passes the build, and it passes validate.
#
# What it does NOT pass is the ceiling. PAN-OS refuses an oversize page by never
# displaying it, and NFD costs two extra bytes for EVERY decomposable character:
# Cyrillic and Vietnamese are the shipped languages where that is most of a page.
# Russian's ё and й and Ukrainian's ї and й all have decomposed forms, and those
# letters are frequent enough that an NFD re-save moves a page's size measurably
# -- silently, against a limit that also fails silently.
#
# And it makes a page disagree with itself. The base language reaches the markup
# as text while every other language reaches an inline <script> as JSON, so a
# document normalised one way beside a document normalised the other renders the
# same word as two different byte sequences on the same page: copy/paste, search
# and any character-count check then behave differently depending on which
# language the browser selected.
#
# NFC rather than "any consistent form": it is the web's default, it is what
# json.dumps(ensure_ascii=False) writes back out, and picking the form the whole
# ecosystem already produces means this rule never fires on a file written by
# ordinary means.
NORMAL_FORM: Literal["NFC"] = "NFC"


def denormalised_leaves(doc: Mapping[str, Any], prefix: str = "") -> list[str]:
    """Paths whose value is not NFC-normalised. Same walk as empty_leaves()."""
    out: list[str] = []
    for key, value in doc.items():
        path = f"{prefix}{key}"
        if isinstance(value, Mapping):
            out += denormalised_leaves(value, f"{path}.")
        elif isinstance(value, list):
            out += [f"{path}[{i}]" for i, v in enumerate(value) if _is_denormalised(v)]
        elif _is_denormalised(value):
            out.append(path)
    return out


def _is_denormalised(value: Any) -> bool:
    return isinstance(value, str) and not unicodedata.is_normalized(NORMAL_FORM, value)


def _refuse_denormalised(lang: str, doc: Mapping[str, Any]) -> None:
    """Names the language AND every key path, like _refuse_empty and
    _refuse_markup -- and for a stronger reason than either.

    A denormalised string is the one failure in this module that a reader cannot
    see. An empty fragment is visible in the file and a tag is visible in the
    file; a decomposed character is byte-level only, so a count alone would send
    the author hunting through a document that looks entirely correct. The path
    is the whole of the remedy, together with the one-line fix below it.
    """
    bad = denormalised_leaves(doc)
    if bad:
        raise BuildError(
            f"{lang}.json has {len(bad)} string(s) that are not {NORMAL_FORM}-normalised:\n  "
            + "\n  ".join(bad)
            + f"\nThey look identical to the {NORMAL_FORM} form in a terminal and in a diff, and they "
            "build, validate and render -- but every decomposed character costs two extra bytes "
            "against a page size PAN-OS enforces by silently not displaying the page, and the same "
            "word then differs between the markup and the runtime dictionary.\n"
            "Re-save the file normalised: "
            f"python -c \"import pathlib,unicodedata as u;p=pathlib.Path('{lang}.json');"
            f"p.write_text(u.normalize('{NORMAL_FORM}',p.read_text(encoding='utf-8')),encoding='utf-8')\""
        )


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

    The markup rule runs over the base language and over the customer's
    `translations` block as well, for the same reason. A tag in the base language
    is only right until a second language is configured, and a `translations`
    value reaches the script by exactly the path a strings value does -- the
    block is the documented place to translate customer-authored copy, so it
    cannot be the one place the rule does not reach.

    And it runs over the config's own copy -- `defaultGloss`, `riskGloss`, the
    per-category glosses and the redirect notice's sentences. Those are the
    base-language originals of exactly the `translations` values swept below:
    guarding the translation of a sentence and not the sentence would be one
    rule with a hole in the middle of it. Here rather than beside each value's
    own validator (redirect.check, page.py) because splitting it across three
    call sites is how the wording, the diagnosis and the coverage drift apart --
    and because these are the values check_complete already reasons about, one
    language over. It is the only rule in this function that does not depend on
    a second language being configured: the config's copy is inside the script
    of a single-language build too. See CONFIG_COPY_KEYS.

    Every strings document is also checked for Unicode normalisation. It sits
    here rather than in the test suite alone because the tests only ever see the
    documents in THIS tree, and the documented way to add a language is to fork
    the data directory with `init` -- the forked file is the one an editor
    re-saves, and it would otherwise reach a firewall decomposed with nothing on
    the path having looked. The shipped tree gets a second, config-free sweep in
    tests/test_i18n.py, the same pair the markup rule already runs in. The
    config's own copy is deliberately NOT swept: unlike a tag, which kills the
    page script, a decomposed character in a customer's own sentence renders
    correctly, and refusing their build over it would refuse a build that works.
    See NORMAL_FORM.
    """
    base = base_language(cfg)
    base_doc = load(base, data_dir)
    want = flat_keys(base_doc)
    _refuse_empty(base, base_doc)
    _refuse_denormalised(base, base_doc)
    _refuse_markup(f"{base}.json", base_doc)
    _refuse_markup("the config", config_copy(cfg), remedy=CONFIG_REMEDY)
    for lang, block in (cfg.get("translations") or {}).items():
        _refuse_markup(f"the config `translations` block for '{lang}'", block, f"translations.{lang}.")
    for lang in languages(cfg):
        if lang == base:
            continue
        doc = load(lang, data_dir)
        _refuse_empty(lang, doc)
        _refuse_denormalised(lang, doc)
        _refuse_markup(f"{lang}.json", doc)
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
