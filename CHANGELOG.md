# Changelog

## [Unreleased]

### Added

- **Two GlobalProtect portal pages**, in all six styles: the portal login page
  (which also serves the agent download page) and the portal home page (which
  also serves logout). The portal home page itself is deliberately left unstyled
  — see `docs/portal.md`.
- **Portal guards** covering the failures PAN-OS does not report: the wrong file
  shape, a duplicated or missing form token, a raw `<` outside a tag, a baked
  CSRF token, an undeclared customization variable, and the 16,170-byte import
  ceiling (enforced on the base64 form, and unrelated to the block pages' 17,999).
- **Spliced previews** rendering each import inside PAN-OS's own captured prefix,
  in all four login states — including change-password, which is taller than the
  viewport and where layouts break.
- **Portal configuration**: `portalName`, `portalLogoSvg`, the optional
  `portalLogoSvgDark` and the seven `logoutMessages`. The three admin-only logout
  errors now name a real support contact instead of telling an end user to reach
  a system administrator.
- **Zero-trust wording throughout.** The portal does not call itself a VPN: it is
  named `GlobalProtect` rather than `<company> VPN`, the login page reads "Use your
  company account to sign in", and the download page is headed "Get Agent Software".
  `portalName` names the service rather than the company on purpose — it is a small
  eyebrow on two surfaces but the whole `<h1>` on logout, where a company name wraps
  it to two lines. The company is on every page already, as the wordmark beside the
  logo. A test fails the build if "VPN" reappears in any built import.
- **A detected-platform download button** on the agent download page. PAN-OS
  serves three equally weighted links — Windows 32-bit first — above three rows
  of prose explaining which one to take; the page now reads the platform from the
  user agent, offers that build, and keeps the rest behind a menu. Its own
  anchors are moved rather than rebuilt, and the stock list is hidden only once
  the replacement is up, so a blocked script or an unrecognised platform still
  leaves working links.

### Changed

- The portal logo now takes its colours from the palette and its wording from
  `company`. It was a frozen `data:` URI: cyan on an orange or yellow build, and
  reading "Example Corp" whatever the company was actually called.
  `portalLogoSvg` is now the symbol alone, as SVG source coloured with `S_*`
  tokens; the build renders it once per scheme, the shells paint it from CSS
  rather than through PAN-OS's `logo` variable, and the company name sits beside
  it as text. So the mark tracks the colour scheme, the name follows a rename,
  both are on screen at first paint, and neither waits on jQuery.
- The preview gallery's chrome is one toolbar row rather than six stacked button
  groups: 49 px instead of 499 px at 1440×900, with the long style and page lists
  as selects and the explanatory prose behind an About toggle.
- Comments and leading indentation are now stripped at emit time for every page.
  Sources keep the reasoning that explains them; block pages shrink by up to 8%.

## [0.1.0] - 2026-07-28

### Added

- **Nine PAN-OS response page types**: URL Filtering block and continue,
  Safe Search enforcement, Application block, Anti-Phishing block and continue,
  Antivirus block, File Blocking block and continue.
- **Six styles** — `assist`, `record`, `banner`, `glass`, `beacon`, `mesh` —
  each supporting all three palettes and both colour schemes.
- **Three palettes**: Cyber Orange, Strata Yellow, Prisma Blue. Every text/fill combination is
  held to 4.5:1 in both schemes by the test suite.
- **Typer CLI** with `build`, `init`, `themes`, `palettes`, `pages` and
  `validate`, shell completion, and rejection that reports the available values
  rather than only refusing.
- **Packaged data** with a `--config-dir` override and `init` to copy the shipped
  shells, palettes, themes and config out for editing.
- **Logging** to stdout with `-v`/`-vv`/`-q`, `--log-json` for a single
  machine-readable stream, and optional rotating file logging configured from
  `~/.panos_response_pages/settings.yaml`.
- **PAN-OS guards** that fail the build rather than letting a page fail silently
  on a firewall: the 17,999-byte ceiling, external references, tokens the page
  type does not provide, missing doctype, and copy the page cannot substantiate.
- **A clickthrough preview gallery** across style, page, viewport and scheme.

### Fixed

- Pages are written with `write_bytes` rather than `write_text`. `write_text`
  translates newlines to `os.linesep`, but the size guard measures the string in
  memory beforehand — on Windows every page would gain a byte per line *after*
  being measured, and could ship over the ceiling with the report saying `ok`.

[Unreleased]: https://github.com/kaisero/panos-response-pages/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/kaisero/panos-response-pages/releases/tag/v0.1.0
