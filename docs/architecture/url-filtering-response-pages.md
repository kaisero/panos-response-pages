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
