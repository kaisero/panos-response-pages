# Multi-Palette Build Matrix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build every style in every palette, and let the preview gallery switch palettes from a dropdown that shows each palette's primary colour, so a reviewer can pick the combination they want to upload to PAN-OS / SCM / Panorama.

**Architecture:** Style and palette become two independent axes of one matrix. `build_all` loops both and writes `deploy/<style>/<palette>/`; a theme's palette pin and the config's `palette` key stop deciding what gets built and instead decide only which palette the gallery opens on. The gallery keys its blobs on `<style>|<palette>|<page>`, keeps the opening palette inline, and loads each other palette from a sibling `blobs-<palette>.js` the first time it is selected.

**Tech Stack:** Python 3.12+, Typer CLI, `unittest` + `pytest` + `subTest`, ruff, mypy, Playwright (via `tmp/nyan-lab/node_modules`) for browser verification.

## Global Constraints

- **7 styles × 4 palettes = 28 combinations, 9 pages each = 252 block pages, plus 56 portal imports.** Verified: all 252 build with zero errors and zero warnings.
- **Every style is built in every palette.** A theme's `palette` pin is ignored when deciding *what to build*.
- **Page size is palette-invariant** in the current data (nyan's `url-block-page` is 15 558 B in all four palettes). Task 2 adds a test asserting this, so the report's collapsed row cannot hide a palette-specific overflow.
- **PAN-OS ceiling `MAX_BYTES = 17999`, soft line `WARN_BYTES = 16000`.** Unchanged.
- **The gallery must work from `file://`.** Frames use `srcdoc` because file:// iframes are cross-origin in Chrome. For the same reason `fetch()` is unavailable — the payload loader **must** use a classic `<script src>` tag. **Do not use `type="module"`**: ES modules are CORS-checked and fail on `file://`.
- **`redirect.supported(theme)` is per style, not per palette.** nyan opts out; palette never changes that.
- **Never commit documentation.** Task 6 writes docs and stops. Do not `git add` anything under `docs/`, `README.md`, or `CHANGELOG.md`. Tell the user the files are ready.
- **Commit style:** imperative subject ≤ 60 chars, capitalised, no trailing period, no `type(scope):` prefix, no AI attribution or trailers.

## Files

| File | Responsibility after this plan |
|---|---|
| `src/panos_response_pages/palettes.py` | Add `select()` — which palettes this run builds. |
| `src/panos_response_pages/builder.py` | Loop style × palette; write `deploy/<style>/<palette>/`; report one row per combination; `opening_palette()` replaces `palette_for()`. |
| `src/panos_response_pages/gallery.py` | Palette axis in blob keys; split payload; palette dropdown; chrome follows selection. |
| `src/panos_response_pages/cli.py` | `--palette` narrows the run instead of selecting the only one. |
| `tests/test_palette_matrix.py` | **New.** The matrix, the layout, and `--palette` narrowing. |
| `tests/test_palette_pinning.py` | Rewritten: the pin now sets the gallery's opening selection, not the build. |
| `tests/test_gallery.py` | **New if absent.** Payload split, key composition, dropdown markup. |

---

### Task 1: Build every style in every palette

**Files:**
- Modify: `src/panos_response_pages/palettes.py`
- Modify: `src/panos_response_pages/builder.py:129-260`
- Modify: `src/panos_response_pages/cli.py:123-127`
- Create: `tests/test_palette_matrix.py`

**Interfaces:**
- Consumes: `palettes.available(palette_dir) -> list[str]`, `palettes.load_palette(name, palette_dir) -> dict`, `builder.load_themes(data_dir, only) -> list[dict]`.
- Produces:
  - `palettes.select(palette_dir: pathlib.Path, only: str | None) -> list[str]`
  - `builder.opening_palette(cfg, chosen, theme, palette_name) -> str`
  - `BuildResult.palettes: list[dict[str, Any]]` — every palette built, in build order.
  - `BuildResult.palette: dict[str, Any]` — unchanged field name, now means *the gallery's opening palette*.
  - Blob keys become `(theme_name, palette_name, page)` 3-tuples.

- [ ] **Step 1: Write the failing test**

Create `tests/test_palette_matrix.py`:

```python
"""Style and palette as two independent axes of one build.

A build used to have one palette. It now has all of them, and the things that
used to choose that one palette choose something else instead -- so every test
here guards a meaning that changed rather than a behaviour that is new.
"""

import pathlib
import tempfile
import unittest

from _paths import DATA
from panos_response_pages import palettes
from panos_response_pages.builder import build_all, load_themes
from panos_response_pages.errors import BuildError
from panos_response_pages.validate import PAGE_TOKENS

THEMES = [t["name"] for t in load_themes(DATA)]
PALETTES = palettes.available(DATA / "palettes")


class TestSelect(unittest.TestCase):
    def test_no_choice_means_every_palette(self):
        self.assertEqual(palettes.select(DATA / "palettes", None), PALETTES)

    def test_a_choice_narrows_to_one(self):
        self.assertEqual(palettes.select(DATA / "palettes", "prisma-blue"), ["prisma-blue"])

    def test_an_unknown_name_is_refused_with_the_list(self):
        with self.assertRaises(BuildError) as caught:
            palettes.select(DATA / "palettes", "lilac")
        self.assertIn("lilac", str(caught.exception))
        for name in PALETTES:
            self.assertIn(name, str(caught.exception))


class TestMatrix(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = pathlib.Path(cls.tmp.name)
        cls.result = build_all(data_dir=DATA, out_dir=cls.out, preview=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_every_style_is_built_in_every_palette(self):
        got = {(r.theme, r.palette) for r in self.result.results}
        self.assertEqual(got, {(t, p) for t in THEMES for p in PALETTES})

    def test_a_pin_does_not_shrink_the_matrix(self):
        """nyan pins its own palette. That decides what the gallery opens on,
        not what exists on disk -- the customer asked for every combination so
        they can choose one, and a pin silently removing three of nyan's four
        would be a choice made for them."""
        nyan = {r.palette for r in self.result.results if r.theme == "nyan"}
        self.assertEqual(nyan, set(PALETTES))

    def test_the_deploy_tree_is_style_then_palette(self):
        for theme in THEMES:
            for palette in PALETTES:
                folder = self.out / "deploy" / theme / palette
                with self.subTest(theme=theme, palette=palette):
                    got = sorted(p.stem for p in folder.glob("*.html"))
                    self.assertEqual(got, sorted(set(PAGE_TOKENS)))

    def test_the_portal_stays_one_level_below_the_pages(self):
        folder = self.out / "deploy" / "glass" / "prisma-blue" / "portal"
        self.assertEqual(sorted(p.name for p in folder.glob("*.html")), ["home.html", "login.html"])

    def test_the_preview_tree_mirrors_the_deploy_tree(self):
        got = sorted(p.stem for p in (self.out / "preview" / "glass" / "nyan").glob("*.html"))
        self.assertIn("url-block-page", got)

    def test_nothing_lands_at_the_old_flat_path(self):
        """The layout is a breaking change, and a leftover file at the old path
        is worse than none: an upload script would keep finding a stale page."""
        self.assertEqual(list((self.out / "deploy" / "glass").glob("*.html")), [])


class TestNarrowing(unittest.TestCase):
    def test_palette_narrows_the_run_the_way_theme_does(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp)
            result = build_all(data_dir=DATA, out_dir=out, palette_name="nyan", theme="glass")
            self.assertEqual({(r.theme, r.palette) for r in result.results}, {("glass", "nyan")})
            self.assertTrue((out / "deploy" / "glass" / "nyan" / "url-block-page.html").is_file())
            self.assertFalse((out / "deploy" / "glass" / "cyber-orange").exists())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `uv run python -m pytest tests/test_palette_matrix.py -q`
Expected: FAIL — `AttributeError: module 'panos_response_pages.palettes' has no attribute 'select'`.

- [ ] **Step 3: Add `palettes.select`**

Append to `src/panos_response_pages/palettes.py`:

```python
def select(palette_dir: pathlib.Path, only: str | None = None) -> list[str]:
    """Which palettes this run builds. Every one, unless narrowed to a single.

    Mirrors how `--theme` narrows the style axis, so the two axes of the matrix
    behave the same way and one flag does not have to be learned twice.
    """
    names = available(palette_dir)
    if not names:
        raise BuildError(f"no palettes found in {palette_dir}")
    if only is None:
        return names
    if only not in names:
        raise BuildError(f"unknown palette '{only}'. Available: {', '.join(names)}")
    return [only]
```

- [ ] **Step 4: Replace `palette_for` with `opening_palette` in `builder.py`**

Delete the `palette_for` closure and the `_pinned_report` function. `_pinned_report` reported "this theme rendered in a palette you did not select", a state the matrix no longer has: every theme renders in every palette. Remove its call from `format_report` too.

Add at module level in `builder.py`:

```python
def opening_palette(
    cfg: Mapping[str, Any],
    chosen: Mapping[str, Any],
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
```

- [ ] **Step 5: Loop the matrix in `build_all`**

Replace the body of the `for th in themes:` loop. The palette loop goes *inside* the theme loop so `deploy/<style>/<palette>/` falls out of the nesting:

```python
    palette_names = palettes_select(palette_dir, palette_name)
    loaded = {name: load_palette(name, palette_dir) for name in palette_names}
    # The gallery's opening view, taken from the first theme: `opening_palette`
    # only consults a theme for its pin, and the pin is a property of the style
    # a reviewer will pick, not of the one that happens to sort first.
    palette = loaded[opening_palette(cfg, chosen, themes[0], palette_name)]

    for th in themes:
        for pname in palette_names:
            th_palette = loaded[pname]
            deploy_dir = out_dir / deploy_subdir / th["name"] / pname
            prev_dir = out_dir / preview_subdir / th["name"] / pname
            if write:
                deploy_dir.mkdir(parents=True, exist_ok=True)
                if preview:
                    prev_dir.mkdir(parents=True, exist_ok=True)

            for page in pages:
                deployable = strip_output(build_page(page, th, cfg, th_palette, False, template_dir))
                size, errors, warnings = validate(page, th["name"], deployable)
                if write:
                    (deploy_dir / f"{page}.html").write_bytes(deployable.encode("utf-8"))

                if preview:
                    pv = strip_output(build_page(page, th, cfg, th_palette, True, template_dir))
                    blobs[th["name"], pname, page] = pv
                    if write:
                        (prev_dir / f"{page}.html").write_bytes(pv.encode("utf-8"))

                    if page == redirect.PAGE and redirect.supported(th):
                        demo = strip_output(
                            build_page(page, th, cfg, th_palette, True, template_dir, redirect_demo=True)
                        )
                        blobs[th["name"], pname, f"{page}{redirect.PREVIEW_SUFFIX}"] = demo
                        if write:
                            (prev_dir / f"{page}{redirect.PREVIEW_SUFFIX}.html").write_bytes(
                                demo.encode("utf-8")
                            )

                results.append(PageResult(th["name"], page, size, errors, warnings, pname))

            imports: dict[str, str] = {}
            for page in PORTAL_PAGES:
                imports[page] = build_portal_page(page, th, cfg, th_palette, False, portal_templates)
                size, errors, warnings = validate_portal(imports[page])
                encoded = encoded_size(imports[page])
                if write:
                    (deploy_dir / "portal").mkdir(parents=True, exist_ok=True)
                    (deploy_dir / "portal" / f"{page}.html").write_bytes(imports[page].encode("utf-8"))
                portal_results.append(
                    PortalResult(th["name"], page, size, encoded, errors, warnings, pname)
                )

            if preview:
                portal_blobs.update(
                    {
                        (th["name"], pname, name): text
                        for name, text in _splice(imports, ASSETS_FROM_GALLERY, fixtures).items()
                    }
                )
                if write:
                    (prev_dir / "portal").mkdir(parents=True, exist_ok=True)
                    for name, text in _splice(imports, ASSETS_FROM_PAGE, fixtures).items():
                        (prev_dir / "portal" / f"{name}.html").write_bytes(text.encode("utf-8"))
```

Import `select` as `palettes_select` at the top of `builder.py`:

```python
from panos_response_pages.palettes import load_palette, select as palettes_select
```

- [ ] **Step 6: Fix the preview asset depth**

`preview/<style>/<palette>/portal/login.html` is one level deeper than before, so its relative path back to the shared asset tree gains a `../`. This is silent when wrong — the prefixes load jQuery by relative path, and jQuery is what fills the login logo, so a wrong depth is a blank box that reads as the page's own fault.

In `builder.py`, change:

```python
ASSETS_FROM_PAGE = f"../../../{PREVIEW_ASSETS}/"
```

`ASSETS_FROM_GALLERY` is unchanged: the gallery document stays at `preview/index.html`, and `srcdoc` resolves relative URLs against it.

- [ ] **Step 7: Widen `BuildResult`**

```python
@dataclass
class BuildResult:
    results: list[PageResult]
    data_dir: pathlib.Path
    data_reason: str
    palette: dict[str, Any]
    out_dir: pathlib.Path
    portal_results: list[PortalResult] = field(default_factory=list)
    # Every palette this run built, in build order. `palette` above is now only
    # the one the gallery opens on, so it can no longer answer "what was built".
    palettes: list[dict[str, Any]] = field(default_factory=list)
```

Return it: `return BuildResult(results, data_dir, data_reason, palette, out_dir, portal_results, [loaded[n] for n in palette_names])`.

- [ ] **Step 8: Make `--palette` a narrowing flag in the CLI**

In `src/panos_response_pages/cli.py`, replace the `--palette` help text and drop the `_require` call for it (`palettes.select` now raises with the list, so validating twice would produce two different messages for the same mistake):

```python
    palette: Annotated[
        str | None,
        typer.Option("--palette", "-p", autocompletion=_complete_palette, help="Build one palette only."),
    ] = None,
```

Delete the line `_require(palette, _names("palettes", ".json", data_dir), "palette")`.

- [ ] **Step 9: Run the new test**

Run: `uv run python -m pytest tests/test_palette_matrix.py -q`
Expected: PASS, 8 tests.

- [ ] **Step 10: Rewrite `tests/test_palette_pinning.py` for its new meaning**

Every test in that file asserts which single palette a theme was *built* in. That question no longer exists. Replace the whole `TestPalettePinning` class with:

```python
class TestOpeningPalette(unittest.TestCase):
    """The pin used to decide what got built. It now decides what a reviewer
    sees first, and nothing else -- every combination is on disk either way."""

    def opening(self, theme_name, customer="contoso", palette_name=None):
        cfg = load_config(customer, DATA / "config")
        chosen = customer_keys(customer, DATA / "config")
        theme = next(t for t in load_themes(DATA) if t["name"] == theme_name)
        return opening_palette(cfg, chosen, theme, palette_name)

    def test_a_pin_decides_when_nothing_else_speaks(self):
        self.assertEqual(self.opening("nyan"), "nyan")

    def test_other_themes_are_untouched_by_one_theme_s_pin(self):
        self.assertEqual(self.opening("glass"), "cyber-orange")

    def test_an_explicit_palette_outranks_everything(self):
        self.assertEqual(self.opening("nyan", palette_name="prisma-blue"), "prisma-blue")

    def test_the_shipped_default_does_not_outrank_the_pin(self):
        """_defaults.json always carries a palette, so a naive cfg['palette']
        would mean a pin could never fire."""
        self.assertEqual(self.opening("nyan"), "nyan")

    def test_a_pin_does_not_remove_anything_from_the_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = build_all(data_dir=DATA, out_dir=pathlib.Path(tmp), theme="nyan", preview=False)
            built = {r.palette for r in result.results}
            self.assertEqual(built, set(palettes.available(DATA / "palettes")))
```

Update that file's imports to pull `opening_palette`, `build_all`, `load_themes` from `panos_response_pages.builder`, `customer_keys`/`load_config` from `panos_response_pages.config`, `palettes`, plus `pathlib` and `tempfile`.

- [ ] **Step 11: Run the whole suite and fix fallout**

Run: `uv run python -m pytest tests/ -q`

Expect failures in any test that reads `deploy/<theme>/<page>.html` or a 2-tuple blob key. Known sites: `tests/_build.py` (`deploy_dir()` helper), `tests/test_shells.py::BuiltOutput`, `tests/test_portal_build.py:104`. Update each to the new path, adding the palette level. Where a test only needs *a* build, narrow it with `palette_name=` so it stays fast.

- [ ] **Step 12: Verify the report still renders and the build is clean**

Run: `uv run panos-response-pages build --customer contoso --config-dir src/panos_response_pages/data --out /tmp/mp1`
Expected: exit 0, and `find /tmp/mp1/deploy -name '*.html' | wc -l` prints `308` (252 block pages + 56 portal imports).

- [ ] **Step 13: Commit**

```bash
git add src/panos_response_pages/palettes.py src/panos_response_pages/builder.py \
        src/panos_response_pages/cli.py tests/
git commit -m "Build every style in every palette"
```

---

### Task 2: Report one row per style and palette

**Files:**
- Modify: `src/panos_response_pages/builder.py:293-322`
- Modify: `tests/test_palette_matrix.py`

**Interfaces:**
- Consumes: `BuildResult.results` (each carries `.theme`, `.palette`, `.page`, `.size`, `.status`).
- Produces: `builder.format_report(result) -> str`, unchanged signature.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_palette_matrix.py`:

```python
class TestReport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.result = build_all(data_dir=DATA, out_dir=pathlib.Path(cls.tmp.name), preview=False)
        cls.text = format_report(cls.result)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_one_row_per_combination_not_per_page(self):
        """252 page rows is long enough that a single warn in the middle scrolls
        past unread, which defeats the only purpose the table has.

        Counted between the rules rather than by matching `ok`, so the test still
        measures the table when a row's status is `warn` or `FAIL`.
        """
        lines = self.text.splitlines()
        rules = [i for i, ln in enumerate(lines) if set(ln.strip()) == {"-"}]
        self.assertEqual(len(rules), 2, "the table should be fenced by exactly two rules")
        self.assertEqual(rules[1] - rules[0] - 1, len(THEMES) * len(PALETTES))

    def test_each_row_names_the_largest_page(self):
        """The only page that can breach the ceiling is the largest one, so it
        is the one the row has to be about."""
        row = next(ln for ln in self.text.splitlines() if "nyan" in ln and "cyber-orange" in ln)
        self.assertIn("url-block-page", row)
        self.assertIn("15558", row)

    def test_palette_does_not_change_page_size(self):
        """The collapsed row is only honest if a palette cannot make a page
        bigger. If this ever fails, the report must stop collapsing."""
        by_page: dict[tuple[str, str], set[int]] = {}
        for r in self.result.results:
            by_page.setdefault((r.theme, r.page), set()).add(r.size)
        for (theme, page), sizes in by_page.items():
            with self.subTest(theme=theme, page=page):
                self.assertEqual(len(sizes), 1, f"{theme}/{page} differs by palette: {sorted(sizes)}")

    def test_a_clean_build_says_so(self):
        self.assertIn("no page warns or fails", self.text)
```

Add `format_report` to that file's imports from `panos_response_pages.builder`.

- [ ] **Step 2: Run it to make sure it fails**

Run: `uv run python -m pytest tests/test_palette_matrix.py::TestReport -q`
Expected: FAIL — the row count is 252, not 28.

- [ ] **Step 3: Rewrite `format_report`**

```python
def format_report(result: BuildResult) -> str:
    """The size table. This is the tool's product, not chatter, so it goes to
    stdout as plain text and stays parseable by eye.

    One row per style and palette rather than per page. A page row each would be
    252 lines, and the only number that can fail is the largest -- so the row
    carries that page, and anything that warns or fails is then named in full
    underneath, where a short list is read and a long table is not.
    """
    worst: dict[tuple[str, str], PageResult] = {}
    for r in result.results:
        key = (r.theme, r.palette)
        if key not in worst or r.size > worst[key].size:
            worst[key] = r

    lines = [
        f"\n  {'theme':10} {'palette':14} {'largest page':24} {'bytes':>7}  {'of limit':>9}  status",
        "  " + "-" * 78,
    ]
    for (theme, palette), r in worst.items():
        status = _worst_status(result, theme, palette)
        pct = f"{r.size / MAX_BYTES * 100:.0f}%"
        lines.append(f"  {theme:10} {palette:14} {r.page:24} {r.size:>7}  {pct:>9}  {status}")
    lines.append("  " + "-" * 78)
    lines.append(
        f"  ceiling {MAX_BYTES} B  |  largest page {result.largest} B  |  headroom {MAX_BYTES - result.largest} B"
    )

    flagged = [r for r in result.results if r.errors or r.warnings]
    if flagged:
        lines.append("")
        for r in flagged:
            lines.append(f"  {r.theme}/{r.palette}/{r.page}  {r.size} B  {r.status}")
            lines += [f"      ! {e}" for e in r.errors]
            lines += [f"      ~ {w}" for w in r.warnings]
    else:
        lines += ["", "  no page warns or fails"]

    if result.portal_results:
        lines += _portal_report(result)
    return "\n".join(lines)


def _worst_status(result: BuildResult, theme: str, palette: str) -> str:
    """FAIL beats warn beats ok, across every page of one combination.

    Taken from the whole combination, not from the largest page: a page can warn
    for a reason that has nothing to do with its size, and the row must not read
    `ok` while a line underneath it says otherwise.
    """
    rows = [r for r in result.results if r.theme == theme and r.palette == palette]
    if any(r.errors for r in rows):
        return "FAIL"
    return "warn" if any(r.warnings for r in rows) else "ok"
```

- [ ] **Step 4: Run the test**

Run: `uv run python -m pytest tests/test_palette_matrix.py::TestReport -q`
Expected: PASS, 4 tests.

- [ ] **Step 5: Look at the output**

Run: `uv run panos-response-pages build --customer contoso --config-dir src/panos_response_pages/data --out /tmp/mp2 | head -36`
Expected: a 28-row table, then `no page warns or fails`, then the portal table.

- [ ] **Step 6: Commit**

```bash
git add src/panos_response_pages/builder.py tests/test_palette_matrix.py
git commit -m "Report one row per style and palette"
```

---

### Task 3: Key the gallery on palette and split its payload

**Files:**
- Modify: `src/panos_response_pages/gallery.py`
- Modify: `src/panos_response_pages/builder.py` (the `build_gallery` call and what it writes)
- Create: `tests/test_gallery_payload.py`

**Interfaces:**
- Consumes: 3-tuple blob keys from Task 1; `BuildResult.palettes`.
- Produces:
  - `gallery.build_gallery(themes, pages, blobs, cfg, palette, palettes, portal_blobs, portal_previews) -> tuple[str, dict[str, str]]` — returns the gallery HTML **and** a mapping of `blobs-<palette>.js` filename to contents. The builder writes both.
  - JS globals in the gallery: `D` (blob map), `PP(name, obj)` (payload registrar), `S.palette`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_gallery_payload.py`:

```python
"""How the gallery carries 28 combinations without loading all of them.

Inlining every blob was fine at 1.56 MB and one palette. Four palettes makes it
5.9 MB, all of it parsed before the first frame renders and most of it never
looked at -- so each palette but the opening one is a sibling file, fetched the
first time it is asked for.
"""

import json
import re
import unittest

from _paths import DATA
from panos_response_pages import palettes
from panos_response_pages.builder import build_all, load_themes

PALETTES = palettes.available(DATA / "palettes")


class TestSplit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import pathlib
        import tempfile

        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = pathlib.Path(cls.tmp.name)
        build_all(data_dir=DATA, out_dir=cls.out, preview=True)
        cls.index = (cls.out / "preview" / "index.html").read_text(encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_the_opening_palette_is_inline(self):
        """The first frame must render without a second file arriving, or the
        gallery opens on a blank iframe and looks broken."""
        self.assertIn("cyber-orange|url-block-page", self.index)

    def test_every_other_palette_is_a_sibling_file(self):
        for name in PALETTES:
            if name == "cyber-orange":
                continue
            with self.subTest(palette=name):
                self.assertTrue((self.out / "preview" / f"blobs-{name}.js").is_file())

    def test_the_other_palettes_are_not_also_inline(self):
        """The whole point. If they are inline as well, the split cost a file
        and saved nothing."""
        self.assertNotIn("prisma-blue|url-block-page", self.index)

    def test_a_payload_file_registers_itself(self):
        text = (self.out / "preview" / "blobs-prisma-blue.js").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("PP("))
        self.assertIn("prisma-blue|url-block-page", text)

    def test_it_is_a_classic_script_not_a_module(self):
        """ES modules are CORS-checked and fail on file://, which is exactly how
        this gallery is opened."""
        self.assertNotIn('type="module"', self.index)

    def test_the_key_carries_both_axes(self):
        self.assertIn('S.theme+"|"+S.palette+"|"+p', self.index)

    def test_the_index_stays_small(self):
        """One palette's worth, not four. A regression here is silent -- the
        gallery still works, it just takes four times as long to open."""
        self.assertLess(len(self.index.encode()), 2_500_000)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `uv run python -m pytest tests/test_gallery_payload.py -q`
Expected: FAIL — no `blobs-prisma-blue.js` is written.

- [ ] **Step 3: Split the payload in `gallery.py`**

Replace the payload construction. `data` keeps only the opening palette; the rest become separate documents:

```python
    def blob_map(pname: str) -> dict[str, str]:
        """Every frame for one palette, keyed <style>|<palette>|<page>."""
        out = {f"{t['name']}|{pname}|{p}": blobs[(t["name"], pname, p)] for t in themes for p in pages}
        out.update(
            {
                f"{t['name']}|{pname}|{RX_KEY}": blobs[(t["name"], pname, RX_KEY)]
                for t in themes
                if (t["name"], pname, RX_KEY) in blobs
            }
        )
        out.update(
            {
                f"{t['name']}|{pname}|portal:{p}": (portal_blobs or {})[(t["name"], pname, p)]
                for t in themes
                for p in portal_previews
            }
        )
        return out

    def encode(obj: dict[str, str]) -> str:
        # </ would close the <script> that carries this, wherever it appears
        # inside a blob -- which it does, in every page that has a </style>.
        return json.dumps(obj).replace("</", "<\\/")

    opening = palette["name"]
    payload = encode(blob_map(opening))
    sidecars = {
        f"blobs-{p['name']}.js": f"PP({json.dumps(p['name'])},{encode(blob_map(p['name']))})"
        for p in palettes
        if p["name"] != opening
    }
```

- [ ] **Step 4: Add the loader to the gallery script**

Replace `var D={payload},S={{...}}` and the `key()`/`render()` block:

```javascript
var D={payload},LOADED={{}},S={{theme:"{themes[0]["name"]}",page:"{pages[0]}",
palette:"{palette["name"]}",view:"both",scheme:"light",
state:"{states[0] if states else ""}",redirect:"off"}};
LOADED[S.palette]=1;
// Each palette but the opening one arrives as a sibling classic script that
// calls this. A module would be CORS-checked and fail on file://, and fetch()
// is unavailable there for the same reason -- which is why this is a <script
// src> and not a request.
function PP(name,obj){{for(var k in obj)D[k]=obj[k];LOADED[name]=1}}
function need(pal,done){{
  if(LOADED[pal]) return done();
  var s=document.createElement("script");
  s.src="blobs-"+pal+".js";
  s.onload=done;
  s.onerror=function(){{LOADED[pal]=1;done()}};
  document.head.appendChild(s);
}}
var RXPAGE="{redirect.PAGE}",RXSUF="{redirect.PREVIEW_SUFFIX}",RXOK={rx_ok};
function key(){{
  var p=S.page;
  if(p==="portal:login") p=p+"-"+S.state;
  if(p===RXPAGE&&S.redirect==="on"&&RXOK[S.theme]) p=p+RXSUF;
  return S.theme+"|"+S.palette+"|"+p;
}}
```

Rename the existing `render` to `draw`, and add a `render` that waits for the payload:

```javascript
function render(){{ need(S.palette,draw); }}
```

`s.onerror` marks the palette loaded so a missing sidecar produces one empty frame rather than a control that silently stops responding.

- [ ] **Step 5: Return the sidecars and write them**

Change the end of `build_gallery` to `return html, sidecars`, add `palettes: Sequence[Mapping[str, Any]]` to its signature after `palette`, and in `builder.py`:

```python
        gallery, sidecars = build_gallery(
            themes, pages, blobs, cfg, palette, result_palettes, portal_blobs, PORTAL_PREVIEWS
        )
        (out_dir / preview_subdir / "index.html").write_bytes(gallery.encode("utf-8"))
        for name, text in sidecars.items():
            (out_dir / preview_subdir / name).write_bytes(text.encode("utf-8"))
```

where `result_palettes = [loaded[n] for n in palette_names]`.

- [ ] **Step 6: Run the test**

Run: `uv run python -m pytest tests/test_gallery_payload.py -q`
Expected: PASS, 7 tests.

- [ ] **Step 7: Commit**

```bash
git add src/panos_response_pages/gallery.py src/panos_response_pages/builder.py tests/test_gallery_payload.py
git commit -m "Load each palette's preview frames on demand"
```

---

### Task 4: The palette dropdown with a swatch on every row

**Files:**
- Modify: `src/panos_response_pages/gallery.py`
- Create: `tmp/nyan-lab/palette-check.mjs`

**Interfaces:**
- Consumes: `S.palette`, `render()` from Task 3; `palettes` (each has `name`, `label`, `colors.accent`).
- Produces: markup `#palgrp` (button `#palbtn` + `ul[role=listbox]#pallist`), and `setPalette(name)` in the gallery script.

A native `<select>` cannot carry the swatch: macOS Chrome and Safari draw `<option>` rows natively and ignore their background colour. This is the only custom control in the gallery, so its keyboard contract has to be written out rather than inherited.

- [ ] **Step 1: Write the failing browser test**

Create `tmp/nyan-lab/palette-check.mjs`:

```javascript
import { chromium } from 'playwright';

const G = 'file://' + process.argv[2] + '/preview/index.html';
const b = await chromium.launch();
const ctx = await b.newContext({ viewport: { width: 1440, height: 950 } });
const p = await ctx.newPage();
const errs = [];
p.on('pageerror', e => errs.push(String(e).slice(0, 160)));
await p.goto(G, { waitUntil: 'load' });

const swatches = await p.$$eval('#pallist [role=option] .sw',
  els => els.map(e => getComputedStyle(e).backgroundColor));
console.log('rows with a swatch colour:', swatches.length, swatches);

await p.click('#palbtn');
console.log('expanded:', await p.getAttribute('#palbtn', 'aria-expanded'));

// Keyboard: Down then Enter must select the second palette.
await p.keyboard.press('ArrowDown');
await p.keyboard.press('Enter');
await p.waitForTimeout(400);
console.log('after Down+Enter:', await p.textContent('#palbtn'));
console.log('collapsed again:', await p.getAttribute('#palbtn', 'aria-expanded'));

// The frame must actually be the new palette, which means the sidecar loaded.
const bg = await p.evaluate(() =>
  getComputedStyle(document.querySelector('iframe').contentDocument.body).backgroundColor);
console.log('frame background:', bg);

await p.click('#palbtn');
await p.keyboard.press('Escape');
console.log('Esc collapsed:', await p.getAttribute('#palbtn', 'aria-expanded'));
console.log('focus returned to button:',
  await p.evaluate(() => document.activeElement.id === 'palbtn'));

// The two axes are independent: nyan pins its own palette, and selecting it
// must NOT drag the palette dropdown onto that pin. The build produces every
// combination precisely so the reviewer chooses, and a control that moves on
// its own is the kind of surprise that makes a toolbar untrustworthy.
const before = await p.textContent('#palbtn');
await p.selectOption('select[data-theme]', 'nyan');
await p.waitForTimeout(400);
const after = await p.textContent('#palbtn');
console.log('palette unmoved by style change:', before === after, `(${before.trim()})`);

console.log('js errors:', errs.length ? errs : 'none');
await b.close();
```

- [ ] **Step 2: Run it to make sure it fails**

```bash
uv run panos-response-pages build --customer contoso --config-dir src/panos_response_pages/data --out /tmp/mp4
cd tmp/nyan-lab && node palette-check.mjs /tmp/mp4
```
Expected: `rows with a swatch colour: 0 []` and a failure on `#palbtn`.

- [ ] **Step 3: Add the control's CSS**

Append inside `GALLERY_CSS` (remember every literal brace in that string is doubled):

```
.pal{{position:relative}}
.pal>button{{display:inline-flex;align-items:center;gap:.45rem;height:2rem;padding:0 1.6rem 0 .5rem;
border:1px solid var(--line);border-radius:.55rem;background:var(--srf);color:var(--fg);
font-size:.8rem;font-weight:550;cursor:pointer}}
.pal>button::after{{content:"";position:absolute;right:.5rem;top:50%;margin-top:-.12rem;
border:.26rem solid transparent;border-top-color:var(--mut)}}
.sw{{flex:none;width:.85rem;height:.85rem;border-radius:50%;
box-shadow:inset 0 0 0 1px rgba(0,0,0,.25)}}
.pal ul{{position:absolute;z-index:10;top:calc(100% + .3rem);left:0;min-width:100%;margin:0;
padding:.25rem;list-style:none;border:1px solid var(--line);border-radius:.55rem;
background:var(--srf);box-shadow:0 .6rem 1.6rem rgba(10,20,30,.22)}}
.pal ul[hidden]{{display:none}}
.pal li{{display:flex;align-items:center;gap:.45rem;padding:.35rem .5rem;border-radius:.35rem;
font-size:.8rem;white-space:nowrap;cursor:pointer}}
.pal li:hover,.pal li[data-on]{{background:var(--srf2)}}
.pal li[aria-selected=true]::after{{content:"\\2713";margin-left:auto;padding-left:.6rem;color:var(--acct)}}
.pal li:focus-visible{{outline:3px solid var(--acct);outline-offset:-3px}}
```

- [ ] **Step 4: Add the control's markup**

Build it beside the other controls in `build_gallery`:

```python
    def swatch(p: Mapping[str, Any]) -> str:
        return f'<span class="sw" style="background:{html.escape(str(p["colors"]["accent"]))}"></span>'

    pal_rows = "".join(
        f'<li role="option" data-palette="{html.escape(p["name"])}" '
        f'aria-selected="{str(p["name"] == palette["name"]).lower()}" tabindex="-1">'
        f'{swatch(p)}{html.escape(str(p["label"]))}</li>'
        for p in palettes
    )
    # Only when there is a choice: a one-entry dropdown is a label pretending to
    # be a control, and `--palette` narrowing the build is a normal thing to do.
    palette_ctl = (
        f'<div class="ctl pal" id="palgrp"><span>Palette</span>'
        f'<button type="button" id="palbtn" aria-haspopup="listbox" aria-expanded="false">'
        f'{swatch(palette)}<span id="pallabel">{html.escape(str(palette["label"]))}</span></button>'
        f'<ul role="listbox" id="pallist" aria-label="Palette" hidden>{pal_rows}</ul></div>'
        if len(palettes) > 1
        else ""
    )
```

Insert `{palette_ctl}` into the `.bar` markup between `{page_ctl}` and `{state_seg}`.

The `.ctl` class supplies the shared caption styling; `.pal` adds the popup. `<span>Palette</span>` sits outside the button so the caption reads like the Style and Page captions.

- [ ] **Step 5: Add the control's behaviour**

Append to the gallery script:

```javascript
(function(){{
  var grp=document.getElementById("palgrp");
  if(!grp) return;
  var btn=document.getElementById("palbtn"),list=document.getElementById("pallist"),
      rows=[].slice.call(list.querySelectorAll("[role=option]")),at=0;
  rows.forEach(function(r,i){{if(r.getAttribute("aria-selected")==="true")at=i}});
  function mark(i){{
    at=(i+rows.length)%rows.length;
    rows.forEach(function(r,j){{
      if(j===at) r.setAttribute("data-on",""); else r.removeAttribute("data-on");
    }});
    rows[at].focus();
  }}
  function open(){{
    list.hidden=false;btn.setAttribute("aria-expanded","true");mark(at);
  }}
  function close(back){{
    list.hidden=true;btn.setAttribute("aria-expanded","false");
    if(back!==false) btn.focus();
  }}
  function choose(i){{
    var r=rows[i];
    rows.forEach(function(o){{o.setAttribute("aria-selected",String(o===r))}});
    S.palette=r.getAttribute("data-palette");
    btn.querySelector(".sw").style.background=r.querySelector(".sw").style.background;
    document.getElementById("pallabel").textContent=r.textContent;
    document.documentElement.setAttribute("data-pal",S.palette);
    close();render();
  }}
  btn.addEventListener("click",function(){{list.hidden?open():close()}});
  list.addEventListener("click",function(e){{
    var r=e.target.closest("[role=option]");
    if(r) choose(rows.indexOf(r));
  }});
  grp.addEventListener("keydown",function(e){{
    if(e.key==="Escape"){{if(!list.hidden){{e.preventDefault();close()}}return}}
    if(list.hidden){{
      if(e.key==="ArrowDown"||e.key==="Enter"||e.key===" "){{e.preventDefault();open()}}
      return;
    }}
    if(e.key==="ArrowDown"){{e.preventDefault();mark(at+1)}}
    else if(e.key==="ArrowUp"){{e.preventDefault();mark(at-1)}}
    else if(e.key==="Home"){{e.preventDefault();mark(0)}}
    else if(e.key==="End"){{e.preventDefault();mark(rows.length-1)}}
    else if(e.key==="Enter"||e.key===" "){{e.preventDefault();choose(at)}}
  }});
  // Pointer-down, not click: a click listener fires after the browser has
  // already moved focus, so the popup would close with focus somewhere else.
  document.addEventListener("pointerdown",function(e){{
    if(!list.hidden&&!grp.contains(e.target)) close(false);
  }});
}})();
```

- [ ] **Step 6: Run the browser test**

```bash
uv run panos-response-pages build --customer contoso --config-dir src/panos_response_pages/data --out /tmp/mp4
cd tmp/nyan-lab && node palette-check.mjs /tmp/mp4
```
Expected: `rows with a swatch colour: 4` with four distinct `rgb(...)` values; `expanded: true`; `after Down+Enter` naming the second palette; `collapsed again: false`; a `frame background` differing from the opening palette's; `Esc collapsed: false`; `focus returned to button: true`; `palette unmoved by style change: true`; `js errors: none`.

The four swatch colours must be `rgb(250, 88, 45)`, `rgb(255, 79, 163)`, `rgb(0, 192, 232)` and `rgb(255, 203, 6)` — the `accent` of cyber-orange, nyan, prisma-blue and strata-yellow. Four identical values means the swatch is reading the chrome's accent rather than each palette's own.

- [ ] **Step 7: Commit**

```bash
git add src/panos_response_pages/gallery.py tmp/nyan-lab/palette-check.mjs
git commit -m "Add a palette dropdown with a swatch on every row"
```

---

### Task 5: Recolour the gallery chrome with the selection

**Files:**
- Modify: `src/panos_response_pages/gallery.py`

**Interfaces:**
- Consumes: `data-pal` on `<html>`, already set by `choose()` in Task 4.
- Produces: `gallery._chrome_tokens(palettes, opening) -> str`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_gallery_payload.py`:

```python
class TestChrome(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import pathlib
        import tempfile

        cls.tmp = tempfile.TemporaryDirectory()
        out = pathlib.Path(cls.tmp.name)
        build_all(data_dir=DATA, out_dir=out, preview=True)
        cls.index = (out / "preview" / "index.html").read_text(encoding="utf-8")
        cls.css = cls.index.split("<style>", 1)[1].split("</style>", 1)[0]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_every_palette_has_a_light_chrome_block(self):
        for name in PALETTES:
            with self.subTest(palette=name):
                self.assertIn(f':root[data-pal="{name}"]{{--bg:', self.css)

    def test_every_palette_has_a_dark_chrome_block(self):
        """Half the reviewers are in dark mode. A palette whose dark block was
        dropped falls back to the opening palette's, so the toolbar and the
        frame disagree about which palette is being previewed."""
        for name in PALETTES:
            with self.subTest(palette=name):
                self.assertIn(
                    f'@media(prefers-color-scheme:dark){{:root[data-pal="{name}"]{{--bg:', self.css
                )

    def test_the_opening_palette_also_paints_without_the_attribute(self):
        """data-pal is set by the dropdown's handler. Before anyone touches it
        there is no attribute, and a toolbar with no colours is not a preview."""
        self.assertIn(":root{--bg:", self.css)

    def test_the_chrome_blocks_carry_real_colours(self):
        """`.format()` on a sheet that still held placeholders used to be how
        these were produced; a block reading `--bg:{ground}` would satisfy every
        assertion above."""
        self.assertNotIn("{ground}", self.css)
        self.assertRegex(self.css, r':root\[data-pal="nyan"\]\{--bg:#[0-9a-fA-F]{3,8}')
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `uv run python -m pytest tests/test_gallery_payload.py::TestChrome -q`
Expected: FAIL — no `:root[data-pal=` in the document.

- [ ] **Step 3: Generate the per-palette token blocks**

Remove the first five lines of `GALLERY_CSS` — the `:root{{...}}` block and the `@media(prefers-color-scheme:dark){{:root{{...}}}}` block that carry `{ground}`-style placeholders. Everything below them stays exactly as it is.

Add to `gallery.py`:

```python
CHROME_KEYS = (
    ("--bg", "ground"),
    ("--srf", "surface"),
    ("--srf2", "surface_alt"),
    ("--fg", "ink"),
    ("--mut", "ink_muted"),
    ("--line", "surface_alt"),
    ("--acc", "accent"),
    ("--acci", "accent_ink"),
    ("--acct", "accent_text"),
)


def _tokens(colors: Mapping[str, Any], dark: bool) -> str:
    prefix = "d_" if dark else ""
    return ";".join(f"{var}:{colors[prefix + key]}" for var, key in CHROME_KEYS)


def _chrome_tokens(palettes: Sequence[Mapping[str, Any]], opening: str) -> str:
    """The toolbar's own colours, one block per palette.

    The chrome follows the selection, so the whole window wears the palette
    being previewed rather than showing it only as a dot in a dropdown.

    The opening palette is emitted twice: once on bare `:root`, because
    `data-pal` is not on the document until the dropdown's handler sets it, and
    once under its own attribute so returning to it works like any other.
    """
    out = []
    for p in palettes:
        colors = p["colors"]
        light, dark = _tokens(colors, False), _tokens(colors, True)
        if p["name"] == opening:
            out.append(f":root{{{light}}}")
            out.append(f"@media(prefers-color-scheme:dark){{:root{{{dark}}}}}")
        sel = f':root[data-pal="{p["name"]}"]'
        out.append(f"{sel}{{{light}}}")
        out.append(f"@media(prefers-color-scheme:dark){{{sel}{{{dark}}}}}")
    return "\n".join(out)
```

`_chrome_tokens` returns finished CSS with single braces, so it must be concatenated, **not** passed through `.format()`:

```python
    css = _chrome_tokens(palettes, palette["name"]) + "\n" + GALLERY_CSS.format()
```

`GALLERY_CSS.format()` with no arguments still un-doubles the braces in the rest of the sheet, so nothing else in that constant changes.

- [ ] **Step 4: Run the test**

Run: `uv run python -m pytest tests/test_gallery_payload.py::TestChrome -q`
Expected: PASS, 3 tests.

- [ ] **Step 5: See it switch**

```bash
uv run panos-response-pages build --customer contoso --config-dir src/panos_response_pages/data --out /tmp/mp5
cd tmp/nyan-lab && node palette-check.mjs /tmp/mp5
```
Expected: still `js errors: none`. Then open `/tmp/mp5/preview/index.html` and confirm the toolbar recolours when the palette changes.

- [ ] **Step 6: Run everything**

```bash
uv run python -m pytest tests/ -q
uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src
```
Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add src/panos_response_pages/gallery.py tests/test_gallery_payload.py
git commit -m "Recolour the gallery chrome with the selected palette"
```

---

### Task 6: Documentation

**Files:**
- Modify: `README.md:41`, `docs/index.md:58-62`, `docs/portal.md:52-53`, `docs/cli.md:25-26`, `docs/customising.md:14`, `CHANGELOG.md`

**Interfaces:** none — prose only.

**This task does not commit.** Per the repository owner's standing rule, documentation is theirs to stage and commit. Write the files, run the docs test, and report.

- [ ] **Step 1: Update every documented path**

The deploy layout is a breaking change. Each of these currently names the old flat path:

- `README.md:41` — `out/deploy/<style>/` → `out/deploy/<style>/<palette>/`
- `docs/index.md:58` — the output table row
- `docs/portal.md:52-53` — `out/deploy/<theme>/portal/login.html` → `out/deploy/<theme>/<palette>/portal/login.html`
- `docs/cli.md:25` — `--palette` now reads "Build one palette only. Omit to build every palette."
- `docs/customising.md:14` — the `palette` key now sets the gallery's opening selection, not the only palette built

- [ ] **Step 2: Document the gallery's palette control**

Add to `docs/index.md`, after the output table:

```markdown
The preview gallery has a **Palette** dropdown listing every palette with its
primary colour. Switching palette reloads the frames from a sibling
`preview/blobs-<palette>.js`, which is why `preview/` contains one of those per
palette — the gallery would otherwise be a 5.9 MB document, most of it never
looked at.

Style and palette are independent. A style that pins its own palette (nyan does)
decides only which palette the gallery opens on; every style is still built in
every palette, because the point of building all of them is to choose.
```

- [ ] **Step 3: Add a CHANGELOG entry**

```markdown
### Changed

- Every style is now built in every palette. Pages move from
  `out/deploy/<style>/` to `out/deploy/<style>/<palette>/`, and portal imports
  from `out/deploy/<style>/portal/` to `out/deploy/<style>/<palette>/portal/`.
  **This breaks any script that globs the old paths.**
- `--palette` narrows a build to one palette instead of selecting the only one
  built, matching how `--theme` narrows the style axis.
- A theme's `palette` pin and the config's `palette` key now choose which
  palette the preview gallery opens on. They no longer decide what is built.
- The build report prints one row per style and palette, naming that
  combination's largest page, with anything that warns or fails listed in full
  underneath.

### Added

- A palette dropdown in the preview gallery, showing each palette's primary
  colour. The gallery chrome follows the selection.
```

- [ ] **Step 4: Check the docs tests still pass**

`tests/test_docs.py` asserts that every style is documented; confirm it has nothing to say about palettes, and extend it if it does.

Run: `uv run python -m pytest tests/test_docs.py -q`
Expected: PASS.

- [ ] **Step 5: Report, do not commit**

Run `git status --porcelain` and confirm the only unstaged files are documentation. Tell the user which files are ready for them to review and commit.

---

## Verification

After Task 6, from a clean tree:

```bash
uv run python -m pytest tests/ -q
uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src
rm -rf /tmp/mpfinal
uv run panos-response-pages build --customer contoso --config-dir src/panos_response_pages/data --out /tmp/mpfinal
find /tmp/mpfinal/deploy -name '*.html' | wc -l    # expect 308
ls /tmp/mpfinal/preview/blobs-*.js | wc -l          # expect 3
cd tmp/nyan-lab && node palette-check.mjs /tmp/mpfinal
```

Then open `/tmp/mpfinal/preview/index.html` and check by hand:

1. The Palette dropdown lists four palettes, each with a distinct colour dot.
2. Choosing one recolours the toolbar and the frame.
3. Style and palette do not move each other — selecting nyan leaves the palette where it was.
4. The Redirect toggle still appears only on `url-block-page`, and never for nyan.
5. Style, Page, Viewport and Colour scheme all still work after a palette change.
