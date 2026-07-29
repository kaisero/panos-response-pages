"""Orchestration: build every page of every theme, validate, report.

Split from the CLI so the whole build is callable in-process. That is what lets
tests assert on results rather than on a subprocess exit code -- and it is why
coverage can see any of this at all.
"""

from __future__ import annotations

import json
import pathlib
import shutil
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from panos_response_pages import datadir
from panos_response_pages.config import load_config
from panos_response_pages.emit import strip_output
from panos_response_pages.errors import BuildError
from panos_response_pages.gallery import build_gallery
from panos_response_pages.page import build_page
from panos_response_pages.palettes import load_palette
from panos_response_pages.portal.page import build_portal_page
from panos_response_pages.portal.splice import LOGIN_PREVIEWS, splice_home, splice_login
from panos_response_pages.portal.validate import MAX_ENCODED, SOFT_MAX, encoded_size, validate_portal
from panos_response_pages.templates import read
from panos_response_pages.validate import MAX_BYTES, PAGE_TOKENS, validate

# The two GlobalProtect portal imports, in the order the report lists them.
PORTAL_PAGES = ("login", "home")

# What a preview of the portal family consists of. The four login states are one
# import rendered four ways -- PAN-OS decides which by what it writes into
# loadPage() -- and getsoftware is that same import with the other form in it.
PORTAL_PREVIEWS = (*LOGIN_PREVIEWS, "getsoftware", "logout")

# Where the captured asset tree is written, relative to the preview root, and
# how to reach it from each of the two places a preview renders.
#
# The prefixes load jQuery by relative path, and jQuery is what fills the login
# logo -- so a wrong prefix here is not a broken image, it is a blank box that
# reads as the page's own fault. The gallery inlines its frames with srcdoc,
# whose relative URLs resolve against the gallery document, hence two answers.
PREVIEW_ASSETS = "portal"
ASSETS_FROM_GALLERY = f"{PREVIEW_ASSETS}/"
ASSETS_FROM_PAGE = f"../../{PREVIEW_ASSETS}/"


@dataclass
class PageResult:
    """One built page and everything the report needs to say about it."""

    theme: str
    page: str
    size: int
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        return "FAIL" if self.errors else ("warn" if self.warnings else "ok")


@dataclass
class PortalResult:
    """One built GlobalProtect portal import.

    Separate from PageResult because the number that matters is a different
    number. A block page is measured against a serving-time byte limit; a portal
    import is measured against an import-time limit on its *base64* form, and
    the encoded length is the figure PAN-OS quotes back when it refuses one.
    Carrying both families in one list would give one column two meanings.
    """

    theme: str
    page: str
    size: int
    encoded: int
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        return "FAIL" if self.errors else ("warn" if self.warnings else "ok")


@dataclass
class BuildResult:
    results: list[PageResult]
    data_dir: pathlib.Path
    data_reason: str
    palette: dict[str, Any]
    out_dir: pathlib.Path
    # Deliberately not merged into `results`: that list is the block-page family
    # and its length is asserted against PAGE_TOKENS. A second family appearing
    # in it would break an invariant that has nothing to do with the portal.
    portal_results: list[PortalResult] = field(default_factory=list)

    @property
    def failed(self) -> bool:
        return any(r.errors for r in self.results) or any(r.errors for r in self.portal_results)

    @property
    def largest(self) -> int:
        return max((r.size for r in self.results), default=0)

    @property
    def portal_largest(self) -> int:
        return max((r.size for r in self.portal_results), default=0)


def load_themes(data_dir: pathlib.Path, only: str | None = None) -> list[dict[str, Any]]:
    themes: list[dict[str, Any]] = [json.loads(read(p)) for p in sorted((data_dir / "themes").glob("*.json"))]
    if not themes:
        raise BuildError(f"no themes found in {data_dir / 'themes'}")
    if only:
        themes = [t for t in themes if t["name"] == only]
        if not themes:
            raise BuildError(f"no theme {only}")
    return themes


def build_all(
    data_dir: pathlib.Path,
    out_dir: pathlib.Path,
    *,
    customer: str = "contoso",
    theme: str | None = None,
    palette_name: str | None = None,
    preview: bool = True,
    data_reason: str = "explicit",
    write: bool = True,
    deploy_subdir: str = "deploy",
    preview_subdir: str = "preview",
) -> BuildResult:
    """Build every page of every selected theme.

    `write=False` builds and validates without touching the filesystem, which is
    what most tests want.

    The two subdirectory names are parameters only so the legacy `build.py`
    entry point can keep emitting `dist/` and `preview/` at the repository root
    while this code is proven against the existing suite. They collapse to their
    defaults when that shim goes.
    """
    cfg = load_config(customer, data_dir / "config")
    palette = load_palette(palette_name or cfg.get("palette", "cyber-orange"), data_dir / "palettes")
    themes = load_themes(data_dir, theme)
    pages = sorted(PAGE_TOKENS)
    template_dir = data_dir / "templates"
    # The portal family may come from elsewhere: a data directory copied out
    # before this family existed has neither templates/portal/ nor fixtures/,
    # and refusing to build at all would take the block pages down with it.
    portal_dir = datadir.portal_data(data_dir)
    portal_templates = portal_dir / "templates"
    fixtures = portal_dir / "fixtures"

    results: list[PageResult] = []
    portal_results: list[PortalResult] = []
    blobs: dict[tuple[str, str], str] = {}
    portal_blobs: dict[tuple[str, str], str] = {}

    for th in themes:
        deploy_dir = out_dir / deploy_subdir / th["name"]
        prev_dir = out_dir / preview_subdir / th["name"]
        if write:
            deploy_dir.mkdir(parents=True, exist_ok=True)
            if preview:
                prev_dir.mkdir(parents=True, exist_ok=True)

        for page in pages:
            # strip_output runs here, before validate(), so the bytes that are
            # measured are the bytes that ship. It must not run any earlier:
            # parse_sections() needs the <!--@SLOT--> markers intact.
            deployable = strip_output(build_page(page, th, cfg, palette, False, template_dir))
            size, errors, warnings = validate(page, th["name"], deployable)
            if write:
                # write_bytes, never write_text: write_text translates "\n" to
                # os.linesep, so on Windows every line would gain a byte AFTER
                # validate() measured the string, and an oversize page would
                # ship with the report still saying ok.
                (deploy_dir / f"{page}.html").write_bytes(deployable.encode("utf-8"))

            if preview:
                pv = strip_output(build_page(page, th, cfg, palette, True, template_dir))
                blobs[th["name"], page] = pv
                if write:
                    (prev_dir / f"{page}.html").write_bytes(pv.encode("utf-8"))

            results.append(PageResult(th["name"], page, size, errors, warnings))

        imports: dict[str, str] = {}
        for page in PORTAL_PAGES:
            # build_portal_page strips on the way out, so these are already the
            # bytes the firewall receives; nothing may touch them afterwards.
            imports[page] = build_portal_page(page, th, cfg, palette, False, portal_templates)
            size, errors, warnings = validate_portal(imports[page])
            encoded = encoded_size(imports[page])
            if write:
                # A subdirectory, not a portal-login.html prefix: the two
                # families are imported into different PAN-OS objects, and
                # keeping them apart on disk is what stops a `deploy/<theme>/*`
                # glob from sweeping a portal import into a block-page upload.
                (deploy_dir / "portal").mkdir(parents=True, exist_ok=True)
                (deploy_dir / "portal" / f"{page}.html").write_bytes(imports[page].encode("utf-8"))
            portal_results.append(PortalResult(th["name"], page, size, encoded, errors, warnings))

        if preview:
            # Spliced. PREVIEW ONLY, and never written anywhere `validate`
            # walks: each of these carries PAN-OS' own prefix and a captured
            # form, which the import guards reject on sight -- correctly.
            portal_blobs.update(
                {(th["name"], name): text for name, text in _splice(imports, ASSETS_FROM_GALLERY, fixtures).items()}
            )
            if write:
                (prev_dir / "portal").mkdir(parents=True, exist_ok=True)
                for name, text in _splice(imports, ASSETS_FROM_PAGE, fixtures).items():
                    (prev_dir / "portal" / f"{name}.html").write_bytes(text.encode("utf-8"))

    if preview and write:
        # The captured portal asset tree, once, beside the gallery. jQuery is in
        # here, and without it the prefixes' ready handler never runs and every
        # login preview shows an empty logo box.
        shutil.copytree(fixtures / "portal", out_dir / preview_subdir / PREVIEW_ASSETS, dirs_exist_ok=True)
        gallery = build_gallery(themes, pages, blobs, cfg, palette, portal_blobs, PORTAL_PREVIEWS)
        (out_dir / preview_subdir / "index.html").write_bytes(gallery.encode("utf-8"))

    return BuildResult(results, data_dir, data_reason, palette, out_dir, portal_results)


def _splice(imports: Mapping[str, str], assets: str, fixtures: pathlib.Path) -> dict[str, str]:
    """The six portal previews, with asset references pointed at `assets`."""
    out = {
        name: splice_login(imports["login"], "login", name.removeprefix("login-"), assets=assets, fixtures=fixtures)
        for name in LOGIN_PREVIEWS
    }
    out["getsoftware"] = splice_login(imports["login"], "getsoftware", assets=assets, fixtures=fixtures)
    out["logout"] = splice_home(imports["home"], assets=assets, fixtures=fixtures)
    return out


def format_report(result: BuildResult) -> str:
    """The size table. This is the tool's product, not chatter, so it goes to
    stdout as plain text and stays parseable by eye."""
    lines = [f"\n  {'theme':10} {'page':24} {'bytes':>7}  {'of limit':>9}  status", "  " + "-" * 66]
    for r in result.results:
        pct = f"{r.size / MAX_BYTES * 100:.0f}%"
        lines.append(f"  {r.theme:10} {r.page:24} {r.size:>7}  {pct:>9}  {r.status}")
        lines += [f"      ! {e}" for e in r.errors]
        lines += [f"      ~ {w}" for w in r.warnings]
    lines.append("  " + "-" * 66)
    lines.append(
        f"  ceiling {MAX_BYTES} B  |  largest page {result.largest} B  |  headroom {MAX_BYTES - result.largest} B"
    )
    if result.portal_results:
        lines += _portal_report(result)
    return "\n".join(lines)


def _portal_report(result: BuildResult) -> list[str]:
    """The portal table, measured against the portal's own ceiling.

    A separate table, not extra rows, because the limit is a different limit.
    MAX_BYTES is what the dataplane will serve; SOFT_MAX is what the management
    plane will accept as a base64 field. Showing a portal import as a percentage
    of MAX_BYTES would read as 60% of a limit it is not subject to.

    The encoded column is there because that is the only number PAN-OS ever
    says out loud: "page can be at most 21845 characters, but current length: N".
    """
    lines = [
        "",
        f"  {'theme':10} {'portal import':24} {'bytes':>7}  {'encoded':>7}  {'of ceiling':>10}  status",
        "  " + "-" * 76,
    ]
    for r in result.portal_results:
        pct = f"{r.size / SOFT_MAX * 100:.0f}%"
        lines.append(f"  {r.theme:10} {r.page:24} {r.size:>7}  {r.encoded:>7}  {pct:>10}  {r.status}")
        lines += [f"      ! {e}" for e in r.errors]
        lines += [f"      ~ {w}" for w in r.warnings]
    lines.append("  " + "-" * 76)
    lines.append(
        f"  import ceiling {SOFT_MAX} B ({MAX_ENCODED} encoded)  |  "
        f"largest import {result.portal_largest} B  |  headroom {SOFT_MAX - result.portal_largest} B"
    )
    return lines
