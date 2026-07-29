# Response page architecture

Per-page reference for what PAN-OS actually does with an imported response page:
the shape of the file it expects, the tokens and variables available, and the limits
it enforces.

Palo Alto documents the *existence* of these pages and a handful of customization
variables. It does not document the file's structure, the substitution semantics, or
the import ceiling. Almost everything here was measured against a live firewall, so
each claim carries an evidence marker.

## Pages

| Page | Import object | Serves |
|---|---|---|
| [GlobalProtect Portal Login Page](globalprotect-portal-login-page.md) | `global-protect-portal-custom-login-page` | `login.esp`, `getsoftwarepage.esp` |
| [GlobalProtect Portal Home Page](globalprotect-portal-home-page.md) | `global-protect-portal-custom-home-page` | `logout.esp`, portal home page |
| [URL Filtering and block pages](url-filtering-response-pages.md) | nine separate objects | dataplane injection into user traffic |

The two GlobalProtect pages are the ones this reference exists for — they are the
pages with undocumented structure. The block pages are comparatively simple and are
covered in one file, per family, because their only per-page difference is which
substitution tokens they accept.

## Evidence markers

Every non-obvious claim in these files is marked. Treat them as load-bearing:

| Marker | Meaning |
|---|---|
| **[verified]** | Observed directly against a live firewall. The observation is recorded alongside it. |
| **[documented]** | Stated in Palo Alto documentation, with the URL. |
| **[inferred]** | Reasoned from evidence but not directly tested. May be wrong. |
| **[unverified]** | Assumed, carried forward, never checked. Treat as a lead, not a fact. |

Where a claim was wrong earlier and later corrected, the correction says so. Knowing
which beliefs have already failed is worth more than a clean-looking document.

## Constraints that apply to both GlobalProtect pages

### Import size ceiling: 16,170 bytes **[verified]**

The limit is enforced on the **base64-encoded** form of the file, not the file itself.
A 24,000-byte import was refused with:

```
page can be at most 21845 characters, but current length: 32422
```

32,422 is exactly `len(base64.encodebytes(24_000 bytes))` — standard base64 wrapped at
76 columns with a trailing newline. Working back from the 21,845-character cap:

| Raw bytes | Encoded chars | Result |
|---|---|---|
| 16,000 | 21,617 | accepted **[verified]** |
| **16,170** | 21,844 | largest that fits **[inferred]** |
| 16,171 | 21,848 | over **[inferred]** |
| 20,000 | 27,019 | refused **[inferred]** |
| 24,000 | 32,422 | refused **[verified]** |

Both endpoints were tested; the exact boundary is arithmetic from the cap PAN-OS
quoted. 21,845 is `floor(65535 / 3)`, which reads like a 64 KB field cap divided by
three rather than by the 4/3 base64 actually expands at.

**This failure is loud.** The import is refused with the message above. That makes it
the *only* failure mode in this document that tells you what went wrong.

Do not borrow `MAX_BYTES = 17999` from `validate.py` here — that is a serving-time
limit for a different page class. See
[URL Filtering and block pages](url-filtering-response-pages.md).

### Content-Security-Policy **[verified]**

Served on portal responses:

```
Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline';
                         img-src * data:; style-src 'self' 'unsafe-inline';
```

Read directly, this permits more than expected:

| Directive | Consequence |
|---|---|
| `script-src 'self' 'unsafe-inline'` | Inline `<script>` **allowed**. External scripts same-origin only. |
| `style-src 'self' 'unsafe-inline'` | Inline `<style>` **allowed**. External stylesheets same-origin only. |
| `img-src * data:` | Images from **any** origin, and `data:` URIs. |
| `default-src 'self'` | Everything else same-origin. No `font-src`, so **external webfonts are blocked**. |

This corrects an earlier belief that the CSP blocked external assets outright. It
blocks external *stylesheets and scripts*; external images are permitted. Inline CSS
and JS — which every technique in these files depends on — are explicitly allowed.

Self-contained pages remain the right default regardless: an external image is a
third party who can see every portal visitor's IP and user-agent, and a load-bearing
one turns their outage into your broken login page.

### No raw `<` outside a tag **[verified]**

The factory files contain **zero** raw `<` characters outside real tags. A file
containing one — `for (var i = 0; i < n; i++)` is the obvious way to get there — was
observed to break `<pan_form/>` substitution, leaving the login form dumped at the end
of the document.

Consequences for anything generating these files:

- No counting loops in JS. Use `[].forEach.call(...)`.
- No building markup in JS. `el.innerHTML = '<a href=…>'` is disqualified; put the
  markup in the body and have JS rewire it.
- Comments count. Prose containing `<` is as dangerous as code containing it.

## Auth methods that bypass these pages entirely **[documented]**

With SAML or Cloud Identity Engine, the browser is redirected to the IdP and
`login.esp` never renders. Confirmed indirectly but solidly by a Palo Alto KB that
*exploits* the redirect to suppress the portal page.

Customizing the login page is therefore worth doing when authentication is local,
LDAP or RADIUS, or when Clientless VPN is in use. On a SAML-fronted portal it styles a
page nobody loads; the branding lever there is the `auth-response-page` CLI (PAN-OS
10.2.11+, not on Panorama, not enabled by default).

The **logout** page still renders on SAML deployments.

## Tooling

Working scripts live in `tmp/gp-lab/` and are not part of the package:

| Script | Purpose |
|---|---|
| `preflight.py` | All checks above, before upload. Knows both GP file shapes. |
| `build.py` | Strips comments and indentation. Not a minifier — deliberately. |
| `splice.py` | Reproduces `login.esp` / `getsoftwarepage.esp` locally from captured prefixes. |
| `splice-logout.py` | Reproduces `logout.esp` locally. |
| `make-logo.py` | Builds the scheme-aware logo as a `data:` URI. |
| `probe.py` | Emits padded copies to test the import ceiling. |

**The simulators have twice invented failures the live page did not have** — once by
splicing the login prefix onto the download form, once through `file://` breaking
absolute asset paths. They are useful for iteration. Live verification is the arbiter.

## Open questions

| Question | Why it matters |
|---|---|
| Does the 21,845-char import cap apply to URL Filtering pages too? | If yes, `MAX_BYTES = 17999` is unreachable — you could never import a file that large. One upload settles it; `tmp/gp-lab/probe-urlfilter-17000.html` is built for it. |
| What does the portal **home** page look like? | Never captured. The lab redirects login straight to `getsoftwarepage.esp`. Its Bootstrap body is unstyled and deliberately left alone. |
| Does PAN-OS sanitize imports? | **[verified] no** for CSS — a `<style>` block came back byte-identical, 5,456 B in, 5,456 B out. Untested for other constructs. |
| Which PAN-OS version was this? | See [Test environment](#test-environment). Unrecorded. |
