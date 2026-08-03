# GlobalProtect portal pages

Two imports, styled across all seven themes, covering four surfaces of the
GlobalProtect portal.

| Import object | Serves | Styled |
|---|---|---|
| `global-protect-portal-custom-login-page` | `login.esp` | yes |
| | `getsoftwarepage.esp` | yes |
| `global-protect-portal-custom-home-page` | `logout.esp` | yes |
| | portal home page | **no — deliberately** |

## Read this before you deploy

**SAML and Cloud Identity Engine bypass the login page entirely.** The browser is
redirected to the identity provider and `login.esp` never renders. On a
SAML-fronted portal, styling it customises a page nobody loads.

The **logout page still renders** on SAML deployments, so the home import is
worth deploying either way. The login import is worth deploying when
authentication is local, LDAP or RADIUS, or when Clientless VPN is in use.

If your portal is SAML-fronted and you want branding on the authentication step
itself, the lever is the `auth-response-page` CLI (PAN-OS 10.2.11+, not
available on Panorama, not enabled by default) — not this project.

## Why the portal home page is left alone

The home import serves both `logout.esp` and the portal home page, but only the
logout page is restyled. The restyle is gated on the URL:

```js
if (location.pathname.indexOf('logout.esp') !== -1) { … }
```

The home page is a Bootstrap navbar with dropdowns and application tiles.
Disabling the stock stylesheets there would leave that structure with nothing to
replace it — worse than stock. It has never been captured against a live portal,
and nothing was written for a body nobody has seen. If you need it styled,
capture it first.

## Build

Portal pages build with everything else:

```bash
panos-response-pages build
```

| Path | What |
|---|---|
| `out/deploy/<theme>/<palette>/portal/login.html` | The login import. Upload this. |
| `out/deploy/<theme>/<palette>/portal/home.html` | The home import. Upload this. |
| `out/preview/<theme>/<palette>/portal/…` | **Preview only. Never upload.** |

Preview files are spliced with PAN-OS's own captured prefix and a sample form so
they render in a browser — neither import is a document on its own. A spliced
file contains markup PAN-OS supplies itself and an inert CSRF token; importing
one would break the page.

The preview covers all four login states, because a page that only looks right
in the default state is not finished:

| State | When a user sees it |
|---|---|
| default | every sign-in |
| error | wrong credentials |
| challenge | MFA prompt |
| **change password** | **expired password — taller than the viewport, where layouts break** |

## Import

`Device > Response Pages > GlobalProtect Portal Login Page` (and
`… Home Page`), then commit. Both are per-vsys.

## Configuration

| Key | Purpose |
|---|---|
| `portalName` | Heading under the portal logo |
| `portalLogoSvg` | Portal mark — the symbol only, as SVG source |
| `portalLogoSvgDark` | Optional. Different dark-scheme artwork |
| `logoutMessages` | The seven logout messages, in order |
| `company`, `supportEmail` / `supportUrl` | Shared with the block pages |

### `portalLogoSvg`

**The symbol only — no company name.** The name is rendered as text beside it,
from `company`, exactly as the block pages do it. So renaming the company is a
one-key edit and nothing else has to change:

```json
{ "company": "Northwind Logistics" }
```

Do not draw the name into the artwork. An SVG cannot measure text against a
fixed viewBox, so a longer name is clipped and a shorter one renders undersized
— and it could not follow a rename anyway, which is how you end up with a page
that *shows* one company and *announces* another to a screen reader.

Keep it square; it is drawn into a square box beside the text.

Plain SVG source, not a `data:` URI — the build does the percent-encoding, and
it cannot encode something already encoded. It is a separate key from `logoSvg`
because the portal takes the mark as a URI rather than as inline markup.

The artwork is rendered as an **isolated document**: it inherits nothing from
the page, so `currentColor` is dead and the shell's custom properties are out of
scope. Colours have to be baked in. So write them as `S_*` tokens and the build
resolves them:

```xml
<rect width='32' height='32' rx='9' fill='{{S_ACCENT}}'/>
<path d='…' fill='{{S_ACCENT_INK}}'/>
```

Every palette colour is available as `S_<NAME>` — `S_ACCENT`, `S_ACCENT_INK`,
`S_INK`, `S_GROUND` and so on. There is deliberately no `S_D_*`: the build
renders the file **twice**, binding `S_*` to the palette's light values for one
copy and its `d_` values for the other, and the shells switch between the two
copies in CSS. A literal hex here is a logo that stays one colour whatever
palette the build was given.

Use single quotes for attributes.

Themes that stand the logo on the accent rather than on the page ground — Accent
Banner does — get a third and fourth rendering in which figure and ground swap,
so an accent mark does not disappear into an accent band. That is the shell's
choice, not a config key.

### `portalLogoSvgDark`

Only needed when the dark mark is genuinely different *artwork* — a different
symbol, a knockout treatment. Left unset, the dark copy is `portalLogoSvg` with
`S_*` bound to the dark palette, which is what a mark drawn from the tokens
wants.

### `logoutMessages`

Seven entries, and the order is fixed — PAN-OS selects one by index via
`logout.esp?code=N`. This array is the only supported way to change logout
wording.

Entries 3, 4 and 5 are system errors an end user cannot act on. The stock text
tells them to "contact system administrator", which names a role they have no way
to reach, so the shipped defaults name `supportEmail` instead. That is a genuine
improvement rather than cosmetics.

A config with `supportUrl` set renders the same messages naming the label *and*
the ticket URL as plain prose — e.g. "Contact the Service Desk at
https://tickets.example.com/new" — rather than just the label. PAN-OS fills this
text in with `.text()`, so it cannot carry a link the way the rest of the portal
does; the URL itself has to be part of the words the user reads, or there is no
way to actually reach the queue named.

## Byte ceiling

**16,170 bytes per import**, enforced on the base64-encoded form (21,845
characters). This is not the block pages' 17,999 B limit — different mechanism,
different number.

This is the one failure PAN-OS reports properly. An oversize import is refused
outright with the encoded length quoted back at you, rather than being accepted
and silently ignored. The build fails first regardless, and reports both figures.

Every shipped theme uses roughly half the ceiling, so there is room for a larger
logo or additional copy.

## Upgrading an existing data directory

If you ran `init` before portal support existed, your data directory has no
`templates/portal/` and no `fixtures/`. Refresh it:

```bash
panos-response-pages init --force
```

The resolver falls back to the packaged templates and warns rather than failing
the build, but a refreshed directory is the supported state.

## Further reading

The protocol-level behaviour — file shapes, substitution semantics, the CSRF
token, the states, and what was measured versus assumed — is documented per page
under [Architecture](architecture/general.md). Every non-obvious claim there
carries an evidence marker.
