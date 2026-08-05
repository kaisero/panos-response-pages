# Multi-Language Response Pages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compile every configured language into each response page and let the browser pick one from `navigator.languages`, so a single imported page serves a mixed-language user population.

**Architecture:** A new `i18n.py` owns one question — *what words does this page use, in this language?* English copy moves out of the page templates into `data/strings/en.json`; templates keep their markup and carry `{{T_*}}` placeholders that the build fills from the **base** language. Every non-base language is compiled into a compact per-page JSON dictionary emitted alongside the existing category script, and a ~240 B runtime selects one by primary subtag and swaps text through selectors that already exist in the shells.

**Tech Stack:** Python 3.11+, stdlib only (no new runtime dependencies). Typer CLI, pytest with unittest-style classes, `uv` for running.

**Spec:** `docs/specs/2026-08-05-multi-language-response-pages.md`. Every decision in that document is settled; this plan implements it and does not re-open it.

## Peer review, incorporated

This plan was reviewed and reworked. Two blockers were found by tracing the real
substitution pipeline, both since verified by reproduction:

1. **A `{{COMPANY}}` inside a translated string does not resolve.** `substitute()`
   uses `re.sub`, which never rescans its own replacement text, so a placeholder
   arriving *inside* a `{{T_*}}` value survives to `assert_resolved` and raises —
   and in the runtime dictionary, which never passes through `substitute()` at
   all, it would have shipped the literal braces to a German user with no error
   anywhere. Task 3b now owns this; an earlier draft of Task 5 asserted the
   opposite and was wrong.
2. **The severity pill reverts to English on `url-block-page` and
   `url-coach-text`.** The category script runs after the language swap and
   re-sets `.sev` from the base-language map. Those two pages are the only
   category-bearing pages without `COPY_LOCK`, so they are exactly where it
   lands. Task 8 Step 6 now fixes it.

Both would have produced a green build and a visibly broken page — the failure
mode this project exists to prevent. Seven further findings are folded into the
tasks below.

## Global Constraints

- **No new runtime dependencies.** `pyproject.toml` runtime deps stay `typer`, `rich`, `pyyaml`.
- **`languages: ["en"]` must produce byte-identical output to today.** This is the promise that makes the feature free for existing customers. Task 2 captures a byte snapshot *before* any migration and every later task re-asserts it. If a task breaks byte-identity, the task is wrong — do not update the snapshot.
- **17,999 B hard ceiling, 16,000 B warn line** (`validate.MAX_BYTES` / `WARN_BYTES`). Hold the warn line: the gap exists because `<url/>` expands at serve time.
- **`substitute()` raises on any key it does not know** (`templates.py:31-45`). Every `{{T_*}}` placeholder introduced into a template must be present in the values dict for that page, or nothing builds.
- **`strip_output()` removes HTML comments** (`emit.py:28-35`), so template comments are free — but only in the *page* templates, never in the JSON.
- **Imports go in the block at the top of the file, never appended at the bottom.** `pyproject.toml` selects ruff `E`, `F`, `I` and pre-commit runs `ruff check --fix`. An appended import trips `E402`, which `--fix` cannot repair. Equally, do not pre-declare an import a task does not yet use: that trips `F401`, which `--fix` *can* repair by deleting it, silently breaking the next task.
- **Commit message style:** short imperative subject, capitalised, no trailing period, ≤ 60 chars. No `feat:`/`fix:`/`docs:` prefixes, no emoji, no AI or tool attribution of any kind. (The `feat:` examples in the writing-plans skill do **not** apply to this repository.)
- **Never `git add` or `git commit` anything under `docs/` (Markdown), `README.md`, `CHANGELOG.md` or `SECURITY.md`.** Write them, then stop and say they are ready for review. Source, templates, JSON data and tests are fine to commit. `docs/plans/` and `docs/specs/` are gitignored working material.
- **German copy is authored, never machine-translated.** If you cannot write a German string, stop and ask — do not guess.

## File Structure

**Created:**
- `src/panos_response_pages/i18n.py` — the only module that knows a language from a string key. Config validation, strings loading, key-completeness checking, per-page dictionary assembly, placeholder resolution.
- `src/panos_response_pages/data/strings/en.json` — English copy, moved out of the templates.
- `src/panos_response_pages/data/strings/de.json` — German.
- `tests/test_i18n.py` — unit tests for the module.
- `tests/test_i18n_build.py` — integration tests over built output in both languages.

**Modified:**
- `src/panos_response_pages/data/templates/pages/*.html` (11 files) — copy replaced by `{{T_*}}` placeholders.
- `src/panos_response_pages/data/config/_defaults.json` — `baseLanguage`, `languages`.
- `src/panos_response_pages/data/themes/nyan.json` — `"i18n": false`.
- `src/panos_response_pages/page.py` — resolve `{{T_*}}` from the base language; pass the dictionary to the script emitter.
- `src/panos_response_pages/scripts.py` — `SEV_LABEL` leaves; `category_js` gains language selection.
- `src/panos_response_pages/builder.py` — per-theme language set, build-table column, ceiling error naming the language set.
- `src/panos_response_pages/portal/page.py` — portal strings and `logout_text_array`.
- `tests/test_copy.py`, `tests/test_layout_details.py` — guards move from templates to strings files and built output.

**Not modified:**
- `templates.py` — `{{T_*}}` matches the existing `[A-Z_0-9]+` placeholder pattern. No change needed, and that is why the placeholders are spelled this way.

---

## Task 1: Language configuration and validation

**Files:**
- Create: `src/panos_response_pages/i18n.py`
- Create: `tests/test_i18n.py`
- Modify: `src/panos_response_pages/data/config/_defaults.json`

**Interfaces:**
- Produces: `i18n.LANG_RE`, `i18n.base_language(cfg) -> str`, `i18n.languages(cfg) -> list[str]`, `i18n.check(cfg, data_dir) -> None`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_i18n.py
"""Language selection, strings loading and dictionary assembly."""

import unittest

import pytest

from _paths import DATA
from panos_response_pages import i18n
from panos_response_pages.errors import BuildError

pytestmark = pytest.mark.unit


class TestLanguageConfig(unittest.TestCase):
    def test_defaults_to_english_only(self):
        self.assertEqual(i18n.base_language({}), "en")
        self.assertEqual(i18n.languages({}), ["en"])

    def test_reads_configured_values(self):
        cfg = {"baseLanguage": "de", "languages": ["de", "en"]}
        self.assertEqual(i18n.base_language(cfg), "de")
        self.assertEqual(i18n.languages(cfg), ["de", "en"])

    def test_rejects_base_language_not_in_languages(self):
        cfg = {"baseLanguage": "fr", "languages": ["en", "de"]}
        with self.assertRaises(BuildError) as ctx:
            i18n.check(cfg, DATA)
        self.assertIn("baseLanguage", str(ctx.exception))
        self.assertIn("fr", str(ctx.exception))

    def test_rejects_empty_language_list(self):
        with self.assertRaises(BuildError):
            i18n.check({"baseLanguage": "en", "languages": []}, DATA)

    def test_rejects_non_two_letter_key(self):
        with self.assertRaises(BuildError) as ctx:
            i18n.check({"baseLanguage": "en", "languages": ["en", "de-AT"]}, DATA)
        self.assertIn("de-AT", str(ctx.exception))

    def test_rejects_language_with_no_strings_file(self):
        with self.assertRaises(BuildError) as ctx:
            i18n.check({"baseLanguage": "en", "languages": ["en", "zz"]}, DATA)
        self.assertIn("zz.json", str(ctx.exception))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/test_i18n.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'panos_response_pages.i18n'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/panos_response_pages/i18n.py
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

import pathlib
import re
from collections.abc import Mapping
from typing import Any

from panos_response_pages.errors import BuildError

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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/test_i18n.py`
Expected: PASS, 6 tests

- [ ] **Step 5: Declare the config keys**

In `src/panos_response_pages/data/config/_defaults.json`, add before `"palette"`, following the file's `_key` comment convention:

```json
  "_baseLanguage": "The language written as real text into the page. What a browser with JavaScript disabled shows, and what any unmatched browser falls back to. Two-letter code; must appear in `languages` below.",
  "baseLanguage": "en",
  "_languages": "Every language compiled into the page. The browser picks one from navigator.languages at load time. Two-letter codes only -- 'de' matches de-AT, de-CH and de-DE. Each needs a strings/<code>.json. Leaving this as [\"en\"] produces byte-identical output to a build from before this feature existed.",
  "languages": ["en"],
```

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest -q`
Expected: PASS — the new keys are inert until Task 5 reads them.

- [ ] **Step 7: Commit**

```bash
git add src/panos_response_pages/i18n.py tests/test_i18n.py src/panos_response_pages/data/config/_defaults.json
git commit -m "Add language configuration and validation"
```

---

## Task 2: Byte-identity snapshot

This task adds no behaviour. It builds the guard that every later task depends on, and it must exist **before** any copy moves.

**Files:**
- Create: `tests/test_i18n_build.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `tests/fixtures/byte-identity.json` — a committed map of `"<theme>/<palette>/<page>" -> sha256` for the current deploy output.

- [ ] **Step 1: Generate the snapshot**

```bash
uv run panos-response-pages build
uv run python - <<'EOF'
import hashlib, json, pathlib
out = {}
for f in sorted(pathlib.Path("out/deploy").rglob("*.html")):
    key = "/".join(f.parts[2:])
    out[key] = hashlib.sha256(f.read_bytes()).hexdigest()
pathlib.Path("tests/fixtures").mkdir(exist_ok=True)
pathlib.Path("tests/fixtures/byte-identity.json").write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
print(f"{len(out)} files snapshotted")
EOF
```

Expected: `364 files snapshotted`

- [ ] **Step 2: Write the test that reads it**

```python
# tests/test_i18n_build.py
"""Multi-language builds, and the promise that single-language builds are free.

The byte-identity assertion is the load-bearing one. `languages: ["en"]` must
produce exactly the bytes a build produced before this feature existed -- that
is what makes multi-language support cost nothing for every customer who does
not want it, and asserting it is how it stays true.

If this test fails, the change that broke it is wrong. Do NOT regenerate the
snapshot to make it pass.
"""

import hashlib
import json
import pathlib
import unittest

import pytest

from _build import built
from _paths import ROOT

pytestmark = pytest.mark.integration

SNAPSHOT = json.loads((ROOT / "tests/fixtures/byte-identity.json").read_text(encoding="utf-8"))


class TestSingleLanguageIsFree(unittest.TestCase):
    def test_english_only_build_is_byte_identical(self):
        out, _result = built()
        checked = 0
        for key, want in SNAPSHOT.items():
            f = pathlib.Path(out) / "deploy" / key
            self.assertTrue(f.is_file(), f"{key} is missing from the build")
            got = hashlib.sha256(f.read_bytes()).hexdigest()
            self.assertEqual(got, want, f"{key} changed; single-language output must stay byte-identical")
            checked += 1
        self.assertEqual(checked, len(SNAPSHOT))
```

- [ ] **Step 3: Run it**

Run: `uv run pytest -q tests/test_i18n_build.py`
Expected: PASS

If `built()` does not return an output path in the shape used above, read `tests/_build.py` and adapt the accessor — do not weaken the assertion.

- [ ] **Step 4: Prove the guard can fail**

Edit any page template's `<!--@GLOSS-->` text by one character, re-run the test, confirm it fails naming that page, then revert.

Run: `uv run pytest -q tests/test_i18n_build.py`
Expected: FAIL naming the changed page. A guard that cannot fail is not a guard.

- [ ] **Step 5: Commit**

```bash
git add tests/test_i18n_build.py tests/fixtures/byte-identity.json
git commit -m "Snapshot deploy output to guard byte identity"
```

---

## Task 3: Strings file loading and key completeness

**Files:**
- Modify: `src/panos_response_pages/i18n.py`
- Modify: `tests/test_i18n.py`
- Create: `src/panos_response_pages/data/strings/en.json` (skeleton only — one page; the rest arrives in Task 5)

**Interfaces:**
- Consumes: `i18n.check`, `i18n.strings_path` from Task 1.
- Produces: `i18n.load(lang, data_dir) -> dict`, `i18n.flat_keys(doc) -> set[str]`, `i18n.check_complete(cfg, data_dir) -> None`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_i18n.py` (imports go in the existing top block — add `import json` and `import pathlib` there):

```python
class TestStringsCompleteness(unittest.TestCase):
    """Every language supplies every key. A missing key is a build error, not a
    runtime fallback: a warning in a build log is the kind of notice that gets
    scrolled past, and the half-translated page it permits ships to users."""

    def _write(self, tmp, name, doc):
        d = tmp / "strings"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{name}.json").write_text(json.dumps(doc), encoding="utf-8")

    def test_flat_keys_walks_nested_documents_and_lists(self):
        doc = {"shared": {"a": "x"}, "pages": {"p": {"facts": ["one", "two"]}}}
        self.assertEqual(
            i18n.flat_keys(doc),
            {"shared.a", "pages.p.facts[0]", "pages.p.facts[1]"},
        )

    def test_accepts_a_language_with_the_same_keys(self):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            tmp = pathlib.Path(td)
            self._write(tmp, "en", {"shared": {"a": "x"}})
            self._write(tmp, "de", {"shared": {"a": "y"}})
            i18n.check_complete({"baseLanguage": "en", "languages": ["en", "de"]}, tmp)

    def test_rejects_a_language_missing_a_key(self):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            tmp = pathlib.Path(td)
            self._write(tmp, "en", {"shared": {"a": "x", "b": "z"}})
            self._write(tmp, "de", {"shared": {"a": "y"}})
            with self.assertRaises(BuildError) as ctx:
                i18n.check_complete({"baseLanguage": "en", "languages": ["en", "de"]}, tmp)
            msg = str(ctx.exception)
            self.assertIn("de.json", msg)
            self.assertIn("shared.b", msg)

    def test_rejects_a_language_with_an_extra_key(self):
        """An extra key is a typo or a stale key, both of which mean a string
        the page will never show. Silence there hides a real mistake."""
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            tmp = pathlib.Path(td)
            self._write(tmp, "en", {"shared": {"a": "x"}})
            self._write(tmp, "de", {"shared": {"a": "y", "typo": "z"}})
            with self.assertRaises(BuildError) as ctx:
                i18n.check_complete({"baseLanguage": "en", "languages": ["en", "de"]}, tmp)
            self.assertIn("shared.typo", str(ctx.exception))

    def test_categories_block_is_exempt_from_completeness(self):
        """Per-language category glosses are optional by design: absent, the
        language falls back to the translated generic gloss and costs ~600 B
        instead of ~2400 B."""
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            tmp = pathlib.Path(td)
            self._write(tmp, "en", {"shared": {"a": "x"}, "categories": {"gambling": "en gloss"}})
            self._write(tmp, "de", {"shared": {"a": "y"}})
            i18n.check_complete({"baseLanguage": "en", "languages": ["en", "de"]}, tmp)
```

- [ ] **Step 2: Run it**

Run: `uv run pytest -q tests/test_i18n.py`
Expected: FAIL — `AttributeError: module 'panos_response_pages.i18n' has no attribute 'flat_keys'`

- [ ] **Step 3: Implement**

Add to `i18n.py` (`import json` joins the top import block):

```python
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


def check_complete(cfg: Mapping[str, Any], data_dir: pathlib.Path) -> None:
    """Every configured language carries exactly the base language's key set.

    Exactly, not merely at least: an extra key is a typo or a stale entry, and
    either way it is a string that will never reach a page. Reported rather than
    ignored, because both are real mistakes that are invisible in the output.
    """
    base = base_language(cfg)
    want = flat_keys(load(base, data_dir))
    for lang in languages(cfg):
        if lang == base:
            continue
        got = flat_keys(load(lang, data_dir))
        missing = sorted(want - got)
        extra = sorted(got - want)
        if missing or extra:
            parts = []
            if missing:
                parts.append(f"missing {len(missing)} key(s):\n  " + "\n  ".join(missing))
            if extra:
                parts.append(f"unknown {len(extra)} key(s):\n  " + "\n  ".join(extra))
            raise BuildError(f"{lang}.json is out of step with {base}.json -- " + "; ".join(parts))
```

- [ ] **Step 4: Run it**

Run: `uv run pytest -q tests/test_i18n.py`
Expected: PASS, 11 tests

- [ ] **Step 5: Commit**

```bash
git add src/panos_response_pages/i18n.py tests/test_i18n.py
git commit -m "Load strings files and check key completeness"
```

---

## Task 3b: Placeholder resolution inside translated strings

**Added by peer review.** Without this, Task 5 cannot complete and Task 8 ships
literal `{{COMPANY}}` to users. Do not skip it as bookkeeping — it is a blocker fix.

Two shipped pages carry a placeholder *inside* their copy:
`credential-block-page`'s `EXTRA` has `{{COMPANY}}`, `url-coach-text`'s has
`{{CONTINUE_GRANT}}`. `substitute()` is a single `re.sub` pass and **re.sub never
rescans replacement text** — the codebase warns about exactly this at
`page.py:90-93`. So a placeholder inside a `{{T_*}}` value is inserted literally
and survives.

Reproduce it first, so you know what you are fixing:

```bash
uv run python -c "
from panos_response_pages.templates import substitute, assert_resolved
base = {'COMPANY':'Example Corp','INFO_MARK':'<svg/>','T_EXTRA':'Report to {{COMPANY}} security.'}
out = substitute('<p class=\"infobox\">{{INFO_MARK}}<span>{{T_EXTRA}}</span></p>', base)
print(out)
assert_resolved(out,'credential-block-page')
"
```

Expected: prints the line with `{{COMPANY}}` still in it, then
`BuildError: unresolved placeholder(s) in credential-block-page: COMPANY`.

**Files:**
- Modify: `src/panos_response_pages/i18n.py`
- Modify: `tests/test_i18n.py`

**Interfaces:**
- Produces: `i18n.resolve(value, values)` — resolves placeholders inside a string,
  a list of strings, or a dict of them, returning the same shape.

- [ ] **Step 1: Write the failing test**

```python
class TestPlaceholderResolution(unittest.TestCase):
    """Copy may itself contain {{COMPANY}} or {{CONTINUE_GRANT}}.

    substitute() is one re.sub pass and re.sub does not rescan its replacement,
    so a placeholder inside a translated value is inserted literally. In the
    base language that surfaces as a BuildError from assert_resolved. In the
    runtime dictionary -- which never passes through substitute() at all --
    it would ship the literal braces to a user with no error anywhere.
    """

    VALUES = {"COMPANY": "Example Corp", "CONTINUE_GRANT": "15 minutes"}

    def test_resolves_inside_a_string(self):
        self.assertEqual(
            i18n.resolve("Report to {{COMPANY}} security.", self.VALUES),
            "Report to Example Corp security.",
        )

    def test_resolves_inside_a_list(self):
        self.assertEqual(
            i18n.resolve(["a {{COMPANY}} b", "c"], self.VALUES),
            ["a Example Corp b", "c"],
        )

    def test_resolves_inside_a_nested_dict(self):
        self.assertEqual(
            i18n.resolve({"r": {"intro": "for {{CONTINUE_GRANT}}"}}, self.VALUES),
            {"r": {"intro": "for 15 minutes"}},
        )

    def test_unknown_placeholder_still_raises(self):
        with self.assertRaises(BuildError):
            i18n.resolve("{{NOPE}}", self.VALUES)

    def test_page_values_are_resolved(self):
        doc = {
            "shared": {"reportLabel": "R", "contactAlt": ["a", "b"]},
            "pages": {"p": {"title": "t", "headline": "h", "gloss": "g", "facts": ["f"],
                            "extra": "Ask {{COMPANY}}.",
                            "report": {"subject": "s", "intro": "i", "prompt": "p"}}},
        }
        v = i18n.page_values(doc, "p", self.VALUES)
        self.assertEqual(v["T_EXTRA"], "Ask Example Corp.")
        self.assertNotIn("{{", "".join(str(x) for x in v.values()))
```

- [ ] **Step 2: Run it**

Run: `uv run pytest -q tests/test_i18n.py -k PlaceholderResolution`
Expected: FAIL — no attribute `resolve`

- [ ] **Step 3: Implement**

`substitute` joins the top import block of `i18n.py`.

```python
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
```

- [ ] **Step 4: Thread it through `page_values`**

`page_values` gains a third parameter and resolves the page block before flattening:

```python
def page_values(doc: Mapping[str, Any], page: str, values: Mapping[str, object]) -> dict[str, str]:
    pages = doc.get("pages", {})
    if page not in pages:
        raise BuildError(f"strings document has no entry for page '{page}'")
    p = resolve(pages[page], values)
    shared = resolve(doc.get("shared", {}), values)
    ...
```

The `values` passed in is the `base` dict as it stands *before* the `T_*` keys
are folded in — `COMPANY`, `SUPPORT_EMAIL`, `CONTINUE_GRANT`, the marks. In
`page.py` that means building `base` first, then updating it:

```python
    base = {
        "COMPANY": cfg["company"],
        ...
        "INFO_MARK": cfg["marks"]["info"],
    }
    # Copy is resolved against the values above, not alongside them: a
    # placeholder inside a translated string has to be substituted BEFORE that
    # string becomes a replacement, because re.sub will not rescan it.
    base.update(i18n.page_values(strings, page, base))
```

- [ ] **Step 5: Run it**

Run: `uv run pytest -q tests/test_i18n.py`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/panos_response_pages/i18n.py tests/test_i18n.py
git commit -m "Resolve placeholders inside translated copy"
```

---

## Task 4: Move one page's copy into en.json

This is the proof of the mechanism on a single page. Task 5 repeats it for the other ten; do not start Task 5 until this one is green and byte-identical.

Use `application-block-page` — it is the simplest page that still has every element type (facts, report action, contact fallback, callout).

**Files:**
- Create: `src/panos_response_pages/data/strings/en.json`
- Modify: `src/panos_response_pages/data/templates/pages/application-block-page.html`
- Modify: `src/panos_response_pages/page.py`
- Modify: `tests/test_i18n.py`

**Interfaces:**
- Consumes: `i18n.load` from Task 3.
- Produces: `i18n.page_values(doc, page) -> dict[str, str]` returning the `{{T_*}}` values for one page.

- [ ] **Step 1: Write the failing test**

```python
class TestPageValues(unittest.TestCase):
    def test_builds_the_placeholder_values_for_one_page(self):
        doc = {
            "shared": {"reportLabel": "Report to IT", "contactAlt": ["Or email ", " with the details above."]},
            "pages": {
                "application-block-page": {
                    "title": "Application blocked",
                    "headline": "This application is blocked",
                    "gloss": "Company policy restricts this application on the network.",
                    "facts": ["Application", "User", "Time"],
                    "extra": "If you need this application for your work, send the report above and IT will review it.",
                    "report": {"subject": "Blocked application report", "intro": "Please review this application block.", "prompt": "Why I need this application:"},
                }
            },
        }
        v = i18n.page_values(doc, "application-block-page")
        self.assertEqual(v["T_TITLE"], "Application blocked")
        self.assertEqual(v["T_FACT1"], "Application")
        self.assertEqual(v["T_FACT3"], "Time")
        self.assertEqual(v["T_REPORT_LABEL"], "Report to IT")
        self.assertEqual(v["T_CONTACT_ALT1"], "Or email ")
        self.assertEqual(v["T_REPORT_SUBJECT"], "Blocked application report")

    def test_names_the_page_when_it_is_absent(self):
        with self.assertRaises(BuildError) as ctx:
            i18n.page_values({"shared": {}, "pages": {}}, "url-block-page")
        self.assertIn("url-block-page", str(ctx.exception))
```

- [ ] **Step 2: Run it**

Run: `uv run pytest -q tests/test_i18n.py -k PageValues`
Expected: FAIL — no attribute `page_values`

- [ ] **Step 3: Implement `page_values`**

```python
def page_values(doc: Mapping[str, Any], page: str) -> dict[str, str]:
    """The {{T_*}} values one page needs, flattened from the strings document.

    Fact labels are numbered rather than named. The runtime swaps them
    positionally against `dl dt` in document order, so the array IS the
    contract; giving the template names as well would create a second ordering
    that could silently disagree with it.
    """
    pages = doc.get("pages", {})
    if page not in pages:
        raise BuildError(f"strings document has no entry for page '{page}'")
    p = pages[page]
    shared = doc.get("shared", {})
    values: dict[str, str] = {
        "T_TITLE": p["title"],
        "T_HEADLINE": p["headline"],
        "T_GLOSS": p["gloss"],
        "T_EXTRA": p.get("extra", ""),
        "T_REPORT_LABEL": shared["reportLabel"],
        "T_REPORT_SUBJECT": p["report"]["subject"],
        "T_REPORT_INTRO": p["report"]["intro"],
        "T_REPORT_PROMPT": p["report"]["prompt"],
        "T_CONTACT_ALT1": shared["contactAlt"][0],
        "T_CONTACT_ALT2": shared["contactAlt"][1],
    }
    for i, label in enumerate(p["facts"], start=1):
        values[f"T_FACT{i}"] = label
    return values
```

- [ ] **Step 4: Run it**

Run: `uv run pytest -q tests/test_i18n.py -k PageValues`
Expected: PASS

- [ ] **Step 5: Create `en.json` with this one page**

Copy the strings **verbatim** out of `application-block-page.html`. A single changed character breaks byte-identity, which is the point.

```json
{
  "lang": "en",
  "shared": {
    "reportLabel": "Report to IT",
    "contactAlt": ["Or email ", " with the details above."]
  },
  "pages": {
    "application-block-page": {
      "title": "Application blocked",
      "headline": "This application is blocked",
      "gloss": "Company policy restricts this application on the network.",
      "facts": ["Application", "User", "Time"],
      "extra": "If you need this application for your work, send the report above and IT will review it.",
      "report": {
        "subject": "Blocked application report",
        "intro": "Please review this application block.",
        "prompt": "Why I need this application:"
      }
    }
  }
}
```

- [ ] **Step 6: Replace the copy in the template with placeholders**

In `application-block-page.html`, keeping every byte of markup identical:

```html
<!--@TITLE-->{{T_TITLE}}<!--/@TITLE-->

<!--@HEADLINE-->{{T_HEADLINE}}<!--/@HEADLINE-->

<!--@GLOSS-->{{T_GLOSS}}<!--/@GLOSS-->

<!--@FACTS-->
<div class="f"><dt>{{T_FACT1}}</dt><dd class="mono"><appname/></dd></div>
<div class="f"><dt>{{T_FACT2}}</dt><dd><user/></dd></div>
<div class="f"><dt>{{T_FACT3}}</dt><dd id="ts"></dd></div>
<!--/@FACTS-->

<!--@ACTIONS-->
<a class="btn" id="rep"{{CONTACT_TO}} data-subject="{{T_REPORT_SUBJECT}}"
   data-intro="{{T_REPORT_INTRO}}" data-prompt="{{T_REPORT_PROMPT}}"
   href="{{CONTACT_HREF}}">{{T_REPORT_LABEL}}</a>
{{CONTACT_ALT}}
<!--/@ACTIONS-->

<!--@CONTACT_ALT--><p class="plain">{{T_CONTACT_ALT1}}<a href="mailto:{{SUPPORT_EMAIL}}">{{SUPPORT_EMAIL}}</a>{{T_CONTACT_ALT2}}</p><!--/@CONTACT_ALT-->

<!--@EXTRA-->
<p class="infobox">{{INFO_MARK}}<span>{{T_EXTRA}}</span></p>
<!--/@EXTRA-->
```

Leave the leading `<!-- -->` documentation comment, `TONE`, `MARK` and `CONTACT_MAILTO` exactly as they are.

- [ ] **Step 7: Wire the values into `page.py`**

In `build_page`, `i18n` joins the top import block. Immediately after `contact.check(cfg)`, add:

```python
    # The base language is written into the markup as real text. Resolved before
    # the sections are substituted, because a translated string may itself carry
    # {{COMPANY}} or {{CONTINUE_GRANT}} -- re.sub does not rescan replacement
    # text, so a value inserted in a later pass would ship as literal braces.
    strings = i18n.load(i18n.base_language(cfg), template_dir.parent / "strings")
```

and fold the page values into `base` where it is constructed:

```python
    base = {
        "COMPANY": cfg["company"],
        ...
        "INFO_MARK": cfg["marks"]["info"],
        **i18n.page_values(strings, page),
    }
```

Note the path: `strings/` is a sibling of `templates/` inside the data dir, and `build_page` receives `template_dir`, not `data_dir`.

- [ ] **Step 8: Verify byte-identity**

Run: `uv run panos-response-pages build && uv run pytest -q tests/test_i18n_build.py`
Expected: PASS — the rendered page is unchanged.

If it fails, diff the rendered output against the snapshot and fix the **string**, not the snapshot. The usual cause is a lost or gained space around `{{T_CONTACT_ALT1}}`.

- [ ] **Step 9: Mark the guard that this migration invalidates**

`test_copy.py::test_user_field_row` asserts `<dt>User</dt><dd><user/></dd>`
verbatim in the templates, and that row is a placeholder from here on. It moves
to the built output in Task 10.

**Do not leave it failing across six tasks.** This plan is executed by a fresh
agent per task, each of which runs the full suite as its own gate; a red suite
reads as broken work, and one executor "helpfully" reverting the migration
undoes everything. Mark it instead, so the suite stays green and the reason is
in the code rather than in a commit message nobody reads:

```python
    @unittest.expectedFailure  # noqa: D102
    def test_user_field_row(self):
        """MIGRATING (Task 4-10): copy has left the templates, so this string is
        no longer there to match. The guard moves to the built output in Task 10,
        which removes this decorator -- and unittest reports an unexpected
        success if that happens before every page has migrated."""
```

`expectedFailure` earns its place twice here: the suite stays green *and*
removing the decorator early fails loudly as an unexpected success.

- [ ] **Step 10: Run everything**

Run: `uv run pytest -q`
Expected: PASS, with one expected failure reported.

- [ ] **Step 11: Commit**

```bash
git add src/panos_response_pages/i18n.py src/panos_response_pages/page.py \
        src/panos_response_pages/data/strings/en.json \
        src/panos_response_pages/data/templates/pages/application-block-page.html \
        tests/test_i18n.py tests/test_copy.py
git commit -m "Move application block page copy into en.json"
```

---

## Task 5: Move the remaining ten pages

Mechanical repetition of Task 4, one page at a time. **Build and run the byte-identity test after each page**, not once at the end — a mismatch is trivial to locate after one page and painful after ten.

**Files:**
- Modify: the other 10 files in `src/panos_response_pages/data/templates/pages/`
- Modify: `src/panos_response_pages/data/strings/en.json`

- [ ] **Step 1: Migrate each page in turn**

For each of `credential-block-page`, `credential-coach-text`, `data-filter-block-page`, `file-block-continue-page`, `file-block-page`, `safe-search-block-page`, `ssl-cert-status-page`, `url-block-page`, `url-coach-text`, `virus-block-page`:

1. Add its block to `en.json` under `pages`, copying strings **verbatim**.
2. Replace the copy in the template with `{{T_*}}` placeholders exactly as in Task 4 Step 6.
3. `uv run panos-response-pages build && uv run pytest -q tests/test_i18n_build.py`
4. Commit that one page.

Three pages need care:

- **`safe-search-block-page`** — its `EXTRA` contains an inline link, so it needs `T_EXTRA1`/`T_EXTRA2` around the anchor rather than a single `T_EXTRA`. Extend `page_values` to emit the pair when `extra` is a list, keeping the single-string form working:

  ```python
      extra = p.get("extra", "")
      if isinstance(extra, list):
          values["T_EXTRA1"], values["T_EXTRA2"] = extra[0], extra[1]
      else:
          values["T_EXTRA"] = extra
  ```

  Its `ACTIONS` also carries a second button ("Open search settings"); give it `T_ACTION2_LABEL` in that page's block.

- **`credential-block-page`** (`{{COMPANY}}` in `EXTRA`) and **`url-coach-text`**
  (`{{CONTINUE_GRANT}}` in `EXTRA`) — keep the placeholder inside the *string* in
  `en.json`. It resolves **only because Task 3b exists**: `resolve()` substitutes
  it before the value ever becomes a `re.sub` replacement. If Task 3b was skipped,
  these two pages fail with `BuildError: unresolved placeholder(s)`. That is the
  symptom; the cause is Task 3b, not these templates.

  `tests/test_copy.py::test_continue_grant_duration_comes_from_config` asserts
  `{{CONTINUE_GRANT}}` appears in the `url-coach-text` template; after migration
  it lives in `en.json`. Update that assertion to read the strings file, in the
  same commit as that page.

- [ ] **Step 2: Assert every page is covered**

Add to `tests/test_i18n.py`:

```python
class TestEnglishCoversEveryPage(unittest.TestCase):
    def test_every_registered_page_has_a_strings_block(self):
        """PAGE_TOKENS is the source of truth for which pages exist. A page
        template with no strings block fails at build time with a KeyError from
        inside substitution; this says which page, before the build runs."""
        from panos_response_pages.validate import PAGE_TOKENS

        doc = i18n.load("en", DATA)
        self.assertEqual(sorted(doc["pages"]), sorted(PAGE_TOKENS))
```

- [ ] **Step 3: Assert no English copy is left in the templates**

```python
class TestTemplatesCarryNoCopy(unittest.TestCase):
    def test_no_prose_left_in_page_slots(self):
        """Copy lives in the strings files now. A slot with words in it is copy
        that no language can override -- it would ship English into a German
        page, silently."""
        import re

        slots = ("TITLE", "HEADLINE", "GLOSS", "EXTRA")
        for f in sorted((DATA / "templates/pages").glob("*.html")):
            text = f.read_text(encoding="utf-8")
            for name, body in re.findall(r"<!--@([A-Z_]+)-->(.*?)<!--/@\1-->", text, re.S):
                if name not in slots:
                    continue
                stripped = re.sub(r"\{\{[A-Z_0-9]+\}\}|<[^>]+>", "", body).strip()
                self.assertEqual(stripped, "", f"{f.stem} {name} still contains copy: {stripped!r}")
```

- [ ] **Step 4: Verify**

Run: `uv run panos-response-pages build && uv run pytest -q tests/test_i18n_build.py tests/test_i18n.py`
Expected: PASS — all 364 files byte-identical.

- [ ] **Step 5: Commit the two coverage tests**

The ten pages were each committed in Step 1 — **one commit per page**, not one
commit for the task. Only the tests added in Steps 2 and 3 remain:

```bash
git add tests/test_i18n.py
git commit -m "Assert every page has strings and templates carry no copy"
```

---

## Task 6: Severity labels leave scripts.py

**Files:**
- Modify: `src/panos_response_pages/scripts.py:21`
- Modify: `src/panos_response_pages/data/strings/en.json`
- Modify: `src/panos_response_pages/page.py`

- [ ] **Step 1: Write the failing test**

```python
class TestSeverityLabels(unittest.TestCase):
    def test_severity_labels_come_from_the_strings_file(self):
        """The third home of English copy. It cannot stay in Python once the
        other two are consolidated -- a German page would show 'Caution'."""
        doc = i18n.load("en", DATA)
        self.assertEqual(doc["shared"]["severity"], {"calm": "", "warn": "Caution", "crit": "Security risk"})

    def test_scripts_module_no_longer_defines_them(self):
        import panos_response_pages.scripts as scripts

        self.assertFalse(hasattr(scripts, "SEV_LABEL"), "SEV_LABEL must not survive in scripts.py")
```

- [ ] **Step 2: Run it**

Run: `uv run pytest -q tests/test_i18n.py -k Severity`
Expected: FAIL on both

- [ ] **Step 3: Add to `en.json` under `shared`**

```json
    "severity": { "calm": "", "warn": "Caution", "crit": "Security risk" },
```

- [ ] **Step 4: Remove `SEV_LABEL` from `scripts.py` and take it as a parameter**

Delete the `SEV_LABEL` constant. `category_js` gains a `severity: Mapping[str, str]` keyword argument and uses it where it used the constant. In `page.py`, replace the `SEV_LABEL` import and the `"SEVERITY": SEV_LABEL.get(tone, "")` line with the strings value:

```python
            "SEVERITY": strings["shared"]["severity"].get(tone, ""),
```

and pass `severity=strings["shared"]["severity"]` into the `category_js(...)` call.

- [ ] **Step 5: Verify byte-identity**

Run: `uv run panos-response-pages build && uv run pytest -q`
Expected: PASS including byte-identity — the values are unchanged, only their home is.

- [ ] **Step 6: Commit**

```bash
git add src/panos_response_pages/scripts.py src/panos_response_pages/page.py src/panos_response_pages/data/strings/en.json tests/test_i18n.py
git commit -m "Move severity labels into the strings files"
```

---

## Task 7: Customer translations overlay

**Files:**
- Modify: `src/panos_response_pages/i18n.py`
- Modify: `tests/test_i18n.py`
- Modify: `src/panos_response_pages/data/config/_defaults.json`

**Interfaces:**
- Produces: `i18n.config_strings(cfg, doc, lang) -> dict[str, str]` — the customer-authored strings for one language, customer config winning over the shipped strings file.

- [ ] **Step 1: Write the failing test**

```python
class TestCustomerTranslations(unittest.TestCase):
    """Customer-authored copy is translated in the customer's own config, not
    in the shipped strings files -- resolution is whole-tree, so putting it
    there would force a customer to fork the entire data directory to
    translate one sentence."""

    DOC = {"shared": {"defaultGloss": "shipped EN", "continueGrantText": "15 minutes"}}

    def test_falls_back_to_the_strings_file(self):
        got = i18n.config_strings({}, self.DOC, "en")
        self.assertEqual(got["defaultGloss"], "shipped EN")

    def test_customer_translation_wins(self):
        cfg = {"translations": {"de": {"defaultGloss": "Kunden-DE", "continueGrantText": "30 Minuten"}}}
        got = i18n.config_strings(cfg, self.DOC, "de")
        self.assertEqual(got["defaultGloss"], "Kunden-DE")
        self.assertEqual(got["continueGrantText"], "30 Minuten")

    def test_untranslated_customer_key_falls_back_to_the_strings_file(self):
        cfg = {"translations": {"de": {"defaultGloss": "Kunden-DE"}}}
        got = i18n.config_strings(cfg, self.DOC, "de")
        self.assertEqual(got["continueGrantText"], "15 minutes")

    def test_rejects_a_translation_for_an_unconfigured_language(self):
        cfg = {"baseLanguage": "en", "languages": ["en"], "translations": {"fr": {"defaultGloss": "x"}}}
        with self.assertRaises(BuildError) as ctx:
            i18n.check(cfg, DATA)
        self.assertIn("fr", str(ctx.exception))
```

- [ ] **Step 2: Run it**

Run: `uv run pytest -q tests/test_i18n.py -k CustomerTranslations`
Expected: FAIL — no attribute `config_strings`

- [ ] **Step 3: Implement**

```python
# Customer-authored copy: shipped in _defaults.json, overridable per customer,
# and therefore translatable only in the customer's own file.
CONFIG_STRING_KEYS = ("defaultGloss", "riskGloss", "continueGrantText", "supportLabel")


def config_strings(cfg: Mapping[str, Any], doc: Mapping[str, Any], lang: str) -> dict[str, str]:
    """Customer-authored strings for one language.

    Precedence mirrors config-over-defaults: the customer's `translations` block
    wins over the shipped strings file, and a key they have not translated falls
    back to it rather than to the base language.
    """
    shared = doc.get("shared", {})
    out = {k: str(shared[k]) for k in CONFIG_STRING_KEYS if k in shared}
    out.update({k: str(v) for k, v in cfg.get("translations", {}).get(lang, {}).items()})
    return out
```

and extend `check()` with, after the strings-file loop:

```python
    for lang in cfg.get("translations", {}):
        if lang not in langs:
            raise BuildError(
                f"`translations` has a block for '{lang}', which is not in `languages` ({', '.join(langs)}). "
                "Add it to `languages` or remove the block."
            )
```

- [ ] **Step 4: Document the key**

Add to `_defaults.json`, after `languages`:

```json
  "_translations": "Your OWN copy, per language. The strings files translate what this project ships; this translates what YOU changed -- defaultGloss, riskGloss, continueGrantText, supportLabel. Keys you leave out fall back to the shipped translation. Example: {\"de\": {\"continueGrantText\": \"30 Minuten\"}}",
  "translations": {},
```

- [ ] **Step 5: Verify**

Run: `uv run pytest -q`
Expected: PASS, byte-identity intact (an empty `translations` changes nothing).

- [ ] **Step 6: Commit**

```bash
git add src/panos_response_pages/i18n.py tests/test_i18n.py src/panos_response_pages/data/config/_defaults.json
git commit -m "Let customers translate their own configured copy"
```

---

## Task 8: The runtime — dictionary and selector swap

**Files:**
- Modify: `src/panos_response_pages/i18n.py`
- Modify: `src/panos_response_pages/scripts.py`
- Modify: `src/panos_response_pages/page.py`
- Modify: `tests/test_i18n.py`

**Interfaces:**
- Produces: `i18n.runtime_dict(cfg, page, data_dir) -> dict[str, dict]` keyed by language, base language excluded; `scripts.category_js(..., lang_dict: str = "")`.

- [ ] **Step 1: Write the failing test**

```python
class TestRuntimeDict(unittest.TestCase):
    def test_base_language_is_not_shipped(self):
        """It is already in the markup as real text. Shipping it again would be
        the largest single waste in the design."""
        cfg = {"baseLanguage": "en", "languages": ["en"]}
        self.assertEqual(i18n.runtime_dict(cfg, "application-block-page", DATA), {})

    def test_carries_only_the_keys_that_page_uses(self):
        cfg = {"baseLanguage": "en", "languages": ["en", "de"]}
        d = i18n.runtime_dict(cfg, "application-block-page", DATA)
        self.assertEqual(sorted(d), ["de"])
        self.assertEqual(set(d["de"]), {"t", "h", "g", "f", "x", "rl", "rs", "ri", "rp", "ca", "s", "dg", "rg"})
        self.assertEqual(len(d["de"]["f"]), 3, "one label per dt on this page")
```

- [ ] **Step 2: Run it**

Run: `uv run pytest -q tests/test_i18n.py -k RuntimeDict`
Expected: FAIL — no attribute `runtime_dict`

- [ ] **Step 3: Implement**

```python
# Single-letter keys. This dictionary ships in every page of every style, so a
# descriptive key costs its own length x pages x styles x languages for nothing:
# the only reader is the emitted script twenty lines away.
def runtime_dict(cfg: Mapping[str, Any], page: str, data_dir: pathlib.Path) -> dict[str, dict[str, Any]]:
    """Per-page translations for every language EXCEPT the base one."""
    base = base_language(cfg)
    out: dict[str, dict[str, Any]] = {}
    for lang in languages(cfg):
        if lang == base:
            continue
        doc = load(lang, data_dir)
        p = doc["pages"][page]
        shared = doc["shared"]
        conf = config_strings(cfg, doc, lang)
        entry: dict[str, Any] = {
            "t": p["title"],
            "h": p["headline"],
            "g": p["gloss"],
            "f": list(p["facts"]),
            "x": p.get("extra", ""),
            "rl": shared["reportLabel"],
            "rs": p["report"]["subject"],
            "ri": p["report"]["intro"],
            "rp": p["report"]["prompt"],
            "ca": list(shared["contactAlt"]),
            "s": shared["severity"],
            "dg": conf["defaultGloss"],
            "rg": conf["riskGloss"],
        }
        if "categories" in doc:
            entry["c"] = doc["categories"]
        out[lang] = entry
    return out
```

- [ ] **Step 4: Run it**

Run: `uv run pytest -q tests/test_i18n.py -k RuntimeDict`
Expected: PASS

- [ ] **Step 5: Write the failing test for the emitted script**

```python
class TestEmittedRuntime(unittest.TestCase):
    def test_single_language_emits_nothing_new(self):
        """The byte-identity promise, at the level of the function that would
        break it."""
        from panos_response_pages import scripts

        a = scripts.category_js({}, "d", "r", lock_copy=True, has_category=False, email_mode=True,
                                severity={"calm": "", "warn": "Caution", "crit": "Security risk"})
        b = scripts.category_js({}, "d", "r", lock_copy=True, has_category=False, email_mode=True,
                                severity={"calm": "", "warn": "Caution", "crit": "Security risk"},
                                lang_dict="")
        self.assertEqual(a, b)

    def test_multi_language_emits_the_selector(self):
        from panos_response_pages import scripts

        js = scripts.category_js({}, "d", "r", lock_copy=True, has_category=False, email_mode=True,
                                 severity={"calm": "", "warn": "Caution", "crit": "Security risk"},
                                 lang_dict='{"de":{"h":"Hallo"}}')
        self.assertIn("navigator.languages", js)
        self.assertIn("Hallo", js)
        self.assertIn("documentElement.lang", js)

    def test_severity_label_consults_the_selected_language(self):
        """The category script runs AFTER the language swap and re-sets .sev.
        Without this it reverts the pill to English on url-block-page and
        url-coach-text -- the only category-bearing pages without COPY_LOCK."""
        from panos_response_pages import scripts

        js = scripts.category_js({"gambling": {"tone": "warn", "gloss": ""}}, "d", "r",
                                 lock_copy=False, has_category=True, email_mode=True,
                                 severity={"calm": "", "warn": "Caution", "crit": "Security risk"},
                                 lang_dict='{"de":{"s":{"warn":"Achtung"}}}')
        self.assertIn("t?t.s:", js, "severity must fall back to the base map only when no language matched")
```

The DOM-level counterpart belongs in `tests/test_i18n_build.py`, where a real
built page can be driven: build `url-block-page` with `languages: ["en","de"]`,
assert the emitted script contains `t?t.s:` and that `"Caution"` appears only
inside the base-language map, never as the sole severity source.

- [ ] **Step 6: Implement the emission in `scripts.py`**

`category_js` gains `lang_dict: str = ""`. When it is empty the function returns exactly what it returns today. When it is not, this block is emitted **first inside the existing IIFE**, so the category lookup and the timestamp both see the final language:

```python
    # Language selection. First, because everything after it reads the words it
    # chose: the category lookup rewrites the gloss, the timestamp formats to a
    # locale, and the mail rebuild folds the rendered rows into a body.
    #
    # The base language is absent from the dictionary -- it is the markup. A
    # browser whose languages do not match leaves the page exactly as served,
    # which is the only failure mode: never blank, never half-swapped.
    lang = (
        (
            "var T=" + lang_dict + ",LS=navigator.languages||[navigator.language||''],t,lk,i;"
            "for(i=0;i<LS.length;i++){lk=LS[i].slice(0,2).toLowerCase();"
            "if(lk==" + json.dumps(base_lang) + ")break;if(T[lk]){t=T[lk];break}}"
            "if(t){var Q=function(s){return document.querySelector(s)};"
            "document.documentElement.lang=lk;document.title=t.t;"
            "var H=Q('h1');if(H)H.textContent=t.h;"
            "var G0=Q('#gloss');if(G0)G0.textContent=t.g;"
            "[].forEach.call(document.querySelectorAll('dl dt'),function(e,i){if(t.f[i])e.textContent=t.f[i]});"
            "var R=Q('#rep');if(R){R.lastChild.nodeValue=t.rl;"
            "R.setAttribute('data-subject',t.rs);R.setAttribute('data-intro',t.ri);"
            "R.setAttribute('data-prompt',t.rp)}"
            "var P=Q('.plain');if(P&&P.childNodes.length>2){P.childNodes[0].nodeValue=t.ca[0];"
            "P.childNodes[2].nodeValue=t.ca[1]}"
            "var X=Q('.infobox span,.warnline span');if(X&&t.x)X.textContent=t.x;"
            "var V=Q('.sev');if(V&&V.textContent)V.textContent=t.s[document.documentElement.getAttribute('data-tone')]||V.textContent;}"
        )
        if lang_dict
        else ""
    )
```

Note the `.sev` line at the end of that block is **not** the whole story — see
the next step.

Three consequences to implement alongside it:

1. **The tone/gloss fallback becomes language-aware.** In `tone_gloss`, the generic fallbacks `d` and the risk gloss become `t?t.dg:d` and `t?t.rg:<risk>`, and a per-category gloss is used only when the selected language ships a `c` block: `(t?(t.c&&t.c[k])||(m[0]=='calm'?t.dg:t.rg):m[1]||...)`.

2. **BLOCKER FIX — the severity label inside `tone_gloss` must consult `t.s`.**
   `tone_gloss` re-sets `.sev` from a baked-in base-language map (`scripts.py:96-98`)
   and it runs *after* the language swap, so it silently reverts the pill to
   English the moment a category resolves. `url-block-page` and `url-coach-text`
   are the only category-bearing pages without `COPY_LOCK`, so this lands exactly
   on the two pages the byte budget is built around. Change:

   ```python
   "var v=document.querySelector('.sev');"
   "if(v)v.textContent=" + json.dumps(severity, separators=(",", ":")) + "[m[0]]||'';"
   ```

   to consult the selected language first:

   ```python
   "var v=document.querySelector('.sev');"
   "if(v)v.textContent=(t?t.s:" + json.dumps(severity, separators=(",", ":")) + ")[m[0]]||'';"
   ```

   With `lang_dict` empty, `t` is not declared at all — so guard it in the
   single-language path by keeping today's exact string. Emit the `t?`-form only
   when `lang_dict` is truthy, or byte-identity breaks and `t` is a ReferenceError.

3. **The timestamp becomes locale-aware, only in multi-language builds.** Keep the single-language form byte-identical:

```python
    ts = (
        "var ts=document.getElementById('ts');"
        + (
            "if(ts)ts.textContent=new Date().toLocaleString(document.documentElement.lang||undefined);"
            if lang_dict
            else "if(ts)ts.textContent=new Date().toLocaleString();"
        )
    )
```

- [ ] **Step 7: Pass it through `page.py`**

```python
            + category_js(
                ...,
                lang_dict=json.dumps(i18n.runtime_dict(cfg, page, template_dir.parent), separators=(",", ":"), ensure_ascii=False)
                if len(i18n.languages(cfg)) > 1
                else "",
            )
```

`ensure_ascii=False` matters: `ä` costs six bytes where `ä` costs two, and this dictionary ships on every page.

- [ ] **Step 8: Verify**

Run: `uv run panos-response-pages build && uv run pytest -q`
Expected: PASS including byte-identity — `languages` is still `["en"]`, so `lang_dict` is empty everywhere.

- [ ] **Step 9: Commit**

```bash
git add src/panos_response_pages/i18n.py src/panos_response_pages/scripts.py src/panos_response_pages/page.py tests/test_i18n.py
git commit -m "Emit the language dictionary and selector runtime"
```

---

## Task 9: German

**Files:**
- Create: `src/panos_response_pages/data/strings/de.json`
- Modify: `src/panos_response_pages/data/config/_defaults.json` (temporarily, to verify)

**Sized honestly: this is the largest task in the plan, comparable to Task 5.** It
is eleven pages of policy-sensitive copy plus a portal block, not the fifteen-line
`shared` skeleton shown below. Split it per page and commit per page, as Task 5 does.

- [ ] **Step 0: Exempt the strings directory from codespell**

Do this *before* writing German, not after the pre-commit hook fails mid-task.
`pyproject.toml:92` skips `data/fixtures` because it is not prose; `data/strings/`
is the opposite — it is prose, in two languages, and codespell's dictionary is
English. The hook runs with `pass_filenames: false` and walks the whole tree, so
gitignore does not reach it.

Prefer `ignore-words-list` over a blanket skip where possible: `en.json` is
English prose and *should* stay spell-checked. If German trips too many entries
to enumerate, skip only `data/strings/de.json` and say why in the comment above
`skip`, following the convention already there.

Verify before writing a single German string:

```bash
uv run codespell src/panos_response_pages/data/strings/
```

- [ ] **Step 1: Author `de.json`**

Same key structure as `en.json`, German copy throughout. **Do not machine-translate.** If you cannot write a string, stop and ask.

The copy rules apply in German exactly as in English: no claim about whether data was transmitted, no claim that a policy applies to all users. `BANNED_COPY` is an English phrase list and will not catch a German violation — Task 10 adds the German phrases.

Note for the translator: `contactAlt` is the two halves either side of the mailto link. German word order must keep the link between them.

```json
{
  "lang": "de",
  "shared": {
    "severity": { "calm": "", "warn": "Achtung", "crit": "Sicherheitsrisiko" },
    "reportLabel": "An die IT melden",
    "contactAlt": ["Oder senden Sie eine E-Mail an ", " mit den obigen Angaben."],
    "defaultGloss": "Diese Kategorie ist durch Unternehmensrichtlinien eingeschränkt.",
    "riskGloss": "Diese Seite wurde gesperrt, weil sie ein Sicherheitsrisiko darstellt.",
    "continueGrantText": "15 Minuten",
    "supportLabel": "IT-Support"
  },
  "pages": { }
}
```

- [ ] **Step 2: Verify completeness before anything else**

```bash
uv run python -c "
from panos_response_pages import i18n, datadir
i18n.check_complete({'baseLanguage':'en','languages':['en','de']}, datadir.PACKAGED)
print('de.json is complete')
"
```

Expected: `de.json is complete`, or an error naming every missing key. Iterate until clean.

- [ ] **Step 3: Build with German and read the output**

Temporarily set `"languages": ["en", "de"]` in `_defaults.json`, then:

```bash
uv run panos-response-pages build
uv run panos-response-pages validate out/deploy
find out/deploy -name 'url-block-page.html' -exec wc -c {} + | grep -v total | sort -n | tail -3
```

Expected: `0 would fail`. Record the actual German page sizes — **this is the measurement that replaces the spec's estimated 1.25 expansion factor**. Update the budget table in the spec with the real numbers.

- [ ] **Step 4: Look at it in a browser**

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --disable-gpu \
  --force-device-scale-factor=2 --window-size=1100,900 --screenshot=/tmp/de.png \
  "file://$PWD/out/preview/banner/prisma-blue/url-block-page.html"
```

The preview renders in the browser's language, so set the browser locale or drive it with `--lang=de-DE`. Check: headline, gloss, every fact label, the button, the callout and the timestamp format are all German; the category label is still the PAN-OS slug title-cased; nothing is clipped by a longer German word.

**German compound nouns are the layout risk here.** `Sicherheitsrisiko` and `Unternehmensrichtlinien` are far wider than their English equivalents — check the `<dt>` column in `banner` and `record`, which give labels the least room.

- [ ] **Step 4b: Exercise the optional category glosses — the one untested path**

Spec Decision 5 permits a per-language `categories` block, and Task 8 emits
`entry["c"]` for it, but nothing so far has ever *authored* one. An unexercised
branch in the emitted script is a branch that does not work.

Add a `categories` block to `de.json` covering **three** categories only — enough
to prove the path, not enough to spend the 1,800 B budget — and assert end to end
that the translated gloss reaches the page:

```python
class TestOptionalCategoryGlosses(unittest.TestCase):
    def test_a_translated_category_gloss_reaches_the_page(self):
        out, _ = built_with_languages(("en", "de"))
        page = (out / "deploy/glass/prisma-blue/url-block-page.html").read_text(encoding="utf-8")
        self.assertIn("Glücksspiel", page, "the German gambling gloss should be compiled in")
        self.assertRegex(page, r"t\.c&&t\.c\[k\]", "the per-category branch must be emitted")
```

Then remove the block again if the measured size in Step 3 leaves no room, and
record which it was — shipping it or not is a size decision, but leaving the code
path untested is not.

- [ ] **Step 5: Revert `_defaults.json` to `["en"]` and confirm byte-identity**

Run: `uv run panos-response-pages build && uv run pytest -q`
Expected: PASS. German ships as an available language, not as the default.

- [ ] **Step 6: Commit**

```bash
git add src/panos_response_pages/data/strings/de.json
git commit -m "Add German response page copy"
```

---

## Task 10: Guard migration

**Files:**
- Modify: `tests/test_copy.py`
- Modify: `tests/test_layout_details.py`
- Modify: `src/panos_response_pages/validate.py`

- [ ] **Step 1: Extend `BANNED_COPY` with the German equivalents**

The copy rules are about what a page can substantiate, not about English. In `validate.py`:

```python
BANNED_COPY = [
    ("nothing you typed", "asserts data was not transmitted"),
    ("was not sent", "asserts data was not transmitted"),
    ("left your device", "asserts data was not transmitted"),
    ("for everyone", "asserts the policy applies to all users"),
    ("everybody", "asserts the policy applies to all users"),
    ("not just you", "asserts the policy applies to all users"),
    # German. The rules are about what the page can know, not about English --
    # a German sentence asserts an unknowable just as easily.
    ("nicht gesendet", "asserts data was not transmitted"),
    ("nicht übertragen", "asserts data was not transmitted"),
    ("hat ihr gerät nicht verlassen", "asserts data was not transmitted"),
    ("für alle benutzer", "asserts the policy applies to all users"),
    ("für jeden", "asserts the policy applies to all users"),
    ("nicht nur für sie", "asserts the policy applies to all users"),
]
```

- [ ] **Step 2: Point `test_copy.py` at the strings files**

Replace `_sources()` so it walks `data/strings/*.json` and `config/_defaults.json` instead of the template slots. Every language file is linted, not just English.

```python
    def _sources(self):
        out = []
        for p in sorted((DATA / "strings").glob("*.json")):
            out.append((p.name, p.read_text(encoding="utf-8")))
        out.append((CONFIG.name, CONFIG.read_text(encoding="utf-8")))
        return out
```

- [ ] **Step 3: Move the structural guards to the built output**

`test_user_field_row` and `test_subjects_are_distinct_per_page` now assert on built pages, per language. Subjects must be distinct **within** a language:

```python
class TestBuiltPagesIdentifyTheUser(unittest.TestCase):
    def test_every_built_page_carries_a_user_row(self):
        """Every page identifies who was blocked. The label is translated now,
        so the assertion is on the token and its row, not on the word 'User'."""
        for f in sorted(DEPLOY.rglob("*.html")):
            if "portal" in f.parts:
                continue
            text = f.read_text(encoding="utf-8")
            self.assertRegex(text, r"<dt>[^<]+</dt><dd><user/></dd>", f"{f} has no user fact row")
```

- [ ] **Step 4: Assert the fact-label count matches the dt count**

**Add this in Task 5 Step 3, not here.** It is written out in this task only
because that is where the other guards live. `check_complete` compares languages
against *each other*, so it never notices an `en.json` with one label too many —
and between Task 4 and Task 10 that is an eight-task window in which the exact
error mode the positional design accepted goes undetected. Move it forward; the
code is identical wherever it lands.

```python
class TestFactLabelCounts(unittest.TestCase):
    def test_every_language_has_one_label_per_dt(self):
        """Fact labels swap positionally against `dl dt` in document order. One
        short and every label below it shifts up by one, silently."""
        import re

        from panos_response_pages import i18n
        from panos_response_pages.validate import PAGE_TOKENS

        for page in sorted(PAGE_TOKENS):
            body = (DATA / "templates/pages" / f"{page}.html").read_text(encoding="utf-8")
            facts = re.search(r"<!--@FACTS-->(.*?)<!--/@FACTS-->", body, re.S).group(1)
            want = len(re.findall(r"<dt>", facts))
            for f in sorted((DATA / "strings").glob("*.json")):
                doc = i18n.load(f.stem, DATA)
                got = len(doc["pages"][page]["facts"])
                self.assertEqual(got, want, f"{f.stem}/{page}: {got} labels for {want} <dt> rows")
```

- [ ] **Step 5: Verify**

Run: `uv run pytest -q`
Expected: PASS — including the `test_user_field_row` failure introduced in Task 4, now fixed.

- [ ] **Step 6: Commit**

```bash
git add tests/test_copy.py tests/test_layout_details.py src/panos_response_pages/validate.py
git commit -m "Move copy guards from templates to strings and output"
```

---

## Task 11: Theme opt-out and the ceiling error

**Files:**
- Modify: `src/panos_response_pages/data/themes/nyan.json`
- Modify: `src/panos_response_pages/builder.py`
- Modify: `src/panos_response_pages/page.py`
- Modify: `tests/test_i18n_build.py`

- [ ] **Step 1: Write the failing test**

```python
class TestThemeOptOut(unittest.TestCase):
    def test_nyan_declares_no_i18n(self):
        """At 15108 B it has 892 B of headroom -- less than two languages --
        because its star field and sprite artwork are half the file. It is a
        novelty style; capping the design around it would be the tail wagging
        the dog."""
        theme = json.loads((DATA / "themes/nyan.json").read_text(encoding="utf-8"))
        self.assertFalse(theme.get("i18n", True))

    def test_opted_out_theme_ships_base_language_only(self):
        out, _ = built(languages=["en", "de"])
        nyan = (pathlib.Path(out) / "deploy/nyan/prisma-blue/url-block-page.html").read_text(encoding="utf-8")
        glass = (pathlib.Path(out) / "deploy/glass/prisma-blue/url-block-page.html").read_text(encoding="utf-8")
        self.assertNotIn("navigator.languages", nyan, "nyan must not carry the language runtime")
        self.assertIn("navigator.languages", glass)
```

**`built()` does not take a `languages` keyword, and there is no data-dir copy to
add one to.** `tests/_build.py:22-30` calls `build_all(DATA, out, preview=True)`
straight against the packaged data dir, memoised with `lru_cache(maxsize=1)`.
Writing a config into `DATA` would mutate the installed package and poison every
other test through that cache.

Build the helper first, as its own step, with its own cache key:

```python
# tests/_build.py -- pathlib, shutil, tempfile and functools are already imported
# at the top of this file; add shutil there if it is absent.

@functools.lru_cache(maxsize=4)
def built_with_languages(languages: tuple[str, ...], base: str = "en") -> tuple[pathlib.Path, BuildResult]:
    """A build with a language set, against a COPY of the packaged data.

    The data directory is copied rather than written to: DATA is the installed
    package, `built()` memoises a build against it, and a config written in
    place would change what every other test in the session sees.

    Keyed on the language tuple so each set is built once. Cached separately
    from built(), whose single slot must keep holding the default build.
    """
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="panos-rp-i18n-data-"))
    data = tmp / "data"
    shutil.copytree(DATA, data)
    cfg_path = data / "config" / "_defaults.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["languages"] = list(languages)
    cfg["baseLanguage"] = base
    cfg_path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")

    out = pathlib.Path(tempfile.mkdtemp(prefix="panos-rp-i18n-out-"))
    return out, build_all(data, out, preview=True)
```

Call it as `built_with_languages(("en", "de"))` — a tuple, because `lru_cache`
needs hashable arguments and a list would raise `TypeError`.

- [ ] **Step 2: Run it**

Run: `uv run pytest -q tests/test_i18n_build.py -k ThemeOptOut`
Expected: FAIL

- [ ] **Step 2b: Template the `lang` attribute**

All seven shells hardcode `<html lang="en" data-tone="{{TONE}}">` (`assist.html:2`
and its six siblings). Task 1's validation permits any two-letter `baseLanguage`,
so a customer setting `baseLanguage: "de"` today gets German markup declaring
itself English — wrong for screen readers and browser spellcheck, and wrong
permanently for a browser with JS disabled, since the runtime is what would
otherwise correct it.

Change all seven to `<html lang="{{LANG}}" data-tone="{{TONE}}">` and add
`"LANG": i18n.base_language(cfg)` to the `values` dict in `page.py`.

**Byte-identity holds:** `{{LANG}}` resolves to `en` for every existing config,
which is the same two bytes. Confirm with `uv run pytest -q tests/test_i18n_build.py`
before moving on — if it fails, the substitution is wrong, not the snapshot.

- [ ] **Step 3: Add the flag and honour it**

`nyan.json` gains `"i18n": false`. In `page.py`, the dictionary is emitted only when the theme allows it:

```python
                lang_dict=... if len(i18n.languages(cfg)) > 1 and theme.get("i18n", True) else "",
```

- [ ] **Step 4: Report it in the build table**

In `builder.py`, where each row is printed, append the language set for that theme, and `(base only — i18n:false)` for an opted-out theme. Silence here would be exactly the invisible failure the design rejected.

- [ ] **Step 5: Name the language set in the ceiling error**

In `validate.py`'s size error, the caller now knows the language set; pass it through so an oversize page says which languages produced the size, and mentions that dropping a `categories` block recovers ~1,800 B.

- [ ] **Step 6: Verify**

Run: `uv run pytest -q && uv run panos-response-pages build`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/panos_response_pages/data/themes/nyan.json src/panos_response_pages/builder.py src/panos_response_pages/page.py tests/test_i18n_build.py tests/_build.py src/panos_response_pages/validate.py
git commit -m "Let a theme opt out of extra languages"
```

---

## Task 12: Portal

**Re-planned from the source after review.** The earlier version of this task was
prose without code; it has been replaced with steps at the same fidelity as
Tasks 1-11, and the analysis behind it corrected three things the spec had wrong.
Read the Portal sections of the spec before starting.

### What the re-analysis established

| Fact | Where |
|---|---|
| Portal copy lives in the **shells**, not the page templates — identically in all 7 | `templates/portal/shells/*.html`, `<!--@BODY-->` |
| Four more strings are **JS literals**, not markup | `templates/portal/login.html` `<!--@FOOT_SCRIPT-->` |
| PAN-OS's injected form carries `Username` / `Password` / `Log In` — **not ours, but reachable** | `data/fixtures/pan_form-login.html` |
| `logout_text_array` is read inside `$(document).ready` — **`HEAD_SCRIPT` beats it** | `data/fixtures/logout-suffix.html:26` |
| The warn line is **15,000 B**, not 16,170 | `portal/validate.py:42` |
| Worst import is `beacon`/`login` at 12,119 B — 2,881 B of headroom | measured |
| A raw `<` anywhere silently breaks `<pan_form/>` substitution | `portal/validate.py:85` |

**Files:**
- Modify: `src/panos_response_pages/data/templates/portal/shells/*.html` (7 files)
- Modify: `src/panos_response_pages/data/templates/portal/login.html`
- Modify: `src/panos_response_pages/portal/page.py`
- Modify: `src/panos_response_pages/i18n.py`
- Modify: `src/panos_response_pages/data/strings/en.json`, `de.json`
- Modify: `tests/test_i18n_build.py`

**Interfaces:**
- Consumes: `i18n.resolve` (Task 3b), `i18n.runtime_dict` (Task 8), `i18n.languages` / `base_language` (Task 1).
- Produces: `i18n.portal_values(doc, surface, values)`, `i18n.portal_runtime(cfg, surface, data_dir)`.

- [ ] **Step 1: Write the failing test for the portal strings shape**

```python
class TestPortalStrings(unittest.TestCase):
    def test_portal_block_covers_both_surfaces(self):
        doc = i18n.load("en", DATA)
        self.assertEqual(sorted(doc["portal"]), ["home", "login"])

    def test_logout_messages_are_seven(self):
        """PAN-OS bakes the index into the generated logout.esp -- see
        fixtures/logout-suffix.html:26, which reads logout_text_array[ 0 ].
        The page cannot know which message will be shown, so every language
        must supply all seven, in the same order."""
        for f in sorted((DATA / "strings").glob("*.json")):
            doc = i18n.load(f.stem, DATA)
            self.assertEqual(len(doc["portal"]["home"]["logoutMessages"]), 7, f.stem)

    def test_portal_values_are_resolved(self):
        doc = {"portal": {"login": {"signIn": "Sign in for {{COMPANY}}"}}}
        v = i18n.portal_values(doc, "login", {"COMPANY": "Example Corp"})
        self.assertEqual(v["T_SIGNIN"], "Sign in for Example Corp")
```

- [ ] **Step 2: Run it**

Run: `uv run pytest -q tests/test_i18n.py -k PortalStrings`
Expected: FAIL — `KeyError: 'portal'`

- [ ] **Step 3: Add the `portal` block to `en.json`**

Copy every string **verbatim** from the shells and from `login.html`'s
`FOOT_SCRIPT`. The `note` is the two halves either side of the contact anchor,
the same pattern the block pages use for `contactAlt`.

```json
  "portal": {
    "login": {
      "signIn": "Sign in",
      "getSoftware": "Get Agent Software",
      "glossSignIn": "Use your company account to sign in.",
      "glossSoftware": "Download the agent for your operating system, then sign in from the app.",
      "download": "Download",
      "otherPlatforms": "Other platforms",
      "note": ["Need help? Contact ", "."],
      "downloadFor": "Download for ",
      "chooseDownload": "Choose your download",
      "macos": "macOS",
      "windows": "Windows ",
      "bit64": "64-bit",
      "bit32": "32-bit",
      "formUser": "Username",
      "formPassword": "Password",
      "formNewPassword": "New Password",
      "formConfirmPassword": "confirm New Password",
      "formSubmit": "Log In"
    },
    "home": {
      "logoutMessages": ["...", "...", "...", "...", "...", "...", "..."]
    }
  }
```

The seven `logoutMessages` move here verbatim from `_defaults.json`'s
`logoutMessages` array. Leave that config key in place — Task 7's
`config_strings` mechanism lets a customer override and translate it.

The five `form*` keys are **PAN-OS's own strings**, transcribed from
`fixtures/pan_form-login.html`. They are in the strings file because we swap
them at runtime, not because we author them; keep them byte-identical to what
PAN-OS emits so a diff against a future capture is meaningful.

- [ ] **Step 4: Implement `portal_values`**

```python
# Portal copy lives in the SHELLS, identically in all seven, rather than in the
# page templates -- the reverse of the block-page family, where the shells carry
# no copy at all. That is a property of this family's split: PAN-OS fixes the
# file shape (page template) and the theme decides decoration (shell), and the
# words are decoration.
PORTAL_SLOTS = {
    "login": ("signIn", "getSoftware", "glossSignIn", "glossSoftware", "download", "otherPlatforms"),
    "home": (),
}


def portal_values(doc: Mapping[str, Any], surface: str, values: Mapping[str, object]) -> dict[str, str]:
    """The {{T_*}} values one portal import needs."""
    block = doc.get("portal", {})
    if surface not in block:
        raise BuildError(f"strings document has no portal entry for '{surface}'")
    s = resolve(block[surface], values)
    out = {f"T_{k.upper()}": s[k] for k in PORTAL_SLOTS[surface]}
    if surface == "login":
        out["T_NOTE1"], out["T_NOTE2"] = s["note"][0], s["note"][1]
    return out
```

- [ ] **Step 5: Placeholder the seven shells**

In each of `templates/portal/shells/*.html`, inside `<!--@BODY-->`, keeping every
byte of markup identical:

```html
<div id="heading"><span class="pn">{{PORTAL_NAME}}</span><span class="pl">{{T_SIGNIN}}</span><span class="ps">{{T_GETSOFTWARE}}</span></div>
<p class="gloss"><span class="pl">{{T_GLOSSSIGNIN}}</span><span class="ps">{{T_GLOSSSOFTWARE}}</span></p>
...
<a class="dlmain" id="dlmain">...<span id="dllab">{{T_DOWNLOAD}}</span></a>
<button class="dlcar" id="dlcar" type="button" aria-expanded="false" aria-haspopup="true" aria-label="{{T_OTHERPLATFORMS}}">...</button>
...
<p class="note">{{T_NOTE1}}<a id="rep" href="{{CONTACT_HREF}}">{{CONTACT_NAME}}</a>{{T_NOTE2}}</p>
```

Wire them in `portal/page.py::_values`, after `values["PORTAL_NAME"] = ...`:

```python
    # Copy, resolved against the values above -- a portal string may carry
    # {{COMPANY}} just as a block-page string may, and substitute() will not
    # rescan its own replacement.
    strings = i18n.load(i18n.base_language(cfg), data_dir / "strings")
    values.update(i18n.portal_values(strings, page, values))
```

`_values` does not currently receive `page` or `data_dir`. Add both parameters
and pass them from `build_portal_page`, which has `template_dir` — `data_dir` is
`template_dir.parent`.

- [ ] **Step 6: Verify byte-identity**

Run: `uv run panos-response-pages build && uv run pytest -q tests/test_i18n_build.py`
Expected: PASS. The portal imports are in the snapshot too.

- [ ] **Step 7: Commit**

```bash
git add src/panos_response_pages/data/templates/portal src/panos_response_pages/portal/page.py \
        src/panos_response_pages/i18n.py src/panos_response_pages/data/strings/en.json tests/test_i18n.py
git commit -m "Move portal copy into the strings files"
```

- [ ] **Step 8: Write the failing test for the login runtime**

```python
class TestPortalRuntime(unittest.TestCase):
    def test_login_import_carries_no_raw_less_than(self):
        """portal/validate.py:85 refuses a '<' NOT followed by a tag-ish
        character -- the observed failure is that <pan_form/> silently stops
        being substituted and the login form is lost entirely.

        Asserted with the module's own regex rather than a plain `"<" not in
        text`: the file is HTML and full of legitimate '<'. json.dumps does not
        escape '<', so the emitted dictionary is where one would arrive from.
        """
        from panos_response_pages.portal.validate import _RAW_LT

        out, _ = built_with_languages(("en", "de"))
        for shell in ("assist", "beacon", "glass"):
            text = (out / f"deploy/{shell}/prisma-blue/portal/login.html").read_text(encoding="utf-8")
            self.assertEqual([m.group(0) for m in _RAW_LT.finditer(text)], [], shell)

    def test_login_import_still_validates(self):
        from panos_response_pages.portal.validate import validate_portal

        out, _ = built_with_languages(("en", "de"))
        for shell in ("assist", "beacon", "glass"):
            for surface in ("login", "home"):
                text = (out / f"deploy/{shell}/prisma-blue/portal/{surface}.html").read_text(encoding="utf-8")
                _size, errors, _warn = validate_portal(text)
                self.assertEqual(errors, [], f"{shell}/{surface}: {errors}")

    def test_home_import_reassigns_the_logout_array(self):
        """fixtures/logout-suffix.html:26 reads logout_text_array inside
        $(document).ready; HEAD_SCRIPT is synchronous in <head> and therefore
        runs first. The reassignment is what makes German logout messages work."""
        out, _ = built_with_languages(("en", "de"))
        text = (out / "deploy/glass/prisma-blue/portal/home.html").read_text(encoding="utf-8")
        self.assertRegex(text, r"logout_text_array\s*=\s*\w+\.lm", "no reassignment from the language dict")
```

- [ ] **Step 9: Implement `portal_runtime` and emit it**

```python
def portal_runtime(cfg: Mapping[str, Any], surface: str, data_dir: pathlib.Path) -> str:
    """The per-import language dictionary, as a JS object literal.

    '<' is escaped rather than left to json.dumps: portal/validate.py refuses a
    raw '<' anywhere in an import, because the observed failure is that
    <pan_form/> silently stops being substituted and the login form is lost.
    """
    base = base_language(cfg)
    out: dict[str, Any] = {}
    for lang in languages(cfg):
        if lang == base:
            continue
        doc = load(lang, data_dir)
        s = doc["portal"][surface]
        conf = config_strings(cfg, doc, lang)
        if surface == "home":
            # A customer may have rewritten the logout messages, in which case
            # their translation of them wins -- same precedence as every other
            # customer-authored string.
            out[lang] = {"lm": list(conf.get("logoutMessages", s["logoutMessages"]))}
        else:
            out[lang] = resolve(dict(s), {})
    return json.dumps(out, separators=(",", ":"), ensure_ascii=False).replace("<", "\\u003c")
```

The `home` runtime goes at the end of `HEAD_SCRIPT`, which already exists and is
already synchronous in `<head>`:

```js
(function(){var T=<dict>,L=navigator.languages||[navigator.language||''],i,k;
for(i=0;i<L.length;i++){k=L[i].slice(0,2).toLowerCase();if(k=='<base>')break;
if(T[k]){logout_text_array=T[k].lm;document.documentElement.lang=k;break}}})();
```

Note `i<L.length` is a **raw `<` and is forbidden here**. Use the same
`[].forEach.call` / `.some()` shape the rest of this family already uses for
exactly this reason (`login.html:48`, `:110`). Write it as:

```js
(function(){var T=<dict>,L=navigator.languages||[navigator.language||''];
L.some(function(x){var k=x.slice(0,2).toLowerCase();
if(k=='<base>'){return true}
if(T[k]){logout_text_array=T[k].lm;document.documentElement.lang=k;return true}
return false})})();
```

The `login` runtime goes at the **start** of `FOOT_SCRIPT`, because it needs the
parsed body and the substituted form. It publishes the selected dictionary on a
uniquely named global so the download block below it can read the strings it
needs:

```js
(function(){var T=<dict>,L=navigator.languages||[navigator.language||''],D=document;
L.some(function(x){var k=x.slice(0,2).toLowerCase();
if(k=='<base>'){return true}
if(!T[k]){return false}
var t=window.__gpT=T[k];D.documentElement.lang=k;
var Q=function(s){return D.querySelector(s)},S=function(s,v){var e=Q(s);if(e&&v){e.textContent=v}};
S('#heading .pl',t.signIn);S('#heading .ps',t.getSoftware);
S('.gloss .pl',t.glossSignIn);S('.gloss .ps',t.glossSoftware);
S('#dllab',t.download);
var c=Q('#dlcar');if(c){c.setAttribute('aria-label',t.otherPlatforms)}
var n=Q('.note');if(n&&n.childNodes.length>2){n.childNodes[0].nodeValue=t.note[0];n.childNodes[2].nodeValue=t.note[1]}
var ph=function(s,v){var e=Q(s);if(e&&v){e.placeholder=v}};
ph('#user',t.formUser);ph('#passwd',t.formPassword);
ph('#new_passwd',t.formNewPassword);ph('#confirm_new_passwd',t.formConfirmPassword);
var b=Q('#submit');if(b&&t.formSubmit){b.value=t.formSubmit}
return true})})();
```

`.pl`/`.ps` are **scoped** to `#heading` and `.gloss`: both classes appear in
both elements, and an unscoped selector would swap the wrong one.

The last five swaps reach **PAN-OS's own injected form**. Every one is guarded,
so a release that renames an id leaves PAN-OS's English wording rather than
breaking the page — the same degradation the download block already relies on.

- [ ] **Step 10: Translate the download button's JS literals**

In `login.html`'s existing download block, read the published dictionary with an
English fallback so a no-match load is byte-for-byte the behaviour it has today:

```js
var T=window.__gpT||{};
a.textContent=mac?(T.macos||'macOS'):win?(T.windows||'Windows ')+(w64?(T.bit64||'64-bit'):(T.bit32||'32-bit')):(a.textContent||'').trim();
...
lab.textContent=(T.downloadFor||'Download for ')+pick.textContent;
...
lab.textContent=T.chooseDownload||'Choose your download';
```

- [ ] **Step 11: Author the German portal block in `de.json`**

Seven logout messages plus the login block. Note two translator constraints:

- `note` must keep the contact link **between** its two halves.
- `windows` keeps its trailing space — it is concatenated with the bit-ness.
- The `form*` strings replace PAN-OS's: `Benutzername`, `Kennwort`, `Anmelden`.

- [ ] **Step 12: Verify against the real ceiling**

```bash
uv run panos-response-pages build
uv run panos-response-pages validate out/deploy
find out/deploy -name 'login.html' -exec wc -c {} + | grep -v total | sort -n | tail -3
```

Expected: `0 would fail`. `beacon`/`login` is the binding import — it starts at
12,119 B and German should land it near 12,800 B, comfortably inside the
15,000 B warn line. **If any import exceeds 15,000 B, stop**: that is the number
`portal/validate.py` warns at, and 16,170 B is where PAN-OS refuses the import
outright.

- [ ] **Step 13: Look at the spliced preview**

The portal preview splices the captured PAN-OS prefix around the import, so it
renders as the firewall would serve it:

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --disable-gpu \
  --lang=de-DE --force-device-scale-factor=2 --window-size=1100,900 \
  --screenshot=/tmp/portal-de.png "file://$PWD/out/preview/glass/prisma-blue/portal/login.html"
```

Check: heading, gloss, note, the download button **and PAN-OS's own form
placeholders** are all German. Then load it with `--lang=fr-FR` and confirm
everything falls back to English rather than half-swapping.

- [ ] **Step 13b: Decide what `i18n: false` means for the portal**

`nyan`'s portal login is 11,438 B with 3,562 B of headroom — it would fit German
comfortably. So the theme flag from Task 11 poses a question the block pages
never raised: does `i18n: false` disable a theme's *portal* imports too?

**Take the flag at theme level: it disables both families.** One flag with one
meaning is easier to explain, to document and to test than "base-language block
pages, multilingual portal", and a style that is half-translated across its own
two families is a worse artefact than one that is consistently English. `nyan` is
a novelty style and this costs it nothing real.

Assert it, so the choice is recorded rather than incidental:

```python
    def test_opted_out_theme_ships_no_portal_runtime_either(self):
        out, _ = built_with_languages(("en", "de"))
        text = (out / "deploy/nyan/prisma-blue/portal/login.html").read_text(encoding="utf-8")
        self.assertNotIn("navigator.languages", text, "i18n:false is theme-level, both families")
```

- [ ] **Step 14: Commit**

```bash
git add src/panos_response_pages/i18n.py src/panos_response_pages/portal \
        src/panos_response_pages/data/templates/portal src/panos_response_pages/data/strings tests
git commit -m "Translate the GlobalProtect portal imports"
```

---

## Task 13: Documentation

Nothing in this task is committed by an agent. Write the files, then stop and say they are ready for review.

- [ ] **Step 1: `docs/customising.md`** — a Languages section: the two config keys, the `translations` block, what a customer must do to add a language, and the byte budget with the **measured** German numbers from Task 9.
- [ ] **Step 2: `docs/architecture/url-filtering-response-pages.md`** — the runtime contract, the selector table, and the positional `facts` coupling with its guard.
- [ ] **Step 3: `CHANGELOG.md`** — under `## [Unreleased]`. Lead with the fact that `languages: ["en"]` is byte-identical, because that is what most readers need to know.
- [ ] **Step 4: `docs/specs/2026-08-05-multi-language-response-pages.md`** — replace the estimated 1.25 expansion factor and the projected budget table with the measured values.
- [ ] **Step 5: Tell the user which files are staged and which await review.**

---

## Verification

- [ ] `uv run pytest -q` — whole suite
- [ ] `uv run panos-response-pages build` — `no page warns or fails`
- [ ] `uv run panos-response-pages validate out/deploy` — `0 would fail`
- [ ] Byte-identity holds with `languages: ["en"]`
- [ ] With `["en","de"]`: every non-nyan style builds, nyan carries no runtime, sizes recorded
- [ ] German rendered and read in `banner` and `record`, both schemes, compound nouns not clipped
- [ ] Live: `logout_text_array` timing on a firewall
