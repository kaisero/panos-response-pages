# Changelog

Notable changes to this project. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.3]

### Added

- **An `import` command, starting with `import scm`** — sends a built variant
  straight into Strata Cloud Manager against a service account, instead of
  pasting thirteen base64 blobs through the UI by hand. `--dry-run` lists every
  page and the folder it would land in without contacting anything, `--only`
  imports a single page, and the exit code is `1` if any page failed, so a
  partial run does not pass quietly. Credentials resolve CLI flag > `SCM_*`
  environment > `settings.yaml` > default, the same precedence as everything
  else here.
- Imported pages are staged, not live. A write lands in the tenant's *candidate*
  configuration and nothing in this tool pushes it, so a successful import does
  not mean the firewalls are serving the new pages yet.
- The two GlobalProtect portal pages always import into `Mobile Users`, whatever
  `--folder` says. A portal page is a named object whose name must be unique
  across the whole folder tree, and the API has no working delete — so writing
  one to the wrong folder is not a rejected write but a *successful* one that
  then blocks the correct folder until the stray object is removed by hand.

## [0.1.2]

### Added

- **Multi-language response pages.** Every configured language is compiled into
  the page and the browser picks one from `navigator.languages` at load time.
  Two new config keys: `baseLanguage` (rendered as real text, and what a browser
  without JavaScript shows) and `languages`. Two-letter primary subtags only, so
  `de` matches `de-AT`, `de-CH` and `de-DE`. A build with the default
  `languages: ["en"]` is byte-identical to before.
- **Thirteen shipped languages** — English, German, Spanish, Italian, French,
  Dutch, Danish, Swedish, Japanese, Chinese (Simplified), Vietnamese, Russian
  and Ukrainian, each a complete `data/strings/<code>.json`. **Everything beyond
  English and German is model-drafted and unreviewed by a native speaker**; have
  one read the pages you intend to serve.
- **Not all thirteen fit in one build.** The GlobalProtect portal's 16,170 B
  import ceiling is the binding constraint: roughly English plus three to five
  others, depending which. Cost is driven by character count, not bytes per
  character — Chinese is cheapest at 651 B per page, Russian dearest at
  1,185 B, plus a one-off 1,197 B runtime.
- **`translations`, for your own copy** — `defaultGloss`, `riskGloss`,
  `continueGrantText`, `supportLabel`, `logoutMessages` and the redirect
  sentence. Your block beats the shipped strings file; a key you omit falls back
  to that language's shipped translation, not to the base language.
- **A theme may decline extra languages with `"i18n": false`.** `nyan` does, for
  lack of headroom. Any other style that overflows fails the build.
- **Guards for translation failures**: exact key parity in both directions, no
  empty strings, no `<` or `>` in any copy (a PAN-OS token inside JSON would be
  expanded by the firewall and break the page script), and a per-language
  `facts` count against the template. The copy audit runs over every language
  file.
- **PAN-OS's own injected login form is translated** — `#user`, `#passwd`,
  `#submit` and the two change-password fields. Re-applied on `window.onload`
  and individually guarded, so a renamed id degrades to English.
- **A tenth page type, `data-filter-block-page`**, plus the `<direction/>`
  token it provides.
- **An eleventh page type, `ssl-cert-status-page`**, plus `<certname/>`,
  `<issuer/>`, `<status/>` and `<reason/>`. Tone is `warn`, not `crit`.

### Changed

- **Page copy has moved out of the templates into `data/strings/<lang>.json`.**
  **If you forked the templates with `init` to reword a page, that wording now
  lives in `strings/en.json`** and your edited template is no longer used.
  `SEV_LABEL` moves from Python into `shared.severity`.
- **If you forked the data directory with `init`, refresh it: `init --force`**
  (back up your `config/` first). A tree without `strings/` now fails every
  build, including single-language ones.
- The redirect notice is translatable: its furniture lives in
  `shared.redirect`, its sentence in `translations.<lang>.redirect`. A language
  translating the per-category sentences but not the default `message` is now
  refused.
- The preview gallery loads languages on demand from `preview/lang-<code>.js`
  instead of inlining them, so `index.html` no longer grows with the language
  count.

### Known limitations

- German plus an enabled redirect puts `url-block-page` over the 16,000 B warn
  line on `beacon`, `glass` and `mesh` (by 202, 494 and 84 B). Well under the
  17,999 B hard ceiling, so the build warns rather than fails.
- The copy-rule guard matches English and German phrases only.
- `zh` is served to Traditional readers too, since keys are two-letter subtags.
- In `supportUrl` mode the portal's logout messages assemble `"<name> at <url>"`
  in code, so that `at` stays English.

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
