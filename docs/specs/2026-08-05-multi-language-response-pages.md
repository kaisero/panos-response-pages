# Multi-Language Response Pages

**Status:** Design spec, agreed. Not yet implemented.
**First additional language:** German (`de`).

## Goal

One imported page serves every language. PAN-OS gives a vsys exactly one page per
type, so a firewall with German and English speakers behind it cannot import two —
the choice has to happen in the browser. Every language a customer configures is
compiled into the page, and the browser picks one from `navigator.languages`.

## Scope

**In:** the 11 block pages × 6 styles, the 3 GlobalProtect portal surfaces, and the
7 `logoutMessages`.

**Out:** the `nyan` style (see Decision 6); machine translation; a visible language
picker; per-region variants (`de-AT` as distinct copy from `de-DE`).

## The budget, measured

Only **6–9% of a built page is language-dependent**. The rest is CSS, the SVG mark
and the emitted script, none of which changes with language — so the cost of a
language is far below the intuition of "another copy of the page".

| | Bytes |
|---|---|
| Translatable copy, ordinary page | 410–600 B |
| Translatable copy, `url-block-page` / `url-coach-text` | 375 B + 1,443 B of category glosses |
| **German, per page** | **~600 B** (copy × 1.25 expansion + ~130 B JSON structure) |
| Runtime mechanism, one-off per page | ~240 B |
| Optional per-language category glosses | ~1,800 B on top, on 2 pages only |

Projected with German added, worst page in each style:

| Style | Worst page today | + German | Total | Headroom to 16,000 |
|---|---|---|---|---|
| `record` | 9,673 B | 838 B | 10,511 B | 5,489 B |
| `assist` | 9,782 B | 838 B | 10,620 B | 5,380 B |
| `banner` | 10,041 B | 838 B | 10,879 B | 5,121 B |
| `mesh` | 10,563 B | 838 B | 11,401 B | 4,599 B |
| `beacon` | 10,681 B | 838 B | 11,519 B | 4,481 B |
| `glass` | 10,973 B | 838 B | 11,811 B | 4,189 B |
| `nyan` | 15,108 B | — | — | **excluded** |

**Eight additional languages fit under the 16,000 B warn line** on the worst
non-nyan page (`glass`/`url-block-page`: 10,973 B + 240 B + 8 × 598 B = 15,997 B).
The ninth exceeds it. Hold the warn line rather than the 17,999 B hard ceiling: the
gap exists because `<url/>` expands at serve time, and a long blocked URL grows the
page after the byte count was taken.

Caveats on that figure:
- **Cyrillic and Greek cost roughly 1.6×** (2 bytes/char in UTF-8), so Russian is
  ~950 B rather than ~600 B. CJK is roughly par with English.
- The 1.25 expansion factor for German is an estimate. **Replace it with a measured
  value once `de.json` exists** — it is the softest number in this spec.

### Portal, measured

**Corrected after re-analysis.** An earlier draft budgeted against 16,170 B; that
is the size at which PAN-OS *refuses the import*. `portal/validate.py:42` warns at
**15,000 B**, and that is the line to hold.

| Shell | `login` today | encoded | vs 15,000 | `home` today | vs 15,000 |
|---|---|---|---|---|---|
| `assist` | 10,411 B | 14,067 | +4,589 | 5,633 B | +9,367 |
| `record` | 10,465 B | 14,140 | +4,535 | 5,787 B | +9,213 |
| `banner` | 10,483 B | 14,164 | +4,517 | 5,908 B | +9,092 |
| `nyan` | 11,438 B | 15,453 | +3,562 | 6,859 B | +8,141 |
| `glass` | 11,601 B | 15,672 | +3,399 | 6,645 B | +8,355 |
| `mesh` | 11,753 B | 15,879 | +3,247 | 6,751 B | +8,249 |
| **`beacon`** | **12,119 B** | 16,373 | **+2,881** | 6,550 B | +8,450 |

`beacon`/`login` is the binding constraint at **2,881 B of headroom**.

| | Bytes |
|---|---|
| `login` translatable copy | 232 B across 13 strings |
| German `login` dictionary | ~430 B |
| `logout_text_array` | 572 B → ~755 B in German |
| Runtime, one-off per import | ~240 B |

German costs `beacon`/`login` **~670 B**, landing it at 12,789 B with 2,211 B to
spare. **Six additional languages fit** on the worst login import
((2,881 − 240) ÷ 430); `home` fits ten. Portal is less constrained than the block
pages, not more.

### Where portal copy actually lives

Not in the page templates, as the block-page family does — in the **shells**, and
identically in all seven of them (`templates/portal/shells/*.html`, `<!--@BODY-->`).
Verified: all 7 contain the same 7 strings. One shared strings block; seven files
to edit.

Three strings sit somewhere else again: `Download for `, `Choose your download`,
`macOS`/`Windows `/`64-bit`/`32-bit` are **JavaScript string literals** inside
`templates/portal/login.html`'s `<!--@FOOT_SCRIPT-->`, not markup. They are
swapped by reading the dictionary, not by rewriting a text node.

## Decisions

### 1. Strings move out of the templates into `en.json`

Templates carry keys; `data/strings/en.json` carries the copy. Textbook i18n, and
symmetric — English is not a special case that the other languages emulate.

*Consequence, accepted:* this is the project's "copy lives in templates, not Python
or JSON" constraint being deliberately retired. See Decision 10 for what happens to
the guards that depended on it.

### 2. Runtime addressing is by stable selector, not by attribute

No `data-t` attributes and no new ids. The swap script walks selectors that already
exist in every shell:

| Target | Selector | Strings key |
|---|---|---|
| Document title | `document.title` | `title` |
| Headline | `h1` | `headline` |
| Gloss | `#gloss` | `gloss` |
| Severity pill | `.sev` | `shared.severity[tone]` |
| Fact labels | `dl dt`, in document order | `facts[]` |
| Report button | `#rep` (text + 3 `data-*`) | `report.*` |
| Contact fallback | `.plain` text nodes | `shared.contactAlt[]` |
| Callout | `.infobox span`, `.warnline span` | `extra` |

**Zero markup cost.** A `data-t` scheme would tax every page ~160 B whether or not
a second language is configured — a quarter of a whole language, charged to
customers who never asked for one.

The price is positional coupling on `facts[]`: reorder the fact rows and the labels
misalign silently. Guarded by a build-time assertion that `len(facts)` equals the
number of `<dt>` the built page contains, per page per language.

### 3. `baseLanguage` and `languages` are separate config keys

```json
"baseLanguage": "en",
"languages": ["en"]
```

`baseLanguage` is rendered as real text into the markup — it is what a browser with
JavaScript disabled shows, and what every language falls back to. `languages` is the
full set compiled into the page.

Validation, all `BuildError`:
- `baseLanguage` not in `languages`
- a language in `languages` with no `strings/<lang>.json`
- a key not matching `^[a-z]{2}$`
- `languages` empty

**`languages: ["en"]` must produce byte-identical output to today.** This is
asserted by test, not assumed. It is what makes the feature free for every existing
customer, and the assertion is how it stays free.

### 4. Two-letter primary subtags only

`en.json`, `de.json`. Detection reduces each entry of `navigator.languages` to its
primary subtag, so `de`, `de-AT`, `de-CH` and `de-DE` all resolve to `de`.

Full BCP-47 (`pt-BR` vs `pt`) is deferred. It needs a fallback chain, a
case-canonicalisation rule between filename and browser tag, and tests for both —
none of which German exercises.

### 5. Per-language category glosses are optional

A language file may carry a `categories` block. Absent — the default — a non-base
language shows the translated `defaultGloss`/`riskGloss` for that category's tone,
and the language costs ~600 B. Present, it costs ~2,400 B.

The **tone map is never translated and never duplicated**: it ships once, so
severity, colour and the severity pill vary per category identically in every
language. Only the sentence changes.

Category *labels* are never translated. They are derived client-side by title-casing
the PAN-OS slug (`command-and-control` → `Command and Control`); they are PAN-OS
identifiers, and a customer reading one back to IT should be reading what PAN-OS
calls it.

When a `categories` block pushes a page over the ceiling the build fails naming the
language, the page and the overshoot, and says that dropping the block costs ~1,800 B.

### 6. `nyan` opts out; any other overflow is a hard error

```json
{ "name": "nyan", "shell": "nyan", "palette": "nyan", "i18n": false }
```

`nyan` builds in `baseLanguage` only. At 15,108 B it has 892 B of headroom — less
than two languages — because its star field and sprite artwork are 50% of the file.
It is a novelty style; capping the whole design around it would be the tail wagging
the dog.

The opt-out is **reported in the build table**, not silent:

```
nyan     prisma-blue  url-block-page  15108  ok  (en only — i18n:false)
glass    prisma-blue  url-block-page  11811  ok  en,de
```

Every other style that overflows fails the build. Automatic language-dropping was
considered and rejected: a customer who configured French, and silently gets French
on four styles out of six, is exactly the invisible failure this project exists to
prevent.

### 7. A missing key is a build error

Every language supplies every key. No runtime fallback to baseline, no partially
translated page.

```
BuildError: de.json is missing 4 keys
  pages.ssl-cert-status-page.headline
  pages.ssl-cert-status-page.gloss
  pages.ssl-cert-status-page.facts[3]
  pages.ssl-cert-status-page.report.subject
```

**Known cost, accepted:** combined with Decision 1, adding page type 12 leaves the
build red until German exists, even for someone who does not speak German. This will
be felt on the very next page added. The alternative — a warning in a build log —
is the kind of notice that gets scrolled past, and the result ships to users.

### 8. Customer-authored copy is translated in the customer's own config

```json
{
  "continueGrantText": "30 minutes",
  "defaultGloss": "Blocked under ACME policy.",
  "translations": {
    "de": {
      "continueGrantText": "30 Minuten",
      "defaultGloss": "Gemäß ACME-Richtlinie gesperrt."
    }
  }
}
```

Deep-merged like every other config key, and it wins over the shipped
`strings/<lang>.json`, mirroring config-over-defaults.

A customer overriding one string adds three lines to the file they already maintain.
Putting these in the strings files instead would force them to `init` and fork the
entire data tree — resolution is whole-tree, not per-file — to translate a sentence.

Keys eligible: `defaultGloss`, `riskGloss`, `continueGrantText`, `supportLabel`,
`logoutMessages`, and `categories` glosses.

### 9. Both families, in this spec

Block pages and portal together. Inline script is permitted on the portal
(`script-src 'self' 'unsafe-inline'`, confirmed in
`docs/architecture/general.md`), and **the portal login page already requires
JavaScript** — the form has no `action` attribute — so a JS-dependent language swap
is no worse there than the status quo.

#### `logout_text_array` timing — RESOLVED, no live verification needed

An earlier draft called this unproven. It is not: the captured firewall output is
in this repository. `data/fixtures/logout-suffix.html:26` is what a real appliance
served, and it reads the array like this:

```js
$(document).ready(function() {
  ...
  $('div#logout').text(logout_text_array[ 0 ]);
  ...
});
```

Two facts follow, both from the capture rather than from reasoning:

- **The read happens inside `$(document).ready`.** Our `<!--@HEAD_SCRIPT-->` is a
  synchronous `<script>` in `<head>`, emitted immediately after `<!--@VARS-->`
  declares the array (`portal/page.py:43`). It therefore runs strictly before the
  ready handler. **Reassigning `logout_text_array` in `HEAD_SCRIPT` wins.**
- **The index is baked into the generated file** — `[ 0 ]` here, not a runtime
  lookup. PAN-OS bakes the index for the logout reason when it generates
  `logout.esp`, so the page cannot know which message will be shown and does not
  need to: the German array must simply be the same seven entries in the same
  order.

`.text()` also means the message is inserted as text, never markup — so German
needs no escaping beyond the JS string literal that already carries it.

#### PAN-OS's injected login form is reachable, and should be translated

`data/fixtures/pan_form-login.html` shows what the `<pan_form/>` substitution
actually delivers: `placeholder="Username"`, `placeholder="Password"`,
`value="Log In"`, plus `New Password` and `confirm New Password`. **These are
PAN-OS's strings, not this project's** — an earlier draft did not account for
them, which would have shipped a German page wrapped around an English form.

They are addressable by id after substitution (`#user`, `#passwd`, `#submit`,
`#new_passwd`, `#confirm_new_passwd`), and `FOOT_SCRIPT` runs after the form is
parsed. Translating them is therefore possible and in scope.

This depends on PAN-OS's own DOM, which is a dependency this family already
carries deliberately — the download button reads `#taGetSofewarePage` and moves
PAN-OS's anchors. It degrades the same way: every swap is guarded, and an element
that is not there is skipped, leaving PAN-OS's own wording.

#### Hard constraints the portal adds

- **No raw `<`.** `portal/validate.py:85` refuses `<` not followed by a tag-ish
  character anywhere in the file, because the observed failure is that
  `<pan_form/>` silently stops being substituted. The emitted German dictionary
  must escape `<` as `<` — `json.dumps` does not do this by default.
- **Every `LOGIN_VARS`/`HOME_VARS` variable must stay declared**
  (`portal/validate.py:57-79`): PAN-OS's ready handler dereferences each one and
  throws on an undeclared name, losing the whole customization.
- **`detect_kind` keys on the string `logout_text_array`**
  (`portal/validate.py:99`). Nothing added to the login import may contain it.

### 10. Guard migration

The template-linting guards lose their subject when copy leaves the templates. They
move rather than disappear:

| Guard | Today | After |
|---|---|---|
| `BANNED_COPY` audit | template slot content | **every language file**, not just `en.json` — a German sentence can assert something untrue just as easily |
| `<dt>User</dt><dd><user/></dd>` verbatim | template text | built output, per language |
| `data-subject` distinct per page | template attribute | built output, per language — subjects must be distinct *within* a language |
| Continue duration not hardcoded | template text | every language file |
| Callout text in one `<span>` | template markup | unchanged; markup stays in templates |

`SEV_LABEL` ("Caution", "Security risk") moves out of `scripts.py` into
`shared.severity`. It is the third home of English copy and cannot stay in Python
once the other two are consolidated.

## Strings file schema

`data/strings/<lang>.json`, inside the whole-tree data dir:

```json
{
  "lang": "de",
  "shared": {
    "severity":     { "calm": "", "warn": "Achtung", "crit": "Sicherheitsrisiko" },
    "defaultGloss": "Diese Kategorie ist durch Unternehmensrichtlinien eingeschränkt.",
    "riskGloss":    "Diese Seite wurde gesperrt, weil sie ein Sicherheitsrisiko darstellt.",
    "continueGrantText": "15 Minuten",
    "supportLabel": "IT-Support",
    "reportLabel":  "An die IT melden",
    "contactAlt":   ["Oder senden Sie eine E-Mail an ", " mit den obigen Angaben."]
  },
  "pages": {
    "ssl-cert-status-page": {
      "title":    "Zertifikatsproblem",
      "headline": "Das Zertifikat dieser Website konnte nicht überprüft werden",
      "gloss":    "Der Server hat ein Zertifikat vorgelegt, das nicht überprüft werden konnte. Die Verbindung wurde daher getrennt.",
      "facts":    ["Server", "Zertifikat", "Aussteller", "Status", "Grund", "Kategorie", "Benutzer", "Zeit"],
      "extra":    "Melden Sie sich auf dieser Website nicht an und geben Sie keine persönlichen Daten ein, bis die IT sie geprüft hat.",
      "report":   { "subject": "Zertifikatsfehler",
                    "intro":   "Bei dieser Verbindung konnte ein Zertifikat nicht überprüft werden.",
                    "prompt":  "Was ich erreichen wollte:" }
    }
  },
  "portal": {
    "login":   { },
    "logoutMessages": ["…", "…", "…", "…", "…", "…", "…"]
  },
  "categories": { }
}
```

### Strings containing inline links

Two slots carry an `<a>` inside prose — `CONTACT_ALT` on 8 pages, and
`safe-search-block-page`'s note. Their strings are **arrays of the two halves either
side of the anchor**, and the script swaps the two text nodes while leaving the
anchor and its `href` untouched. No `innerHTML` anywhere.

```
["Oder senden Sie eine E-Mail an ", " mit den obigen Angaben."]
             ↑ text node 0        ↑ <a> kept   ↑ text node 2
```

**Documented limitation:** a language whose word order requires the link *first* or
*last* cannot be expressed. German does not; if a future language does, that string
becomes a full-markup exception with its own rule.

### Placeholders

Translated strings may carry `{{COMPANY}}`, `{{SUPPORT_EMAIL}}`,
`{{CONTINUE_GRANT}}` etc. They are resolved **per language at build time**, before
the dictionary is emitted — so `{{CONTINUE_GRANT}}` inside a German string resolves
to the German `continueGrantText`. `credential-block-page` (`{{COMPANY}}`) and
`url-coach-text` (`{{CONTINUE_GRANT}}`) exercise this.

## Runtime contract

Emitted only when `len(languages) > 1`; a single-language build emits nothing, which
is what keeps Decision 3's byte-identity promise.

```js
(function(){
  var T=<dict>,                                    // {de:{...}}, base language absent
      L=navigator.languages||[navigator.language||''],
      i,k,t;
  for(i=0;i<L.length;i++){
    k=L[i].slice(0,2).toLowerCase();
    if(T[k]){t=T[k];break}
    if(k==='<base>')break;                          // base wins if listed first
  }
  if(!t)return;                                     // no match: markup stands
  document.documentElement.lang=k;
  document.title=t.title;
  /* …selector swaps per Decision 2… */
})();
```

Rules:
- **Base language is not in the dictionary.** It is already in the markup; shipping
  it twice would be the largest single waste in the design.
- **Runs before the category and timestamp scripts.** The category lookup reads the
  gloss element and the timestamp writes into `#ts`; both must see the final
  language. Ordering is: language → category → timestamp → redirect.
- **`toLocaleString()` for the Time row takes the selected language**, so a German
  page shows a German-formatted timestamp.
- **The mail rebuild runs after the swap**, so the mail body is in the user's
  language — its fields are read from the rendered `<dt>`/`<dd>` pairs.
- **No match leaves the markup untouched.** The failure mode is the base language,
  never a blank page.

## Build behaviour

- Per language per page, the build emits only the keys that page uses. There is no
  shared dictionary across pages; each page is self-contained, because PAN-OS
  imports them one at a time.
- The build table gains a language column and reports the `i18n: false` styles.
- `validate` reports per-page size as today; the ceiling error names the language
  set that produced the size.

## Live verification debt

One item, down from two. The `logout_text_array` timing was settled from the
captured fixture (above) and no longer needs a firewall.

1. **The 1.25 German expansion factor.** Replace it with the measured value once
   `de.json` is written, and re-run every budget table in this document.

Worth confirming opportunistically, but not blocking: that PAN-OS's injected form
still uses the ids in `pan_form-login.html` on the target release. The swap is
guarded, so a changed id degrades to PAN-OS's own English wording rather than
breaking the page.

## Explicitly not in this design

- **A visible language picker.** A response page is a transient interstitial; a user
  who lands on one wants to know why, not to configure it. It would also need its own
  persisted state, which a page served from the blocked site's origin cannot have.
- **Machine translation.** German copy is authored. A response page tells a user
  their organisation blocked something; the tone that carries is the point of this
  project, and it does not survive a translation API.
- **Server-side negotiation.** PAN-OS serves a static file. There is no
  `Accept-Language` to read.
