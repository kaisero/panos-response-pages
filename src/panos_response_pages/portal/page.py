"""Assembling one GlobalProtect portal import from a shell, a page template, a
config and a palette.

The block-page family puts the frame in the shell and the slots in the page
template. This family cannot: the file *shape* is fixed by PAN-OS and differs
per import, while the *decoration* differs per theme -- so both the page
template and the shell are slots-only and the frame lives here.

The two frames are the whole contract with PAN-OS:

  login -- a BODY fragment. PAN-OS supplies <html> and an open <head>, so this
           closes </head>, writes the whole <body>, and ends </html>.
  home  -- SCRIPT-ONLY. Embedded verbatim mid-<head>, so it must not carry
           </head>, <body> or </html>. A <style> block is legal there and is
           served -- verified against a live portal.

The style slots are split per import rather than shared. Their rule sets are
disjoint (`.pane`/`#formdiv`/`#taGetSofewarePage` against
`html[data-gp=logout] ...`), and a single shared slot would put both on the
login import, leaving under a kilobyte of headroom against the 16,170 B ceiling
-- less than the spread between the lightest and heaviest shell.
"""

from __future__ import annotations

import pathlib
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import quote

from panos_response_pages import contact, i18n
from panos_response_pages.emit import strip_output
from panos_response_pages.errors import BuildError
from panos_response_pages.scripts import PREVIEW_SWAP
from panos_response_pages.templates import assert_resolved, parse_sections, read, substitute

# Slot order is document order. Nothing here is optional: a missing slot is a
# silent failure on the firewall, so every one is required and named.
FRAMES = {
    "login": (
        "{{VARS}}\n{{HEAD_SCRIPT}}\n<style>\n{{STYLE_LOGIN}}\n</style>\n"
        "</head>\n<body>\n{{BODY}}\n{{FOOT_SCRIPT}}\n</body>\n</html>\n"
    ),
    "home": "{{VARS}}\n{{HEAD_SCRIPT}}\n<style>\n{{STYLE_LOGOUT}}\n</style>\n",
}

# Which file each slot comes from. The page template owns everything PAN-OS
# dictates; the shell owns everything a theme decides.
FROM_PAGE = {
    "login": ("VARS", "HEAD_SCRIPT", "FOOT_SCRIPT"),
    "home": ("VARS", "HEAD_SCRIPT"),
}
FROM_SHELL = {
    "login": ("STYLE_LOGIN", "BODY"),
    "home": ("STYLE_LOGOUT",),
}

# The logo is a CSS background on both imports, and the shells write this prefix
# literally so the rule reads as artwork rather than as a substitution.
SVG_URI_PREFIX = "data:image/svg+xml,"

# What survives percent-encoding intact. Everything outside this set is escaped,
# which covers the four characters that actually matter:
#
#   #   mandatory -- unencoded, everything after the first colour is read as a
#       URL fragment and the artwork loses its palette.
#   '   the URI is also assigned inside a JS string literal on the home import,
#       and the SVG quotes its own attributes with '; raw, they end the literal.
#   < > the import path may or may not sanitize markup, and a data: URI carrying
#       raw <svg> through a naive HTML filter is exactly the shape that gets
#       mangled. It also keeps the file clear of the no-raw-'<' rule.
#
# `{` and `}` are escaped as well, which the lab's encoder left literal. They
# are legal in a quoted url(), but the SVG carries a <style> block full of them
# and the templates are delimited by {{...}} -- encoding removes any chance of
# artwork colliding with the substitution syntax.
LOGO_SAFE = "/:=,;.()- "


def build_portal_page(
    page: str,
    theme: Mapping[str, Any],
    cfg: Mapping[str, Any],
    palette: Mapping[str, Any],
    template_dir: pathlib.Path,
    *,
    preview: bool = False,
    preview_languages: Sequence[str] = (),
    preview_swap: bool = False,
) -> str:
    """Compose one portal import. `page` is "login" or "home".

    `preview` changes ONE thing and only ever adds to it: the import compiles
    `preview_languages` rather than the configured set, and parks the apply half
    of its language selector on `window` so the gallery's Language control can
    call it. Everything else -- the file shape, the slots, the frame -- is what
    the firewall receives, because a preview of a different page is not a
    preview. Nothing is spliced here; that is a separate stage.

    Guarded exactly as build_page's list is, and for the same reason: the swap
    global lands on `window` of a page whose markup PAN-OS half owns, and a
    preview construct reaching an import a customer uploads is precisely the
    silent failure this family exists to refuse.
    """
    if preview_languages and not preview:
        raise BuildError("preview_languages is a preview-only build; it must never reach deploy/")
    if preview_swap and not preview:
        raise BuildError("preview_swap is a preview-only build; it must never reach deploy/")
    if page not in FRAMES:
        raise BuildError(f"unknown portal page {page!r} -- expected one of {', '.join(sorted(FRAMES))}")

    shell = parse_sections(read(template_dir / "portal" / "shells" / f"{theme['shell']}.html"))
    parts = parse_sections(read(template_dir / "portal" / f"{page}.html"))

    for slot in FROM_PAGE[page]:
        if slot not in parts:
            raise BuildError(f"portal/{page}.html is missing its <!--@{slot}--> section")
    for slot in FROM_SHELL[page]:
        if slot not in shell:
            raise BuildError(f"portal/shells/{theme['shell']}.html is missing its <!--@{slot}--> section")
        parts[slot] = shell[slot]

    # `shipped`, not `languages`: a style declaring `"i18n": false` opts out of
    # BOTH families. One flag with one meaning is easier to explain, to document
    # and to test than "base-language block pages, multilingual portal", and a
    # style half-translated across its own two families is a worse artefact than
    # one that is consistently English. nyan's login import has 3562 B of
    # headroom and would fit German comfortably; it is a novelty style, and this
    # costs it nothing real.
    #
    # A preview build compiles `preview_languages` instead -- every language the
    # tree ships, whatever `languages` turned on -- but only where the style
    # carries the feature at all. The opt-out is the same opt-out either way, so
    # the gallery's control hides itself on nyan rather than offering a language
    # nyan's frames cannot answer. Same shape as build_page's `compiled`.
    #
    # `preview_swap` is the gallery's form: the hook without a single language
    # compiled behind it, because the gallery hands the dictionary in when a
    # reader asks for that language rather than inlining thirteen of them into
    # every frame it carries. The opt-out gates it here rather than inside
    # _values(), which never sees a theme -- and it gates the LIST too, where it
    # was previously left to `compiled` collapsing to one language.
    compiled = list(preview_languages) if preview_languages and i18n.enabled(theme) else i18n.shipped(cfg, theme)
    swap = preview and (bool(preview_languages) or preview_swap) and i18n.enabled(theme)
    values = _values(cfg, palette, page, template_dir.parent, compiled, swap=swap, external=swap and preview_swap)
    # Slot bodies carry {{COMPANY}}, {{PORTAL_NAME}} and the palette tokens, so
    # they are resolved BEFORE being placed in the frame -- re.sub does not
    # rescan replacement text.
    filled = {slot: substitute(parts[slot], values) for slot in FROM_PAGE[page] + FROM_SHELL[page]}

    out = substitute(FRAMES[page], filled)
    assert_resolved(out, f"portal/{page}")

    # Last, so the bytes that are measured are the bytes that ship. It must not
    # run earlier: parse_sections() needs the <!--@SLOT--> markers intact.
    return strip_output(out)


def preview_dicts(
    cfg: Mapping[str, Any],
    palette: Mapping[str, Any],
    page: str,
    template_dir: pathlib.Path,
    langs: Sequence[str],
) -> dict[str, Any]:
    """The per-language dictionaries the gallery hands a preview import.

    PREVIEW ONLY, and the reason this is here rather than in the builder: the
    copy has to be resolved against the same values the import itself was
    resolved against, or a swap would fill in a different {{COMPANY}} than the
    page was built with -- which is a preview of a page nobody will be served.

    Palette-independent and theme-independent in everything it reads, so the
    builder computes it once for the whole gallery rather than per frame.
    """
    values = _values(cfg, palette, page, template_dir.parent, [i18n.base_language(cfg)])
    return i18n.portal_dicts(cfg, page, template_dir.parent, values, langs=langs)


# The published dictionary. A global rather than a closure variable because the
# download widget below it is a separate <script> that needs three of these
# strings, and it must keep working -- in the base language -- when this block
# matched nothing. Uniquely named for the same reason every id here is: this
# runs inside PAN-OS' own document, beside PAN-OS' own scripts.
PORTAL_LANG_GLOBAL = "window.__gpT"


# Two rules govern every line of this family's JavaScript, and both fail
# SILENTLY on a firewall:
#
#   * No raw '<'. `i<L.length` is one, which is why the selection is written
#     with .some() rather than as a counting loop -- the same reason the stylesheet
#     disabler and the download widget already avoid one. A raw '<' anywhere in
#     the import stops PAN-OS substituting <pan_form/>, and the login form is
#     simply not there.
#   * Nothing in the LOGIN import may contain the string `logout_text_array`.
#     portal/validate.py tells the two imports apart by looking for it, and a
#     login file carrying it would be checked against the home rules.
def _i18n_open(dict_json: str) -> str:
    """Open the closure over the dictionary and the browser's language list."""
    return "(function(){var T=" + dict_json + ",L=navigator.languages||[navigator.language||''];\n"


def _i18n_select(base_lang: str) -> str:
    """Choose a language, or fall through to the markup.

    Split from the apply half below so a PREVIEW build can put that half behind
    a callable and this half in front of it. The two are concatenated back in
    the order they were always in for a deploy build, which is what keeps those
    imports byte-identical -- see _i18n_script.
    """
    return (
        "L.some(function(x){var k=x.slice(0,2).toLowerCase();\n"
        # The base language STOPS the search: a browser that ranks it above a
        # compiled language must keep the import it was served, which is already
        # in that language as real text.
        "if(k=='" + base_lang + "'){return true}\n"
        "if(!T[k]){return false}\n"
    )


# What closes the selection loop and the closure around it, once the apply half
# has run. A deploy build ends with exactly this; a preview build calls the apply
# half by name instead and closes the closure after publishing it.
_I18N_TAIL = "return true})})();"


# The home import is script-only and PAN-OS writes that body itself, so the one
# thing to translate is the array its ready handler reads.
#
# The timing is settled rather than assumed: fixtures/logout-suffix.html:26
# shows a real appliance reading logout_text_array[ 0 ] inside
# $(document).ready, and this is emitted at the end of <!--@HEAD_SCRIPT-->, a
# synchronous <script> in <head> that runs long before ready fires. Which of the
# seven the firewall picked is baked into the generated file, so the German
# array has to be the same seven entries in the same order -- the page has no
# way to know which index it will be handed.
_I18N_HOME = "var t=T[k];logout_text_array=t.lm;document.documentElement.lang=k;"

# The login import. This runs at the START of <!--@FOOT_SCRIPT--> because it
# needs both the parsed body and the form PAN-OS substituted into it -- in
# <head> it would find neither.
#
# `.pl` and `.ps` are SCOPED to #heading and .gloss. Both classes appear in both
# elements (one file serves login.esp and getsoftwarepage.esp, and the copy
# switches with them), so an unscoped selector swaps the wrong one.
#
# The last five swaps reach PAN-OS' OWN injected form, whose placeholders and
# button value are English -- see fixtures/pan_form-login.html. They are not
# this project's words, but they are addressable by id once the form has been
# substituted, and a German login page with an English "Username" box is a
# half-translated page. Every one is guarded, so a release that renames an id
# leaves PAN-OS' wording rather than breaking the page: the same degradation the
# download widget already takes on #taGetSofewarePage.
#
# Those five run TWICE, and the second time is not belt and braces. PAN-OS'
# prefix ends with `window.onload = loadPage`, and loadPage re-assigns
# #user.placeholder and #passwd.placeholder from its own labelUsername /
# labelPassword -- after this script, which is parser-inserted at the end of the
# body. Swapped once, the two boxes visibly revert to "Username" and "Password"
# while the rest of the page stays German. `window.onload` was assigned in the
# head, so it is registered before this listener and runs before it; re-applying
# on `load` is what makes the swap stick. This was found in a browser, not by
# reading: a DOM harness that never fires `load` shows the swap working.
#
# The placeholder swap also requires the existing placeholder to be NON-EMPTY.
# loadPage's Challenge branch deliberately blanks #passwd, because #dInputStr
# then carries the challenge prompt and the field is no longer a password;
# writing "Kennwort" over that blank would state something false.
_I18N_LOGIN = (
    "var t=" + PORTAL_LANG_GLOBAL + "=T[k],D=document;\n"
    "D.documentElement.lang=k;\n"
    "var Q=function(s){return D.querySelector(s)},"
    "S=function(s,v){var e=Q(s);if(e&&v){e.textContent=v}};\n"
    "S('#heading .pl',t.signIn);S('#heading .ps',t.getSoftware);\n"
    "S('.gloss .pl',t.glossSignIn);S('.gloss .ps',t.glossSoftware);\n"
    "S('#dllab',t.download);\n"
    "var c=Q('#dlcar');if(c){c.setAttribute('aria-label',t.otherPlatforms)}\n"
    # text, anchor, text -- the same three-node sentence the block pages swap,
    # and the same guard on it. The anchor between the fragments is built here,
    # so only the two text nodes are copy.
    "var n=Q('.note');if(n&&n.childNodes.length>2){"
    "n.childNodes[0].nodeValue=t.note[0];n.childNodes[2].nodeValue=t.note[1]}\n"
    "var P=function(s,v){var e=Q(s);if(e&&v&&e.placeholder){e.placeholder=v}};\n"
    "var F=function(){P('#user',t.formUser);P('#passwd',t.formPassword);\n"
    "P('#new_passwd',t.formNewPassword);P('#confirm_new_passwd',t.formConfirmPassword);\n"
    "var b=Q('#submit');if(b&&t.formSubmit){b.value=t.formSubmit}};\n"
    "F();window.addEventListener('load',F);\n"
)

_I18N = {"login": _I18N_LOGIN, "home": _I18N_HOME}


# PREVIEW ONLY, and appended INSIDE the apply half rather than to the swap that
# calls it -- `t` and `D` are declared there with `var`, so nothing outside can
# read them. Both blocks are no-ops on the load-time call, which is what lets
# them sit there: the login one is gated on an attribute the download widget
# sets in a LATER <script>, and the home one on an element that is not parsed
# yet when this runs in <head>.
#
# They exist for the same reason the block pages' gloss is re-resolved on a
# swap: a preview that agrees with the served page everywhere except the one
# element a reviewer opened it to judge is worse than no preview.
#
# login -- the download button's text is COMPUTED from the user agent, in a
# widget that moves PAN-OS' own anchors into a menu and therefore cannot be run
# twice. Its six strings are JS literals read out of the published dictionary at
# widget time, when nothing has been swapped yet, so a swap has to re-derive
# them. The hrefs the widget left behind carry everything needed: the platform,
# the bit-ness, and -- on #dlmain -- which of them was picked.
#
# home -- the seven logout messages reach the page through PAN-OS' own ready
# handler, which has already written one of them into #logout by the time a swap
# arrives. WHICH one is decided by the firewall at request time, so the index is
# found by looking the rendered text up in the array the page still holds,
# BEFORE the apply half replaces it. A re-captured fixture that shows a
# different message stays correct.
_PREVIEW_BEFORE = {
    "login": "",
    "home": "var e0=document.getElementById('logout'),i0=(window.logout_text_array||[]).indexOf(e0&&e0.textContent);\n",
}
_PREVIEW_AFTER = {
    "login": (
        "var dm=D.getElementById('dlmenu');\n"
        "if(dm&&D.documentElement.getAttribute('data-dl')=='on'){\n"
        "var H=function(e){return e.getAttribute('href')||''};\n"
        "var A=[].slice.call(dm.querySelectorAll('a'));\n"
        "A.forEach(function(e){var u=H(e);\n"
        "if(u.indexOf('platform=mac')!==-1){e.textContent=t.macos}\n"
        "else if(u.indexOf('platform=windows')!==-1){"
        "e.textContent=t.windows+(u.indexOf('version=64')!==-1?t.bit64:t.bit32)}});\n"
        "var mn=D.getElementById('dlmain'),lb=D.getElementById('dllab'),p=null;\n"
        "if(mn){A.forEach(function(e){if(H(e)===H(mn))p=e})}\n"
        "if(lb){lb.textContent=p?t.downloadFor+p.textContent:t.chooseDownload}\n"
        "}\n"
    ),
    "home": "if(e0&&i0!==-1&&t.lm[i0]){e0.textContent=t.lm[i0]}\n",
}


def _i18n_script(page: str, dict_json: str, base_lang: str, *, swap: bool = False) -> str:
    """The language selector for one import, or nothing to select between.

    An empty dictionary is not merely a saving: `T` would be `{}`, every lookup
    would miss, and the import would carry ~700 B of script that can never do
    anything.

    `swap` is the PREVIEW form. The apply half becomes `AP(k)`, the selection
    calls it, and the gallery gets the same function on `window` under the name
    the block pages already use -- one convention, so the control's load handler
    needs to know nothing about which family a frame belongs to.

    The deploy form is the two halves concatenated in the order they were always
    written in, so those imports do not move by a byte. That is asserted; it is
    the whole reason the split is a split rather than a second runtime.
    """
    # An empty dictionary in a PREVIEW build is not nothing to select between: it
    # is the gallery's form, where the words arrive from a sibling file at the
    # moment a reader picks that language. `T` starts empty, every lookup misses,
    # and the import renders the base language until the swap files one in.
    if dict_json == "" or (dict_json == "{}" and not swap):
        return ""
    if swap:
        # `g` rather than the block pages' `L`: that name is already the browser's
        # language list in this closure, and a parameter shadowing it reads as a
        # bug even where it is not one.
        body = (
            _i18n_open(dict_json)
            + "var AP=function(k){"
            + _PREVIEW_BEFORE[page]
            + _I18N[page]
            + _PREVIEW_AFTER[page]
            + "};\n"
            + _i18n_select(base_lang)
            + "AP(k);return true});\n"
            # The dictionary as an argument, filed in `T` before it is read back
            # out: the gallery compiles none into the import and hands one over
            # when a reader asks for that language. Omitted, `T` answers as it
            # always did -- which is what an import built with its languages
            # compiled in still does.
            + f"window.{PREVIEW_SWAP}=function(g,d){{if(d)T[g]=d;if(!T[g])return;AP(g)}};\n"
            + "})();"
        )
    else:
        body = _i18n_open(dict_json) + _i18n_select(base_lang) + _I18N[page] + _I18N_TAIL
    return "<script>\n" + body + "\n</script>"


# The six strings the download widget writes. They are the only copy in this
# family that is a JS LITERAL rather than markup: the button's text is COMPUTED
# from the user agent, so there is no element standing in the document with the
# words already in it for the selector above to swap.
#
# They are filled from the strings file all the same, which is what keeps the
# base language out of the template -- and it is what makes the two forms below
# possible at all.
DOWNLOAD_LITERALS = ("macos", "windows", "bit64", "bit32", "downloadFor", "chooseDownload")


def _download_values(login: Mapping[str, Any], *, multilingual: bool) -> dict[str, str]:
    """The DL_* placeholders: a bare literal, or a lookup that falls back to it.

    The single-language form is the literal ALONE -- not `(T.x||'...')` with an
    empty dictionary behind it. That is the promise the byte-identity snapshot
    holds this family to: a customer who configures one language gets exactly the
    import they got before any of this existed, down to the byte.
    """
    out = {}
    for key in DOWNLOAD_LITERALS:
        literal = _js_string(str(login[key]))
        out[f"DL_{key.upper()}"] = f"(T.{key}||{literal})" if multilingual else literal
    # Read once, at the top of the widget, so a swap does not depend on the
    # selector still being in scope -- it is a separate <script>. `||{}` is what
    # makes every lookup above degrade to its literal when nothing matched.
    out["DL_T"] = f"var T={PORTAL_LANG_GLOBAL}||{{}};" if multilingual else ""
    return out


def _css_string(value: str) -> str:
    """The body of one double-quoted CSS string, for a `content:` declaration.

    The logout page's body belongs to PAN-OS, so the company name cannot be put
    beside the mark as markup there -- a ::after on our own stylesheet is the
    only way in. That makes this text a CSS string, and customer config is where
    an unescaped quote would come from.

    '<' becomes a hex escape rather than being left alone: one raw '<' outside a
    tag stops PAN-OS substituting the form token, and a company name is not
    somewhere anyone would look for that.
    """
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("<", "\\3c ")


def _js_string(value: str) -> str:
    """One single-quoted JS string literal.

    Single quotes to match every other variable in the two imports. '<' is
    escaped rather than emitted: one raw '<' outside a tag stops PAN-OS
    substituting the form token, and this text comes from customer config where
    the guard would only surface it after the fact.
    """
    body = value.replace("\\", "\\\\").replace("'", "\\'").replace("<", "\\x3c")
    return f"'{body}'"


# Which palette entry each S_* token falls back to when the artwork is drawn on
# the accent rather than on the ground. Figure and ground swap: everything that
# was ink becomes the colour that reads on the accent, and everything that was a
# page surface becomes the accent itself. Without this a shell that puts the
# logo on an accent band -- banner does -- paints an accent mark on an accent
# field and the logo vanishes.
ON_ACCENT = {
    "ink": "accent_ink",
    "ink_muted": "accent_ink",
    "ink_faint": "accent_ink",
    "accent": "accent_ink",
    "accent_text": "accent_ink",
    "ground": "accent",
    "surface": "accent",
    "surface_alt": "accent",
    "accent_ink": "accent",
    "accent_wash": "accent",
}


def _logo(
    cfg: Mapping[str, Any],
    palette: Mapping[str, Any],
    base: Mapping[str, str],
    *,
    dark: bool,
    on_accent: bool = False,
) -> str:
    """The portal logo, percent-encoded, for one scheme and one backdrop.

    An SVG referenced by `url()` or by an `<img>` renders as an isolated
    document: it inherits nothing from the embedding page, so `currentColor` is
    dead and the shell's custom properties are out of scope. The colours have to
    be baked in, which is why this runs more than once.

    The scheme is expressed as `S_*` rather than as the shells' `C_*`. Every
    copy of the artwork is the same source file, and it has no way to say "the
    accent for whichever scheme this copy is" if the token names already carry a
    scheme. So `S_ACCENT` is the light `accent` in one pass and `d_accent` in
    the other, and the shell picks between the results.
    """
    colors = palette["colors"]
    scheme = {k: str(v) for k, v in colors.items() if not k.startswith("d_")}
    if dark:
        scheme.update({k[2:]: str(v) for k, v in colors.items() if k.startswith("d_")})
    if on_accent:
        scheme = {k: scheme.get(ON_ACCENT.get(k, k), v) for k, v in scheme.items()}
    scheme = {f"S_{k.upper()}": v for k, v in scheme.items()}

    key = "portalLogoSvgDark" if dark and cfg.get("portalLogoSvgDark") else "portalLogoSvg"
    svg = substitute(str(cfg[key]), {**base, **scheme})
    if not svg.lstrip().startswith("<svg"):
        raise BuildError(f"{key} must be SVG source starting with <svg -- the build does the data: encoding")
    # Caught here rather than by the frame's leftover check: by the time this
    # reaches the frame it is percent-encoded, so an unresolved token reads as
    # %7B%7BFOO%7D%7D and the generic check never sees it.
    assert_resolved(svg, key)
    return quote(svg, safe=LOGO_SAFE)


def _values(
    cfg: Mapping[str, Any],
    palette: Mapping[str, Any],
    page: str,
    data_dir: pathlib.Path,
    langs: Sequence[str],
    *,
    swap: bool = False,
    external: bool = False,
) -> dict[str, str]:
    """Everything a portal slot may reference.

    `langs` is what this import COMPILES -- the configured set on a deploy build,
    every language the tree ships on a preview one. `swap` publishes the preview
    hook; it is derived from the preview list rather than passed on its own, so
    it cannot be turned on for an import a firewall serves.

    `external` is the gallery's form: no language is compiled, and the runtime is
    emitted anyway so there is something to hand a dictionary to. It only ever
    accompanies `swap`, so nothing a firewall serves can take this branch.
    """
    multilingual = len(langs) > 1 or external
    contact.check(cfg)
    base = {
        "COMPANY": str(cfg["company"]),
        "SUPPORT_EMAIL": contact.email(cfg),
    }
    # The portal has no pre-filled body to carry -- there is no incident to
    # describe on a login page -- so email mode is a bare mailto rather than the
    # per-page mailto the response pages build.
    contact_values = {
        "CONTACT_HREF": contact.href(cfg, f"mailto:{contact.email(cfg)}"),
        "CONTACT_NAME": contact.name(cfg),
        "CONTACT_REACHABLE": contact.reachable(cfg),
    }
    values: dict[str, str] = dict(base)
    values.update(contact_values)
    values["MARK"] = str(cfg["marks"]["shield"])
    # The same name again, escaped for a CSS content: string. The mark is only a
    # symbol; the wordmark is live text, which is what makes a rename in config
    # reach the portal at all.
    values["COMPANY_CSS"] = _css_string(base["COMPANY"])
    # The heading text. Carried in markup rather than in gp_portal_name, which
    # PAN-OS applies with .html() and would use to replace the whole heading.
    values["PORTAL_NAME"] = substitute(str(cfg["portalName"]), base)
    # Copy, resolved against the values above -- a portal string may carry
    # {{COMPANY}} just as a block-page string may, and substitute() will not
    # rescan its own replacement.
    #
    # Read from `data_dir`, which is the portal template directory's parent. On a
    # data directory that predates this family that is the PACKAGED tree rather
    # than the customer's -- the same fallback datadir.portal_data() already
    # warns about, and the same consequence: portal edits made there are ignored
    # until `init --force` refreshes it.
    strings = i18n.load(i18n.base_language(cfg), data_dir)
    values.update(i18n.portal_values(strings, page, values))
    if page == "login":
        values.update(_download_values(i18n.resolve(strings["portal"]["login"], values), multilingual=multilingual))
    # The language runtime, and the empty string on the single-language builds
    # that are every existing customer -- which is what keeps those imports
    # byte-identical to imports from before this existed. `strip_output` drops
    # the blank line the empty value leaves behind.
    values["PORTAL_I18N"] = (
        _i18n_script(
            page,
            i18n.portal_runtime(cfg, page, data_dir, values, langs=langs),
            i18n.base_language(cfg),
            swap=swap,
        )
        if multilingual
        else ""
    )
    # The artwork, encoded once per scheme. The shells write the media type
    # prefix themselves, so these are the encoded SVG alone; PORTAL_LOGO_URI is
    # the whole URI, for the one place that still needs it in a JS string.
    light = _logo(cfg, palette, base, dark=False)
    values["PORTAL_LOGO_LIGHT"] = light
    values["PORTAL_LOGO_DARK"] = _logo(cfg, palette, base, dark=True)
    # For shells that stand the logo on the accent instead of on the ground. A
    # shell references one pair or the other, never both, so this costs nothing
    # in the imports that do not use it.
    values["PORTAL_LOGO_ACC_LIGHT"] = _logo(cfg, palette, base, dark=False, on_accent=True)
    values["PORTAL_LOGO_ACC_DARK"] = _logo(cfg, palette, base, dark=True, on_accent=True)
    # The `logo` variable brands the portal HOME page -- stock Bootstrap markup
    # this family does not restyle, and which is light whatever the visitor's
    # scheme is. So it gets the light copy, and only that page uses it.
    values["PORTAL_LOGO_URI"] = SVG_URI_PREFIX + light
    # The messages name a contact, so they need the contact tokens as well as
    # `base`. Resolved before encoding -- substitute() does not rescan
    # replacement text, so a token left inside the array would ship literally.
    messages = [substitute(str(m), {**base, **contact_values}) for m in cfg["logoutMessages"]]
    values["LOGOUT_MESSAGES"] = "[" + ",".join(_js_string(m) for m in messages) + "]"
    values.update({f"C_{k.upper()}": str(v) for k, v in palette["colors"].items()})
    grad = palette.get("gradient", {})
    values.update(
        {
            "C_GRAD_FROM": str(grad.get("from", palette["colors"]["accent"])),
            "C_GRAD_TO": str(grad.get("to", palette["colors"]["accent"])),
            "C_GRAD_ANGLE": str(grad.get("angle", "135deg")),
        }
    )
    return values
