---
name: add-response-page
description: Integrate a new PAN-OS default response page into panos-response-pages. Use when adding support for a page type the project does not yet generate (application-block-page, data filtering, SSL decrypt opt-out, captive portal, etc.), or when asked to "add/integrate a response page" from a PAN-OS default HTML file.
---

Integrate one PAN-OS response page type end to end: token registration, page
template, sample data, docs, tests.

The whole project exists because **PAN-OS accepts a broken response page without
complaint** — the import succeeds, the commit succeeds, and users silently get
the default page or nothing. Every step below maps to a failure that is invisible
on the firewall. Do not skip one because the build is green; a green build is
exactly what the failure looks like.

## 1. Establish the facts before writing anything

Two things must be known and neither should be guessed:

**The API category string.** It is the filename, exactly. `Device > Response
Pages` in the UI and the XML API `category=` parameter use the same string.
Getting it wrong produces a file nobody can import. Derive it from the PAN-OS
default HTML's filename if you were given one.

> **The published API category list is stale — do not check against it.** The
> PAN-OS XML API "Import/Export Files" reference lists a PAN-OS 6-era set and
> omits `data-filter-block-page`, `safe-search-block-page`, `credential-block-page`,
> `credential-coach-text` and `mfa-login-page`, every one of which exists. An
> absence there is evidence of nothing. Corroborate instead against the
> vendor-maintained [`pan-os-ansible`](https://paloaltonetworks.github.io/pan-os-ansible/modules/panos_export_module.html)
> collection, whose `panos_import`/`panos_export` `category` choices are current,
> or the PAN-OS CLI command tree (`scp import <category>`), which mirrors the API
> keyword exactly.

**Which substitution tokens that page type provides.** Read them out of the
PAN-OS default HTML rather than assuming:

```bash
grep -o '<[a-z_]*/>' <the-default>.html | sort -u
```

A token the page type does not provide renders as **nothing** — a blank field on
a live page, with no error anywhere. `validate()` refuses tokens outside the
registered set, which is the only thing standing between a typo and a blank row.

### Known page types

Verified against PAN-OS defaults and the official docs. The `Device > Response
Pages` help page lists the page types but **not** their variables; the variable
list lives in the URL-filtering admin guide and the LIVEcommunity tech note.

| API category (= filename) | UI name | Tokens |
|---|---|---|
| `url-block-page` | URL Filtering and Category Match Block | `user url category` |
| `url-coach-text` | URL Filtering Continue and Override | `user url category pan_form` |
| `safe-search-block-page` | URL Filtering Safe Search Enforcement Block | `user ssurl` |
| `application-block-page` | Application Block | `user appname` |
| `credential-block-page` | Anti Phishing Block | `user url category` |
| `credential-coach-text` | Anti Phishing Continue | `user url category pan_form` |
| `virus-block-page` | Antivirus Block | `user fname` |
| `file-block-page` | File Blocking Block | `user fname` |
| `file-block-continue-page` | File Blocking Continue | `user fname cookie` |
| `data-filter-block-page` | Data Filtering Block | `user fname appname direction` |
| `ssl-cert-status-page` | SSL Certificate Status | `user url category certname issuer status reason` |

Documented meanings: `<user/>` username or IP, `<url/>` requested URL (or
destination IP when decrypting), `<category/>` URL category, `<appname/>`
application, `<fname/>` filename, `<pan_form/>` injected form markup,
`<cookie/>` File Blocking Continue mechanism, `<ssurl/>` safe-search settings URL,
`<direction/>` transfer direction (inferred `Upload`/`Download`, unverified),
`<certname/>` presented certificate name, `<issuer/>` its issuing authority,
`<status/>` and `<reason/>` PAN-OS's verdict on it (contents undocumented).

**Re-check the docs when adding a page** — variables have been added across
releases and this table is a snapshot:

- <https://docs.paloaltonetworks.com/pan-os/11-1/pan-os-web-interface-help/device/device-response-pages> — the page-type list
- <https://docs.paloaltonetworks.com/advanced-url-filtering/administration/url-filtering-features/url-filtering-response-pages/customize-url-filtering-response-pages> — the variable list
- Search LIVEcommunity for "which variables are allowed in response pages"

**The shipped default outranks every list, including a doc's silence.** No
official source gives per-page variables for the file, application, data
filtering or SSL pages at all — the only published table is URL-filtering-scoped
and covers four tokens. So "absent from the docs" is the normal condition, not a
signal. A token *in the vendor's own default for that exact category* is primary
evidence; a token attested only in a forum thread is not. The two failure modes
are not symmetrical:

- **In the default, absent from every list → register it**, with a
  live-verification note. `<direction/>` (data filtering) and `<certname/>`,
  `<issuer/>`, `<status/>`, `<reason/>` (SSL cert status) are all in this class.
- **In a forum list, absent from the defaults → leave it out.** `<threatname/>`
  and `<badcert/>` are in this class. An unsupported token renders blank.

Standing caveats already learned here:

- The docs say `<pan_form/>` works only on the Captive Portal Comfort and URL
  Filtering Continue pages, but the shipped `credential-coach-text` default
  carries it. The project uses it there and says so in the template comment.
- The file/antivirus defaults use only `<fname/>`. `<user/>` is documented as
  available on every response page but is absent from those defaults — flag it
  for live verification rather than assuming.
- `<url/>` renders the **destination IP**, not a URL, on the decryption-path
  pages — the `ssl-cert-status-page` default labels its `<url/>` row "IP". Label
  the row for what it will actually contain.

## 2. Register the page

`src/panos_response_pages/validate.py`:

```python
PAGE_TOKENS = {
    ...
    "application-block-page": {"user", "appname"},
}
```

If the page introduces a token **no existing page uses**, add it to `TOKEN_RE`
in the same file, or `validate()` will not see it at all and the legality check
silently passes:

```python
TOKEN_RE = re.compile(r"<(user|url|category|ssurl|pan_form|fname|cookie|appname)\s*/>")
```

Then add a preview value in `src/panos_response_pages/page.py`:

```python
SAMPLE = {
    ...
    "appname": "bittorrent",
}
```

Missing that raises a `KeyError` during the preview build — loud, at least.

**If a token renders something different on your page than it does elsewhere, add
a `PAGE_SAMPLE` override** in the same file, rather than living with a misleading
preview:

```python
PAGE_SAMPLE = {
    "ssl-cert-status-page": {"url": "192.0.2.24"},  # <url/> is the destination IP here
}
```

`SAMPLE` is keyed by token, not by page, so one entry serves every page that uses
that token. `<url/>` is the token this bites on: it is a URL on the filtering
pages and a destination **IP** on the decryption ones. Left shared, the gallery
shows a long URL in a row that will hold a short address — and judging whether a
row fits is the entire reason the gallery exists. Use documentation values
(RFC 5737 `192.0.2.0/24`) so a preview never points at a real host.

## 3. Write the page template

`src/panos_response_pages/data/templates/pages/<category>.html`. Copy the closest
existing page and change it; do not start from the PAN-OS default, whose markup
is irrelevant here.

Open with a `<!-- -->` block recording the API category, the available tokens and
anything needing live verification. That comment is developer documentation and
is exempt from the copy audit, so it may discuss the banned phrases.

Required slots: `TITLE HEADLINE GLOSS FACTS ACTIONS`. Optional: `TONE MARK EXTRA
COPY_LOCK`.

```html
<!--@TITLE-->Application blocked<!--/@TITLE-->
<!--@TONE-->calm<!--/@TONE-->
<!--@MARK--><svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor"
  stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">...</svg><!--/@MARK-->
<!--@HEADLINE-->Application blocked<!--/@HEADLINE-->
<!--@GLOSS-->One sentence saying what happened and why.<!--/@GLOSS-->

<!--@FACTS-->
<div class="f"><dt>Application</dt><dd class="mono"><appname/></dd></div>
<div class="f"><dt>User</dt><dd><user/></dd></div>
<div class="f"><dt>Time</dt><dd id="ts"></dd></div>
<!--/@FACTS-->

<!--@ACTIONS-->
<a class="btn" id="rep"{{CONTACT_TO}} data-subject="<distinct subject>"
   data-intro="..." data-prompt="..."
   href="{{CONTACT_HREF}}">Report to IT</a>
{{CONTACT_ALT}}
<!--/@ACTIONS-->

<!--@CONTACT_MAILTO-->mailto:{{SUPPORT_EMAIL}}<!--/@CONTACT_MAILTO-->

<!--@CONTACT_ALT--><p class="plain">Or email <a href="mailto:{{SUPPORT_EMAIL}}">{{SUPPORT_EMAIL}}</a> ...</p><!--/@CONTACT_ALT-->

<!--@EXTRA-->
<p class="infobox">{{INFO_MARK}}<span>One supplementary sentence.</span></p>
<!--/@EXTRA-->
```

### Rules the tests enforce, and why each exists

| Rule | Why |
|---|---|
| A `<dt>User</dt><dd><user/></dd>` row, verbatim | Every page identifies who was blocked; the string is matched exactly |
| `id="ts"` on the Time row | The emitted script fills it; without the id it is permanently blank |
| `id="cat"` on the Category row, if there is one | Drives the per-category tone and gloss rewrite, and the friendly-label rewrite |
| `class="mono"` on URLs, filenames, app names | Machine values; proportional type makes them hard to read back to IT |
| `id="rep"`, `{{CONTACT_TO}}` and the three `data-*` attributes | The script rebuilds the mailto from the rendered rows. `data-to` is emitted by the build, not the template, because it is an address and a `supportUrl` config has none |
| A `<!--@CONTACT_MAILTO-->` section, on one line | It is the href in email mode. `parse_sections` does not strip interior whitespace, so a newline lands inside the href |
| The static href goes in that section, never in the anchor | The anchor's href is chosen at build time between the mailto and a configured ticket URL |
| That section carries the **bare address** — no `?`, no query, **no PAN-OS tokens** | The body used to be spelled out here too, pre-encoded, with `<url/>` last so a raw `&` truncated only trailing text. It no longer is: the script rebuilds the body from the rendered fact rows with `encodeURIComponent`, which is the only place the encoding can be correct. `test_the_static_href_carries_no_panos_tokens` asserts the absence — which is stronger than asserting an order, because an ordering rule passes trivially on a page that has no `<url/>` |
| A distinct `data-subject` | Duplicate subjects make tickets indistinguishable |
| `Report to IT` is a `class="btn"` anchor | It read as prose when it was a bare link |
| Every page reaches IT somehow | Asserted by count against the number of templates |
| Callout text inside **one** `<span>` | The callout is `display:flex`; bare text either side of a `<strong>` lays out as separate columns |
| Callout opens with `{{INFO_MARK}}` / `{{WARN_MARK}}` | — |
| Never both `.infobox` and `.warnline` | Two stacked callouts read as competing alerts |
| No hardcoded Continue duration | Admin-configurable; use `{{CONTINUE_GRANT}}` |

### Copy

Two classes of statement fail the build because the page cannot substantiate
either: **that data was or was not transmitted** ("nothing you typed was sent"),
and **that a policy applies to all users** ("blocked for everyone"). The page has
no visibility into what the browser already sent, and no PAN-OS variable exposes
which rule matched. The list is `BANNED_COPY` in `validate.py`.

Set `TONE` to `calm`, `warn` or `crit`. Add `<!--@COPY_LOCK-->1<!--/@COPY_LOCK-->`
when the tone must not be repainted by the category map — the credential pages
use it, because a phishing interstitial must never render calm.

### `id="cat"` and `COPY_LOCK` are independent, and the pair is often what you want

`COPY_LOCK` pins the tone **and** the gloss; `id="cat"` drives the rewrite of the
raw slug into a friendly label (`online-storage-and-backup` → `Online Storage and
Backup`). Setting both keeps your page's own copy while still spelling the
category readably — and it is *cheaper*, not more expensive: `category_js` emits
the ~1.7 KB category map only when `has_category and not lock_copy`, so the pair
buys the ~0.2 KB label code with no map at all.

Use the pair whenever the page shows `<category/>` but the category is not the
*reason* for the page — an SSL certificate error is about the certificate, and
letting the map overwrite that gloss with a category sentence loses the reason
the user is looking at the page.

## 4. Check for hardcoded page counts

Most of the suite derives from `PAGE_TOKENS` and adapts on its own. Anything that
does not will fail with an off-by-one that looks like a bug in the new page:

```bash
rg -n 'len\(.*\), [0-9]+|== [0-9]+.*page|assertEqual\(len' tests/
```

Fix by deriving rather than by bumping the number — `len(PAGE_TOKENS)`, not `9`.
A hardcoded count is a small tax charged again on every future page.

As of the data filtering page every test derives correctly and none needed
touching. Prose counts are the ones that rot; see step 5.

### Prove the new token's guard can actually fail

Adding a token to `TOKEN_RE` is the step whose omission is silent, so the test
for it must be shown to work rather than assumed:

1. Add a test asserting the new token is *rejected* on some other page —
   `validate("file-block-page", "...<direction/>...")` must produce
   `not available on file-block-page`.
2. Temporarily delete the token from `TOKEN_RE` and confirm that test fails.
3. Put it back.

Without step 2 you have a test that passes for the wrong reason: with the token
missing from the regex, nothing is scanned, `errors` is empty, and an assertion
written the other way round would sail through.

## 5. Documentation

`docs/deploying.md` does not exist — do not go looking for it.

- `docs/assets/preview-embed.js` — add the page to the hand-written `PAGES`
  dropdown, in alphabetical order. **Test-enforced**
  (`test_docs.py::test_the_embed_offers_every_page`); it is the one docs change
  that turns the suite red, and without it the page is invisible on the docs
  home page.
- `docs/architecture/url-filtering-response-pages.md` — add the row to the
  **Substitution tokens** table, extend the token-meanings sentence, and mark
  anything inferred `[unverified]` per that file's convention.
- **Sweep the prose page counts.** They are not test-enforced and go stale
  silently: `rg -n '\bnine\b|\bten\b' docs/ src/ --glob '!plans/**'`. Today that
  is `docs/styles.md`, `docs/customising.md`, `docs/architecture/general.md`,
  `docs/architecture/url-filtering-response-pages.md`, plus comments in
  `contact.py` and `validate.py`. **Read each hit before editing it** —
  `docs/styles.md` also says "six shells × three palettes is nine files", which
  counts *files*, not pages, and must not be changed.
- `CHANGELOG.md` — an entry under `## [Unreleased]`, added above the last
  released version.
- This skill's **Known page types** table — add the row you just verified, so
  the next page starts from a table that includes yours.

`docs/plans/` is gitignored working material; the repo's convention is that
plans are not committed.

## 6. Verify

```bash
uv run panos-response-pages build                    # all styles, all pages
uv run pytest -q                                   # the whole contract
uv run panos-response-pages validate out/deploy      # guards over real output
```

`validate` should report `0 would fail`, over
`combinations x (pages + 2 portal)` files — 28 combinations today (7 styles × 4
palettes; the build emits every pairing, including `nyan` both ways), so 10 pages
reads as `checked 336 page(s)`. If the total is short by a whole multiple of 28,
the page never registered. Confirm directly too:

```bash
find out/deploy -name '<category>.html' | wc -l    # must equal the combination count
```

Then look at it, in more than one style and both schemes — the tests prove the
page is well-formed, not that it reads well:

```bash
open out/preview/index.html
```

Check specifically:

- The new page in a **glass or banner** style, not just `assist` — those reflow
  the facts differently, and both ends of the fact count are where layouts break.
- **Dark scheme**, via the gallery's toggle.
- The **fact count**: two or three rows must look deliberate rather than
  truncated; seven or eight must not read as a form.

If no browser tooling is available — the MCP browser servers are frequently
unconfigured — **say so and hand the paths over**, rather than reporting the
page as verified. `out/preview/<style>/<palette>/<category>.html` opens directly.
What you *can* check without a renderer, and should: the sample values
substituted, `class="mono"` landing only where intended, and no shell capping the
fact list (`rg -n 'nth-child|grid-template-rows' .../shells/*.html` — the only
positional rules today are count-agnostic `.f:first-child` borders).

### Byte budget

Every page must stay under 17,999 bytes (PAN-OS 8.1.3+; 8,191 on 8.1.2 and
earlier). The build warns above 16,000 to leave room for `<url/>` expanding at
serve time. Oversize does not error on the firewall — it silently serves the
default page.

## 7. What this does *not* cover

The test is **file shape**, not subject matter. A vendor default that is a whole
`<!DOCTYPE html>` document explaining why a request was refused belongs here,
whatever it is about — `ssl-cert-status-page` is a certificate error rather than a
policy block and still fits this route exactly.

What does not fit: page types PAN-OS serves as **fragments** (no doctype, no
`<head>` — `ssl-optout-text` is one) or as bare scripts, and those carrying forms
and auth flows these shells are not built for. They are a separate family with
their own slot contract, their own guards and a different byte ceiling. Check
before assuming from the name: `url-coach-text` reads like a fragment and this
project ships it as a full document.

**For the GlobalProtect portal login and home/logout pages, use
`add-portal-page`.** The same route is the right starting point for MFA login,
captive portal comfort and SAML error pages, none of which are implemented yet —
each needs its file shape established against a live firewall first.
