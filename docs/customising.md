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
| `baseLanguage` | The language written into the markup as real text — see [Languages](#languages) |
| `languages` | Every language compiled into the page. `["en"]` is byte-identical to a build from before the feature existed |
| `translations` | Your *own* copy, per language. The strings files translate what this project ships; this translates what you changed |

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
there so that adding it does not mean editing all eleven page templates again.

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

## Languages

One imported page serves every language. PAN-OS gives a vsys exactly one page per
type, so a firewall with German and English speakers behind it cannot import two —
the choice has to happen in the browser. Every language you configure is compiled
into the page, and the browser picks one from `navigator.languages` at load time.

```json
"baseLanguage": "en",
"languages": ["en", "de"]
```

| Key | Notes |
|---|---|
| `baseLanguage` | The language written into the markup as **real text**. It is what a browser with JavaScript disabled shows, and what any browser that matches nothing falls back to. Must appear in `languages` |
| `languages` | Every language compiled into the page, base included. Two-letter codes only; each needs a `strings/<code>.json` |

**`languages: ["en"]` produces byte-identical output to a build from before this
feature existed.** Not approximately — the test suite compares the bytes. A
single-language build emits no dictionary and no selector, and keeps the timestamp
script's previous form down to its variable name. That is what makes the feature
free for everyone who does not want it, and the assertion is how it stays free.

The build refuses, as a `BuildError` before any page is written: a `baseLanguage`
that is not in `languages`; a configured language with no strings file; a code that
is not two lowercase letters; an empty `languages`; and a `translations` block for a
language `languages` does not list — that last one is copy you wrote that no user
would ever read.

> **`language 'en' is configured but en.json is missing`** on a tree you did not
> touch means the data directory predates this release: `languages` defaults to
> `["en"]`, so a directory `init`-ed before `strings/` existed fails every build.
> Refresh it with `panos-response-pages init --force`, backing up your `config/`
> first. The message says so too.

Two-letter **primary subtags only**. The browser's tag is reduced to its primary
subtag before the lookup, so `de` matches `de`, `de-AT`, `de-CH` and `de-DE`.
Writing `de-AT` in `languages` is refused rather than quietly truncated: truncating
it would send the build looking for a file you did not write, and you would find out
from the missing translation rather than from the config.

### Translating your own copy

The strings files translate what this project ships. They cannot translate what
*you* wrote — a German `defaultGloss` is worthless to a customer who replaced the
English sentence it translates. Your translations therefore live in your own config
file, beside the English they translate:

```json
{
  "company": "Example Corp",
  "continueGrantText": "30 minutes",
  "defaultGloss": "Blocked under Example Corp policy.",
  "languages": ["en", "de"],
  "translations": {
    "de": {
      "continueGrantText": "30 Minuten",
      "defaultGloss": "Gemäß Richtlinie von Example Corp gesperrt.",
      "supportLabel": "der IT-Servicedesk",
      "redirect": {
        "message": "Weiterleitung zu {app} — die freigegebene Alternative.",
        "categories": {
          "web-based-email": "Dienstliche Post liegt auf {app}. Wir leiten Sie weiter."
        }
      }
    }
  }
}
```

Eligible keys: `defaultGloss`, `riskGloss`, `continueGrantText`, `supportLabel`, the
portal's `logoutMessages`, and the nested `redirect` block — its default `message`
and its per-category sentences.

**Precedence mirrors config-over-defaults: your block beats the shipped strings
file, and a key you leave out falls back to that language's shipped translation, not
to the base language.** The distinction is the whole point. Falling back to English
would put one English sentence on an otherwise German page, which is exactly the
half-translated result the build refuses everywhere else — and it would do it
silently, because the page still builds and still validates.

`redirect` is the one block that merges a level down rather than wholesale.
Translating `message` and leaving `categories` alone keeps the shipped category
sentences; the alternative would make translating half the block discard the other
half without saying so.

Per-language **category glosses** are not here. They live in the optional
`categories` block of the strings file — see below — because they are this project's
map of PAN-OS categories, not your copy.

> **The redirect notice is translated in two halves.** Its furniture — the **Go
> now** and **Stay** buttons, the line that replaces the sentence when you stay,
> and the two sentences a screen reader is read — is copy *this project* ships, so
> it lives in `shared.redirect` in every strings file and is already German. Only
> the *sentence* is routed through `translations`, because it names **your**
> sanctioned app in wording you may well have rewritten. Left untranslated it is
> the one English sentence on an otherwise German page, so write it when you switch
> the redirect on — and note that translating `categories` while leaving `message`
> behind is refused rather than falling back to English: `message` is the fallback
> for every category, in each language exactly as in the base one.

### Adding a language

1. Copy `strings/en.json` to `strings/<code>.json` in your `init`-ed data tree.
2. Translate every value. Leave every key exactly where it is.
3. Add the code to `languages`.

**Key parity is exact, in both directions.** A missing key fails the build naming
every path that is missing; an *extra* key fails too, because it is a typo or a
stale entry and either way it is a string no page will ever read. Both are
invisible in the output, which is why neither is a warning:

```
BuildError: de.json is out of step with en.json -- missing 4 key(s):
  pages.ssl-cert-status-page.headline
  pages.ssl-cert-status-page.gloss
  pages.ssl-cert-status-page.facts[3]
  pages.ssl-cert-status-page.report.subject
```

Lists are indexed rather than counted, so a `facts` array one entry short names the
position instead of reporting a length mismatch you then have to find by eye.

**Every configured language must have a file, and there is no runtime fallback.** No
partially translated page, no missing key quietly resolving to English. The
alternative is a line in a build log, which gets scrolled past, and the page ships.

A known cost of that, accepted rather than overlooked: adding a twelfth page type
leaves the build red until every language file has an entry for it, even for someone
who does not speak the language.

The one block a language file may omit is `categories`, the per-language category
glosses. Absent — the default — a non-base language shows the translated
`defaultGloss`/`riskGloss` for that category's tone, and the language costs about
1,800 B less on the two pages that carry the category map. The tone map itself is
never translated and never duplicated: severity, colour and the severity pill vary
per category identically in every language, and only the sentence changes. Category
*labels* are never translated either — they are title-cased from the PAN-OS slug, and
a user reading one back to IT should be reading what PAN-OS calls it.

### What a translator must not change

None of these is obvious from reading the file, and all of them fail quietly.

- **A split string is the fragments either side of an element, and the element stays
  between them.** `shared.contactAlt` is `["Or email ", " with the details above."]`
  with the address in the gap; `url-coach-text`'s `extra` is three fragments where
  the middle one is the emphasised phrase inside a `<strong>`. The runtime swaps
  text nodes by position and never touches the element. A language whose word order
  needs the link or the emphasis *first* or *last* cannot be expressed in this shape
  — German does not; a language that does would need its own exception rather than a
  creative translation.
- **No fragment may be empty.** `""` renders no text node at all, the sentence
  collapses from three child nodes to two, and the runtime's shape check declines to
  swap it — leaving one sentence in the base language on an otherwise translated
  page, with a clean build behind it. Every other check passes it: the key exists,
  and the array is the right length. The build therefore refuses any empty string
  outright, naming the language and every path. `" "` is fine, and several fragments
  legitimately end in a space. The single documented exception is
  `shared.severity.calm`, empty because a calm page carries a pill with no words in
  it.
- **No `<` or `>` in any string.** The build refuses both, in a strings file and in
  a `translations` block, naming the language and every path. In the base language a
  `<strong>` reaches the markup through substitution and renders; in every other
  language the dictionary is handed to `textContent`, so the reader sees the literal
  characters `<strong>` — the same class of defect as an unresolved placeholder.
  A **PAN-OS token** is worse again. `<user/>` in a German gloss builds clean and
  validates clean (the token is legal on that page), and then the *firewall*
  expands it at serve time — inside a JS string literal. A username of the shape
  `ACME\ukaiser` reads as an invalid `\u` escape and the **entire page script
  dies**: no language swap, no category label, no timestamp, no report mail. On the
  portal a raw `<` is refused for a third reason — `<pan_form/>` silently stops
  being substituted and the login form disappears.
- **The same rule covers the copy in your config**, and it does not wait for a
  second language: `defaultGloss`, `riskGloss`, every `categories.<name>.gloss`,
  `redirect.message` and each `redirect.categories.<name>.message` and `app` are
  compiled into the page script of *every* build, single-language ones included. A
  `<user/>` in any of them kills that script exactly as one in a strings file does,
  so the build refuses it and names the config path. These values reach the page
  through `textContent` and are never markup, so there is no tag to preserve —
  remove it and say the same thing in words. Nothing else in the config is checked
  this way: `logoSvg`, `marks.*` and the portal logos are SVG on purpose.
- **`{{COMPANY}}`, `{{SUPPORT_EMAIL}}` and `{{CONTINUE_GRANT}}` must survive
  verbatim.** They are resolved per language at build time, so `{{CONTINUE_GRANT}}`
  inside a German sentence resolves to the German `continueGrantText` rather than to
  the English duration. Mangle one and the build fails naming the page.
- **`{app}` and `{n}` in the redirect notice are a different syntax, and nothing
  checks them.** They are single-braced because they are substituted in the
  *browser* by the redirect script, not by the build's `{{...}}` pass — which means
  the build's unresolved-placeholder check does not look at them. `{{COMPANY}}`
  mistyped fails the build; `{App}`, `{app }` or `{Anwendung}` does not. The notice
  then simply names no application — on the one page whose job is to name one — or
  announces no countdown. Copy them character for character. `{n}` appears in
  `shared.redirect.announce`, which is a sentence rather than a concatenation
  precisely so a translation can put the number where its grammar wants it.

### Styles that opt out: `i18n: false`

```json
{ "name": "nyan", "shell": "nyan", "palette": "nyan", "i18n": false }
```

A theme may decline the extra languages. `nyan` does. Its worst page is 15,108 B and
has 892 B of headroom — less than a single extra language — because the star field
and the sprite artwork are half the file. It is a novelty style, and capping the
whole design around it would be the tail wagging the dog.

Three things to know about the flag:

- **It is theme-level, not per page.** It covers that theme's eleven block pages
  *and* both of its GlobalProtect portal imports. There is no way to keep the
  languages on a theme's portal while dropping them from its block pages.
- **The pages still build.** An opted-out style renders `baseLanguage` as real text,
  builds every page and is still measured against the ceiling. It simply carries no
  dictionary and no selector.
- **It is reported, never silent.** Shipping one language where you configured two
  is a real reduction in what your users get, so the build table says so on that
  style's rows:

```
nyan   prisma-blue  url-block-page  15108  ok  en (base only -- i18n:false)
glass  prisma-blue  url-block-page  12811  ok  en,de
```

Every other style that overflows **fails** the build. Automatic language-dropping was
considered and rejected: a customer who configured French and silently gets it on
four styles out of six is precisely the invisible failure this project exists to
prevent.

### What a language costs

Measured from real builds, not estimated. An earlier estimate put the one-off
runtime at 240 B and was wrong by a factor of five — it grew while absorbing the
page-shape fixes the feature turned out to need.

| | Bytes |
|---|---|
| Runtime, one-off per page | 1,197 |
| Dictionary, per language | 641 |
| **First extra language** | **1,838** |
| Each further language | 641 |

Only 6–9% of a built page is language-dependent. The rest is CSS, the SVG mark and
the emitted script, none of which changes with language — which is why a language
costs far less than the intuition of "another copy of the page".

On the worst non-`nyan` block page (`glass`/`url-block-page`, 10,973 B in English):

| Languages | Size | |
|---|---|---|
| English only | 10,973 B | byte-identical to pre-feature |
| + 1 | 12,811 B | 3,189 B under the warn line |
| + 2 | 13,452 B | |
| + 3 | 14,093 B | |

**Five additional languages fit under the 16,000 B warn line.** Real German measures
**×1.206** of English, so call it **four in practice**. Hold the warn line rather
than the 17,999 B hard ceiling: the 1,999 B gap exists because `<url/>` expands at
serve time, and a long blocked URL grows the page after the byte count was taken.

Cyrillic and Greek cost roughly 1.6× (two bytes per character in UTF-8); CJK is
roughly par with English.

**The portal is the tighter of the two**, not the looser, because it starts from a
larger baseline. Its worst import is `beacon`/`login` at 12,119 B, and its warn line
is 15,000 B:

| Languages | `beacon`/`login` | |
|---|---|---|
| English only | 12,119 B | byte-identical to pre-feature |
| + German | 13,945 B | 1,055 B under the warn line |
| + 2 | 14,588 B | |
| + 3 | 15,231 B | **over the warn line** |

**Two additional languages fit under the warn line, four before PAN-OS refuses the
import outright at 16,170 B.** If you are planning more than one extra language, the
portal is the constraint to plan against.

#### German plus an enabled redirect crosses the warn line

On `beacon`, `glass` and `mesh`, `url-block-page` with German *and* the redirect
switched on lands over 16,000 B — by 202 B, 494 B and 84 B respectively. Nothing
comes near the 17,999 B hard ceiling, and the build **warns** rather than refusing.

That is a deliberate choice, and both alternatives are worse:

- **Refusing** would stop the build for an opt-in configuration because of a
  property of a style you may not deploy. The redirect costs roughly 3.3 KB on one
  page; three of six styles have room for it in two languages and three do not.
- **Making the redirect language-aware** — dropping the notice when a second
  language is configured — would make it vanish from a page you configured it on,
  with no error anywhere. That is the failure this project exists to prevent, traded
  for 494 bytes.

If you run one of those three styles with German and the redirect, check the size
column and decide whether you are comfortable at ~16.2 KB with `<url/>` still to
expand. Dropping the per-language `categories` block, if you added one, buys back
about 1,800 B on that page.

### Checking it in a browser

Chrome needs **`--accept-lang`**, not `--lang`:

```
open -na "Google Chrome" --args --accept-lang=de-DE,de --user-data-dir=/tmp/chrome-de \
  file:///path/to/out/preview/glass/url-block-page.html
```

`--lang` changes Chrome's *interface* language and does not move
`navigator.languages`, so the page renders in English and looks like a broken
feature rather than a wrong flag. This has already caught someone on this branch.
The same trap applies to any check you make: the selector reads
`navigator.languages`, so that is the thing that has to change.

### Known rough edges

- **`supportUrl` mode puts an English "at" inside German logout messages.** The
  portal's logout messages are filled by PAN-OS with `.text()`, so they cannot carry
  a link and print the contact as prose instead — `"the Service Desk at
  https://…"`. That `at` is assembled in code rather than taken from a strings file,
  so it stays English whatever language the page selected. Pre-existing, and only
  visible in `supportUrl` mode.
- **PAN-OS's own login form is translated by reaching into its DOM.** The
  `<pan_form/>` substitution delivers PAN-OS's English `placeholder="Username"`,
  `placeholder="Password"` and `value="Log In"`, which would otherwise sit inside an
  otherwise-German page. They are swapped by id — `#user`, `#passwd`, `#submit`,
  `#new_passwd`, `#confirm_new_passwd` — and swapped **twice**, because PAN-OS
  re-applies its own placeholders from `loadPage` on `window.onload`, after our
  script has run. This is a dependency on PAN-OS's markup and worth re-checking on a
  major upgrade. Every swap is guarded, so a release that renames an id degrades to
  PAN-OS's own English wording rather than breaking the page — the same degradation
  the download widget already accepts on `#taGetSofewarePage`.
