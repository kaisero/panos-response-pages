# GlobalProtect Portal Login Page

**Import object:** `global-protect-portal-custom-login-page`
**Location:** Device → Response Pages → GlobalProtect Portal Login Page
**Serves:** `login.esp` **and** `getsoftwarepage.esp`

Shared constraints — import ceiling, CSP, the no-`<` rule, upgrade exposure — are in
the [architecture reference](general.md). This file covers what is specific to this page.

## File shape: a body fragment, not a document **[verified]**

The import is **not** a complete HTML document. PAN-OS emits a fixed prefix and
concatenates the file onto it. The file must therefore close `</head>` itself and
supply the entire `<body>`.

```
┌─ PAN-OS prefix (8,394 B on login.esp) ─────────────────────┐
│ <html lang="en"><head>                                     │
│   meta, <title>, favicon                                   │
│   bootstrap.min.css, latofonts.css, login.css,             │
│   ie10-viewport-bug-workaround.css                         │
│   jquery.min.js, ie10-viewport-bug-workaround.js           │
│   loadPage(), submitClicked(), checkCapsLock()             │
│   $(document).ready(…) applying the six variables          │
│   ← head still OPEN                                        │
└────────────────────────────────────────────────────────────┘
┌─ YOUR FILE starts here ────────────────────────────────────┐
│ <script> the six variables </script>                       │
│ <style> … </style>                                         │
│ </head>                                                    │
│ <body> … <pan_form/> … </body></html>                      │
└────────────────────────────────────────────────────────────┘
```

Verified by locating the factory file byte-for-byte inside a served page: the custom
content began at offset 8,394, with `<head>` still open.

The prefix differs per page: **8,394 B** on `login.esp`, **1,797 B** on
`getsoftwarepage.esp` — and the download page's prefix has **no `loadPage()` or
`submitClicked()` at all**.

### `login.esp` is served in quirks mode **[verified]**

The login prefix opens `<html lang="en">` with **no `<!DOCTYPE>`**. Both
`getsoftwarepage.esp` and `logout.esp` carry one, so this is specific to the login
page and cannot be fixed from the import — the prefix is emitted ahead of it.

The consequence is not cosmetic. In quirks mode the **body is the scrolling
element**, so a layout that centres its card with `display:flex` on `body` cannot
scroll: the change-password state sits below the fold and no wheel event reaches
it. Centre on the card wrapper, never on `body`.

Found by driving all six shipped themes in a headless browser. Only the shell that
had inherited body-centring from its block-page ancestor was affected, and only in
the change-password state — which is precisely the state a live portal reveals
last.

## One file, two pages **[verified]**

`getsoftwarepage.esp` serves this **same import**. A `<style>` block came back
byte-identical on both URLs. PAN-OS substitutes the `pan_form` token differently:

| URL | Token expands to |
|---|---|
| `login.esp` | `<form name="login" id="login_form">` — credentials, 2,066 B |
| `getsoftwarepage.esp` | `<form name="getsoftwarepage" id="getsoftwarepage_form">` — agent downloads, 1,588 B |

A page styled only for the login form will render the download page badly. Detect
context and switch:

```html
<script>if(document.getElementById('getsoftwarepage_form'))
  document.documentElement.setAttribute('data-page','sw')</script>
```

Place it **after** the token so the injected form is already parsed. Default to the
login presentation, so a page where the script never runs degrades to the login
wording rather than to nothing.

## `<pan_form/>` semantics **[verified]**

Three behaviours, none documented, each with teeth:

**1. It is inserted *after*, not replaced.** The literal token survives in the output:

```html
<div id="formdiv">
  <pan_form/>
<div id="activearea">
  <div id="formdiv">
  <form name="login" id="login_form" …
```

Note the injected fragment brings its **own** `id="activearea"` and `id="formdiv"`,
producing duplicate ids. Invalid HTML, unavoidable while using the token, benign in
practice — but do not write CSS or JS that assumes those ids are unique.

**2. Only the first occurrence is substituted, and context is ignored.** A token
written inside a CSS comment wins. The observed result: the entire login form injected
into the `<style>` block, where the browser swallows it as stylesheet text, and the
real token left unexpanded. Symptom is unstyled form fields stretched across the
bottom of the page.

> Name the token in prose, never write it literally outside the body. `preflight.py`
> fails a file with more than one.

**3. Omitting it does not remove the form.** PAN-OS force-appends the login form at
the end of the document. Community testing confirms a file containing only
`<html></html>` still renders a form. The failure is cosmetic — form outside your
layout — not functional.

## The CSRF token **[verified]**

The injected form carries:

```html
<input type="hidden" name="csrf-token" value="lE50gDIGwTn3X1Y8S6Nuu55uUhg:1785261531211">
```

`<random>:<epoch-millis>`, generated **server-side per page load**, inside the
`pan_form` substitution.

> **The "view source and paste" recipe breaks logins.** A widely circulated workaround
> is: render the page, copy the output HTML into your custom page, drop the pan_form
> token. On current PAN-OS that bakes in a stale token and authentication fails.
> Keep the token; let PAN-OS inject a live one.

Undocumented, and added at some point after a 2020 customer request for CSRF
protection with no release-note coverage. `preflight.py` fails any file containing a
literal `csrf-token` value.

## Customization variables **[documented]**

All six must be declared. PAN-OS's own `$(document).ready` handler dereferences each
one; a missing name throws a `ReferenceError` and aborts the handler.

| Variable | Applied as | Notes |
|---|---|---|
| `favicon` | `$('link[rel="shortcut icon"]').attr('href', …)` | URL |
| `logo` | `$('#logo img').attr('src', …)` | URL — a `data:` URI qualifies |
| `bg_color` | `$('body').css('background', …)` | |
| `gp_portal_name` | `$('#heading').html(…)` | **`.html()`, not `.text()`** |
| `gp_portal_name_color` | `$('#heading').css('color', …)` | |
| `error_text_color` | `$('#dError').css('color', …)` | |

Leave a variable **empty** to keep control in your own CSS — a non-empty value
overrides what the stylesheet did, at ready time.

These six are the entire *documented* customization surface. Everything else in this
file is undocumented behaviour that happens to work.

## DOM contract

`loadPage()` and `submitClicked()` look these up by id. All arrive via `pan_form`;
restyle them where they stand rather than restructuring.

| Id | Role |
|---|---|
| `user`, `passwd` | credential inputs |
| `new_passwd`, `confirm_new_passwd` | change-password inputs, hidden by default |
| `dUserName`, `dPassword`, `dNewPassword`, `dConfirmNewPassword` | field wrappers |
| `dInputStr` | MFA challenge prompt |
| `dError` | failure message |
| `taLogin` | form container, hidden on submit |
| `dChangePasswordMsg` | password-expiry message |
| `submit` | submit button, `class="buttonFixed"` |
| `dCAC` | referenced by `loadPage()` but **not present** in the injected form |

`submitClicked()` sets three hidden fields — `prot`, `server`, `action=getsoftware` —
and the form has **no `action` attribute**. There is no `<noscript>`.

> **The factory login page already requires JavaScript.** Without it the form posts
> empty hidden fields and login cannot complete. Techniques here that depend on JS add
> no new requirement.

## States to test

Four, all driven by `loadPage()` from server-set variables. A page that only looks
right in the default state is not finished — the change-password state is the one that
breaks layouts, and it only appears on an expired password.

| State | Trigger | Effect |
|---|---|---|
| Default | `respStatus = "Success"` | username + password |
| Error | `respStatus = "Error"` | `#dError` shown, message as `<li>…` with no list around it |
| MFA challenge | `respStatus = "Challenge"` | `#dUserName` hidden, `#dInputStr` shows the prompt |
| Change password | `isChangePasswdForm = 1` | two extra inputs + message; **grows taller than the viewport** |

That last one is a trap: clamping `overflow` on both axes to suppress orb scrollbars
silently cuts it off. Clamp `overflow-x` only.

## Neutralising the stock stylesheets **[verified]**

`bootstrap.min.css` and `login.css` are linked by the prefix and cannot be removed at
source — but they are in the DOM by the time your file parses, and a disabled sheet
stops applying:

```js
[].forEach.call(document.getElementsByTagName('link'), function (l) {
  if (l.rel === 'stylesheet') { l.disabled = true; }
});
```

Written without a counting loop deliberately — see the no-`<` rule.

Disable **all four**, `latofonts.css` included, if your styles use a system font
stack. Those files ship in the Clientless VPN content package, not in your import, and
that package can 404 after an upgrade. Verified by deleting `portal/css/` entirely and
re-rendering: pixel-identical.

The stock sheets are still *fetched* (200) — `disabled` stops them applying, not
loading. Check `disabled: true` and `body` `background-image: none`, not the network
tab.

## Logo without a flash **[verified]**

The documented path is an `<img>` with **no `src`**, filled by the `logo` variable at
`$(document).ready`. It works, and it costs more than it is worth:

- The mark is absent until jQuery has loaded and run. On a preview served without the
  captured `portal/` tree, that is an empty box forever.
- An `<img>`-referenced SVG renders as an **isolated document**. `currentColor` is
  dead there, the page's custom properties are out of scope, and one `src` means one
  asset — so the only way to react to the scheme is a `@media (prefers-color-scheme)`
  block inside the SVG. That query tracks the browser setting and nothing else, so a
  page that forces a scheme (a preview, a print sheet) cannot move the logo with it.

Paint it as a **CSS background** instead, leave `logo` empty, and ship no `<img>` at
all. A stylesheet applies at first paint, and the choice between two whole copies of
the artwork is then an ordinary cascade the page can reach:

```css
:root{--lgl:url("data:image/svg+xml,…light…");
--lgd:url("data:image/svg+xml,…dark…");--lg:var(--lgl)}
@media(prefers-color-scheme:dark){:root{--lg:var(--lgd)}}
html[data-force-scheme=dark]{--lg:var(--lgd)}
#logo{height:2.2rem;background:var(--lg) left center/contain no-repeat}
```

Define each copy once and select through `--lg`; naming them in every rule set carries
the artwork that many times, and it is around 700 bytes a copy. Reserve the height
either way. The `<div>` carrying the background needs `role="img"` and an
`aria-label` — a background image is invisible to a screen reader.

`logo` still has one job: the portal **home** page, which is stock Bootstrap markup
and out of scope for a restyle. That is an `<img>` src with no way to be told the
scheme, and the page is light in either case, so it takes the light copy.

The isolation cuts the other way too: the artwork cannot inherit the theme, so its
colours must be substituted in at build time. Baking a hex in means a logo that stays
one colour whatever palette it is built with.

For the same reason, **keep the company name out of the artwork**. SVG cannot measure
text against a fixed viewBox, so a name drawn in is clipped when it is long and
undersized when it is short — and it cannot follow a rename in config, which leaves a
page showing one company while its `aria-label` announces another. Ship a square
symbol and put the name beside it as text. On the login page that is a `<span>`, in a
body we own. On the logout page the body is PAN-OS', so the only way in is our own
stylesheet:

```css
#logo{display:flex;align-items:center;gap:.55rem}
#logo img{display:none}
#logo::before{content:"";width:1.9rem;height:1.9rem;background:var(--lg) center/contain no-repeat}
#logo::after{content:"Northwind Logistics"}
```

That also shrinks the imports — the name is no longer carried twice inside two copies
of an SVG — and lets it take its colour from the cascade, which is what makes it read
correctly on a theme that stands the lockup on a coloured band.

Percent-encode `'`, `<`, `>` and `#` in the URI. `#` is mandatory or everything after
the first colour reads as a fragment; the quotes and angle brackets are what let the
URI sit inside a JS string literal without ending it, and keep the file compliant with
the no-`<` rule.

One more trap, and it is invisible until you change palette: a theme that stands the
logo on the **accent** — a coloured banner — needs its own copy of the symbol with
figure and ground swapped. The ordinary copy paints an accent mark onto an accent
field. The text beside it needs no such copy: `color:inherit` is already right,
because the band has set it.

## The download page (`getsoftwarepage.esp`) **[verified]**

Injected markup is table layout with presentational attributes and an inline
`padding-top` on the outer table — inline styles outrank a stylesheet, so width and
padding resets need `!important`.

| Selector | Contents |
|---|---|
| `#getsoftwarepage_form` | outer `<form>` |
| `#taGetSofewarePage` | content wrapper — **note PAN-OS's typo, "Sofeware"** |
| `#taGetSofewarePage p a` | one anchor per download |
| `#dDescription32`, `#dDescription64`, `#dDescriptionMac` | description rows |
| `#dFormat` | empty in the observed lab |

Anchor hrefs are stable and parseable:

```
/global-protect/getmsi.esp?version=32&platform=windows
/global-protect/getmsi.esp?version=64&platform=windows
/global-protect/getmsi.esp?version=none&platform=mac
```

That is a page whose entire content is a decision the browser has already made, so
replace it with one button for the detected platform and a menu for the rest.

**Move** PAN-OS's anchors into your own markup rather than building new ones —
`innerHTML` with a `<` is disqualified, and moving the nodes means the hrefs are never
retyped and cannot drift. Relabel them in place (`textContent`, never markup) and
append them to the menu.

Four rules learned the hard way:

- **Hide the stock list only after the replacement is built.** Gate it on an attribute
  the script sets last, so a thrown exception, a blocked script or an unfamiliar
  platform leaves working links behind rather than an empty card. The description rows
  go with the links — they exist to answer the question the button now answers — but
  they stay styled for the fallback, because this import disables the stock sheets.
- **Do not style the first anchor as primary.** PAN-OS lists Windows 32-bit first;
  picking by DOM position steers users onto a 32-bit build. Detect the platform or
  weight all options equally. `Win64|WOW64|x64|x86_64` in the user-agent is a reliable
  64-bit signal; bit-ness is not otherwise detectable, and an unrecognised platform
  should say so rather than guess.
- **No counting loop.** `i < n` is a raw `<`. `[].slice.call(nodeList)` plus `forEach`
  does the same work and keeps the file compliant.
- **Stop the click propagating** when the button itself opens the menu. A handler that
  only calls `toggle()` lets the event reach the document's close-on-click listener,
  and the menu opens and shuts in the same tick — visible as a menu that never opens,
  on the one path (unrecognised platform) least likely to be tested.

## Checklist

```
✓ Fragment, not a document — no <!DOCTYPE>, closes </head>, ends </html>
✓ Exactly one <pan_form/>, in the body, never in a comment
✓ No raw '<' outside a tag, comments included
✓ All six variables declared
✓ No baked-in csrf-token
✓ ≤ 16,170 bytes (≤ 21,845 base64 chars)
✓ Renders on login.esp AND getsoftwarepage.esp
✓ All four login states, light and dark
✓ A real login completes
```

`tmp/gp-lab/preflight.py` enforces every static item.
