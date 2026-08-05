# Changelog

Notable changes to this project. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Multi-language response pages — and `languages: ["en"]` is byte-identical.**
  A build configured for one language emits exactly the bytes it emitted before
  any of this existed: no dictionary, no language selector, the timestamp script
  unchanged down to its variable name. The suite compares the bytes rather than
  assuming it. Nothing else in this release costs an existing single-language
  customer anything.
- **Every configured language is compiled into the page**, and the browser
  selects one from `navigator.languages` at load time. PAN-OS serves one page
  per type per vsys and the file is static, so a firewall with German and
  English speakers behind it can neither import two pages nor negotiate — the
  choice has to happen in the browser. Two new config keys: `baseLanguage`, which
  is written into the markup as real text and is what a browser with JavaScript
  disabled shows, and `languages`, the full set. Two-letter primary subtags only:
  `de` matches `de-AT`, `de-CH` and `de-DE`. A browser that matches nothing is
  left with the page exactly as served.
- **German (`de`) is the first additional language**, covering the eleven block
  pages, the three GlobalProtect portal surfaces and the seven logout messages.
  It costs the worst non-`nyan` block page 1,838 B — 1,197 B of one-off runtime
  plus a 641 B dictionary — and measures ×1.206 of English. **Five** additional
  languages fit under the 16,000 B warn line, four at German's expansion. The
  **portal is the tighter of the two**: two additional languages under its
  15,000 B warn line, four before PAN-OS refuses the import at 16,170 B.
- **`translations`, for your own copy.** The strings files translate what this
  project ships; `translations` translates what you changed — `defaultGloss`,
  `riskGloss`, `continueGrantText`, `supportLabel`, the portal's
  `logoutMessages` and the redirect notice. Your block beats the shipped strings
  file, and a key you leave out falls back to that language's shipped
  translation rather than to the base language, so an untranslated key never
  drops a lone English sentence into a German page.
- **A theme may decline the extra languages with `"i18n": false`.** `nyan` does:
  its worst page has 892 B of headroom, less than one language, because the star
  field and the sprite artwork are half the file. The flag is theme-level and
  covers that theme's block pages *and* its portal imports, and the build table
  names it on that style's rows rather than dropping a language in silence.
  Every other style that overflows fails the build.
- **Guards for the failures a translation makes possible.** Language files must
  carry exactly the base language's key set, in both directions — a missing key
  and a stale one are both strings no page will read. No string may be empty: an
  empty fragment renders no text node, collapses the three-node sentence the
  runtime swaps, and leaves that one sentence in the base language with a clean
  build behind it. No copy may contain `<` or `>` — in a strings file or in a
  `translations` block. Outside the base language copy reaches the page as JSON
  inside a `<script>`, where a tag renders as literal angle brackets and a PAN-OS
  token such as `<user/>` is worse: the *firewall* expands it at serve time,
  inside a JS string literal, so a username like `ACME\ukaiser` reads as an
  invalid `\u` escape and kills the entire page script — no language swap, no
  category label, no timestamp — from a build and a validate that were both
  clean. On the portal a raw `<` silently stops `<pan_form/>` being substituted. Every language's `facts` array is counted against
  the `<dt>` rows in the page template, because the labels swap positionally and
  one short shifts every label below it. The copy audit now runs over every
  language file, not just `en.json`.
- **PAN-OS's own injected login form is translated too** — `#user`, `#passwd`,
  `#submit` and the two change-password fields, whose English wording arrives
  with `<pan_form/>` and would otherwise sit inside an otherwise-German page. The
  swap is re-applied on `window.onload`, because PAN-OS re-asserts its own
  placeholders after our script runs. Every swap is guarded, so a PAN-OS release
  that renames an id degrades to PAN-OS's English rather than breaking the page.
- **Known limitation:** German plus an enabled redirect puts `url-block-page`
  over the 16,000 B warn line on `beacon`, `glass` and `mesh`, by 202, 494 and
  84 B. Nothing approaches the 17,999 B hard ceiling and the build warns rather
  than refusing — refusing would stop a build over an opt-in feature because of
  a style you may not deploy, and dropping the notice when a second language is
  configured would make it disappear from a page you configured it on.
- **A tenth page type, `data-filter-block-page`** — the Data Filtering block,
  served when a transfer matches a Data Filtering profile. It surfaces every
  token PAN-OS provides on that page: the transfer direction, the file, the
  application and the user.
- `<direction/>` joins the token registry. It is provided on the data filtering
  page alone, and it is the first token whose rendered value is not documented
  anywhere — it appears in the shipped PAN-OS default but in none of the
  published variable lists. The default uses it sentence-initially, implying a
  capitalised `Upload`/`Download`, so the page uses it only as a fact-row value,
  where either casing reads correctly. Confirm it on live hardware before
  relying on it in prose.
- **An eleventh page type, `ssl-cert-status-page`** — the certificate error a
  user meets on a decrypted session. It is the first page whose subject is the
  *server* rather than the organisation: it explains that a certificate could
  not be verified, and its advice is to not sign in, rather than to ask for the
  site to be allowed. Tone is `warn` rather than `crit` deliberately — an expired
  certificate and an active interception arrive here identically, and rendering
  every one as a security risk teaches people to click through the ones that
  matter.
- Four more tokens: `<certname/>`, `<issuer/>`, `<status/>` and `<reason/>`, all
  provided on the certificate page alone. They appear in the shipped PAN-OS
  default and are corroborated as a group by the community variable list; no
  official source documents them, and nothing documents what `<status/>` and
  `<reason/>` contain. `<badcert/>` is named in that same community list but does
  *not* appear in the vendor default, so it is deliberately left unregistered.
- `<url/>` is documented as rendering the **destination IP** on the decryption
  path, which is what it does on the certificate page — the vendor default labels
  that row `IP:`. The page labels it `Server` so it reads correctly whether an
  address or a hostname arrives, and the preview gallery now substitutes an
  address there rather than the shared long-URL sample — `SAMPLE` is keyed by
  token, so a new `PAGE_SAMPLE` map carries the per-page exceptions.

### Changed

- **Page copy has moved out of the templates into `data/strings/<lang>.json`.**
  Templates carry keys; the strings files carry the words. **If you forked the
  templates with `init` to reword a page, that wording now lives in
  `strings/en.json`** and your edited template will not be picked up. English is
  no longer a special case that the other languages emulate, which is what makes
  the key-parity and empty-string checks possible at all. `SEV_LABEL`
  ("Caution", "Security risk") moves out of Python into `shared.severity` for
  the same reason.
- The redirect notice is translatable, in two halves. Its **furniture** — the
  **Go now** and **Stay** buttons, the line that replaces the sentence when you
  stay, and the two sentences a screen reader is read — is shipped copy and now
  lives in `shared.redirect` in every strings file, German included. Its
  **sentence** is yours: it names *your* sanctioned app in wording you may have
  rewritten, so it stays under `translations.<lang>.redirect`, and left
  untranslated it is the one English sentence on an otherwise German page. A
  language that translates the per-category sentences and not the default
  `message` is now refused rather than falling back to English underneath a
  German notice. `{app}` — and `{n}`, the countdown — use a single-braced syntax
  that the build's placeholder check does not see, so a mangled token fails
  silently and simply names no application.
- **If you forked the data directory with `init`, refresh it: `init --force`**
  (back up your `config/` first). A tree copied out before this release has no
  `strings/` at all, and every build of it now fails with `language 'en' is
  configured but en.json is missing` — `languages` defaults to `["en"]`, so this
  reaches every forked tree, not only the ones adding a language. A tree forked
  mid-release may have `strings/` but no `shared.redirect`; that is refused the
  same way, naming the file and the missing keys.
- In `supportUrl` mode the portal's logout messages print the contact as
  `"<name> at <url>"`, and that `at` is assembled in code rather than taken from
  a strings file — so it stays English in an otherwise German message.
  Pre-existing and unchanged; noted because a German page is where it becomes
  visible.

## [0.1.1]

### Added

- Response pages and the portal can point their contact action at an `https://`
  ticket system instead of a `mailto:`, via a new `supportUrl` config key.
  `supportUrl` and `supportEmail` are mutually exclusive; a config setting both
  fails the build. The ticket link carries no pre-filled context, but the page
  still declares the incident metadata as `data-*` attributes for a future
  ticket-system adapter to read.
- A palette dropdown in the preview gallery, showing each palette's primary
  colour. The gallery chrome follows the selection.
- **A seventh style, `nyan`** — Nyan Runway. A pixel cat flying across a star
  field beside the notice, laying a spectrum trail; legs and tail animate as a
  frame swap, and a click on empty sky rolls it once and doubles the trail. The
  notice sits out of the flight lane on a glass card, and the trail bends to
  follow wherever the cat is steered — behind the glass it reads as a blurred
  smear rather than being hidden by it. The GlobalProtect imports take the same
  star field and the same glass card, but not the rainbow: it is a trail, and
  without the cat drawing it there is nothing for it to be. The flight stays on
  the block pages, because the Home Page import is script-only and has no
  element to draw on.
- **Style palettes.** Palettes now declare a `kind`: `brand` palettes are the
  customer axis, a `style` palette belongs to one shell and is pinned by it with
  a `palette` key in the theme. Resolution order is `--palette`, then the
  customer's own config file, then the pin, then the default — see above for
  what that order now decides.

### Changed

- Every style is now built in every palette. Pages move from
  `out/deploy/<style>/` to `out/deploy/<style>/<palette>/`, and portal imports
  from `out/deploy/<style>/portal/` to `out/deploy/<style>/<palette>/portal/`.
  **This breaks any script that globs the old paths.**
- `--palette` narrows a build to one palette instead of selecting the only one
  built, matching how `--theme` narrows the style axis.
- A theme's `palette` pin and the config's `palette` key now choose which
  palette the preview gallery opens on. They no longer decide what is built.
- The build report prints one row per style and palette, naming that
  combination's largest page, with anything that warns or fails listed in full
  underneath.

## [0.1.0]

First release.

### Added

- **Nine URL Filtering and Threat Prevention response pages**: URL block and
  coach text, Safe Search enforcement, Application block, credential block and
  coach text, Antivirus block, and File Blocking block and continue.
- **Two GlobalProtect portal pages**, covering three visitor-facing screens: the
  portal login page, the agent download page and the logout page. The portal home
  page is deliberately left as PAN-OS ships it.
- **Six styles** — `assist`, `record`, `banner`, `glass`, `beacon` and `mesh` —
  with every page available in every style.
- **Three palettes**: Cyber Orange, Strata Yellow and Prisma Blue. Every text and
  fill pairing meets 4.5:1 contrast, enforced by the test suite.
- **Light and dark mode** on every page, following the visitor's system setting.
- **Responsive layouts** for desktop and mobile.
- **Self-contained pages.** Each is a single HTML file that makes no external
  requests, so it renders on a blocked site with no network access.
- **A command-line interface** with `build`, `init`, `themes`, `palettes`,
  `pages` and `validate`, plus shell completion.
- **Customisation through JSON config**: company name, support address, logos,
  portal wording, per-category explanations and the GlobalProtect logout
  messages. `init` copies the shipped templates, palettes, themes and config out
  for editing, and `--config-dir` points a build at them.
- **Operating-system detection on the GlobalProtect download page.** Visitors are
  offered the agent build for their platform, with the rest behind a menu, in
  place of the three undifferentiated links PAN-OS serves.
- **A clickthrough preview gallery** across style, page, viewport and colour
  scheme, published with the documentation site. The documentation home page
  carries a live inline preview.
- **Build-time validation** against the limits PAN-OS enforces silently: the
  17,999-byte serving ceiling for response pages, the 16,170-byte import ceiling
  for GlobalProtect portal pages, external references, missing doctypes, tokens a
  page type does not provide, and copy the page cannot substantiate. The build
  fails rather than emitting a page that breaks on the firewall.
- **Logging** to stdout with `-v`, `-vv` and `-q`, `--log-json` for a single
  machine-readable stream, and optional rotating file logging.

[0.1.0]: https://github.com/kaisero/panos-response-pages/releases/tag/v0.1.0
