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
import re
from collections.abc import Mapping
from typing import Any

from panos_response_pages.emit import strip_output
from panos_response_pages.errors import BuildError
from panos_response_pages.templates import parse_sections, read, substitute

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

_SLOT_RE = re.compile(r"\{\{([A-Z_0-9]+)\}\}")

# The logout logo is a CSS background, and the shells write this prefix
# literally so the rule reads as artwork rather than as a substitution.
SVG_URI_PREFIX = "data:image/svg+xml,"


def build_portal_page(
    page: str,
    theme: Mapping[str, Any],
    cfg: Mapping[str, Any],
    palette: Mapping[str, Any],
    preview: bool,
    template_dir: pathlib.Path,
) -> str:
    """Compose one portal import. `page` is "login" or "home".

    `preview` is accepted for symmetry with build_page and because the caller
    decides per build; neither import changes shape for preview. Preview is
    produced by splicing the captured PAN-OS prefix around this output, which is
    a separate stage -- these bytes are always the bytes the firewall receives.
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
    if "{{" in out:
        leftover = sorted(set(_SLOT_RE.findall(out)))
        raise BuildError(f"unresolved placeholder(s) in portal/{page}: {', '.join(leftover)}")

    # Last, so the bytes that are measured are the bytes that ship. It must not
    # run earlier: parse_sections() needs the <!--@SLOT--> markers intact.
    return strip_output(out)


def _js_string(value: str) -> str:
    """One single-quoted JS string literal.

    Single quotes to match every other variable in the two imports. '<' is
    escaped rather than emitted: one raw '<' outside a tag stops PAN-OS
    substituting the form token, and this text comes from customer config where
    the guard would only surface it after the fact.
    """
    body = value.replace("\\", "\\\\").replace("'", "\\'").replace("<", "\\x3c")
    return f"'{body}'"


def _values(cfg: Mapping[str, Any], palette: Mapping[str, Any]) -> dict[str, str]:
    """Everything a portal slot may reference."""
    base = {
        "COMPANY": str(cfg["company"]),
        "SUPPORT_EMAIL": str(cfg["supportEmail"]),
    }
    values: dict[str, str] = dict(base)
    values["MARK"] = str(cfg["marks"]["shield"])
    # The heading text. Carried in markup rather than in gp_portal_name, which
    # PAN-OS applies with .html() and would use to replace the whole heading.
    values["PORTAL_NAME"] = substitute(str(cfg["portalName"]), base)
    # A data: URI, not inline markup: the portal needs it inside a JS string.
    uri = str(cfg["portalLogoUri"])
    if not uri.startswith(SVG_URI_PREFIX):
        raise BuildError(f"portalLogoUri must be an {SVG_URI_PREFIX} URI -- the logout logo is painted from CSS")
    values["PORTAL_LOGO_URI"] = uri
    # The same artwork with the media type split off, because the logout shells
    # write that prefix literally. A stylesheet is the only thing that paints the
    # logo at first paint, and spelling the media type out in the shell is what
    # lets that rule be asserted rather than assumed.
    values["PORTAL_LOGO_SVG"] = uri[len(SVG_URI_PREFIX) :]
    # {{SUPPORT_EMAIL}} is resolved before encoding -- substitute() does not
    # rescan replacement text, so a token left inside the array would ship
    # literally. No spaces after the commas: every byte is measured.
    messages = [substitute(str(m), base) for m in cfg["logoutMessages"]]
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
