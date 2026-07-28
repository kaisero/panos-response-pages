# Changelog

## [Unreleased]

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
