# Customising

Run `panos-response-pages init` first, then edit `config/_defaults.json` in the
copied tree, or add `config/<customer>.json` with only the keys
that differ — it is deep-merged over the defaults. Keys prefixed `_` are inline
documentation and are ignored by the build.

| Key | Notes |
|---|---|
| `company` | Brand row, and the credential pages' "will never ask for your password" line |
| `supportEmail` | Target of every `mailto:`. Mutually exclusive with `supportUrl` |
| `supportUrl`   | Absolute `https://` ticket-system link, used instead of `mailto:` |
| `supportLabel` | What that link is called. `supportUrl` mode only; defaults to `IT support` |
| `logoSvg` | **Inline SVG, ≤2 KB optimised.** A traced-path export can be 40 KB and will silently break the page. Use `currentColor` so it inherits the theme. |
| `continueGrantText` | Must match your URL Admin Override timeout |
| `palette` | Which palette the preview gallery opens on: `cyber-orange`, `strata-yellow` or `prisma-blue`. Every style is built in every palette regardless; override per build with `--palette`. Setting it here also outranks a style that [pins its own](styles.md#a-style-that-owns-its-colour) |
| `categories` | `category → {tone, gloss}`; tone is `calm`, `warn` or `critical`. An **empty** `gloss` means "no tailored copy" and falls back to `defaultGloss`/`riskGloss` — that is how a category earns a tone without paying for a sentence |
| `defaultGloss` | Used for any category not in the map — keep it true of every category |
| `riskGloss` | The same, for a `warn` or `critical` category. Separate because a banner reading "Security risk" over "restricted by company policy" contradicts itself |
| `redirect` | Opt-in handoff to a sanctioned app on the URL block page. Off by default — see [below](#redirecting-to-a-sanctioned-app) |

Each page declares its own `<!--@MARK-->` — an inline SVG shown as a large
indicator beside the heading, tinted by severity. `marks.warning` in config is a
separate icon used by the warning callouts.

The category map is applied **client-side**, by reading the substituted
`<category/>` value from the DOM. PAN-OS exposes no severity variable and serves
one page per type, so per-category messaging cannot happen server-side.

The two credential pages set `<!--@COPY_LOCK-->1<!--/@COPY_LOCK-->`, which pins
their tone and gloss to what the template declares. A phishing interstitial must
not be repainted calm because of how its category happens to map.

### Why the map is not all 90 categories

The Category row shows a **friendly label** — `online-storage-and-backup`
renders as "Online Storage and Backup". It is derived from the slug in the
browser rather than mapped, so all 90 PAN-OS categories get one, as will any
category Palo Alto adds after this build. An explicit label for each is ~3.3 KB
of JSON against ~0.2 KB of code, and the pages have no room for the difference.

The same arithmetic is why `categories` lists only the categories where the
default would be *wrong*. A category absent from the map renders calm with
`defaultGloss`, which is already the right answer for most of them — writing all
90 out with that same sentence adds ~5.6 KB and breaches the byte ceiling
without changing a single page. Entries are worth their bytes only for a
tailored gloss, or for a tone the default would get wrong; the latter cost
nothing but the tone, by leaving `gloss` empty.

## Sending users to a ticket system

By default every "Report to IT" action opens the user's mail client with the
incident already described — the user, the blocked address, the category and a
prompt, folded into the mail body by a small script on the page.

A customer whose front door is a ticket system sets `supportUrl` instead:

```json
{
  "company": "Example Corp",
  "supportEmail": "",
  "supportUrl": "https://example.service-now.com/sp?id=sc_cat_item&sys_id=...",
  "supportLabel": "the Service Desk"
}
```

`supportLabel` is optional and names the link. It is what a user reads where a
`mailto:` page would have printed the address — on the safe-search page and on
every portal page. Leave it out and the pages say "IT support". It has no effect
in `supportEmail` mode, where the address is its own label.

**The blank `supportEmail` line is required, not decoration.** Your customer file
is merged over `_defaults.json`, which ships a `supportEmail`; adding `supportUrl`
alone leaves both set and the build stops. Blanking is also the better habit than
deleting, because the next reader can see what the alternative was.

The URL must be absolute `https://`. A response page is served *as* the blocked
site, so a relative path resolves against whatever host the user was refused, and
an `http://` link on a page whose whole job is to be trusted is not one.

The build also rejects a `supportUrl` that would break the page rather than
just look wrong: one with no host (`https://` alone), one containing a quote,
an angle bracket, whitespace or a control character (it lands unescaped inside
`href="{{CONTACT_HREF}}"`, so any of those breaks out of the attribute), and a
`supportLabel` containing `<` or `>` (it is printed as the link text). A query
string is fine — `https://x.example.com/new?cat=1&sev=2` passes as written.

### What you give up

The ticket link carries no context. A `mailto:` can pre-fill a subject and a body;
an `<a href>` cannot, so the user arrives at a blank ticket form and describes the
problem themselves.

The page still *carries* the context, though. Every contact link declares the
incident metadata as attributes:

```html
<a id="rep" data-subject="Blocked site report"
   data-intro="Please review this block."
   data-prompt="Why I need access:"
   href="https://tickets.example.com/new">Report to IT</a>
```

Those three attributes are the seam for ticket-system support: a ServiceNow or
Jira Service Management adapter reads them and builds a pre-filled URL —
`short_description` from `data-subject`, `description` from `data-intro` plus the
page's fact table. That adapter does not exist yet; the attributes are already
there so that adding it does not mean editing all nine page templates again.

### Also affected

`supportUrl` applies to the GlobalProtect portal as well: the "Need help?" note on
every portal page, and the three logout messages that name a contact. The "Need
help?" note is a link, so it prints the label. The logout messages are not —
PAN-OS fills them in with `.text()`, so markup would render as literal
characters — and print the label *and* the URL as plain prose instead, e.g.
"Contact the Service Desk at https://tickets.example.com/new", so the address is
still something the user can actually find and use.

## Redirecting to a sanctioned app

When a blocked category has a company-sanctioned equivalent, the **URL block
page** can name it and hand the user over after a countdown. It is off unless you
both set `enabled` and map at least one category — with either unset, not one
byte of it reaches any page.

```json
"redirect": {
  "enabled": true,
  "seconds": 10,
  "message": "Taking you to {app} — the approved alternative for this.",
  "categories": {
    "online-storage-and-backup": {
      "app": "Company Drive",
      "url": "https://drive.example.com/"
    },
    "web-based-email": {
      "app": "Company Mail",
      "url": "https://mail.example.com/",
      "seconds": 5,
      "message": "Work mail lives on {app}. Taking you there."
    }
  }
}
```

| Key | Notes |
|---|---|
| `enabled` | The toggle. A toggle with an empty `categories` does nothing |
| `seconds` | Default countdown, 1–60. Override per category |
| `message` | Default notice text. `{app}` is replaced with that category's `app` |
| `categories` | `category → {app, url}`, plus optional `seconds` and `message` |

**Allow the target in policy first.** If the sanctioned app is itself matched by
the policy that produced the block, the user is sent to a page that blocks them.

The page will not *loop* on that: a response page is served as the blocked site,
so it can see that the host it is being blocked on is one of your sanctioned
apps, and it will not hop again. Because a hop only ever targets something in
this table, every cycle passes through one of those hosts — so one wrong entry
costs the user one wasted redirect, not an unbreakable loop. What no page can do
is make the target reachable. That is policy's job.

Three rules the build enforces, because each fails in a way you would not see:

- **Only a `calm` category may redirect.** The category must also appear in
  `categories` above, and a `warn` or `critical` tone is refused. Nobody gets
  forwarded off a malware or phishing block, whatever the config says. The
  browser re-checks the tone the category map resolved before arming.
- **`url` must be an absolute `https://` URL.** It is read from your config and
  never from `<url/>` — that value is chosen by whoever the user was trying to
  reach, and a redirect built from it would make the firewall an open redirector.
- **`seconds` must be a whole number, 1–60.**

It applies to the URL block page only. No other response page has a `<category/>`
token to key on, and the two coach pages already carry a Continue action that a
countdown would race.

The notice takes its colours from the shell, so every style renders it without
opting in. It costs roughly 3.3 KB on the URL block page — check the size column
in the build report if you are near the ceiling.

Cancelling — the **Stay** button or `Esc` — stops the countdown for that page
view only. The countdown also pauses while the tab is in the background, so a
tab left open behind others does not navigate itself.

### Seeing it before you switch it on

The preview gallery grows a **Redirect** control whenever `url-block-page` is the
selected page. **On** renders the handoff; **Off** is the page as it is today.

It ignores `redirect.enabled` on purpose — the point is to evaluate the handoff
*before* committing to it, and `enabled` is false on every config until someone
opts in. What ships is still governed entirely by your config; only the gallery
looks past the flag.

Two things about the demo frame differ from what the firewall serves, both
deliberate:

- **The countdown restarts instead of handing over.** The frame is a `srcdoc`
  iframe on `file://`, so navigating it would leave the gallery and need the
  network. The served page hands over exactly once. Everything else — **Stay**,
  `Esc`, the background-tab pause, the loop guard — is the script that ships.
- **The category is not the usual sample.** `<category/>` previews as
  `command-and-control`, which is `critical`, and the page refuses to forward
  anyone off a security block. The demo stands in the first category you mapped,
  so the tone and gloss are the ones a user would really see. If you have mapped
  nothing yet it falls back to `online-storage-and-backup` → **Company Drive**,
  the worked example above.

The same page is written to `preview/<style>/url-block-page-redirect.html`. It is
preview-only and is never written under `deploy/`.
