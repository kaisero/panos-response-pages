# Configurable Contact Link Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a customer point every "Report to IT" action at an `https://` ticket system instead of a `mailto:`, by setting `supportUrl` instead of `supportEmail` in their config.

**Architecture:** A new `contact.py` module owns one question — *where does a user who needs a human get sent?* — and answers it with a mode (`email` or `url`) resolved from mutually exclusive config keys. The nine page templates stop hardcoding `mailto:` and instead reference `{{CONTACT_*}}` tokens. Each page moves its pre-filled mailto and its email-only fallback paragraph into their own `<!--@CONTACT_MAILTO-->` / `<!--@CONTACT_ALT-->` sections; `page.py` resolves those two first, folds the resulting contact values into the existing substitution dict, and the single existing pass over `parts` then resolves everything. The mailto-specific runtime href rebuild becomes conditional. The per-page incident metadata (`data-subject`, `data-intro`, `data-prompt`) is deliberately retained in URL mode: it is the structured payload a future ServiceNow/Jira adapter will turn into pre-filled ticket fields.

**Tech Stack:** Python 3.11+, stdlib only (no new dependencies). Typer CLI, pytest + unittest-style test classes, `uv` for running.

## Global Constraints

- **No new runtime dependencies.** `pyproject.toml` runtime deps stay `typer`, `rich`, `pyyaml`.
- **`substitute()` raises on any key it does not know, not merely on keys left unresolved** (`templates.py:37-44`). Every `{{CONTACT_*}}` token introduced into a page section must therefore be present in the values dict used for the pass over `parts` — see Task 4 Step 4. This is the single most important constraint in this plan; an earlier draft got it wrong and no page built at all.
- **17999-byte hard ceiling per page** (`validate.MAX_BYTES`). Headroom is ample: the largest block page today is 15558 B (`nyan`/`url-block-page`) and URL mode is *smaller* than email mode (it drops `data-to`, the fallback paragraph, and the ~430 B rebuild script). Portal max is 12110 B against a 16170 B ceiling. Budget is not a risk here; do not spend time on it.
- **Email mode must stay byte-identical.** The single-pass design in Task 4 has been verified to reproduce today's output byte for byte for `url-block-page`/assist. Any deviation is a bug in the implementation, not an acceptable difference.
- **Copy lives in templates, not Python.** `tests/test_copy.py` lints template copy; do not move page wording into `.py` files.
- **Imports in `tests/test_contact.py` go in the block at the top of the file, never appended at the bottom.** When a later task needs a new import, *edit the existing block*. `pyproject.toml` selects ruff `E`, `F` and `I`, and `.pre-commit-config.yaml` runs `ruff check --fix` on staged Python. An appended import trips `E402` (module level import not at top of file), which `--fix` cannot repair, so the commit fails. Equally, do **not** pre-declare imports a task does not yet use: that trips `F401`, which `--fix` *can* repair — by deleting the import, silently breaking the next task.
- **Commit message style:** short imperative subject, capitalised, no trailing period, ≤ 60 chars. No `feat:`/`fix:`/`docs:` prefixes, no emoji, no AI/tool attribution of any kind.
- **Never `git add` or `git commit` anything under `docs/`, `README.md`, `CHANGELOG.md`, or `SECURITY.md`.** Write those files, then stop and tell the user they are ready for manual review. Committing source, templates, config data and tests is fine. `.claude/skills/**` is source, not docs — commit it.

## Design Decisions (settled — do not re-litigate)

1. **`supportEmail` and `supportUrl` are mutually exclusive.** Both present → `BuildError` naming both keys. Neither present → `BuildError`. An empty string counts as absent, which is the documented way to turn one off, because JSON has no comments.
2. **`_defaults.json` ships `supportEmail`, and configs are merged, not replaced.** So a customer file adding `supportUrl` must also set `"supportEmail": ""`. The error message and the docs both have to say this or the first user hits a wall on their first attempt.
3. **`supportUrl` must be an absolute `https://` URL.** Same rule and rationale as `redirect.py:196-199`: the page is served *as* the blocked site, so a relative path resolves against the host the user was refused.
4. **The portal follows `supportUrl` too.** Without this, a `supportUrl`-only config does not crash — it silently ships `<a href="mailto:"></a>` and a logout message reading `Contact .`, which is worse than a crash. Task 6 closes that window; it is open between Tasks 2 and 6 and that is accepted.
5. **Safe-search keeps its sentence and swaps the link text.** In URL mode: `Still blocked after turning SafeSearch on? Email <a …>IT support</a> and IT will take a look.` **Known wart, accepted by the user:** "Email" is inaccurate when the link opens a ticket form. Recorded so a later reader does not mistake it for an oversight; the fix is a second copy variant, deferred.
5a. **Both guards identify the contact anchor with a shared `_IS_REP` regex**, not a substring test. `re.compile(r'(?<![\w-])id\s*=\s*"rep"')` — anchored so that only the real `id` attribute counts. `'id="rep"' in tag` would also accept an attribute whose name merely *ends* in `id`, which is a wider hole than either guard intends. Defined once and used by `validate.py` and `portal/validate.py` alike.
6. **The `href="http` self-containment guard becomes structural, not config-driven.** `validate()` is also called by `cli.py:271` on arbitrary built files with no config in hand, so the rule cannot depend on knowing `supportUrl`. Instead: `https://` is permitted **only** on an anchor carrying `id="rep"`; `http://` never. The portal guard gets the *same* `id="rep"` requirement, which is why Task 6 adds that id to the portal note.
7. **The URL-mode link label is a config key, `supportLabel`, defaulting to `IT support`.** Ruled by the owner after Task 1's review flagged the original hardcoded constant against the "copy lives in templates" constraint. Neither a template nor a hardcode: a ticket queue has a name — "Service Desk", "Helpdesk" — and a page that calls it something else sends the user somewhere they cannot find. The default lives in `contact.py` as well as `_defaults.json`, so a config assembled without the defaults document still renders an anchor with text. Delivered by Task 1a; declared and documented by Task 7.
8. **`data-subject` / `data-intro` / `data-prompt` survive in URL mode; `data-to` does not.** Those three are the documented seam for a future ticket adapter. `data-to` is an email address and has no meaning in URL mode.

## File Structure

**Created:**
- `src/panos_response_pages/contact.py` — mode resolution, config validation, per-mode token values. The single place that knows a `mailto:` from an `https:`.
- `tests/test_contact.py` — unit tests for the module plus integration tests over built pages in both modes.

**Modified:**
- `src/panos_response_pages/page.py` — `contact.check()`, contact token values, `email_mode` passed to `category_js`.
- `src/panos_response_pages/scripts.py:25-74` — `category_js()` gains `email_mode`; the `#rep` rebuild becomes conditional.
- `src/panos_response_pages/validate.py:66-78` — structural https rule.
- `src/panos_response_pages/portal/page.py:210-250` — contact tokens for the portal family.
- `src/panos_response_pages/portal/validate.py:166-168` — same structural rule.
- `src/panos_response_pages/data/templates/pages/*.html` — all nine.
- `src/panos_response_pages/data/templates/portal/shells/*.html` — all seven.
- `src/panos_response_pages/data/config/_defaults.json` — `supportUrl` key and docs; `logoutMessages` token swap.
- `tests/test_layout_details.py` (`TestMailto`), `tests/test_portal_config.py`.
- `.claude/skills/add-response-page/SKILL.md` — the page-authoring template it teaches.
- `docs/customising.md`, `docs/portal.md`, `docs/copy-rules.md`, `docs/architecture/url-filtering-response-pages.md`, `SECURITY.md`, `CHANGELOG.md` — write only, never commit.

## Task order, and why

`scripts.py` (Task 3) is changed **before** the templates (Task 4). The rebuild at `scripts.py:69` assigns `a.href` unconditionally; once a template drops `data-to` but the rebuild still runs, the page ships `mailto:null?subject=…` and destroys the configured href on load. Doing the templates first would leave the tree in that broken state between two commits.

---

### Task 1: The `contact` module

Pure config logic, no templates and no filesystem. Everything downstream depends on the names defined here.

**Files:**
- Create: `src/panos_response_pages/contact.py`
- Create: `tests/test_contact.py`

**Interfaces:**
- Consumes: `panos_response_pages.errors.BuildError`
- Produces:
  - `contact.EMAIL: str` (`"email"`), `contact.URL: str` (`"url"`)
  - `contact.mode(cfg: Mapping[str, Any]) -> str` — `EMAIL` or `URL`; raises `BuildError` on both-set or neither-set
  - `contact.check(cfg: Mapping[str, Any]) -> None` — full validation; raises `BuildError`
  - `contact.href(cfg: Mapping[str, Any], mailto: str) -> str` — the resolved `href`, given the page's own mailto string
  - `contact.name(cfg: Mapping[str, Any]) -> str` — link text: the address, or `"IT support"`
  - `contact.to_attr(cfg: Mapping[str, Any]) -> str` — `' data-to="…"'` or `""`
  - `contact.email(cfg: Mapping[str, Any]) -> str` — the address, or `""` in URL mode

- [ ] **Step 1: Write the test file**

Create `tests/test_contact.py`. Every import below is used by the module-level helpers or by this task's tests, so ruff `F401` stays quiet. Exactly one later task needs a new import (Task 4 needs `MAX_BYTES`) and it edits this block in place rather than appending — see Global Constraints.

```python
"""Where a response page sends a user who needs a human.

Two modes, and the config picks exactly one. Every assertion here covers a
config mistake that would otherwise surface as a raw KeyError, a page that
silently names nobody, or an href the firewall's own policy would refuse.
"""

import pathlib
import unittest

import pytest
from _paths import DATA

from panos_response_pages import contact
from panos_response_pages.builder import load_themes
from panos_response_pages.config import load_config
from panos_response_pages.emit import strip_output
from panos_response_pages.errors import BuildError
from panos_response_pages.page import build_page
from panos_response_pages.palettes import load_palette
from panos_response_pages.portal.page import build_portal_page
from panos_response_pages.validate import PAGE_TOKENS

THEMES = load_themes(DATA)
PALETTE = load_palette("cyber-orange", DATA / "palettes")
TEMPLATES: pathlib.Path = DATA / "templates"
PAGES = sorted(PAGE_TOKENS)

# What a customer file must contain to switch modes. supportEmail has to be
# blanked explicitly: _defaults.json ships one, and the two documents are
# merged rather than replaced, so adding supportUrl alone sets both.
URL_CFG_KEYS = {"supportEmail": "", "supportUrl": "https://tickets.example.com/new"}


def shipped(**over):
    """The shipped config, with contact keys overridden."""
    cfg = load_config("contoso", DATA / "config")
    cfg.update(over)
    return cfg


def render(cfg, page="url-block-page", theme=None):
    return strip_output(build_page(page, theme or THEMES[0], cfg, PALETTE, False, TEMPLATES))


def portal(cfg, page="login", theme=None):
    return build_portal_page(page, theme or THEMES[0], cfg, PALETTE, preview=False, template_dir=TEMPLATES)


def rep_anchor(html):
    """The contact anchor, as source.

    Bounded by `">` rather than by `>`, and that is the whole subtlety: the
    email-mode href embeds literal PAN-OS tokens, so the first `>` after
    `href="` is the one closing <user/> -- about 60 characters into a 250
    character href, before <category/> and <url/> ever appear. A slice taken
    there cannot contain what the assertions look for, so they fail whatever
    the implementation does. The href value is percent-encoded and carries no
    bare quote, so `">` occurs exactly once: at the end of the attribute.
    """
    i = html.index('id="rep"')
    return html[html.rindex("<a ", 0, i) : html.index('">', html.index('href="', i)) + 2]


@pytest.mark.unit
class TestMode(unittest.TestCase):
    def test_email_only_is_email_mode(self):
        assert contact.mode({"supportEmail": "it@example.com"}) == contact.EMAIL

    def test_url_only_is_url_mode(self):
        assert contact.mode({"supportUrl": "https://tickets.example.com/new"}) == contact.URL

    def test_both_set_is_an_error_naming_both_keys(self):
        with pytest.raises(BuildError) as err:
            contact.mode({"supportEmail": "it@example.com", "supportUrl": "https://t.example.com/"})
        message = str(err.value)
        assert "supportEmail" in message
        assert "supportUrl" in message

    def test_both_set_error_explains_the_merge(self):
        """The first person to hit this will have added supportUrl to a customer
        file and set nothing else. The message has to say why that is not enough."""
        with pytest.raises(BuildError) as err:
            contact.mode({"supportEmail": "it@example.com", "supportUrl": "https://t.example.com/"})
        assert "_defaults.json" in str(err.value)

    def test_neither_set_is_an_error(self):
        with pytest.raises(BuildError) as err:
            contact.mode({})
        assert "supportEmail" in str(err.value)

    def test_empty_string_counts_as_unset(self):
        """JSON has no comments, so blanking a value is how a key is turned off."""
        assert contact.mode({"supportEmail": "it@example.com", "supportUrl": ""}) == contact.EMAIL
        assert contact.mode({"supportEmail": "", "supportUrl": "https://t.example.com/"}) == contact.URL


@pytest.mark.unit
class TestCheck(unittest.TestCase):
    def test_https_url_passes(self):
        contact.check({"supportEmail": "", "supportUrl": "https://tickets.example.com/new"})

    def test_http_url_is_refused(self):
        with pytest.raises(BuildError) as err:
            contact.check({"supportEmail": "", "supportUrl": "http://tickets.example.com/new"})
        assert "https://" in str(err.value)

    def test_relative_url_is_refused(self):
        """The page is served AS the blocked site, so a relative path resolves there."""
        with pytest.raises(BuildError) as err:
            contact.check({"supportEmail": "", "supportUrl": "/servicedesk/new"})
        assert "https://" in str(err.value)

    def test_email_mode_needs_an_at_sign(self):
        with pytest.raises(BuildError) as err:
            contact.check({"supportEmail": "servicedesk"})
        assert "supportEmail" in str(err.value)


@pytest.mark.unit
class TestValues(unittest.TestCase):
    EMAIL_CFG = {"supportEmail": "it@example.com"}
    URL_CFG = {"supportEmail": "", "supportUrl": "https://tickets.example.com/new"}

    def test_href_is_the_page_mailto_in_email_mode(self):
        assert contact.href(self.EMAIL_CFG, "mailto:it@example.com?subject=X") == "mailto:it@example.com?subject=X"

    def test_href_is_the_url_in_url_mode(self):
        assert contact.href(self.URL_CFG, "mailto:ignored") == "https://tickets.example.com/new"

    def test_name_is_the_address_in_email_mode(self):
        assert contact.name(self.EMAIL_CFG) == "it@example.com"

    def test_name_is_a_fixed_label_in_url_mode(self):
        assert contact.name(self.URL_CFG) == "IT support"

    def test_data_to_attribute_only_exists_in_email_mode(self):
        assert contact.to_attr(self.EMAIL_CFG) == ' data-to="it@example.com"'
        assert contact.to_attr(self.URL_CFG) == ""

    def test_email_is_empty_in_url_mode(self):
        assert contact.email(self.URL_CFG) == ""
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_contact.py -v`
Expected: collection error — `ModuleNotFoundError: No module named 'panos_response_pages.contact'`

- [ ] **Step 3: Write the module**

Create `src/panos_response_pages/contact.py`:

```python
"""Where a response page sends a user who needs a human.

Two modes, and a config picks exactly one:

* `supportEmail` -- a `mailto:` the browser hands to a mail client. The page
  pre-fills subject and body, so IT receives the incident already described.
* `supportUrl` -- an absolute https link to a ticket system.

They are mutually exclusive rather than ranked. A config carrying both has an
author who believes one of them is doing something, and guessing which would
mean shipping the other one's wording to users who will never see it.

The URL mode loses the pre-filled body: an `<a href>` carries no payload the way
a mailto does. That is accepted. What is NOT dropped is the metadata the body was
built from -- each page still declares `data-subject`, `data-intro` and
`data-prompt`. A ticket-system adapter (ServiceNow, Jira Service Management) is
the reason: those fields are exactly what such a system wants as
`short_description` and `description`, and an adapter added later reads them from
the anchor rather than needing all nine templates edited again.

Why `supportUrl` must be absolute https, and never a relative path: a response
page is served AS the blocked site, so its origin is whatever the user was
refused. A relative link resolves against that host, and an http link is
strippable in transit on a page whose whole job is to be trusted.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from panos_response_pages.errors import BuildError

EMAIL = "email"
URL = "url"

# What the link is called when there is no address to print. Not per-customer
# config: it is one string, and a customer who wants different wording is
# describing a copy change, not a configuration.
URL_LINK_TEXT = "IT support"


def _set(cfg: Mapping[str, Any], key: str) -> str:
    """The value of `key`, treating an empty string as absent.

    JSON has no comments, so the documented way to disable one of these keys is
    to blank it. That has to mean the same thing as deleting it, or "turn one
    off" would be advice that does not work.
    """
    return str(cfg.get(key) or "").strip()


def mode(cfg: Mapping[str, Any]) -> str:
    email, url = _set(cfg, "supportEmail"), _set(cfg, "supportUrl")
    if email and url:
        raise BuildError(
            "config sets both supportEmail and supportUrl; they are mutually exclusive. "
            "Blank the one you are not using and build again. Note that _defaults.json "
            'ships a supportEmail, so a customer file adding supportUrl must also set '
            '"supportEmail": "" -- the two documents are merged, not replaced.'
        )
    if url:
        return URL
    if email:
        return EMAIL
    raise BuildError("config sets neither supportEmail nor supportUrl; every page needs a way to reach IT")


def check(cfg: Mapping[str, Any]) -> None:
    """Validate the contact configuration. Raises BuildError, never returns a value."""
    if mode(cfg) == URL:
        url = _set(cfg, "supportUrl")
        if not url.startswith("https://"):
            raise BuildError(
                f"supportUrl is {url!r}; it must be an absolute https:// URL. A response page is "
                "served as the blocked site, so a relative path resolves against that host."
            )
    elif "@" not in _set(cfg, "supportEmail"):
        raise BuildError(f"supportEmail is {_set(cfg, 'supportEmail')!r}; it must be an email address")


def href(cfg: Mapping[str, Any], mailto: str) -> str:
    """The `href` the contact anchor carries.

    `mailto` is the page's own pre-filled mailto string, which only the page
    template can supply -- the subject and body are page-specific copy.
    """
    return _set(cfg, "supportUrl") if mode(cfg) == URL else mailto


def name(cfg: Mapping[str, Any]) -> str:
    """Human-facing link text, for the places that print the contact inline."""
    return URL_LINK_TEXT if mode(cfg) == URL else _set(cfg, "supportEmail")


def to_attr(cfg: Mapping[str, Any]) -> str:
    """The `data-to` attribute, including its leading space, or nothing.

    Only the mailto rebuild in scripts.py reads it, and that rebuild does not
    run in URL mode -- so in URL mode this would be bytes with no reader.
    """
    return f' data-to="{_set(cfg, "supportEmail")}"' if mode(cfg) == EMAIL else ""


def email(cfg: Mapping[str, Any]) -> str:
    """The address, or an empty string in URL mode.

    `{{SUPPORT_EMAIL}}` still has to resolve to something in URL mode: it appears
    in sections URL mode discards, and substitute() raises on an unknown key
    whether or not the text survives.
    """
    return _set(cfg, "supportEmail")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_contact.py -v`
Expected: PASS, 16 tests

- [ ] **Step 5: Run lint and typecheck**

Run: `uv run ruff check src/panos_response_pages/contact.py tests/test_contact.py && uv run ruff format --check src/panos_response_pages/contact.py tests/test_contact.py && uv run mypy src/panos_response_pages/contact.py`
Expected: no findings. Every import is consumed by a module-level helper (`build_portal_page` by `portal()`, `strip_output` and `build_page` by `render()`, `PAGE_TOKENS` by `PAGES`), so `F401` does not fire even though some helpers have no caller until later tasks. If ruff reports `F401` anyway, do not add `# noqa` — find which helper is missing and add it.

- [ ] **Step 6: Commit**

```bash
git add src/panos_response_pages/contact.py tests/test_contact.py
git commit -m "Add contact module resolving email or URL support target"
```

---

### Task 2: Fail the build on a contradictory config

**Files:**
- Modify: `src/panos_response_pages/page.py:51-61`
- Modify: `src/panos_response_pages/portal/page.py:214-217`
- Test: `tests/test_contact.py`

**Interfaces:**
- Consumes: `contact.check`, `contact.email`
- Produces: nothing new; `build_page()` and `build_portal_page()` keep their signatures

- [ ] **Step 1: Append the failing tests**

Append to `tests/test_contact.py` (no new imports):

```python
@pytest.mark.integration
class TestBuildRefusesBadConfig(unittest.TestCase):
    def test_both_keys_fails_the_build(self):
        cfg = shipped(supportUrl="https://tickets.example.com/new")
        with pytest.raises(BuildError) as err:
            build_page("url-block-page", THEMES[0], cfg, PALETTE, False, TEMPLATES)
        assert "mutually exclusive" in str(err.value)

    def test_http_url_fails_the_build(self):
        cfg = shipped(supportEmail="", supportUrl="http://tickets.example.com/new")
        with pytest.raises(BuildError) as err:
            build_page("url-block-page", THEMES[0], cfg, PALETTE, False, TEMPLATES)
        assert "https://" in str(err.value)

    def test_missing_both_fails_with_a_sentence_not_a_keyerror(self):
        cfg = shipped(supportEmail="")
        with pytest.raises(BuildError):
            build_page("url-block-page", THEMES[0], cfg, PALETTE, False, TEMPLATES)
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_contact.py::TestBuildRefusesBadConfig -v`
Expected: FAIL — `test_both_keys_fails_the_build` raises nothing (the build ignores `supportUrl`); the other two raise `KeyError` or the wrong message.

- [ ] **Step 3: Wire the check into `page.py`**

In `src/panos_response_pages/page.py`, change the existing import line to:

```python
from panos_response_pages import contact, redirect
```

Then replace lines 51-61 — the `base` dict — with:

```python
    # Refused here rather than at first use: a contradictory contact config
    # otherwise surfaces as a KeyError from inside substitution, naming a
    # template token instead of the config key the author got wrong.
    contact.check(cfg)
    base = {
        "COMPANY": cfg["company"],
        # Empty in URL mode. The token still has to resolve: it appears in
        # sections URL mode discards, and substitute() raises on an unknown key
        # whether or not the text survives.
        "SUPPORT_EMAIL": contact.email(cfg),
        "LOGO_SVG": cfg["logoSvg"],
        # The Continue/Override grant duration is administrator-configurable per
        # firewall (PAN-OS only defaults to 15 minutes), so the page must not
        # hardcode it -- that would assert a fact it cannot know.
        "CONTINUE_GRANT": cfg["continueGrantText"],
        "WARN_MARK": cfg["marks"]["warning"],
        "INFO_MARK": cfg["marks"]["info"],
    }
```

- [ ] **Step 4: Wire the check into `portal/page.py`**

Add `from panos_response_pages import contact` to the imports, then replace the `base` dict in `_values()` (lines 214-217) with:

```python
    contact.check(cfg)
    base = {
        "COMPANY": str(cfg["company"]),
        "SUPPORT_EMAIL": contact.email(cfg),
    }
```

- [ ] **Step 5: Run to verify they pass**

Run: `uv run pytest tests/test_contact.py -v`
Expected: PASS, 19 tests

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest`
Expected: PASS (baseline is 389 passed). The shipped configs set only `supportEmail`, so nothing else moves.

- [ ] **Step 7: Commit**

```bash
git add src/panos_response_pages/page.py src/panos_response_pages/portal/page.py tests/test_contact.py
git commit -m "Refuse a config that sets both or neither support target"
```

---

### Task 3: Stop the browser rewriting the href in URL mode

Done **before** the templates on purpose. `scripts.py:69` assigns `a.href` unconditionally; a template that has dropped `data-to` while this still runs ships `mailto:null?subject=…` and destroys the configured href on load.

**Files:**
- Modify: `src/panos_response_pages/scripts.py:25-74`
- Modify: `src/panos_response_pages/page.py:104-110`
- Test: `tests/test_contact.py`

**Interfaces:**
- Consumes: `contact.mode`, `contact.EMAIL`
- Produces: `category_js(categories, default_gloss, lock_copy, email_mode=True) -> str`

- [ ] **Step 1: Append the failing tests**

```python
@pytest.mark.integration
class TestRuntimeRewrite(unittest.TestCase):
    def test_email_mode_still_rebuilds_the_href(self):
        """The rebuild is what folds the fact table into the mail body."""
        assert "a.href='mailto:'" in render(shipped())

    def test_url_mode_does_not_rebuild_the_href(self):
        html = render(shipped(**URL_CFG_KEYS))
        assert "a.href=" not in html
        assert "getElementById('rep')" not in html

    def test_url_mode_still_fills_the_timestamp(self):
        """The rep block shares an IIFE with the clock; dropping one must not
        drop the other."""
        assert "getElementById('ts')" in render(shipped(**URL_CFG_KEYS))

    def test_url_mode_still_resolves_the_category(self):
        assert "getElementById('cat')" in render(shipped(**URL_CFG_KEYS))
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_contact.py::TestRuntimeRewrite -v`
Expected: FAIL on `test_url_mode_does_not_rebuild_the_href` — the rebuild is unconditional.

- [ ] **Step 3: Make the rebuild conditional in `scripts.py`**

Change the signature at `scripts.py:25` from:

```python
def category_js(categories: Mapping[str, Mapping[str, str]], default_gloss: str, lock_copy: bool) -> str:
```

to:

```python
def category_js(
    categories: Mapping[str, Mapping[str, str]],
    default_gloss: str,
    lock_copy: bool,
    email_mode: bool = True,
) -> str:
```

Add this paragraph to the existing docstring:

```
    email_mode drops the mailto rebuild entirely. It is not a size optimisation:
    the rebuild assigns a.href unconditionally, so leaving it in would overwrite
    a configured ticket URL the moment the page finished loading.
```

Then replace the `return (...)` block at lines 58-74 with:

```python
    # The mailto rebuild, and only in email mode. It exists to fold the page's
    # own fact table into the mail body, which is something an href cannot carry.
    report = (
        (
            "var a=document.getElementById('rep');"
            "if(a){var p=[];"
            "[].forEach.call(document.querySelectorAll('dl .f'),function(f){"
            "var k=f.querySelector('dt'),v=f.querySelector('dd');"
            "if(k&&v&&v.textContent.trim())p.push(k.textContent.trim()+': '+v.textContent.trim());});"
            "a.href='mailto:'+a.getAttribute('data-to')"
            "+'?subject='+encodeURIComponent(a.getAttribute('data-subject'))"
            "+'&body='+encodeURIComponent(a.getAttribute('data-intro')+'\\n\\n'"
            "+p.join('\\n')+'\\n\\n'+a.getAttribute('data-prompt')+'\\n');}"
        )
        if email_mode
        else ""
    )
    return (
        "<script>(function(){"
        + ("" if lock_copy else "var M=" + json.dumps(compact, separators=(",", ":")) + ";")
        + lookup
        + "var t=document.getElementById('ts');"
        "if(t)t.textContent=new Date().toLocaleString();"
        + report
        + "})();</script>"
    )
```

- [ ] **Step 4: Pass the flag from `page.py`**

Change the `category_js(...)` call at `page.py:105-109` to:

```python
            + category_js(
                eff["categories"],
                eff["defaultGloss"],
                lock_copy=parts.get("COPY_LOCK", "").strip() == "1" or 'id="cat"' not in parts["FACTS"],
                email_mode=contact.mode(cfg) == contact.EMAIL,
            )
```

- [ ] **Step 5: Run to verify they pass**

Run: `uv run pytest tests/test_contact.py -v`
Expected: PASS, 23 tests

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/panos_response_pages/scripts.py src/panos_response_pages/page.py tests/test_contact.py
git commit -m "Skip the mailto href rebuild when a ticket URL is configured"
```

---

### Task 4: The templating seam, across all nine pages

One task rather than nine: the templates are near-identical edits, and `TestMailto` in `tests/test_layout_details.py` globs *all* page templates, so it breaks the moment the first one changes and cannot be fixed incrementally.

**Files:**
- Modify: `src/panos_response_pages/page.py:62`
- Modify: all nine `src/panos_response_pages/data/templates/pages/*.html`
- Modify: `tests/test_layout_details.py` (`TestMailto`)
- Test: `tests/test_contact.py`

**Interfaces:**
- Consumes: `contact.href`, `contact.to_attr`, `contact.name`, `contact.mode`, `contact.EMAIL`
- Produces: four template tokens usable in any page section —
  - `{{CONTACT_HREF}}` — the resolved href
  - `{{CONTACT_TO}}` — `' data-to="…"'` or `''`
  - `{{CONTACT_ALT}}` — the email-only fallback paragraph, or `''`
  - `{{CONTACT_NAME}}` — the link text
  and two page sections read by `page.py`, never emitted directly —
  - `<!--@CONTACT_MAILTO-->` — the page's pre-filled mailto URL
  - `<!--@CONTACT_ALT-->` — the page's email-only fallback paragraph

**How the substitution works.** `substitute()` raises on any key it does not know, so the moment a section contains `{{CONTACT_HREF}}` it must be resolvable in the *same* pass that resolves `{{SUPPORT_EMAIL}}`. The two contact sections are therefore resolved against `base` first, their results folded into `base`, and the existing single pass over `parts` then handles everything. This has been verified to produce byte-identical email-mode output.

- [ ] **Step 1: Append the failing tests**

First add `MAX_BYTES` to the existing import at the top of `tests/test_contact.py` — edit the line in place, do not append a new import:

```python
from panos_response_pages.validate import MAX_BYTES, PAGE_TOKENS
```

Then append the test classes:

```python
@pytest.mark.integration
class TestContactSeam(unittest.TestCase):
    def test_email_mode_href_is_unchanged(self):
        anchor = rep_anchor(render(shipped()))
        assert 'href="mailto:servicedesk@example.com?subject=Blocked%20site%20report' in anchor
        assert "%0AAddress%3A%20<url/>" in anchor

    def test_email_mode_keeps_data_to(self):
        assert 'data-to="servicedesk@example.com"' in rep_anchor(render(shipped()))

    def test_email_mode_keeps_the_fallback_paragraph(self):
        html = render(shipped())
        assert "Or email" in html

    def test_url_mode_href_is_the_ticket_system(self):
        cfg = shipped(**URL_CFG_KEYS)
        assert 'href="https://tickets.example.com/new"' in rep_anchor(render(cfg))

    def test_url_mode_drops_data_to(self):
        assert "data-to" not in rep_anchor(render(shipped(**URL_CFG_KEYS)))

    def test_url_mode_keeps_the_incident_metadata(self):
        """The seam a ticket adapter will read. Dropping it would mean editing
        all nine templates again when that adapter arrives."""
        anchor = rep_anchor(render(shipped(**URL_CFG_KEYS)))
        assert 'data-subject="Blocked site report"' in anchor
        assert 'data-intro="Please review this block."' in anchor
        assert 'data-prompt="Why I need access:"' in anchor

    def test_url_mode_drops_the_fallback_paragraph(self):
        assert "Or email" not in render(shipped(**URL_CFG_KEYS))


@pytest.mark.integration
class TestEveryPageInBothModes(unittest.TestCase):
    def test_every_page_still_offers_a_contact_in_url_mode(self):
        for page in PAGES:
            html = render(shipped(**URL_CFG_KEYS), page=page)
            assert 'id="rep"' in html, f"{page} lost its contact link"
            assert 'href="https://tickets.example.com/new"' in html, page

    def test_no_page_carries_a_mailto_in_url_mode(self):
        for page in PAGES:
            assert "mailto:" not in render(shipped(**URL_CFG_KEYS), page=page), page

    def test_no_page_names_an_email_address_in_url_mode(self):
        for page in PAGES:
            assert "servicedesk@example.com" not in render(shipped(**URL_CFG_KEYS), page=page), page

    def test_no_page_has_an_unresolved_token_in_url_mode(self):
        for page in PAGES:
            assert "{{" not in render(shipped(**URL_CFG_KEYS), page=page), page

    def test_every_page_keeps_its_mailto_in_email_mode(self):
        for page in PAGES:
            assert 'href="mailto:servicedesk@example.com' in render(shipped(), page=page), page

    def test_both_modes_stay_under_the_byte_ceiling(self):
        for theme in THEMES:
            for page in PAGES:
                for cfg in (shipped(), shipped(**URL_CFG_KEYS)):
                    size = len(render(cfg, page=page, theme=theme).encode("utf-8"))
                    assert size <= MAX_BYTES, f"{theme['name']}/{page} is {size} B"

    def test_safe_search_names_the_link_rather_than_an_address(self):
        assert ">IT support</a>" in render(shipped(**URL_CFG_KEYS), page="safe-search-block-page")

    def test_safe_search_still_prints_the_address_in_email_mode(self):
        assert ">servicedesk@example.com</a>" in render(shipped(), page="safe-search-block-page")
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_contact.py -k "ContactSeam or EveryPage" -v`
Expected: the email-mode tests PASS (nothing changed yet); every URL-mode test FAILS — the href is still the mailto.

- [ ] **Step 3: Resolve the contact tokens in `page.py`**

Replace line 62:

```python
    parts = {k: substitute(v, base) for k, v in parts.items()}
```

with:

```python
    # The two contact sections are resolved first and on their own: they carry
    # {{SUPPORT_EMAIL}} and nothing else, and their results ARE the values the
    # {{CONTACT_*}} tokens in ACTIONS and EXTRA resolve to. Folding them into
    # `base` keeps this to one pass over the sections -- and one pass is not a
    # nicety. substitute() raises on any key it does not recognise, so a section
    # containing {{CONTACT_HREF}} cannot be run through a dict that lacks it.
    mailto = substitute(parts.get("CONTACT_MAILTO", ""), base)
    alt = substitute(parts.get("CONTACT_ALT", ""), base)
    base.update(
        {
            "CONTACT_HREF": contact.href(cfg, mailto),
            "CONTACT_TO": contact.to_attr(cfg),
            "CONTACT_ALT": alt if contact.mode(cfg) == contact.EMAIL else "",
            "CONTACT_NAME": contact.name(cfg),
        }
    )
    parts = {k: substitute(v, base) for k, v in parts.items()}
```

- [ ] **Step 4: Rewrite `url-block-page.html`**

Replace the `<!--@ACTIONS-->` block with:

```html
<!--@ACTIONS-->
<a class="btn" id="rep"{{CONTACT_TO}} data-subject="Blocked site report"
   data-intro="Please review this block." data-prompt="Why I need access:"
   href="{{CONTACT_HREF}}">Report to IT</a>
{{CONTACT_ALT}}
<!--/@ACTIONS-->

<!--
  The pre-filled mailto, used only when the config sets supportEmail. It lives in
  its own section because its body is this page's copy, and only this file can say
  what belongs in it.

  Keep it on ONE line. parse_sections() strips the section's outer whitespace but
  not its interior, so a newline introduced by reformatting lands inside the href.

  <url/> stays LAST: PAN-OS expands it at serve time, and a raw "&" in the
  expanded address terminates the body parameter, dropping every field after it.
-->
<!--@CONTACT_MAILTO-->mailto:{{SUPPORT_EMAIL}}?subject=Blocked%20site%20report&amp;body=Please%20review%20this%20block.%0A%0AUser%3A%20<user/>%0ACategory%3A%20<category/>%0A%0AWhy%20I%20need%20access%3A%0A%0AAddress%3A%20<url/><!--/@CONTACT_MAILTO-->

<!--@CONTACT_ALT--><p class="plain">Or email <a href="mailto:{{SUPPORT_EMAIL}}">{{SUPPORT_EMAIL}}</a> with the details above.</p><!--/@CONTACT_ALT-->
```

- [ ] **Step 5: Rewrite `url-coach-text.html`**

```html
<!--@ACTIONS-->
<pan_form/>
<a class="btn" id="rep"{{CONTACT_TO}} data-subject="Category warning - continue page"
   data-intro="I was warned before continuing." data-prompt="Why I think the category is wrong:"
   href="{{CONTACT_HREF}}">Report to IT</a>
<!--/@ACTIONS-->

<!--@CONTACT_MAILTO-->mailto:{{SUPPORT_EMAIL}}?subject=Category%20warning%20-%20continue%20page&amp;body=I%20was%20warned%20before%20continuing.%0A%0AUser%3A%20<user/>%0ACategory%3A%20<category/>%0A%0AWhy%20I%20think%20the%20category%20is%20wrong%3A%0A%0AAddress%3A%20<url/><!--/@CONTACT_MAILTO-->
```

This page has no fallback paragraph today and so declares no `<!--@CONTACT_ALT-->`; `parts.get("CONTACT_ALT", "")` handles that.

- [ ] **Step 6: Rewrite `credential-block-page.html`**

```html
<!--@ACTIONS-->
<a class="btn" id="rep"{{CONTACT_TO}} data-subject="Possible phishing page - credential submission blocked"
   data-intro="A credential submission was blocked." data-prompt="What I was doing:"
   href="{{CONTACT_HREF}}">Report to IT</a>
{{CONTACT_ALT}}
<!--/@ACTIONS-->

<!--@CONTACT_MAILTO-->mailto:{{SUPPORT_EMAIL}}?subject=Possible%20phishing%20page%20-%20credential%20submission%20blocked&amp;body=A%20credential%20submission%20was%20blocked.%0A%0AUser%3A%20<user/>%0ACategory%3A%20<category/>%0A%0AWhat%20I%20was%20doing%3A%0A%0AAddress%3A%20<url/><!--/@CONTACT_MAILTO-->

<!--@CONTACT_ALT--><p class="plain">Or email <a href="mailto:{{SUPPORT_EMAIL}}">{{SUPPORT_EMAIL}}</a> straight away.</p><!--/@CONTACT_ALT-->
```

- [ ] **Step 7: Rewrite `credential-coach-text.html`**

```html
<!--@ACTIONS-->
<pan_form/>
<a class="btn" id="rep"{{CONTACT_TO}} data-subject="Possible phishing page - credential prompt"
   data-intro="I was warned before submitting credentials." data-prompt="What I was doing:"
   href="{{CONTACT_HREF}}">Report to IT</a>
<!--/@ACTIONS-->

<!--@CONTACT_MAILTO-->mailto:{{SUPPORT_EMAIL}}?subject=Possible%20phishing%20page%20-%20credential%20prompt&amp;body=I%20was%20warned%20before%20submitting%20credentials.%0A%0AUser%3A%20<user/>%0ACategory%3A%20<category/>%0A%0AWhat%20I%20was%20doing%3A%0A%0AAddress%3A%20<url/><!--/@CONTACT_MAILTO-->
```

- [ ] **Step 8: Rewrite `file-block-page.html`**

```html
<!--@ACTIONS-->
<a class="btn" id="rep"{{CONTACT_TO}} data-subject="Blocked file transfer"
   data-intro="A file transfer was blocked by policy." data-prompt="Why I need this file:"
   href="{{CONTACT_HREF}}">Report to IT</a>
{{CONTACT_ALT}}
<!--/@ACTIONS-->

<!--@CONTACT_MAILTO-->mailto:{{SUPPORT_EMAIL}}?subject=Blocked%20file%20transfer&amp;body=A%20file%20transfer%20was%20blocked%20by%20policy.%0A%0AUser%3A%20<user/>%0A%0AWhy%20I%20need%20this%20file%3A%0A%0AFile%3A%20<fname/><!--/@CONTACT_MAILTO-->

<!--@CONTACT_ALT--><p class="plain">Or email <a href="mailto:{{SUPPORT_EMAIL}}">{{SUPPORT_EMAIL}}</a> with the details above.</p><!--/@CONTACT_ALT-->
```

- [ ] **Step 9: Rewrite `file-block-continue-page.html`**

```html
<!--@ACTIONS-->
<cookie/>
<a class="btn" id="rep"{{CONTACT_TO}} data-subject="File download warning"
   data-intro="I was warned before downloading a restricted file type." data-prompt="What I was doing:"
   href="{{CONTACT_HREF}}">Report to IT</a>
<!--/@ACTIONS-->

<!--@CONTACT_MAILTO-->mailto:{{SUPPORT_EMAIL}}?subject=File%20download%20warning&amp;body=I%20was%20warned%20before%20downloading%20a%20restricted%20file%20type.%0A%0AUser%3A%20<user/>%0A%0AWhat%20I%20was%20doing%3A%0A%0AFile%3A%20<fname/><!--/@CONTACT_MAILTO-->
```

- [ ] **Step 10: Rewrite `virus-block-page.html`**

```html
<!--@ACTIONS-->
<a class="btn" id="rep"{{CONTACT_TO}} data-subject="Malware detected in a download"
   data-intro="A download was blocked by antivirus scanning." data-prompt="What I was doing:"
   href="{{CONTACT_HREF}}">Report to IT</a>
{{CONTACT_ALT}}
<!--/@ACTIONS-->

<!--@CONTACT_MAILTO-->mailto:{{SUPPORT_EMAIL}}?subject=Malware%20detected%20in%20a%20download&amp;body=A%20download%20was%20blocked%20by%20antivirus%20scanning.%0A%0AUser%3A%20<user/>%0A%0AWhat%20I%20was%20doing%3A%0A%0AFile%3A%20<fname/><!--/@CONTACT_MAILTO-->

<!--@CONTACT_ALT--><p class="plain">Or email <a href="mailto:{{SUPPORT_EMAIL}}">{{SUPPORT_EMAIL}}</a> straight away.</p><!--/@CONTACT_ALT-->
```

- [ ] **Step 11: Rewrite `application-block-page.html`**

```html
<!--@ACTIONS-->
<a class="btn" id="rep"{{CONTACT_TO}} data-subject="Blocked application report"
   data-intro="Please review this application block." data-prompt="Why I need this application:"
   href="{{CONTACT_HREF}}">Report to IT</a>
{{CONTACT_ALT}}
<!--/@ACTIONS-->

<!--@CONTACT_MAILTO-->mailto:{{SUPPORT_EMAIL}}?subject=Blocked%20application%20report&amp;body=Please%20review%20this%20application%20block.%0A%0AUser%3A%20<user/>%0A%0AWhy%20I%20need%20this%20application%3A%0A%0AApplication%3A%20<appname/><!--/@CONTACT_MAILTO-->

<!--@CONTACT_ALT--><p class="plain">Or email <a href="mailto:{{SUPPORT_EMAIL}}">{{SUPPORT_EMAIL}}</a> with the details above.</p><!--/@CONTACT_ALT-->
```

- [ ] **Step 12: Rewrite `safe-search-block-page.html` EXTRA**

The odd one: the contact is a sentence in `EXTRA`, not a button, and its link text is the contact itself.

```html
<!--@EXTRA-->
<p class="infobox">{{INFO_MARK}}<span>Set SafeSearch to its strictest option, then run your search again. If you are signed in to the search engine, lock the setting as well.</span></p>
<p class="note">Still blocked after turning SafeSearch on? Email <a id="rep"{{CONTACT_TO}} data-subject="SafeSearch still blocked"
   data-intro="SafeSearch is enabled but my search is still blocked."
   data-prompt="What I searched for:"
   href="{{CONTACT_HREF}}">{{CONTACT_NAME}}</a> and IT will take a look.</p>
<!--/@EXTRA-->

<!--@CONTACT_MAILTO-->mailto:{{SUPPORT_EMAIL}}?subject=SafeSearch%20still%20blocked&amp;body=SafeSearch%20is%20enabled%20but%20my%20search%20is%20still%20blocked.%0A%0AUser%3A%20<user/>%0A%0AWhat%20I%20searched%20for%3A%0A<!--/@CONTACT_MAILTO-->
```

- [ ] **Step 13: Rewrite `TestMailto` in `tests/test_layout_details.py`**

**Read this step carefully — a minimal edit here silently disarms a real guard.** `TestMailto` reads the *template files*, and `_report_links()` yields the `<a …>` tag only. `test_static_fallback_puts_the_url_token_last` looks for `<url/>` inside that tag; the mailto has moved out to its own section, so the test's `continue` guard would skip every page and it would pass while checking nothing.

Keep the class docstring; replace the body with:

```python
    def _report_links(self):
        for page in PAGES.glob("*.html"):
            body = page.read_text(encoding="utf-8")
            if 'id="rep"' in body:
                start = body.index('id="rep"')
                # Bounded by `">`, not `>`. A bare `>` bound stops at the first
                # PAN-OS token in the href -- <user/> -- and silently returns a
                # fragment. That is not hypothetical: it is what made the
                # <url/>-last guard below skip every page for its whole life.
                end = body.index('">', body.index('href="', start)) + 2
                yield page.stem, body[body.rindex("<a ", 0, start) : end]

    def _mailto_sections(self):
        """The pre-filled mailto each page declares.

        It lives in its own section rather than in the anchor, because the anchor's
        href is now chosen at build time between this and a configured ticket URL.
        The <url/> ordering rule follows the mailto, not the anchor.
        """
        for page in PAGES.glob("*.html"):
            body = page.read_text(encoding="utf-8")
            m = re.search(r"<!--@CONTACT_MAILTO-->(.*?)<!--/@CONTACT_MAILTO-->", body, re.S)
            if m:
                yield page.stem, m.group(1)

    def test_every_report_link_carries_the_rebuild_attributes(self):
        # data-to is email-mode only -- it is an address, and a ticket URL has
        # none -- so the template carries {{CONTACT_TO}} and the build decides.
        # The other three ship in both modes: they are the page's incident
        # metadata, and what a ticket adapter will read.
        found = 0
        for name, tag in self._report_links():
            found += 1
            for attr in ("{{CONTACT_TO}}", "data-subject", "data-intro", "data-prompt"):
                self.assertIn(attr, tag, f"{name} missing {attr}")
        expected = len(list(PAGES.glob("*.html")))
        self.assertEqual(found, expected, "every page should offer a way to reach IT")

    def test_every_page_declares_a_mailto_section(self):
        """Email mode is the default, so a page without one has no href at all.
        page.py falls back to an empty string rather than raising."""
        declared = {name for name, _ in self._mailto_sections()}
        expected = {p.stem for p in PAGES.glob("*.html")}
        self.assertEqual(declared, expected, "every page needs a pre-filled mailto for email mode")

    def test_mailto_sections_are_single_line(self):
        """parse_sections strips the outer whitespace but not the interior, so a
        newline introduced by reformatting would land inside the href."""
        for name, mailto in self._mailto_sections():
            self.assertNotIn("\n", mailto.strip(), f"{name}: the mailto section must stay on one line")

    def test_static_fallback_puts_the_url_token_last(self):
        checked = 0
        for name, mailto in self._mailto_sections():
            if "<url/>" not in mailto:
                continue  # safe-search, application and file pages have no <url/> token
            checked += 1
            after = mailto[mailto.index("<url/>") + len("<url/>") :]
            self.assertNotIn(
                "%0A",
                after,
                f"{name}: no field may follow <url/> in the static href, or an '&' in the URL truncates it away",
            )
        # A `continue` that skips everything passes while asserting nothing, which
        # is exactly how this guard was dead before. Four pages carry <url/>;
        # a floor rather than an equality so a tenth page does not break it.
        self.assertGreaterEqual(checked, 4, "no mailto was examined -- the <url/> guard is asserting nothing")

    def test_subjects_are_distinct_per_page(self):
        subjects = {}
        for name, tag in self._report_links():
            m = re.search(r'data-subject="([^"]+)"', tag)
            self.assertIsNotNone(m, name)
            subjects.setdefault(m.group(1), []).append(name)
        dupes = {s: n for s, n in subjects.items() if len(n) > 1}
        self.assertEqual(dupes, {}, f"pages share a mail subject, so tickets are indistinguishable: {dupes}")
```

- [ ] **Step 14: Run to verify they pass**

Run: `uv run pytest tests/test_contact.py tests/test_layout_details.py -v`
Expected: PASS

- [ ] **Step 15: Confirm email-mode output really is byte-identical**

```bash
git stash
uv run panos-response-pages build --out /tmp/rp-before --no-preview
git stash pop
uv run panos-response-pages build --out /tmp/rp-after --no-preview
diff -r /tmp/rp-before/deploy /tmp/rp-after/deploy && echo "BYTE IDENTICAL"
```

Expected: `BYTE IDENTICAL`. If `diff` reports anything, stop — the seam has changed default output and that is a defect, not a tolerance.

- [ ] **Step 16: Run the full suite**

Run: `uv run pytest`
Expected: PASS

- [ ] **Step 17: Commit**

```bash
git add src/panos_response_pages/page.py src/panos_response_pages/data/templates/pages/ tests/test_contact.py tests/test_layout_details.py
git commit -m "Route every response page contact link through config"
```

---

### Task 5: Let the validator accept the contact anchor

Until this task, a URL-mode build fails at `validate.py:73-78` with "external reference found".

**Files:**
- Modify: `src/panos_response_pages/validate.py:66-78`
- Test: `tests/test_build_guards.py`

**Interfaces:**
- Consumes: nothing — deliberately config-blind, because `cli.py:271` calls `validate()` on arbitrary built files.
- Produces: `validate()` keeps its exact signature.

- [ ] **Step 1: Append the failing tests**

`tests/test_build_guards.py:16` imports the module as `build` (`from panos_response_pages import validate as build`) — there is no bare `validate` name in that file. Call `build.validate(...)`, and match the file's `unittest.TestCase` style:

```python
CONTACT_OK = (
    '<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1">'
    '</head><body><a id="rep" href="https://tickets.example.com/new">Report to IT</a></body></html>'
)
CONTACT_HTTP = CONTACT_OK.replace("https://", "http://")
STRAY_LINK = CONTACT_OK.replace('id="rep" ', "")
STRAY_IMG = CONTACT_OK.replace(
    '<a id="rep" href="https://tickets.example.com/new">Report to IT</a>',
    '<img src="https://cdn.example.com/logo.png">',
)


class TestContactAnchor(unittest.TestCase):
    """The one link allowed to leave the page, and only that one."""

    def test_https_on_the_contact_anchor_is_allowed(self):
        _size, errors, _warnings = build.validate("url-block-page", "assist", CONTACT_OK)
        self.assertEqual(errors, [])

    def test_http_on_the_contact_anchor_is_refused(self):
        """Cleartext on a page whose whole job is to be trusted."""
        _size, errors, _warnings = build.validate("url-block-page", "assist", CONTACT_HTTP)
        self.assertTrue(any("not self-contained" in e for e in errors))

    def test_https_on_any_other_link_is_still_refused(self):
        _size, errors, _warnings = build.validate("url-block-page", "assist", STRAY_LINK)
        self.assertTrue(any("not self-contained" in e for e in errors))

    def test_external_image_is_still_refused(self):
        _size, errors, _warnings = build.validate("url-block-page", "assist", STRAY_IMG)
        self.assertTrue(any("not self-contained" in e for e in errors))
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_build_guards.py::TestContactAnchor -v`
Expected: FAIL on `test_https_on_the_contact_anchor_is_allowed` — "external reference found".

- [ ] **Step 3: Rewrite the self-containment guard**

Replace `validate.py` lines 73-78 with:

```python
    # One exception, and it is structural rather than configured: the contact
    # anchor. `validate` is also run by the CLI over already-built files, where no
    # config is in hand to say which origin was meant -- so the rule is "the
    # anchor carrying id=rep may leave the page, nothing else may", which is
    # checkable from the HTML alone. That the URL is absolute https and sane is
    # contact.check()'s job, at build time.
    #
    # http:// is refused even there. A response page's entire value is that the
    # user trusts what it says; a cleartext link out of it is not that.
    #
    # Matched with _IS_REP rather than `'id="rep"' in tag`: a bare substring test
    # also accepts any attribute whose NAME merely ends in `id`, so a `xid="rep"`
    # would open the same hole this is trying to keep to one anchor.
    #
    # rfind("<") walks back to the opening of the tag the match sits in. Verified
    # against all 7 styles x 9 pages in both modes: no false positives, including
    # the multi-line anchor and safe-search's inline one. `<a` also prefixes
    # `<area` and `<audio`, which is harmless -- neither can carry id="rep" and an
    # href in a page this build produces.
    for m in re.finditer(r"""(?:src|href)\s*=\s*["']https?://""", html_text):
        tag_start = html_text.rfind("<", 0, m.start())
        tag_end = html_text.find(">", m.start())
        tag = html_text[tag_start : tag_end + 1] if tag_start >= 0 and tag_end >= 0 else ""
        if tag.startswith("<a") and _IS_REP.search(tag) and m.group(0).endswith("https://"):
            continue
        errors.append(f"external reference found ({m.group(0)}...) -- not self-contained")
        break
```

Two deliberate behaviour changes: the unreachable `mailto` exemption is gone (a match on `href="http` could never start with `href="mailto`), and at most one error is reported in total rather than one per attribute spelling. No existing test counts errors — they all use `any(...)` — so neither is observable.

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/test_build_guards.py -v`
Expected: PASS, including the existing `test_allows_mailto`.

- [ ] **Step 5: Verify a URL-mode build validates end to end**

Use `--config-dir` against a copy so nothing is written into tracked package data:

```bash
rm -rf /tmp/rp-data && cp -R src/panos_response_pages/data /tmp/rp-data
cat > /tmp/rp-data/config/ticketco.json <<'JSON'
{
  "company": "Ticket Co",
  "supportEmail": "",
  "supportUrl": "https://tickets.example.com/new"
}
JSON
uv run panos-response-pages build --customer ticketco --config-dir /tmp/rp-data --out /tmp/rp-urlmode
grep -o 'href="https://tickets.example.com/new"' /tmp/rp-urlmode/deploy/*/*/url-block-page.html | head -1
grep -c 'mailto:' /tmp/rp-urlmode/deploy/assist/cyber-orange/url-block-page.html
```

Expected: the build reports every page ok with no "external reference found"; the first `grep` prints the href; the second prints `0`.

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/panos_response_pages/validate.py tests/test_build_guards.py
git commit -m "Allow an https contact link on the report anchor only"
```

---

### Task 6: The portal family

Between Task 2 and this task a `supportUrl`-only config does not crash the portal — it ships `<a href="mailto:"></a>` and a logout message reading `Contact .`. This closes that.

**Files:**
- Modify: `src/panos_response_pages/portal/page.py:210-250`
- Modify: all seven `src/panos_response_pages/data/templates/portal/shells/*.html`
- Modify: `src/panos_response_pages/data/config/_defaults.json`
- Modify: `src/panos_response_pages/portal/validate.py:166-168`
- Modify: `tests/test_portal_config.py`
- Test: `tests/test_contact.py`

**Interfaces:**
- Consumes: `contact.href`, `contact.name`, `contact.email`
- Produces: two portal tokens — `{{CONTACT_HREF}}`, `{{CONTACT_NAME}}`

The portal has no per-page pre-filled body, so `CONTACT_HREF` here is a bare `mailto:<address>` — unlike the response pages, where it comes from the page's own section.

- [ ] **Step 1: Append the failing tests**

```python
@pytest.mark.integration
class TestPortalContact(unittest.TestCase):
    def test_email_mode_keeps_the_mailto_note(self):
        for theme in THEMES:
            assert "mailto:servicedesk@example.com" in portal(shipped(), theme=theme), theme["name"]

    def test_url_mode_links_the_ticket_system(self):
        for theme in THEMES:
            html = portal(shipped(**URL_CFG_KEYS), theme=theme)
            assert "https://tickets.example.com/new" in html, theme["name"]
            assert "mailto:" not in html, theme["name"]

    def test_url_mode_logout_messages_name_the_link_not_an_address(self):
        html = portal(shipped(**URL_CFG_KEYS), page="home")
        assert "servicedesk@example.com" not in html
        assert "IT support" in html

    def test_url_mode_portal_has_no_unresolved_token(self):
        for page in ("login", "home"):
            assert "{{" not in portal(shipped(**URL_CFG_KEYS), page=page), page

    def test_the_portal_contact_anchor_is_identified(self):
        """portal/validate.py exempts the contact link by id, exactly as the
        block-page guard does. Without the id the exemption would have to be
        'any https anchor', which is a much larger hole."""
        assert 'id="rep"' in portal(shipped())
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_contact.py::TestPortalContact -v`
Expected: FAIL — URL mode finds an empty `mailto:`, the logout messages carry the literal address, and there is no `id="rep"`.

- [ ] **Step 3: Add the tokens in `portal/page.py`**

In `_values()`, immediately after the `base` dict from Task 2, insert:

```python
    # The portal has no pre-filled body to carry -- there is no incident to
    # describe on a login page -- so email mode is a bare mailto rather than the
    # per-page mailto the response pages build.
    contact_values = {
        "CONTACT_HREF": contact.href(cfg, f"mailto:{contact.email(cfg)}"),
        "CONTACT_NAME": contact.name(cfg),
    }
```

After `values: dict[str, str] = dict(base)` add:

```python
    values.update(contact_values)
```

And change the `logoutMessages` line to resolve the contact tokens too:

```python
    # The messages name a contact, so they need the contact tokens as well as
    # `base`. Resolved before encoding -- substitute() does not rescan
    # replacement text, so a token left inside the array would ship literally.
    messages = [substitute(str(m), {**base, **contact_values}) for m in cfg["logoutMessages"]]
```

- [ ] **Step 4: Update the seven portal shells**

In each of `assist.html`, `banner.html`, `beacon.html`, `glass.html`, `mesh.html`, `nyan.html`, `record.html`, replace:

```html
<p class="note">Need help? Contact <a href="mailto:{{SUPPORT_EMAIL}}">{{SUPPORT_EMAIL}}</a>.</p>
```

with:

```html
<p class="note">Need help? Contact <a id="rep" href="{{CONTACT_HREF}}">{{CONTACT_NAME}}</a>.</p>
```

The `id="rep"` is what `portal/validate.py` keys its exemption on in Step 6. It costs ~11 bytes against 4060 bytes of headroom on the largest portal import.

- [ ] **Step 5: Update the logout messages in `_defaults.json`**

Replace `{{SUPPORT_EMAIL}}` with `{{CONTACT_NAME}}` in messages at indices 3, 4 and 5:

```json
    "System error. Contact {{CONTACT_NAME}}.",
    "System error, failed to delete user session. Contact {{CONTACT_NAME}}.",
    "Cannot create user session, maximum capacity reached. Contact {{CONTACT_NAME}}.",
```

Leave the other four exactly as they are. In the `_logoutMessages` documentation string, change the trailing sentence to: `Entries 3, 4 and 5 are admin-only errors an end user cannot act on, so they name a real contact instead of saying 'contact system administrator' -- {{CONTACT_NAME}} resolves to the support address, or to the words 'IT support' when supportUrl is set.`

- [ ] **Step 6: Relax the portal CSP guard**

Replace `portal/validate.py` lines 166-168 with:

```python
    # The portal's CSP blocks external CSS and JS. data: and same-origin are fine.
    # A navigational <a href> is not a subresource load and is not what the CSP
    # refuses -- so the contact link may point off-origin. Keyed on id="rep", the
    # same way validate.py keys the block-page rule: "any https anchor" would be a
    # far larger exemption than this needs.
    for m in _EXTERNAL.finditer(text):
        tag_start = text.rfind("<", 0, m.start())
        tag_end = text.find(">", m.start())
        tag = text[tag_start : tag_end + 1] if tag_start >= 0 and tag_end >= 0 else ""
        if tag.startswith("<a") and _IS_REP.search(tag) and m.group(1).startswith("https://"):
            continue
        errors.append(f"external reference blocked by the portal CSP: {m.group(1)[:60]}")
```

- [ ] **Step 7: Update `tests/test_portal_config.py`**

`test_admin_only_errors_name_a_contact` (lines 37-42) asserts `{{SUPPORT_EMAIL}}` is in messages 3, 4 and 5. Change the asserted token to `{{CONTACT_NAME}}` and update the docstring's second sentence to `The raw token survives here and is resolved during composition, where it becomes either the support address or the words "IT support".`

- [ ] **Step 8: Run to verify they pass**

Run: `uv run pytest tests/test_contact.py tests/test_portal_build.py tests/test_portal_validate.py tests/test_portal_shells.py tests/test_portal_config.py tests/test_portal_budget.py -v`
Expected: PASS

- [ ] **Step 9: Run the full suite**

Run: `uv run pytest`
Expected: PASS

- [ ] **Step 10: Commit**

```bash
git add src/panos_response_pages/portal/ src/panos_response_pages/data/templates/portal/ src/panos_response_pages/data/config/_defaults.json tests/test_contact.py tests/test_portal_config.py
git commit -m "Follow the configured support target in the portal too"
```

---

### Task 7: Config defaults, the page-authoring skill, and documentation

**Files:**
- Modify: `src/panos_response_pages/data/config/_defaults.json`
- Modify: `.claude/skills/add-response-page/SKILL.md:133-137,153`
- Modify: `docs/customising.md`, `docs/portal.md`, `docs/copy-rules.md`, `docs/architecture/url-filtering-response-pages.md`, `SECURITY.md`, `CHANGELOG.md`

- [ ] **Step 1: Document the keys in `_defaults.json`**

Before the `"supportEmail"` line, insert:

```json
  "_supportEmail": "Where every 'Report to IT' action goes. Mutually exclusive with supportUrl: set one, and blank the other. This mode pre-fills the mail with the page's own fact table -- the user, the address, the category -- so IT receives the incident already described.",
  "_supportUrl": "An alternative to supportEmail, for a customer whose front door is a ticket system rather than a mailbox. Must be an absolute https:// URL: a response page is served AS the blocked site, so a relative path resolves against whatever host the user was refused. The link carries no pre-filled context -- an href cannot -- so the user describes the problem themselves. This file ships a supportEmail, and customer configs are MERGED over it, so a customer file setting supportUrl must also set \"supportEmail\": \"\" or the build stops.",
  "supportUrl": "",
  "_supportLabel": "What the contact link is CALLED when supportUrl is set. Ignored in supportEmail mode, where the link prints the address itself -- there, the address is both the label and the destination. Name the queue the way your users find it: 'the Service Desk', 'Helpdesk', 'IT Support'. Blank means the built-in default, 'IT support'.",
  "supportLabel": "IT support",
```

Keep `"supportEmail": "servicedesk@example.com"` as the shipped default so an untouched checkout builds in email mode.

`contact.py` carries the same `IT support` default independently (`DEFAULT_URL_LABEL`), so the two must agree. They are duplicated on purpose: `_defaults.json` is where a customer discovers the key exists, and the constant is what keeps a config assembled without that document from rendering an anchor with no text.

- [ ] **Step 2: Update the page-authoring skill**

`.claude/skills/add-response-page/SKILL.md` still teaches the old markup, so a page written from it would fail `test_every_page_declares_a_mailto_section` and `test_every_report_link_carries_the_rebuild_attributes`, and would hardcode a mailto that URL mode cannot override.

Replace the `<!--@ACTIONS-->` block in its worked example (lines 133-137) with:

```html
<!--@ACTIONS-->
<a class="btn" id="rep"{{CONTACT_TO}} data-subject="<distinct subject>"
   data-intro="..." data-prompt="..."
   href="{{CONTACT_HREF}}">Report to IT</a>
{{CONTACT_ALT}}
<!--/@ACTIONS-->

<!--@CONTACT_MAILTO-->mailto:{{SUPPORT_EMAIL}}?subject=...&amp;body=...<url/><!--/@CONTACT_MAILTO-->

<!--@CONTACT_ALT--><p class="plain">Or email <a href="mailto:{{SUPPORT_EMAIL}}">{{SUPPORT_EMAIL}}</a> ...</p><!--/@CONTACT_ALT-->
```

In the "Rules the tests enforce" table, replace the `id="rep"` row and add two:

```markdown
| `id="rep"`, `{{CONTACT_TO}}` and the three `data-*` attributes | The script rebuilds the mailto from the rendered rows. `data-to` is emitted by the build, not the template, because it is an address and a `supportUrl` config has none |
| A `<!--@CONTACT_MAILTO-->` section, on one line | It is the href in email mode. `parse_sections` does not strip interior whitespace, so a newline lands inside the href |
| The static href goes in that section, never in the anchor | The anchor's href is chosen at build time between the mailto and a configured ticket URL |
```

Keep the `<url/>` **last** row as it is — the rule now applies to the section rather than the anchor, so update only its "Why" column to say so.

- [ ] **Step 3: Update `docs/customising.md`**

Replace the `supportEmail` table row with:

```markdown
| `supportEmail` | Target of every `mailto:`. Mutually exclusive with `supportUrl` |
| `supportUrl`   | Absolute `https://` ticket-system link, used instead of `mailto:` |
| `supportLabel` | What that link is called. `supportUrl` mode only; defaults to `IT support` |
```

Then add:

```markdown
## Sending users to a ticket system

By default every "Report to IT" action opens the user's mail client with the
incident already described — the user, the blocked address, the category and a
prompt, folded into the mail body by a small script on the page.

A customer whose front door is a ticket system sets `supportUrl` instead:

```json
{
  "company": "Example Corp",
  "supportEmail": "",
  "supportUrl": "https://example.service-now.com/sp?id=sc_cat_item&sys_id=...",
  "supportLabel": "the Service Desk"
}
```

`supportLabel` is optional and names the link. It is what a user reads where a
`mailto:` page would have printed the address — on the safe-search page and on
every portal page. Leave it out and the pages say "IT support". It has no effect
in `supportEmail` mode, where the address is its own label.

**The blank `supportEmail` line is required, not decoration.** Your customer file
is merged over `_defaults.json`, which ships a `supportEmail`; adding `supportUrl`
alone leaves both set and the build stops. Blanking is also the better habit than
deleting, because the next reader can see what the alternative was.

The URL must be absolute `https://`. A response page is served *as* the blocked
site, so a relative path resolves against whatever host the user was refused, and
an `http://` link on a page whose whole job is to be trusted is not one.

### What you give up

The ticket link carries no context. A `mailto:` can pre-fill a subject and a body;
an `<a href>` cannot, so the user arrives at a blank ticket form and describes the
problem themselves.

The page still *carries* the context, though. Every contact link declares the
incident metadata as attributes:

```html
<a id="rep" data-subject="Blocked site report"
   data-intro="Please review this block."
   data-prompt="Why I need access:"
   href="https://tickets.example.com/new">Report to IT</a>
```

Those three attributes are the seam for ticket-system support: a ServiceNow or
Jira Service Management adapter reads them and builds a pre-filled URL —
`short_description` from `data-subject`, `description` from `data-intro` plus the
page's fact table. That adapter does not exist yet; the attributes are already
there so that adding it does not mean editing all nine page templates again.

### Also affected

`supportUrl` applies to the GlobalProtect portal as well: the "Need help?" note on
every portal page, and the three logout messages that name a contact. Where those
would print an email address, they print the words "IT support" instead.
```

- [ ] **Step 4: Update the remaining docs**

- `docs/portal.md:84` — change the shared-keys row to `| `company`, `supportEmail` / `supportUrl` | Shared with the block pages |`. At line 146, note that a `supportUrl` config renders the same messages with "IT support" as the contact.
- `SECURITY.md:24` — the self-containment bullet currently reads that `http(s)` `src`/`href` outside of `mailto:` are rejected. Rewrite it to: rejected except an `https://` href on the `id="rep"` contact anchor, which is the one navigation a response page is allowed to offer.
- `docs/architecture/url-filtering-response-pages.md:104` — describes the contact action as a mailto. Add the URL-mode alternative.
- **`docs/copy-rules.md` is deliberately NOT edited.** The owner is removing that page; it is already deleted in the working tree, and its two failing `tests/test_docs.py` assertions (the `mkdocs.yml` nav entry and `test_documents_the_copy_rules_and_their_source`) are his to resolve along with the removal. The contact-link copy guidance that would have gone there is covered by the `docs/customising.md` section in Step 3 instead. Do not recreate the file, do not edit `mkdocs.yml`, and do not touch `tests/test_docs.py`.

- [ ] **Step 5: Add a `CHANGELOG.md` entry**

```markdown
- Response pages and the portal can point their contact action at an `https://`
  ticket system instead of a `mailto:`, via a new `supportUrl` config key.
  `supportUrl` and `supportEmail` are mutually exclusive; a config setting both
  fails the build. The ticket link carries no pre-filled context, but the page
  still declares the incident metadata as `data-*` attributes for a future
  ticket-system adapter to read.
```

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest`
Expected: PASS. `tests/test_docs.py` asserts specific needles in specific pages rather than enumerating config keys, but it does check `docs/portal.md` — rerun it after Step 4 in case a rewritten line dropped one.

- [ ] **Step 7: Commit source only**

```bash
git add src/panos_response_pages/data/config/_defaults.json .claude/skills/add-response-page/SKILL.md
git commit -m "Document the supportUrl config key"
```

**Do not `git add` `docs/` or `CHANGELOG.md` or `SECURITY.md`.** Stop and tell the user those files are written and ready for their review and their own commit.

---

### Task 8: End-to-end verification in a browser

Confirms the ticket href survives page load — the failure the runtime rewrite would have caused, which no template assertion can see.

- [ ] **Step 1: Build both modes**

```bash
rm -rf /tmp/rp-data && cp -R src/panos_response_pages/data /tmp/rp-data
cat > /tmp/rp-data/config/ticketco.json <<'JSON'
{
  "company": "Ticket Co",
  "supportEmail": "",
  "supportUrl": "https://tickets.example.com/new"
}
JSON
uv run panos-response-pages build --customer ticketco --config-dir /tmp/rp-data --out /tmp/rp-urlmode
uv run panos-response-pages build --customer contoso --out /tmp/rp-emailmode
```

Expected: both report every page ok.

- [ ] **Step 2: Check the URL-mode anchor after load**

Open `/tmp/rp-urlmode/preview/assist/cyber-orange/url-block-page.html`, then in the console:

```js
document.getElementById('rep').href
```

Expected: `"https://tickets.example.com/new"` — **not** a `mailto:`. A `mailto:` here means Task 3 did not take effect. Also confirm the Time row is populated (the clock shares a script with the removed rebuild) and no "Or email" paragraph is present.

- [ ] **Step 3: Check email mode is unchanged**

Open `/tmp/rp-emailmode/preview/assist/cyber-orange/url-block-page.html`, then:

```js
document.getElementById('rep').href
```

Expected: `mailto:servicedesk@example.com?subject=Blocked%20site%20report&body=…` containing Address, Category and User.

- [ ] **Step 4: Check the portal in URL mode**

Open the URL-mode portal login import and confirm "Need help? Contact IT support" links to the ticket URL.

- [ ] **Step 5: Clean up and confirm the tree**

```bash
rm -rf /tmp/rp-data /tmp/rp-urlmode /tmp/rp-emailmode /tmp/rp-before /tmp/rp-after
git status --short
```

Expected: only `docs/`, `CHANGELOG.md` and `SECURITY.md` remain modified — everything else committed, and no `ticketco.json` under `src/`.

---

## Deferred (explicitly not in this plan)

- **Ticket-system adapters** (ServiceNow, Jira Service Management). The seam is the three `data-*` attributes on the contact anchor plus `contact.href()`, the single function an adapter would extend. A future `supportTicket: {system, fields}` config block would be read there.
- **A second copy variant for the safe-search sentence.** Design Decision 5 records the accepted wart.
- **Per-customer link label.** "Report to IT" reads correctly for both a mailbox and a ticket queue.
