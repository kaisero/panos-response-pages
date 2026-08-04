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
from collections.abc import Mapping
from typing import Any
from urllib.parse import quote

from panos_response_pages import contact
from panos_response_pages.emit import strip_output
from panos_response_pages.errors import BuildError
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
) -> str:
    """Compose one portal import. `page` is "login" or "home".

    There is deliberately no `preview` parameter, unlike build_page: neither
    import changes shape for preview. Preview is produced by splicing the
    captured PAN-OS prefix around this output, which is a separate stage -- so
    these bytes are always the bytes the firewall receives.
    """
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

    values = _values(cfg, palette)
    # Slot bodies carry {{COMPANY}}, {{PORTAL_NAME}} and the palette tokens, so
    # they are resolved BEFORE being placed in the frame -- re.sub does not
    # rescan replacement text.
    filled = {slot: substitute(parts[slot], values) for slot in FROM_PAGE[page] + FROM_SHELL[page]}

    out = substitute(FRAMES[page], filled)
    assert_resolved(out, f"portal/{page}")

    # Last, so the bytes that are measured are the bytes that ship. It must not
    # run earlier: parse_sections() needs the <!--@SLOT--> markers intact.
    return strip_output(out)


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


def _values(cfg: Mapping[str, Any], palette: Mapping[str, Any]) -> dict[str, str]:
    """Everything a portal slot may reference."""
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
