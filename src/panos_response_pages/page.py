"""Assembling one page from a shell, a page template, a config and a palette."""

from __future__ import annotations

import pathlib
import re
from collections.abc import Mapping
from typing import Any

from panos_response_pages import redirect
from panos_response_pages.errors import BuildError
from panos_response_pages.scripts import FRAME_BUSTER, SEV_LABEL, category_js
from panos_response_pages.templates import parse_sections, read, substitute
from panos_response_pages.validate import TOKEN_RE

# Sample values used only in preview builds.
SAMPLE = {
    "user": "ACME\\jdoe",
    "url": "https://example.com/promo/spring-sale?ref=email&id=88213",
    "category": "command-and-control",
    "ssurl": "https://www.bing.com/account/general",
    "pan_form": ('<form method="post" action="#"><input type="submit" value="Continue"></form>'),
    "fname": "Q4-forecast-final.xlsm",
    "appname": "bittorrent",
    # <cookie/> is the File Blocking Continue mechanism: PAN-OS injects markup
    # that sets a cookie and reloads to resume the download.
    "cookie": ('<form method="post" action="#"><input type="submit" value="Continue"></form>'),
}


def build_page(
    page: str,
    theme: Mapping[str, Any],
    cfg: Mapping[str, Any],
    palette: Mapping[str, Any],
    preview: bool,
    template_dir: pathlib.Path,
) -> str:
    shell = read(template_dir / "shells" / f"{theme['shell']}.html")
    parts = parse_sections(read(template_dir / "pages" / f"{page}.html"))

    for required in ("TITLE", "HEADLINE", "GLOSS", "FACTS", "ACTIONS"):
        if required not in parts:
            raise BuildError(f"{page}.html is missing its <!--@{required}--> section")

    # Page sections may themselves contain {{COMPANY}} / {{SUPPORT_EMAIL}}, so they
    # must be resolved BEFORE being inserted into the shell -- re.sub does not
    # rescan replacement text, which would otherwise emit a literal
    # "mailto:{{SUPPORT_EMAIL}}" into every page.
    base = {
        "COMPANY": cfg["company"],
        "SUPPORT_EMAIL": cfg["supportEmail"],
        "LOGO_SVG": cfg["logoSvg"],
        # The Continue/Override grant duration is administrator-configurable per
        # firewall (PAN-OS only defaults to 15 minutes), so the page must not
        # hardcode it -- that would assert a fact it cannot know.
        "CONTINUE_GRANT": cfg["continueGrantText"],
        "WARN_MARK": cfg["marks"]["warning"],
        "INFO_MARK": cfg["marks"]["info"],
    }
    parts = {k: substitute(v, base) for k, v in parts.items()}

    # Three empty strings unless this is the URL block page and a customer opted
    # in, so every other page -- and every build with the feature off -- is
    # byte-identical to one from before it existed.
    redirect_css, redirect_html, redirect_js = redirect.emit(cfg, page)

    values = dict(base)
    values.update(
        {
            "TITLE": parts["TITLE"],
            "HEADLINE": parts["HEADLINE"],
            "GLOSS": parts["GLOSS"],
            "FACTS": parts["FACTS"],
            "ACTIONS": parts["ACTIONS"],
            "EXTRA": parts.get("EXTRA", ""),
            "TONE": parts.get("TONE", "calm"),
            "SEVERITY": SEV_LABEL.get(parts.get("TONE", "calm"), ""),
            "MARK": parts.get("MARK", cfg["marks"]["shield"]),
            "REDIRECT_CSS": redirect_css,
            "REDIRECT": redirect_html,
            # The frame-buster is correct on a live page -- a response page rendered
            # inside a third-party iframe is a broken state. But it must not ship in
            # preview builds, or every gallery iframe would replace the gallery itself.
            # Emit the category map only where it can actually be used: a page that
            # declares no id="cat" (safe-search has no <category/> token) would carry
            # ~1.7 KB of dead JSON.
            # The redirect script runs LAST: it reads the tone the category
            # lookup resolved, and a calm-only guard against an attribute that
            # has not been set yet would arm on every page.
            "SCRIPTS": ("" if preview else FRAME_BUSTER)
            + category_js(
                cfg["categories"],
                cfg["defaultGloss"],
                lock_copy=parts.get("COPY_LOCK", "").strip() == "1" or 'id="cat"' not in parts["FACTS"],
            )
            + redirect_js,
        }
    )
    values.update({f"C_{k.upper()}": v for k, v in palette["colors"].items()})
    # Gradients are linear and run the 500 stop to the 1000 stop.
    # Radial variants and mixed hues are not used, so only these two
    # stops and one angle are exposed.
    grad = palette.get("gradient", {})
    values.update(
        {
            "C_GRAD_FROM": grad.get("from", palette["colors"]["accent"]),
            "C_GRAD_TO": grad.get("to", palette["colors"]["accent"]),
            "C_GRAD_ANGLE": grad.get("angle", "135deg"),
        }
    )

    out: str = substitute(shell, values)
    if "{{" in out:
        leftover = sorted(set(re.findall(r"\{\{([A-Z_0-9]+)\}\}", out)))
        raise BuildError(f"unresolved placeholder(s) in {page}: {', '.join(leftover)}")

    if preview:
        out = TOKEN_RE.sub(lambda m: SAMPLE[m.group(1)], out)

    return out
