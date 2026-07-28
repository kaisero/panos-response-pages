"""Orchestration: build every page of every theme, validate, report.

Split from the CLI so the whole build is callable in-process. That is what lets
tests assert on results rather than on a subprocess exit code -- and it is why
coverage can see any of this at all.
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field
from typing import Any

from panos_response_pages.config import load_config
from panos_response_pages.errors import BuildError
from panos_response_pages.gallery import build_gallery
from panos_response_pages.page import build_page
from panos_response_pages.palettes import load_palette
from panos_response_pages.templates import read
from panos_response_pages.validate import MAX_BYTES, PAGE_TOKENS, validate


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
class BuildResult:
    results: list[PageResult]
    data_dir: pathlib.Path
    data_reason: str
    palette: dict[str, Any]
    out_dir: pathlib.Path

    @property
    def failed(self) -> bool:
        return any(r.errors for r in self.results)

    @property
    def largest(self) -> int:
        return max((r.size for r in self.results), default=0)


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

    results: list[PageResult] = []
    blobs: dict[tuple[str, str], str] = {}

    for th in themes:
        deploy_dir = out_dir / deploy_subdir / th["name"]
        prev_dir = out_dir / preview_subdir / th["name"]
        if write:
            deploy_dir.mkdir(parents=True, exist_ok=True)
            if preview:
                prev_dir.mkdir(parents=True, exist_ok=True)

        for page in pages:
            deployable = build_page(page, th, cfg, palette, False, template_dir)
            size, errors, warnings = validate(page, th["name"], deployable)
            if write:
                # write_bytes, never write_text: write_text translates "\n" to
                # os.linesep, so on Windows every line would gain a byte AFTER
                # validate() measured the string, and an oversize page would
                # ship with the report still saying ok.
                (deploy_dir / f"{page}.html").write_bytes(deployable.encode("utf-8"))

            if preview:
                pv = build_page(page, th, cfg, palette, True, template_dir)
                blobs[th["name"], page] = pv
                if write:
                    (prev_dir / f"{page}.html").write_bytes(pv.encode("utf-8"))

            results.append(PageResult(th["name"], page, size, errors, warnings))

    if preview and write:
        gallery = build_gallery(themes, pages, blobs, cfg, palette)
        (out_dir / preview_subdir / "index.html").write_bytes(gallery.encode("utf-8"))

    return BuildResult(results, data_dir, data_reason, palette, out_dir)


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
    return "\n".join(lines)
