# GlobalProtect Portal Home Page

**Import object:** `global-protect-portal-custom-home-page`
**Location:** Device → Response Pages → GlobalProtect Portal Home Page
**Serves:** `logout.esp` **and** the portal home page

Shared constraints — import ceiling, CSP, the no-`<` rule, upgrade exposure — are in
the [architecture reference](general.md).

> **This import has a different shape from the login page.** It is script-only. Rules
> that hold for
> [the login page](globalprotect-portal-login-page.md) do not carry over.

## File shape: script-only **[verified]**

The factory file is 1,840 bytes of pure `<script>`. **No markup at all** — no
`</head>`, no `<body>`, no `</html>`, and no `pan_form` token.

PAN-OS embeds it verbatim into the `<head>` of the pages it serves and writes both
bodies itself. Verified against a live `logout.esp`, where the block appears character
for character.

```
┌─ PAN-OS ───────────────────────────────────────────────────┐
│ <!DOCTYPE html><html><head>                                │
│   meta, <title>, favicon                                   │
│   bootstrap.min.css, latofonts.css, login.css,             │
│   ie10-viewport-bug-workaround.css                         │
│   jquery.min.js                                            │
│   ┌─ YOUR FILE, embedded verbatim ─────────────────────┐   │
│   │ <script> the fourteen variables </script>          │   │
│   │ …anything else you add lands here, mid-<head>…     │   │
│   └────────────────────────────────────────────────────┘   │
│   $(document).ready(…) applying the variables              │
│ </head>                                                    │
│ <body> …PAN-OS' markup, which you cannot change… </body>   │
└────────────────────────────────────────────────────────────┘
```

### What this rules out

**No markup can be added.** No card wrapper, no decorative elements, no extra
containers. Styling works on the body PAN-OS already wrote.

Two techniques close most of that gap:

- **Extra elements become pseudo-elements.** Where the login page uses `<span>`s inside
  a `.field` div for background orbs, `body::before` and `body::after` render the same
  thing with no markup.
- **The existing wrapper becomes the card.** `.loginscreen_logo` is the only element
  wrapping all the content, so it takes the treatment the login page splits across two
  nested divs.

### What it permits

Despite being nominally script-only, **`<style>` and additional `<script>` blocks are
accepted and served** — the file is embedded into an open `<head>`, which is a legal
place for both. **[verified]**

Critically, the block lands **after** the stylesheet links, so the stock sheets can
still be disabled from here.

## Two pages, one file — and only one is styled **[verified]**

| URL | Body | Status |
|---|---|---|
| `logout.esp` | Small: logo, heading, message, button | **Styled** |
| Portal home page | Bootstrap navbar, dropdowns, app tiles | **Deliberately untouched** |

The reference implementation gates its restyle on the URL:

```js
if (location.pathname.indexOf('logout.esp') === -1) return;
document.documentElement.setAttribute('data-gp', 'logout');
```

**Why URL and not DOM:** this runs in `<head>`, so `#taLogout` has not been parsed and
cannot be tested for.

**Why gate at all:** disabling Bootstrap on the portal home page would leave a
navbar-and-tiles layout with nothing to replace it — worse than stock. The home page
has never been captured (the reference lab redirects login straight to
`getsoftwarepage.esp`), so nothing was written for a body nobody has seen.

If you need the home page styled, capture it first.

## Customization variables **[documented]**

Fourteen, all of which must be declared — PAN-OS's ready handler dereferences each one
and a missing name throws a `ReferenceError`.

| Variable | Purpose |
|---|---|
| `favicon` | URL for the address-bar icon |
| `logo` | URL for the company logo — a `data:` URI qualifies |
| `navbar_text` | Navigation bar text *(home page)* |
| `navbar_text_color` | Navigation bar text colour *(home page)* |
| `navbar_bg_color` | Navigation bar background *(home page)* |
| `dropdown_bg_color` | Dropdown menu background *(home page)* |
| `bg_color` | Main background colour |
| `label_custom_app_url` | Label for the custom/internal application URL *(home page)* |
| `display_globalprotect_agent` | `1` to show the agent download entry *(home page)* |
| `label_globalprotect_agent` | Label for that entry *(home page)* |
| `gp_portal_name` | Text under the logo *(logout page)* |
| `gp_portal_name_color` | Colour for that text *(logout page)* |
| `logout_text_array` | **Array of seven logout messages** — see below |
| `logout_text_color` | Colour for the logout message |

`gp_portal_name` is applied with `$('#heading').html(…)` — **`.html()`, not `.text()`**.

Leave a variable empty to keep control in CSS; a non-empty value overrides the
stylesheet at ready time.

### `logout_text_array` **[verified]**

Seven messages, selected by the `code` query parameter — `logout.esp?code=N` renders
`logout_text_array[N]`. Verified for `N` absent (index 0) and `N=1` (index 1).

| Index | Message |
|---|---|
| 0 | You have successfully logged out of GlobalProtect portal. |
| 1 | The GlobalProtect portal is not licensed. Purchase or activate the license for your GlobalProtect subscription. |
| 2 | User not authenticated to GlobalProtect portal. |
| 3 | System error, contact system administrator. |
| 4 | System error, failed to delete user session. Contact system administrator. |
| 5 | Can not create user session. Max-capacity reached. Contact system administrator. |
| 6 | Your login session has expired and you have been logged out for security reasons. Please log in again if you wish to continue. |

**This array is editable** — it is a variable in your file, not fixed by PAN-OS. It is
the only supported way to change logout wording. Keep all seven entries and the order;
the index is chosen by PAN-OS.

Messages 3 and 4 are visible to end users but actionable only by an administrator, so
rewriting them to name a real support contact is a genuine improvement rather than
cosmetics.

## DOM contract — `logout.esp` **[verified]**

Fixed by PAN-OS. Restyle in place; none of it can be changed.

```html
<div class="loginscreen_logo">
  <div id="logo"><img src="/global-protect/portal/images/logo-pan-48525a.svg" alt=""></div>
  <div id="activearea">
    <div id="heading">GlobalProtect Portal</div>
    <div id="formdiv">
      <form name="login_form" id="login_form">
        <div id="logout" class="msg"> </div>
        <div id="taLogout">
          <input class="buttonFixed-logout" type="button" id="submit"
                 value="Log In Again" onclick="location.href = '/global-protect/login.esp';">
        </div>
      </form>
    </div>
  </div>
</div>
```

| Selector | Notes |
|---|---|
| `.loginscreen_logo` | Only element wrapping everything — the natural card |
| `#logo img` | **Hard-coded to the Palo Alto SVG** — see below |
| `#heading` | Stock text; overridden by `gp_portal_name` if set |
| `#logout` | **Empty at parse time**; filled at ready. Give it a `min-height` or the card resizes when text lands |
| `.buttonFixed-logout` | The "Log In Again" button |

## The stock logo flashes — fix it in CSS **[verified]**

PAN-OS hard-codes `<img src="…logo-pan-48525a.svg">` into the body. The browser
**fetches and paints** the Palo Alto mark, and only at `$(document).ready` does jQuery
rewrite the src from `logo`. The wrong logo is visibly on screen in between.

The login page avoids this by shipping the `<img>` with no `src` — not possible here,
because the body belongs to PAN-OS.

**A stylesheet applies at first paint.** Move the artwork into CSS and hide the img:

```css
html[data-gp=logout] #logo{
  height:2.2rem;
  background:url("data:image/svg+xml,…") left center/contain no-repeat}
html[data-gp=logout] #logo img{display:none}
```

`display:none` means the img's `src` never matters, whatever jQuery does to it later.

Verified by aborting `jquery.min.js` at the network layer against the live portal: the
logo still renders. Nothing about it is script-dependent, so the flash cannot recur.

> Keep `logo` set anyway. The same variable brands the **portal home page**, which this
> file does not restyle. The URI is carried twice, once per page — about 950 B against
> a 16,170 B ceiling.

## Checklist

```
✓ Script-only — no </head>, no <body>, no </html>
✓ No <pan_form/> — there is no form to place
✓ All fourteen variables declared
✓ logout_text_array keeps all seven entries, in order
✓ No raw '<' outside a tag, comments included
✓ Restyle gated so the portal home page is untouched
✓ Logo painted from CSS, stock img hidden
✓ #logout has a min-height
✓ ≤ 16,170 bytes (≤ 21,845 base64 chars)
✓ Verified with jQuery blocked — no logo flash
```

`tmp/gp-lab/preflight.py` detects this file shape via `logout_text_array` and applies
these rules instead of the login page's.
