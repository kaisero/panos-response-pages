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

Documented meanings: `<user/>` username or IP, `<url/>` requested URL (or
destination IP when decrypting), `<category/>` URL category, `<appname/>`
application, `<fname/>` filename, `<pan_form/>` injected form markup,
`<cookie/>` File Blocking Continue mechanism, `<ssurl/>` safe-search settings URL.

**Re-check the docs when adding a page** — variables have been added across
releases and this table is a snapshot:

- <https://docs.paloaltonetworks.com/pan-os/11-1/pan-os-web-interface-help/device/device-response-pages> — the page-type list
- <https://docs.paloaltonetworks.com/advanced-url-filtering/administration/url-filtering-features/url-filtering-response-pages/customize-url-filtering-response-pages> — the variable list
- Search LIVEcommunity for "which variables are allowed in response pages"

Two standing caveats already learned here:

- The docs say `<pan_form/>` works only on the Captive Portal Comfort and URL
  Filtering Continue pages, but the shipped `credential-coach-text` default
  carries it. The project uses it there and says so in the template comment.
- `<threatname/>` is community-attested only and is deliberately unused. Do not
  add a token on the strength of a forum post; an unsupported one renders blank.
- The file/antivirus defaults use only `<fname/>`. `<user/>` is documented as
  available on every response page but is absent from those defaults — flag it
  for live verification rather than assuming.

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

<!--@CONTACT_MAILTO-->mailto:{{SUPPORT_EMAIL}}?subject=...&amp;body=...<url/><!--/@CONTACT_MAILTO-->

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
| `id="cat"` on the Category row, if there is one | Drives the per-category tone and gloss rewrite |
| `class="mono"` on URLs, filenames, app names | Machine values; proportional type makes them hard to read back to IT |
| `id="rep"`, `{{CONTACT_TO}}` and the three `data-*` attributes | The script rebuilds the mailto from the rendered rows. `data-to` is emitted by the build, not the template, because it is an address and a `supportUrl` config has none |
| A `<!--@CONTACT_MAILTO-->` section, on one line | It is the href in email mode. `parse_sections` does not strip interior whitespace, so a newline lands inside the href |
| The static href goes in that section, never in the anchor | The anchor's href is chosen at build time between the mailto and a configured ticket URL |
| `<url/>` **last** in the static href | Same truncation, now inside the `<!--@CONTACT_MAILTO-->` section rather than the anchor's href: only trailing text should be lost |
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

## 4. Check for hardcoded page counts

Most of the suite derives from `PAGE_TOKENS` and adapts on its own. Anything that
does not will fail with an off-by-one that looks like a bug in the new page:

```bash
rg -n 'len\(.*\), [0-9]+|== [0-9]+.*page|assertEqual\(len' tests/
```

Fix by deriving rather than by bumping the number — `len(PAGE_TOKENS)`, not `9`.
A hardcoded count is a small tax charged again on every future page.

## 5. Documentation

- `docs/deploying.md` — add the row to the page-type table. `test_docs.py`
  asserts every registered type appears there.
- `CHANGELOG.md` — an entry under `## [Unreleased]`.

## 6. Verify

```bash
uv run panos-response-pages build                    # all styles, all pages
uv run pytest -q                                   # the whole contract
uv run panos-response-pages validate out/deploy      # guards over real output
```

`validate` should report `styles x pages` files checked and `0 would fail`. If
the count is short by a multiple of the style count, the page never registered.

Then look at it, in more than one style and both schemes — the tests prove the
page is well-formed, not that it reads well:

```bash
open out/preview/index.html
```

Check specifically:

- The new page in a **glass or banner** style, not just `assist` — those reflow
  the facts differently and a short fact list is where layouts break.
- **Dark scheme**, via the gallery's toggle.
- The **fact count**: two or three rows must look deliberate, not truncated.

### Byte budget

Every page must stay under 17,999 bytes (PAN-OS 8.1.3+; 8,191 on 8.1.2 and
earlier). The build warns above 16,000 to leave room for `<url/>` expanding at
serve time. Oversize does not error on the firewall — it silently serves the
default page.

## 7. What this does *not* cover

Page types whose function is not "explain a block" carry forms and auth flows
these shells are not built for, and PAN-OS serves them as fragments or bare
scripts rather than whole documents. They are a separate family with their own
slot contract, their own guards and a different byte ceiling.

**For the GlobalProtect portal login and home/logout pages, use
`add-portal-page`.** The same route is the right starting point for MFA login,
captive portal comfort and SAML error pages, none of which are implemented yet —
each needs its file shape established against a live firewall first.
