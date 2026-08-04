"""Orchestration: build every page of every theme, validate, report.

Split from the CLI so the whole build is callable in-process. That is what lets
tests assert on results rather than on a subprocess exit code -- and it is why
coverage can see any of this at all.
"""

from __future__ import annotations

import json
import pathlib
import shutil
from collections.abc import Container, Mapping
from dataclasses import dataclass, field
from typing import Any

from panos_response_pages import datadir, logs, redirect
from panos_response_pages.config import customer_keys, load_config
from panos_response_pages.emit import strip_output
from panos_response_pages.errors import BuildError
from panos_response_pages.gallery import build_gallery
from panos_response_pages.page import build_page
from panos_response_pages.palettes import load_palette
from panos_response_pages.palettes import select as palettes_select
from panos_response_pages.portal.page import FRAMES, build_portal_page
from panos_response_pages.portal.splice import LOGIN_PREVIEWS, splice_home, splice_login
from panos_response_pages.portal.validate import MAX_ENCODED, SOFT_MAX, encoded_size, validate_portal
from panos_response_pages.templates import read
from panos_response_pages.validate import MAX_BYTES, PAGE_TOKENS, validate

# The two GlobalProtect portal imports, in the order the report lists them.
# Derived from FRAMES rather than restated: FRAMES is the module that would break
# first if a third import appeared, so it is the one that gets to say how many
# there are.
PORTAL_PAGES = tuple(FRAMES)

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
ASSETS_FROM_PAGE = f"../../../{PREVIEW_ASSETS}/"


@dataclass
class PageResult:
    """One built page and everything the report needs to say about it."""

    theme: str
    page: str
    size: int
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    # Which palette this row was rendered in. Every theme now renders in every
    # palette by design, so this is not a verdict on the row -- it is the
    # coordinate that says which cell of the theme x palette matrix it is.
    palette: str = ""

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
    palette: str = ""

    @property
    def status(self) -> str:
        return "FAIL" if self.errors else ("warn" if self.warnings else "ok")


@dataclass
class BuildResult:
    results: list[PageResult]
    # The palette the gallery opens on. Not "what was built" -- every palette is
    # built every time; this is only the one a reviewer sees first.
    palette: dict[str, Any]
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


def opening_palette(
    cfg: Mapping[str, Any],
    chosen: Container[str],
    theme: Mapping[str, Any],
    palette_name: str | None,
) -> str:
    """Which palette the gallery opens on, first hit wins.

    1. --palette, because asking for it on the command line means it
    2. `palette` in the CUSTOMER's config file -- their document, their call
    3. the theme's own pin, for a style that owns its colour
    4. the shipped default

    The same precedence that used to decide which palette a theme was BUILT in.
    Every theme is now built in every palette, so all this decides is which one
    a reviewer sees first -- and the dropdown moves off it in one click.

    Step 2 is why `chosen` exists rather than a plain `cfg["palette"]`:
    _defaults.json sets a palette, so the merged config always carries one and a
    pin would never fire.
    """
    return str(
        palette_name
        or (cfg["palette"] if "palette" in chosen else None)
        or theme.get("palette")
        or cfg.get("palette", "cyber-orange")
    )


def build_all(
    data_dir: pathlib.Path,
    out_dir: pathlib.Path,
    *,
    customer: str = "contoso",
    theme: str | None = None,
    palette_name: str | None = None,
    preview: bool = True,
    write: bool = True,
) -> BuildResult:
    """Build every page of every selected theme.

    `write=False` builds and validates without touching the filesystem, which is
    what most tests want.
    """
    cfg = load_config(customer, data_dir / "config")
    chosen = customer_keys(customer, data_dir / "config")
    palette_dir = data_dir / "palettes"

    themes = load_themes(data_dir, theme)
    pages = sorted(PAGE_TOKENS)
    template_dir = data_dir / "templates"
    # The portal family may come from elsewhere: a data directory copied out
    # before this family existed has neither templates/portal/ nor fixtures/,
    # and refusing to build at all would take the block pages down with it.
    portal_dir = datadir.portal_data(data_dir)
    portal_templates = portal_dir / "templates"
    fixtures = portal_dir / "fixtures"

    def emit(path: pathlib.Path, text: str) -> None:
        """Write one built file, or nothing at all when write=False.

        write_bytes, never write_text: write_text translates "\n" to os.linesep,
        so on Windows every line would gain a byte AFTER validate() measured the
        string, and an oversize page would ship with the report still saying ok.
        Stated here once rather than at each of the five call sites.

        The mkdir calls stay guarded at their own sites: folding them in here
        would mean a mkdir per file rather than per directory, ~750 syscalls a
        build for no gain.
        """
        if write:
            path.write_bytes(text.encode("utf-8"))

    results: list[PageResult] = []
    portal_results: list[PortalResult] = []
    blobs: dict[tuple[str, str, str], str] = {}
    portal_blobs: dict[tuple[str, str, str], str] = {}

    palette_names = palettes_select(palette_dir, palette_name)
    loaded = {name: load_palette(name, palette_dir) for name in palette_names}
    # The gallery's opening view, taken from the first theme: `opening_palette`
    # only consults a theme for its pin, and the pin is a property of the style
    # a reviewer will pick, not of the one that happens to sort first.
    #
    # `loaded` is keyed only by the names `palettes.select` already validated
    # against --palette, so a name arriving from the customer config or a
    # theme's own pin has never been checked -- and `loaded[...]` would raise
    # a raw KeyError instead of the BuildError every other bad name gets.
    opening_name = opening_palette(cfg, chosen, themes[0], palette_name)
    if opening_name not in loaded:
        raise BuildError(f"unknown palette '{opening_name}'. Available: {', '.join(sorted(loaded))}")
    palette = loaded[opening_name]

    # A configured redirect that reaches no style at all is the signature of a
    # data directory copied out before the flag existed. Warned about rather than
    # refused, because the build is otherwise correct and the pages are still
    # worth having -- but never passed over in silence, since the symptom is the
    # notice simply not being there, which reads as the feature being broken.
    if redirect.enabled(cfg):
        stale = [th["name"] for th in themes if not redirect.declares(th)]
        if stale:
            logs.get().warning(
                "redirect is configured but %s %s no `redirect` flag, so the notice is off there. "
                "This is what an older %s looks like: refresh it with `panos-response-pages init "
                '--force` (back up your config/ first), or add "redirect": true to each theme file.',
                ", ".join(stale),
                "declares" if len(stale) == 1 else "declare",
                data_dir,
            )

    for th in themes:
        for pname in palette_names:
            th_palette = loaded[pname]
            deploy_dir = out_dir / "deploy" / th["name"] / pname
            prev_dir = out_dir / "preview" / th["name"] / pname
            if write:
                deploy_dir.mkdir(parents=True, exist_ok=True)
                if preview:
                    prev_dir.mkdir(parents=True, exist_ok=True)

            for page in pages:
                # strip_output runs here, before validate(), so the bytes that are
                # measured are the bytes that ship. It must not run any earlier:
                # parse_sections() needs the <!--@SLOT--> markers intact.
                deployable = strip_output(build_page(page, th, cfg, th_palette, False, template_dir))
                size, errors, warnings = validate(page, deployable)
                emit(deploy_dir / f"{page}.html", deployable)

                if preview:
                    pv = strip_output(build_page(page, th, cfg, th_palette, True, template_dir))
                    blobs[th["name"], pname, page] = pv
                    emit(prev_dir / f"{page}.html", pv)

                    # The second url-block blob the gallery's Redirect toggle switches
                    # to. Built unconditionally so the toggle can demonstrate the
                    # handoff on a config that has not enabled it -- which is every
                    # config until someone opts in. PREVIEW ONLY: it is not measured
                    # against the byte ceiling and never written under deploy/,
                    # because its countdown loops rather than hands over.
                    #
                    # th_palette, not the build-level palette: a style that pins its
                    # own colour must demonstrate the notice in the colour it wears.
                    if page == redirect.PAGE and redirect.supported(th):
                        demo = strip_output(
                            build_page(page, th, cfg, th_palette, True, template_dir, redirect_demo=True)
                        )
                        blobs[th["name"], pname, f"{page}{redirect.PREVIEW_SUFFIX}"] = demo
                        emit(prev_dir / f"{page}{redirect.PREVIEW_SUFFIX}.html", demo)

                results.append(PageResult(th["name"], page, size, errors, warnings, pname))

            imports: dict[str, str] = {}
            for page in PORTAL_PAGES:
                # build_portal_page strips on the way out, so these are already the
                # bytes the firewall receives; nothing may touch them afterwards.
                imports[page] = build_portal_page(page, th, cfg, th_palette, portal_templates)
                size, errors, warnings = validate_portal(imports[page])
                encoded = encoded_size(imports[page])
                if write:
                    # A subdirectory, not a portal-login.html prefix: the two
                    # families are imported into different PAN-OS objects, and
                    # keeping them apart on disk is what stops a `deploy/<theme>/*`
                    # glob from sweeping a portal import into a block-page upload.
                    (deploy_dir / "portal").mkdir(parents=True, exist_ok=True)
                    emit(deploy_dir / "portal" / f"{page}.html", imports[page])
                portal_results.append(PortalResult(th["name"], page, size, encoded, errors, warnings, pname))

            if preview:
                # Spliced. PREVIEW ONLY, and never written anywhere `validate`
                # walks: each of these carries PAN-OS' own prefix and a captured
                # form, which the import guards reject on sight -- correctly.
                portal_blobs.update(
                    {
                        (th["name"], pname, name): text
                        for name, text in _splice(imports, ASSETS_FROM_GALLERY, fixtures).items()
                    }
                )
                if write:
                    (prev_dir / "portal").mkdir(parents=True, exist_ok=True)
                    for name, text in _splice(imports, ASSETS_FROM_PAGE, fixtures).items():
                        emit(prev_dir / "portal" / f"{name}.html", text)

    if preview and write:
        # The captured portal asset tree, once, beside the gallery. jQuery is in
        # here, and without it the prefixes' ready handler never runs and every
        # login preview shows an empty logo box.
        shutil.copytree(fixtures / "portal", out_dir / "preview" / PREVIEW_ASSETS, dirs_exist_ok=True)
        result_palettes = [loaded[n] for n in palette_names]
        gallery, sidecars = build_gallery(
            themes, pages, blobs, cfg, palette, result_palettes, portal_blobs, PORTAL_PREVIEWS
        )
        (out_dir / "preview" / "index.html").write_bytes(gallery.encode("utf-8"))
        for name, text in sidecars.items():
            (out_dir / "preview" / name).write_bytes(text.encode("utf-8"))

    return BuildResult(results, palette, portal_results)


def _splice(imports: Mapping[str, str], assets: str, fixtures: pathlib.Path) -> dict[str, str]:
    """The six portal previews, with asset references pointed at `assets`."""
    out = {
        name: splice_login(imports["login"], "login", name.removeprefix("login-"), assets=assets, fixtures=fixtures)
        for name in LOGIN_PREVIEWS
    }
    out["getsoftware"] = splice_login(imports["login"], "getsoftware", assets=assets, fixtures=fixtures)
    out["logout"] = splice_home(imports["home"], assets=assets, fixtures=fixtures)
    return out


def _worst_rows(rows: list[Any]) -> dict[tuple[str, str], Any]:
    """The largest row of each style x palette, which is the one the table names.

    Shared by both tables: the block-page family and the portal family collapse
    the same way, and having written the fold twice is how the two drifted into
    saying `ok` under different rules.
    """
    worst: dict[tuple[str, str], Any] = {}
    for r in rows:
        key = (r.theme, r.palette)
        if key not in worst or r.size > worst[key].size:
            worst[key] = r
    return worst


def _status(rows: list[Any], theme: str, palette: str) -> str:
    """FAIL beats warn beats ok, across every row of one combination.

    Taken from the whole combination, not from the largest row: a page can warn
    for a reason that has nothing to do with its size, and the row must not read
    `ok` while a line underneath it says otherwise.
    """
    of_cell = [r for r in rows if r.theme == theme and r.palette == palette]
    if any(r.errors for r in of_cell):
        return "FAIL"
    return "warn" if any(r.warnings for r in of_cell) else "ok"


def _flagged(rows: list[Any], all_clear: str | None = None) -> list[str]:
    """Everything that warned or failed, named in full under the table.

    `all_clear` is the line to print when nothing is flagged. Only the block-page
    table has one -- the portal table is already preceded by its own summary, and
    a second all-clear under it read as if it were about the whole build.
    """
    flagged = [r for r in rows if r.errors or r.warnings]
    if not flagged:
        return ["", f"  {all_clear}"] if all_clear else []
    lines = [""]
    for r in flagged:
        lines.append(f"  {r.theme}/{r.palette}/{r.page}  {r.size} B  {r.status}")
        lines += [f"      ! {e}" for e in r.errors]
        lines += [f"      ~ {w}" for w in r.warnings]
    return lines


def format_report(result: BuildResult) -> str:
    """The size table. This is the tool's product, not chatter, so it goes to
    stdout as plain text and stays parseable by eye.

    One row per style and palette rather than per page. A page row each would be
    252 lines, and the only number that can fail is the largest -- so the row
    carries that page, and anything that warns or fails is then named in full
    underneath, where a short list is read and a long table is not.
    """
    lines = [
        f"\n  {'theme':10} {'palette':14} {'largest page':24} {'bytes':>7}  {'of limit':>9}  status",
        "  " + "-" * 78,
    ]
    for (theme, palette), r in _worst_rows(result.results).items():
        status = _status(result.results, theme, palette)
        pct = f"{r.size / MAX_BYTES * 100:.0f}%"
        lines.append(f"  {theme:10} {palette:14} {r.page:24} {r.size:>7}  {pct:>9}  {status}")
    lines.append("  " + "-" * 78)
    lines.append(
        f"  ceiling {MAX_BYTES} B  |  largest page {result.largest} B  |  headroom {MAX_BYTES - result.largest} B"
    )
    lines += _flagged(result.results, all_clear="no page warns or fails")

    if result.portal_results:
        lines += _portal_report(result)
    return "\n".join(lines)


def _portal_report(result: BuildResult) -> list[str]:
    """The portal table, measured against the portal's own ceiling.

    A separate table, not extra rows, because the limit is a different limit.
    MAX_BYTES is what the dataplane will serve; SOFT_MAX is what the management
    plane will accept as a base64 field. Showing a portal import as a percentage
    of MAX_BYTES would read as 60% of a limit it is not subject to.

    Collapsed the same way format_report collapses the block-page table: one row
    per style x palette, carrying a palette column, rather than one row per
    import. Portal import sizes are palette-invariant -- every palette's hex
    values are the same length -- which is the same property that makes the
    block-page collapse honest. Left uncollapsed, the shipped matrix put four
    byte-identical `assist login ...` lines in a row with nothing on the row
    saying why, which reads as four different imports that happen to match.

    The encoded column is there because that is the only number PAN-OS ever
    says out loud: "page can be at most 21845 characters, but current length: N".
    """
    lines = [
        "",
        f"  {'theme':10} {'palette':14} {'portal import':16} {'bytes':>7}  {'encoded':>7}  {'of ceiling':>10}  status",
        "  " + "-" * 88,
    ]
    for (theme, palette), r in _worst_rows(result.portal_results).items():
        status = _status(result.portal_results, theme, palette)
        pct = f"{r.size / SOFT_MAX * 100:.0f}%"
        lines.append(f"  {theme:10} {palette:14} {r.page:16} {r.size:>7}  {r.encoded:>7}  {pct:>10}  {status}")
    lines.append("  " + "-" * 88)
    lines.append(
        f"  import ceiling {SOFT_MAX} B ({MAX_ENCODED} encoded)  |  "
        f"largest import {result.portal_largest} B  |  headroom {SOFT_MAX - result.portal_largest} B"
    )

    return lines + _flagged(result.portal_results)
