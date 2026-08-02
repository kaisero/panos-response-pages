# Changelog

Notable changes to this project. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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
  customer's own config file, then the pin, then the default; a theme rendering
  in anything other than the build's palette is named in the build report.

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
