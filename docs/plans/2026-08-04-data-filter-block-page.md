# Data Filtering Block Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Add `data-filter-block-page` — the tenth block-page type — so a customer's Data Filtering (DLP) block is served in the project's house style instead of the PAN-OS default.

**Architecture:** No new modules. This is the ordinary "add a page type" path: register the type and its tokens in `validate.py`, add its preview sample in `page.py`, write one template under `data/templates/pages/`, and update the four places that enumerate pages by hand. The whole build and almost the whole test suite derives from `PAGE_TOKENS`, so registration is what makes the page real.

**The one thing that makes this page different from the other nine:** it carries a substitution token no existing page uses — `<direction/>`. That means `TOKEN_RE` must be extended, and until it is, `validate()` will not even *see* the token, so the legality check passes silently on a page that renders a blank field.

**Tech Stack:** Python 3.11+, stdlib only for this change. pytest + unittest-style classes, `uv` for running.

## Source material

`tmp/pages/data-filter-block-page.html` is the shipped PAN-OS default. Its markup is irrelevant here — the template is copied from `file-block-page.html`, not from it — but it is the authority on two facts:

```
$ grep -o '<[a-z_]*/>' tmp/pages/data-filter-block-page.html | sort -u
<appname/>
<direction/>
<fname/>
<user/>
```

and the default's title, **"Data Transfer Blocked"**, which is what a user who has seen the stock page will recognise.

The default's body sentence is `<direction/> of the file <fname/> has been blocked in accordance with company policy.` — i.e. `<direction/>` is used sentence-initially and capitalised there, which is the strongest available evidence that PAN-OS substitutes a capitalised word (`Upload` / `Download`). See Design Decision 4 for why this plan still does not put it in prose.

## Global Constraints

- **`PAGE_TOKENS` and the template directory must change in the same commit.** `tests/test_layout.py:45` asserts they agree; either alone is a red suite.
- **A token missing from `TOKEN_RE` is invisible to `validate()`.** The legality loop iterates `TOKEN_RE.finditer`, so an unregistered token name is not checked against the page's allowed set at all — the build goes green and the firewall renders nothing. `direction` must be added to the regex, not only to the dict.
- **A token missing from `SAMPLE` raises `KeyError` during the preview substitution.** Loud, but only if a preview build is run.
- **17,999-byte hard ceiling per page** (`validate.MAX_BYTES`), warning at 16,000. Not a risk here: the comparable pages build to ~7.5 KB (`mesh/prisma-blue/file-block-page.html` is 7,511 B) and this page adds two fact rows. Do not spend time on byte golf.
- **Copy lives in templates, not Python.** `tests/test_copy.py` lints template slot content against `BANNED_COPY`.
- **`BANNED_COPY` is a live hazard on *this* page specifically.** A DLP block is exactly where an author reaches for "your data was not sent" / "nothing you typed left your device". The page has no visibility into what the browser already transmitted, and three of the six banned phrases target precisely that claim. Write around it (Design Decision 5).
- **Commit message style:** short imperative subject, capitalised, no trailing period, ≤ 60 chars. No `feat:`/`fix:`/`docs:` prefixes, no emoji, no AI/tool attribution of any kind.
- **Never `git add` or `git commit` anything under `docs/` (Markdown), `README.md`, `CHANGELOG.md`, or `SECURITY.md`.** Write those files, then stop and tell the user they are ready for manual review. Source, templates, config data and tests are fine to commit.
  - **Judgement call flagged for the user:** `docs/assets/preview-embed.js` is a *test-enforced JavaScript asset* that happens to live under `docs/`. `tests/test_docs.py::test_the_embed_offers_every_page` fails without it, so the suite is only green once it is edited. Treat it as source for the purpose of the test run; ask the user whether they want it in the code commit or held back with the Markdown.

## Design Decisions (settled — do not re-litigate)

1. **API category is `data-filter-block-page`, taken verbatim from the default's filename.** The filename, the `Device > Response Pages` UI row and the XML API `category=` parameter are the same string. Getting it wrong produces a file nobody can import.
2. **Registered tokens are exactly `{user, fname, appname, direction}`** — read out of the shipped default, not assumed. `<url/>` and `<category/>` are *not* available; a URL row would render blank.
3. **Tone is `warn` with `COPY_LOCK`.** Same reasoning as `file-block-page`: this is a policy restriction on a transfer, not a threat verdict, so it is not `crit`; and there is no `<category/>` token for the runtime category map to derive a tone or gloss from, so the static tone must not be repainted. `warn` rather than `application-block-page`'s `calm` because a DLP hit is a content decision with a compliance edge, not a preference about which app to use.
4. **`<direction/>` appears as a fact-row *value* only, never in prose.** Its rendered casing is not documented — only inferred from the default's sentence-initial usage. In a fact row (`Direction: Upload`) either casing reads correctly; mid-sentence, `Download of this file was stopped` versus `download of this file was stopped` is the difference between correct and sloppy, decided by a value the build cannot see. The template's header comment must carry a **VERIFY ON A LIVE FIREWALL** note for it.
5. **The copy describes the *action stopped*, not the *data's fate*.** "The transfer was stopped" is substantiated — the page exists because it was. "Your data never left" is not, and is banned. `file-block-page`'s "so the transfer was stopped" is the precedent to follow.
6. **`<direction/>` gets no `class="mono"`.** `mono` marks machine values the user may have to read back to IT — URLs, filenames, App-IDs. "Upload" is an English word. `<fname/>` and `<appname/>` do get it, matching `file-block-page` and `application-block-page` respectively.
7. **Five fact rows: Direction, File, Application, User, Time.** Every available token is surfaced. Five rows is the most of any block page (the others run three or four); check it in `banner` and `glass`, which reflow the fact list into a sidebar and into cards respectively.
8. **`data-subject` is `Blocked data transfer`.** Distinct from `file-block-page`'s "Blocked file transfer" and `application-block-page`'s "Blocked application report"; `tests/test_layout_details.py::test_subjects_are_distinct_per_page` enforces distinctness, and near-identical subjects make tickets indistinguishable in practice even when they pass.
9. **`<!--@CONTACT_MAILTO-->` carries the bare address and nothing else** — `mailto:{{SUPPORT_EMAIL}}`, on one line, no query string, no PAN-OS tokens. **This supersedes the `add-response-page` skill's stale guidance to put `<url/>` last in the static href.** The incident detail now lives only in the `data-*` attributes, which the emitted script folds into the body with `encodeURIComponent`; `test_the_static_href_carries_no_panos_tokens` asserts the absence of both tokens and `?`.
10. **One callout, an `.infobox`, not a `.warnline`.** `test_no_page_mixes_a_warnline_and_an_infobox` forbids both; the useful thing to tell a blocked user is how to get unblocked, which is informational.

## File Structure

**Created:**
- `src/panos_response_pages/data/templates/pages/data-filter-block-page.html` — the template.

**Modified:**
- `src/panos_response_pages/validate.py` — `PAGE_TOKENS` entry, `TOKEN_RE` extension, and the stale `9 pages` count in the `external_refs` docstring.
- `src/panos_response_pages/page.py` — `SAMPLE["direction"]`.
- `src/panos_response_pages/contact.py` — the stale "all nine templates" comment (line ~19).
- `tests/test_build_guards.py` — one test for the new token's legality checking.
- `docs/assets/preview-embed.js` — the hand-written dropdown list (test-enforced).
- `docs/architecture/url-filtering-response-pages.md` — token table row, plus "nine page types" → ten.
- `docs/architecture/general.md` — "nine separate objects" → ten.
- `docs/styles.md` — "the same nine pages" (line 4) → ten.
- `docs/customising.md` — "all nine page templates" (line ~108) → ten.
- `CHANGELOG.md` — a new `## [Unreleased]` section (0.1.1 is tagged and released).

**Deliberately NOT modified:**
- `docs/styles.md` line ~21 — "six shells × three palettes is nine files" counts *shells plus palettes*, not pages. Changing it would be wrong. Read the sentence before touching any "nine" in that file.
- `docs/plans/*.md` — historical records; their counts were correct when written.
- Any test asserting a page count. Every one of them already derives from `len(PAGE_TOKENS)` or from the template glob (`test_cli.py:102`, `test_errors.py:129`, `test_datadir.py:114`, `test_portal_build.py:49`, `test_layout_details.py:228`). This plan adds no hardcoded count and bumps none.

---

## Task 1: Register the page type

- [x] **Step 1.** In `src/panos_response_pages/validate.py`, add to `PAGE_TOKENS`, keeping it beside the other file-oriented pages:

  ```python
      "data-filter-block-page": {"user", "fname", "appname", "direction"},
  ```

- [x] **Step 2.** In the same file, extend `TOKEN_RE` with the new alternative:

  ```python
  TOKEN_RE = re.compile(r"<(user|url|category|ssurl|pan_form|fname|cookie|appname|direction)\s*/>")
  ```

  Without this the token is not scanned, not validated, and not substituted in preview builds — it would ship as literal `<direction/>` markup that a browser renders as nothing.

- [x] **Step 3.** In `src/panos_response_pages/page.py`, add the preview sample:

  ```python
      # <direction/> is the transfer direction PAN-OS substitutes on the data
      # filtering page. The shipped default uses it sentence-initially, so a
      # capitalised word is expected -- unverified on a live firewall.
      "direction": "Upload",
  ```

- [x] **Step 4.** Fix the stale count in `validate.py`'s `external_refs` docstring: `against all 7 styles x 9 pages` → `x 10 pages`. Do not re-verify the claim it makes; the new page's contact anchor follows the identical shape.

- [x] **Step 5.** Run `uv run pytest -q tests/test_layout.py`. It **must fail** on `templates and PAGE_TOKENS disagree` — that is the proof the registration took effect and that Task 2 is genuinely required. Do not proceed by disabling it.

## Task 2: Write the template

- [x] **Step 1.** Copy `src/panos_response_pages/data/templates/pages/file-block-page.html` to `data-filter-block-page.html`. Do not start from `tmp/pages/data-filter-block-page.html`.

- [x] **Step 2.** Replace the header comment. It is developer documentation, exempt from the copy audit, and is where the live-verification debt is recorded:

  ```html
  <!--
    Data Filtering Block Page
    API category: data-filter-block-page
    Tokens available: <user/> <fname/> <appname/> <direction/>   -- NO url, NO category

    <direction/> is unique to this page: no other block page provides it. It is
    registered in TOKEN_RE for that reason -- an unregistered token is not
    checked against the page's allowed set at all.

    VERIFY ON A LIVE FIREWALL: the rendered value and casing of <direction/> are
    not documented. The shipped PAN-OS default uses it sentence-initially
    ("<direction/> of the file <fname/> has been blocked"), which implies
    "Upload"/"Download" capitalised. It is used here only as a fact-row value,
    where either casing reads correctly.

    Tone is warn, not crit: this is a policy restriction on a transfer, not a
    threat verdict. COPY_LOCK because there is no category token to derive
    severity or a gloss from.
  -->
  ```

- [x] **Step 3.** Set the slots. `TITLE` and `HEADLINE` echo the stock page's "Data Transfer Blocked" so a user who has seen the default recognises this one:

  ```html
  <!--@TITLE-->Data transfer blocked<!--/@TITLE-->

  <!--@TONE-->warn<!--/@TONE-->

  <!--@COPY_LOCK-->1<!--/@COPY_LOCK-->

  <!--@HEADLINE-->Data transfer blocked<!--/@HEADLINE-->

  <!--@GLOSS-->Company policy restricts transferring this content, so the transfer was stopped.<!--/@GLOSS-->
  ```

  Re-read Design Decision 5 before rewording the gloss. Do not write anything about where the data did or did not go.

- [x] **Step 4.** Give the page its own `<!--@MARK-->` SVG. `file-block-page` uses a document glyph and `application-block-page` a window; this page is about a transfer, so a document with an arrow (or a shield over a document) distinguishes it at a glance. Match the existing attribute set exactly — `viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"` — and keep it on one line, as every other template does.

- [x] **Step 5.** The fact rows. The `User` row must be the exact string below; `tests/test_copy.py::test_user_field_row` matches it verbatim, and the `id="ts"` on the Time row is what the emitted script fills:

  ```html
  <!--@FACTS-->
  <div class="f"><dt>Direction</dt><dd><direction/></dd></div>
  <div class="f"><dt>File</dt><dd class="mono"><fname/></dd></div>
  <div class="f"><dt>Application</dt><dd class="mono"><appname/></dd></div>
  <div class="f"><dt>User</dt><dd><user/></dd></div>
  <div class="f"><dt>Time</dt><dd id="ts"></dd></div>
  <!--/@FACTS-->
  ```

  No `id="cat"` — there is no `<category/>` token, and declaring one would emit ~1.7 KB of category JSON that nothing can select.

- [x] **Step 6.** The actions and contact sections. `data-subject` must be the distinct string from Design Decision 8, and the mailto section stays on one line with no query and no tokens:

  ```html
  <!--@ACTIONS-->
  <a class="btn" id="rep"{{CONTACT_TO}} data-subject="Blocked data transfer"
     data-intro="A data transfer was blocked by policy." data-prompt="Why I need to send this:"
     href="{{CONTACT_HREF}}">Report to IT</a>
  {{CONTACT_ALT}}
  <!--/@ACTIONS-->

  <!--@CONTACT_MAILTO-->mailto:{{SUPPORT_EMAIL}}<!--/@CONTACT_MAILTO-->

  <!--@CONTACT_ALT--><p class="plain">Or email <a href="mailto:{{SUPPORT_EMAIL}}">{{SUPPORT_EMAIL}}</a> with the details above.</p><!--/@CONTACT_ALT-->
  ```

- [x] **Step 7.** One callout, all its text inside a single `<span>`, opening with `{{INFO_MARK}}` — `.infobox` is `display:flex`, so bare text either side of a child element lays out as a separate column:

  ```html
  <!--@EXTRA-->
  <p class="infobox">{{INFO_MARK}}<span>If you need to send this for your work, send the report above and IT will review it.</span></p>
  <!--/@EXTRA-->
  ```

- [x] **Step 8.** Run `uv run pytest -q tests/test_layout.py tests/test_copy.py tests/test_layout_details.py`. All three green.

## Task 3: Guard the new token

- [x] **Step 1.** In `tests/test_build_guards.py`, beside `test_rejects_token_unavailable_on_page`, add its mirror for `direction`. The point is not that the dict has the right contents — it is that `TOKEN_RE` sees the token at all, which is the failure mode that passes silently:

  ```python
      def test_direction_is_rejected_off_the_data_filtering_page(self):
          """<direction/> is provided only on data-filter-block-page. If it were
          missing from TOKEN_RE this would pass by never being scanned."""
          page = self.HEAD.format("<p><direction/></p>")
          _size, errors, _warnings = build.validate("file-block-page", page)
          self.assertTrue(any("not available on file-block-page" in e for e in errors), errors)
  ```

- [x] **Step 2.** Sanity-check the test by temporarily removing `direction` from `TOKEN_RE` and confirming the new test fails. Restore it. A guard that cannot fail is not a guard.

- [x] **Step 3.** Run the full suite: `uv run pytest -q`. Everything green. If a count assertion fails, **fix it by deriving** (`len(PAGE_TOKENS)`, the template glob) — never by bumping a literal.

## Task 4: Documentation

Nothing in this task may be committed by an agent; see the Global Constraints.

- [x] **Step 1.** `docs/assets/preview-embed.js` — add `"data-filter-block-page",` to the dropdown list, keeping the existing alphabetical order (it sorts between `credential-coach-text` and `file-block-continue-page`). Enforced by `tests/test_docs.py::test_the_embed_offers_every_page`; without it the page is invisible on the docs home page and nothing else notices.

- [x] **Step 2.** `docs/architecture/url-filtering-response-pages.md` — add the row to the **Substitution tokens** table:

  ```
  | `data-filter-block-page` | `<user/>` `<fname/>` `<appname/>` `<direction/>` |
  ```

  Extend the token-meanings sentence below the table with `direction` the transfer direction. Change "The nine page types this project generates" and "rather than in nine near-identical files" to ten. Mark `<direction/>`'s meaning as inferred from the shipped default rather than documented, consistent with that file's `[verified]` / `[documented]` / `[unverified]` convention.

- [x] **Step 3.** `docs/architecture/general.md` line ~18 — "nine separate objects" → "ten separate objects".

- [x] **Step 4.** `docs/styles.md` line 4 — "the same nine pages" → "the same ten pages". **Leave line ~21 alone**; its "nine files" is six shells plus three palettes.

- [x] **Step 5.** `docs/customising.md` line ~108 — "all nine page templates" → "all ten page templates".

- [x] **Step 6.** `src/panos_response_pages/contact.py` line ~19 — "all nine templates" → "all ten templates". (Source, not docs — this one is committable.)

- [x] **Step 7.** `CHANGELOG.md` — add a new `## [Unreleased]` section above `## [0.1.1]` with an `### Added` entry. Say what the page is, that it is the tenth type, and that `<direction/>` is new to the token registry and unverified on live hardware.

- [x] **Step 8.** Tell the user which files are staged and which are waiting for their review. Do not stage the Markdown.

## Task 5: Verify

The suite proves the page is well-formed, not that it reads well. Both halves are required.

- [x] **Step 1.** `uv run panos-response-pages build` — all styles, all pages, no warnings.

- [x] **Step 2.** `uv run pytest -q` — the whole contract.

- [x] **Step 3.** `uv run panos-response-pages validate out/deploy` — expect `0 would fail`. The file count must rise by **exactly one per style/palette combination** (28 today: seven styles × four palettes — the build emits every combination, including `nyan` both ways). If it is short by a whole multiple of that, the page never registered.

- [x] **Step 4.** Confirm the byte budget with room to spare. Expect ~7.5–8 KB, well under the 16,000 B warning line:

  ```bash
  find out/deploy -name 'data-filter-block-page.html' -exec wc -c {} + | sort -n | tail -3
  ```

- [ ] **Step 5.** NOT DONE — no browser tooling is configured in this environment (both the Playwright and Chrome DevTools MCP servers are missing required arguments). Handed to the user. Look at it — `open out/preview/index.html`:
  - In **`banner`** and **`glass`**, not just `assist`. Five fact rows is the longest list any block page carries; banner puts them in a sidebar and glass in cards, and that is where the count shows.
  - In **dark scheme**, via the gallery toggle.
  - Check the `Direction` row reads deliberately with the sample value, and that `File` and `Application` are visibly mono while `Direction` and `User` are not.

- [x] **Step 6.** Record the outstanding live-firewall verification in the handover: that `<direction/>` renders at all, what it renders (`Upload` / `Download` and its casing), and — per the standing note on the file and antivirus defaults — that `<user/>` renders here, since the shipped default *does* use it on this page, unlike those two.

## Out of scope

The remaining files in `tmp/pages/` are a different family and must not be swept in with this change:

- `captive-portal-text.txt`, `mfa-login-page.txt`, `ssl-cert-status-page.txt`, `ssl-optout-text.txt`, `saml-auth-internal-error-page.txt` — these carry forms and auth flows the block-page shells are not built for, and PAN-OS serves several of them as fragments or bare scripts rather than whole documents. They belong to the `add-portal-page` route and each needs its file shape established against a live firewall first.
