# URL Filtering and block pages

**Location:** Device → Response Pages
**Serves:** dataplane injection into user traffic

The eleven page types this project generates. They share one file shape and one set of
constraints, differing only in which substitution tokens PAN-OS provides — so they are
documented together rather than in eleven near-identical files.

These are a **different page class** from the
[GlobalProtect portal pages](general.md#pages). Do not carry constraints between them:
the GP pages are served by the management plane and take a body fragment; these are
injected into user traffic by the dataplane and take a complete document.

## File shape: a complete document **[documented]**

Unlike the GlobalProtect imports, these are whole HTML documents — `<!DOCTYPE html>`
through `</html>`. `validate.py` requires the doctype; without it browsers fall back
to quirks mode.

## Substitution tokens **[verified]**

The registry lives in `src/panos_response_pages/validate.py`. A token used outside its
page's set renders as inert markup — it shows nothing, silently.

| Page type | Tokens |
|---|---|
| `url-block-page` | `<user/>` `<url/>` `<category/>` |
| `url-coach-text` | `<user/>` `<url/>` `<category/>` `<pan_form/>` |
| `safe-search-block-page` | `<user/>` `<ssurl/>` — **no `<url/>`, no `<category/>`** |
| `application-block-page` | `<user/>` `<appname/>` |
| `credential-block-page` | `<user/>` `<url/>` `<category/>` |
| `credential-coach-text` | `<user/>` `<url/>` `<category/>` `<pan_form/>` |
| `virus-block-page` | `<user/>` `<fname/>` |
| `file-block-page` | `<user/>` `<fname/>` |
| `file-block-continue-page` | `<user/>` `<fname/>` `<cookie/>` |
| `data-filter-block-page` | `<user/>` `<fname/>` `<appname/>` `<direction/>` |
| `ssl-cert-status-page` | `<user/>` `<url/>` `<category/>` `<certname/>` `<issuer/>` `<status/>` `<reason/>` |

Token meanings: `user` the identified user; `url` the blocked address; `category` the
URL category; `ssurl` the safe-search URL; `appname` the application; `fname` the
filename; `cookie` the continue-grant control; `pan_form` the continue form;
`direction` the transfer direction; `certname` the presented certificate's name;
`issuer` its issuing authority; `status` and `reason` PAN-OS's verdict on it.

`<url/>` is **the destination IP, not a URL, on the decryption path.** The
`ssl-cert-status-page` default labels its `<url/>` row `IP:`, and the official
description of the variable says as much — "requested URL, or destination IP when
decrypting". A row labelled "URL" there promises a scheme and path that will not
arrive; this project labels it **Server**. **[documented]**

The four certificate tokens are **[unverified]** in the same sense as
`<direction/>`: they appear in the shipped `ssl-cert-status-page` default and are
corroborated as a group by the LIVEcommunity variable list, but no official source
documents them, and nothing documents what `<status/>` and `<reason/>` actually
contain. `<badcert/>` appears in that community list and **not** in the vendor
default, so it is deliberately not registered — the evidence runs the wrong way,
and an unsupported token renders blank.

`<direction/>` is **[unverified]**, and deliberately kept so after a search that came
back empty. It appears in the shipped `data-filter-block-page` default — which is the
primary source this table is built from — and in **none** of the published variable
lists: not the URL-filtering variable table, not the "Customize Your Response Pages"
LIVEcommunity blog (the fullest list that exists anywhere), and not the two community
threads that specifically asked for the complete set. Its rendered value and casing are
therefore inferred, not documented. The default uses it sentence-initially —
`<direction/> of the file <fname/> has been blocked` — which implies a capitalised
`Upload`/`Download`. The template uses it only as a fact-row value, where either casing
reads correctly, and carries a live-verification note.

The vendor's own default page is trusted over the absence, because the absence is what
the published lists look like generally: they are URL-filtering-scoped and do not
attempt per-page coverage for the file, application or data filtering pages either.
Note also that a `Direction` (upload / download / both) field exists on the Data
Filtering *profile*, so the token has an obvious thing to render.

### The published API category list is stale **[verified]**

The PAN-OS XML API "Import/Export Files" reference lists a PAN-OS 6-era set of
`category=` values. It omits `data-filter-block-page` — and also `safe-search-block-page`,
`credential-block-page`, `credential-coach-text` and `mfa-login-page`, all of which
plainly exist. **Do not read that omission as evidence a category is wrong.**
`data-filter-block-page` is corroborated by two Palo Alto-authored sources: the
vendor-maintained [`pan-os-ansible`](https://paloaltonetworks.github.io/pan-os-ansible/modules/panos_export_module.html)
collection, which lists it in the `category` choices of both `panos_import` and
`panos_export`, and the PAN-OS 11.0 CLI command tree, where `scp import
data-filter-block-page` mirrors the API keyword exactly.

The UI row is **"Data Filtering Block Page"**, described as *"Content was matched
against a data filtering profile and blocked because sensitive information was
detected."* — [Device > Response Pages](https://docs.paloaltonetworks.com/pan-os/11-1/pan-os-web-interface-help/device/device-response-pages). **[documented]**

The two `*-coach-text` pages and `file-block-continue-page` inject **form controls you
do not author** — style `input[type=submit]` and `button` so those controls match the
page.

## Size: two different limits

### Serving-time, on decrypted sites: 17,999 bytes **[documented]**

> "Custom response pages larger than the maximum supported size are not decrypted or
> displayed to users. In PAN-OS 8.1.2 and earlier PAN-OS 8.1 releases, custom response
> pages on a decrypted site can't exceed 8,191 bytes; the maximum size is 17,999 bytes
> in PAN-OS 8.1.3 and later releases."
>
> — [Customize URL Filtering Response Pages](https://docs.paloaltonetworks.com/advanced-url-filtering/administration/url-filtering-features/url-filtering-response-pages/customize-url-filtering-response-pages)

Note what this is and is not:

- A **display-time** limit, not an import limit. The page imports fine and is silently
  not shown.
- Scoped to **decrypted sites** — it is about injecting into a decrypted TLS session.
- **Silent.** No error, no log line.

This is the source of `MAX_BYTES = 17999` in `validate.py`. `WARN_BYTES = 16000`
leaves headroom because `<url/>` expands at serve time — a long blocked URL grows the
page after the byte count was taken.

### Import-time: unknown, possibly 16,170 bytes **[unverified]**

The GlobalProtect portal login page is refused at import above **16,170 bytes**
(21,845 base64 characters) — see [the README](general.md#import-size-ceiling-16170-bytes-verified).

**Whether that cap is generic to response-page objects or specific to the GP page has
not been tested.** It matters:

> If the import cap is shared, **`MAX_BYTES = 17999` is unreachable** — a 17,999-byte
> page could never be imported in the first place, and the effective ceiling is 16,170.

| Raw bytes | Encoded chars | vs 21,845 cap |
|---|---|---|
| 12,222 (largest generated page) | 16,511 | fits |
| 16,170 | 21,844 | fits |
| 17,000 | 22,967 | over |
| 17,999 | 24,316 | over |

**One upload settles it.** `tmp/gp-lab/probe-urlfilter-17000.html` is a generated
block page padded to 17,000 bytes — legal by the serving limit, over the GP import
cap. Import it as URL Filtering Block Page:

- **Refused** → one shared cap. `MAX_BYTES` should become 16,170.
- **Accepted** → caps are per page type. `17999` stands; 16,170 is GP-specific.

No action is required today either way: the largest page this project generates is
**12,222 bytes** (`beacon/url-block-page.html`), comfortably inside both numbers.

## Self-containment **[enforced]**

`validate.py` rejects:

| Rule | Reason |
|---|---|
| `<base>` | Resolves relative URLs against the **blocked site** |
| `<link>` | External stylesheet — not self-contained |
| `src="http…"` / `href="http…"` | External reference (`mailto:` excepted, plus an `https://` href on the `id="rep"` contact anchor when the config sets `supportUrl` instead of `supportEmail`) |

**The origin argument is what makes this stricter than the GP pages.** A block page is
served *as if it were the blocked site*. Any relative URL resolves against a host the
user was just prevented from reaching, and any external fetch tells a third party which
users hit which blocks. The GP portal pages are served by the firewall's own
management plane, where that reasoning does not apply.

Generated pages inline everything: CSS in a `<style>` block, icons as inline `<svg>`
using `currentColor`, no webfonts, no images.

## Copy rules **[enforced]**

`validate.py` fails a build on six phrases in two classes:

| Phrase | Why |
|---|---|
| "nothing you typed", "was not sent", "left your device" | Asserts data was not transmitted. The page has no visibility into what the browser sent. |
| "for everyone", "everybody", "not just you" | Asserts the policy applies to all users. Different users match different rules. |

Both classes make claims the page cannot substantiate.

The audit runs over **every language file**, not just `en.json`. A German sentence
asserts something untrue exactly as easily as an English one, and the reviewer who
would have caught it in a template is less likely to be reading the translation.

**But it matches phrases, and the phrases are English and German.** Thirteen
languages ship; the guard knows two of them. For the other eleven the audit walks
the file, finds nothing it recognises, and passes — so the rule is enforced by the
translator's judgement and by review, not by the build. This is deliberate: eleven
sets of banned phrases is a maintenance burden with a false-positive risk this
project has already met once, in a deliberately wide German phrase that matched
copy meaning something else. Extending the list to a third language is therefore
a deliberate decision rather than something a translation is expected to carry
with it. Treat "the copy audit passed" as evidence about English and German only.

## Language selection at load time

PAN-OS serves one page per type per vsys. A firewall with German and English
speakers behind it cannot import two, and there is no `Accept-Language` to negotiate
against because the file is static — so the choice happens in the browser. Every
configured language is compiled into the page and one is selected on load. See
[Customising](../customising.md#languages) for the config keys and the byte budget;
this is the contract the emitted script honours.

**Thirteen languages ship and the contract below is unchanged by that.** Nothing
here is per-language: the dictionary is a flat map keyed by code, the loop reads
`navigator.languages` in order, and adding a twelfth or a thirteenth entry to `T`
adds no branch and no rule. What thirteen languages changed is the budget, not the
runtime — a build compiles English plus three to five others before the portal
import is refused, so the emitted `T` is small whatever the strings directory
holds. The `T` this section describes is the one a real build emits.

**Nothing is emitted at all when only one language is configured.** Not an empty
dictionary and not a disabled selector: the byte-identity guarantee is asserted
against the bytes, so a single-language page has to be the page it was before.

### Selection

```js
var T={"de":{…}},LS=navigator.languages||[navigator.language||''],t,lk,i;
for(i=0;i<LS.length;i++){lk=LS[i].slice(0,2).toLowerCase();
  if(lk=="en")break;            // the base language stops the search
  if(T[lk]){t=T[lk];break}}
if(t){ … }
```

Four properties, each of which is a decision:

- **Two-letter primary subtags.** Each entry of `navigator.languages` is truncated
  to its first two characters and lowercased, so `de`, `de-AT`, `de-CH` and `de-DE`
  all resolve to `de`. Full BCP-47 (`pt-BR` as distinct copy from `pt`) needs a
  fallback chain and a case-canonicalisation rule between filename and browser tag,
  neither of which German exercises.
- **The base language is absent from the dictionary.** It is already in the markup
  as real text; shipping it twice would be the largest single waste in the design.
- **The base language stops the search.** A browser that ranks it above a compiled
  language must keep the page it was served — otherwise a user who prefers English
  with German second would be handed German.
- **No match leaves the page exactly as served.** The failure mode is the base
  language, never a blank page and never a half-swapped one. `documentElement.lang`
  is set only on a match, which is what lets the redirect script downstream tell
  "base language" from "some other language" without repeating the lookup.

### The selector table

Addressing is by **selector**, not by attribute. There are no `data-t` attributes and
no new ids: a `data-t` scheme would tax every page ~160 B whether or not a second
language was configured — a quarter of a whole language, charged to customers who
never asked for one.

| Target | Selector | Key |
|---|---|---|
| Document language | `document.documentElement.lang` | the matched code |
| Document title | `document.title` | `t` |
| Headline | `h1` | `h` |
| Gloss | `#gloss` | `g` |
| Fact labels | `dl dt`, in document order | `f[]` |
| Primary button | `a.btn#rep`, falling back to `a.btn` | `a2` or `rl` |
| Report metadata | `#rep` `data-subject` / `data-intro` / `data-prompt` | `rs` / `ri` / `rp` |
| Contact fallback | `.plain`, three-node | `ca[0]`, `ca[1]` |
| Callout | `.infobox span`, `.warnline span` | `x` |
| Split note | `.note`, three-node | `x[1]`, `x[2]` |
| Severity pill | `.sev`, only when it already says something | `s[data-tone]` |
| Category gloss | via the `#cat` lookup | `c`, `dg`, `rg` |

Two of those rows are less arbitrary than they look:

- **The report button prefers `#rep` before any `a.btn`.** Three pages carry a
  PAN-OS token — `<pan_form/>` on the two coach pages, `<cookie/>` on
  `file-block-continue-page` — that the firewall expands into markup of its own
  *before* the report anchor. Whether that markup contains an `a.btn` cannot be
  established from this repository, so a bare selector would make the label's
  destination depend on serve-time injection, and the report label could land in
  PAN-OS's own Continue control. `#rep` is ours and the firewall never injects it.
- **The severity pill is swapped only when it is non-empty.** A calm page carries a
  pill with no words in it, and writing a label into it would invent a severity the
  page never declared.

### Ordering

`language → category → timestamp → mail rebuild → redirect`, in one emitted IIFE.

Everything after the swap reads the words it chose. The category lookup rewrites the
gloss and re-sets the pill; `toLocaleString()` formats the Time row to
`documentElement.lang`, so a German page shows a German timestamp; the mail rebuild
folds the *rendered* `<dt>`/`<dd>` pairs into the body, so the mail is in the user's
language; and the redirect reads `documentElement.lang` to find its translated
notice. Reorder these and each one silently produces base-language output on a
translated page.

### Split sentences are swapped by node position

A sentence a single child element splits is three nodes — text, element, text — and
the runtime writes node 0 and node 2, leaving the element and its `href` untouched.
`innerHTML` is not used anywhere in this project, and on the portal a raw `<` is
outright illegal.

The middle node is written only where it is copy: `.plain` and `.note` wrap a
build-time anchor holding a configured address, which must survive exactly as
served, while `url-coach-text`'s callout wraps a `<strong>` whose text *is* the
emphasised phrase. The swap keys on `childNodes.length>2` and does nothing when it
does not find that shape — which is why an empty fragment in a strings file is a
build error rather than a cosmetic problem: it removes a text node, collapses the
sentence to two children, and the swap declines in silence.

### The `facts` array is positionally coupled to `<dt>` — and guarded

Fact labels are numbered, not named: `{{T_FACT1}}` in the template, `f[0]` in the
dictionary, swapped against `dl dt` in document order. Giving them names as well
would create a second ordering that could disagree with the first.

The price is that **one label short shifts every label below it up by one, on a page
that builds and validates clean.** Nothing about the output looks wrong; the Time
row is simply labelled "User".

Key-parity checking does not catch it, and this is the part worth understanding: it
compares the languages against *each other*, so a `facts` array that is wrong in
every language — which is what an `en.json` with one label too many becomes the
moment it is translated — passes. Only the template knows how many rows there are.
The guard therefore reads the template: it extracts the `<!--@FACTS-->` block from
each page, counts `<dt>`, and asserts that every strings file's `facts` array for
that page has exactly that many entries. Per page, per language.

**It catches a length, not an order.** A `facts` array with the right number of
labels in the wrong sequence is indistinguishable from a correct one to every
check in the build: key parity passes, the count passes, the page renders, and the
Time row is labelled "User" in that language alone. There is no guard to write for
it — the arrays are positional by design, and a checker would need to know what
each row means in a language it does not read. It is caught by rendering the page
and reading it, which is why every language shipped here was rendered before it was
committed, and why the reviewer checklists name the fact rows as something to check
rather than leaving it to a general read-through.

## What is not covered here

Page types whose function is not "explain a block" — GlobalProtect portal pages, MFA
login, captive portal comfort, SAML errors — carry forms and authentication flows the
shells in this project are not built for.

The two GlobalProtect portal pages now have their own references
([login](globalprotect-portal-login-page.md),
[home](globalprotect-portal-home-page.md)) and a working implementation, but they are
**not** generated by this project's build. Integrating them means a fragment shell
that emits a `<style>`-only file instead of a document, per-page-class validation
rules, and a preview that covers all four login states. That remains a design
conversation, not a checklist.
