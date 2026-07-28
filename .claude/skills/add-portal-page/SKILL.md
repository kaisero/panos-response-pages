---
name: add-portal-page
description: Add or change a GlobalProtect portal page in panos-response-pages. Use when working on the portal login page, the portal home/logout page, or a new portal-family surface (captive portal comfort, MFA login, SAML error) — anything PAN-OS serves as a fragment or a bare script rather than a whole document. For URL-filtering and block pages use add-response-page instead.
---

Integrate or change a GlobalProtect portal page end to end: file shape,
variables, per-theme shells, guards, spliced preview, docs.

**The portal family is not the block-page family.** Block pages are complete
documents that explain a block. Portal pages are fragments PAN-OS assembles into
its own markup, around a form it injects and a DOM it owns. The byte ceiling is
different, the failure modes are different, and the slot contract is different.
Do not carry block-page habits across.

Protocol-level detail lives in `docs/architecture/`. Every claim there carries an
evidence marker — **[verified]** means it was measured against a live firewall.
Trust those markers over anything you infer from the code.

## 1. Establish the file shape first

This is the decision everything else depends on, and the two shipped imports
disagree:

| Import | Shape |
|---|---|
| `global-protect-portal-custom-login-page` | **Body fragment.** PAN-OS emits `<html>` and an open `<head>`; the file closes `</head>`, supplies the whole `<body>`, ends `</html>`, and carries the form token. |
| `global-protect-portal-custom-home-page` | **Script-only.** Embedded verbatim mid-`<head>`. No `</head>`, no `<body>`, no `</html>`, no form token. PAN-OS writes both bodies itself. |

`detect_kind()` in `portal/validate.py` discriminates them by the presence of
`logout_text_array`, which only the home import has.

A whole document is always wrong. `<!DOCTYPE>` in either file is an error.

## 2. One import serves two URLs

Neither import maps to one page:

| Import | Also serves | Consequence |
|---|---|---|
| login | `getsoftwarepage.esp` | Same file, **different injected form**. A page styled only for login renders the download page badly. Detect via `#getsoftwarepage_form` and switch on `data-page`. |
| home | portal home page | Deliberately **not** restyled. Gate on `location.pathname`, not the DOM — this runs in `<head>`, before the body is parsed. |

The prefixes are asymmetric too: 8,394 B for `login.esp`, 1,797 B for
`getsoftwarepage.esp`, and the download prefix has no `loadPage()` or
`submitClicked()` at all. Splicing the wrong prefix onto a form invents errors
the live page does not have.

## 3. Declare every variable

Six on login, fourteen on home — the lists are `LOGIN_VARS` and `HOME_VARS` in
`portal/validate.py`. PAN-OS's own `$(document).ready` handler dereferences each
one; **a single missing name throws `ReferenceError` and aborts the whole
handler**, losing every customization at once.

Leave a variable **empty** to keep control in CSS. A non-empty value overrides
the stylesheet at ready time. Three exceptions, each with a reason:

| Variable | Value | Why |
|---|---|---|
| `logo` | the data URI | Login ships its `<img>` with no `src`; this is the only thing that fills it. |
| `display_globalprotect_agent` | `1` | `''` is falsy and removes the agent entry from the portal home page. |
| `gp_portal_name` | **empty on login**, set on home | PAN-OS runs `$('#heading').html(…)` when non-empty. On login that heading holds the login/download switch spans, and setting the variable wipes them — the download page then reads "Sign in" forever. The login heading takes its text from the shell markup instead. |

That last one is the trap most worth remembering: it is silent, and it only
shows on the surface you are least likely to open.

## 4. Rules that break the page silently

Each of these was measured. None produces an error anywhere.

- **No raw `<` outside a tag, comments included.** `i < n` is the obvious way to
  get one. A naive tag scanner reads it as the start of a tag and **the form
  token stops being substituted**. Use `[].forEach.call(…)`, never a counting
  loop; never build markup in JS.
- **Exactly one form token, in the body, never in a comment.** PAN-OS
  substitutes the first literal occurrence and is blind to context — one inside
  a CSS comment wins, and the login form lands in your `<style>` block.
- **Never bake a `csrf-token` value.** It is generated per page load inside the
  substitution. The widely circulated "view source and paste the rendered HTML"
  recipe bakes in a stale one and breaks authentication.
- **Never `getElementById` an id PAN-OS also emits.** The injected form brings
  its own `#activearea` and `#formdiv`, so those ids are not unique.
- **Clamp `overflow-x` only.** The change-password state is taller than the
  viewport; clamping both axes truncates it, and only an expired password
  reveals that.
- **`login.esp` has no DOCTYPE** and renders in quirks mode, where the body is
  the scrolling element. Centre on the card, never on `body`.

## 5. Write the shells

`data/templates/portal/shells/<theme>.html`, with `STYLE_LOGIN`, `STYLE_LOGOUT`
and `BODY` sections. Copy the closest existing shell.

The two surfaces express a theme differently, and this is by design:

- **Login** — you own the whole `<body>`, so the theme keeps its structural
  identity (`band`/`bandin`, `rule`/`bar`, `field`/`pane`, and so on).
- **Logout** — there is **no markup at all**. The DOM is fixed:
  `.loginscreen_logo > #logo`, `#activearea > #heading`,
  `#formdiv > form > #logout`, `#taLogout > #submit`. A theme expresses itself
  decoratively: `body::before`/`::after` for orbs, `.loginscreen_logo` as the
  card.

Two per-shell rules the tests enforce, both fixing a visible flash:

- **The logout logo is painted from CSS**, with `#logo img{display:none}`.
  PAN-OS hard-codes its own `<img src>` into that body and only rewrites it at
  ready — a stylesheet is the only thing that applies at first paint.
- **`#logout` needs a `min-height`.** It is empty at parse time and filled at
  ready; without one the card visibly resizes when text lands.

Keep `STYLE_LOGIN` and `STYLE_LOGOUT` separate. Sharing one stylesheet puts the
logout rules in the login import and vice versa, and the login import is the
tighter of the two.

## 6. Byte ceiling

**16,170 B raw / 21,845 base64 chars per import.** Enforced on the encoded form.

Do **not** borrow `MAX_BYTES = 17999` from `validate.py` — that is a
serving-time limit for a different page class.

This is the one portal failure PAN-OS reports properly: it refuses the import
and quotes the encoded length back. The build fails first anyway. Sources keep
their comments; `emit.strip_output` removes them on the way out.

## 7. Verify

```bash
uv run panos-response-pages build
uv run panos-response-pages validate out/deploy
uv run nox -s tests      # not just gate: this enforces the coverage floor
```

Then look at it. `out/preview/<theme>/portal/` renders each import spliced with
PAN-OS's captured prefix, in all four login states.

**Open the change-password state.** It is where layouts break and the only state
a live portal will not show you until someone's password expires.

Preview output is spliced and **must never be imported** — it contains PAN-OS's
own prefix and an inert token. It must never be passed to `validate_portal()`
either, which rejects anything containing a `csrf-token` string.

> **The simulators have twice invented failures the live page did not have** —
> once by splicing the login prefix onto the download form, once through
> `file://` breaking absolute asset paths. They are for iteration. A live portal
> is the arbiter, and `tmp/gp-lab/*.mjs` drives one.

## 8. Documentation

- `docs/portal.md` — user-facing: config keys, build, import.
- `docs/architecture/` — protocol-level, with an evidence marker on every
  non-obvious claim. If you measured something new, record **how** you measured
  it; if you disproved something, say so rather than deleting it. Knowing which
  beliefs have already failed is worth more than a clean-looking document.
- `CHANGELOG.md` — an entry under `## [Unreleased]`.
