# panos-response-pages

[![CI](https://github.com/kaisero/panos-response-pages/actions/workflows/ci.yml/badge.svg)](https://github.com/kaisero/panos-response-pages/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Modern, responsive response pages for PAN-OS. Generate response pages to delight users while protecting them from threats.

**[Full documentation →](https://kaisero.github.io/panos-response-pages/)**

## Install

```bash
pip install panos-response-pages
```

## Install (From Source)

```bash
uv tool install panos-response-pages
uvx panos-response-pages build          # or run it without installing
```

## Use

```bash
panos-response-pages build              # every style, into ./out
panos-response-pages themes             # what styles exist
panos-response-pages init               # copy the templates out to customise them
```

`out/deploy/<style>/` is what you import. `out/preview/index.html` is a
clickthrough gallery for review — style, page, viewport and colour scheme — built
with sample data standing in for the PAN-OS tokens.

Six styles ship, all supporting three brand palettes and both colour schemes:
`assist`, `record`, `banner`, `glass`, `beacon`, `mesh`. See [Styles].

## Development

```bash
uv sync --all-groups
uv run pre-commit install
uv run nox                            # lint, type-check, tests, docs
```

`nox -s tests` runs the suite with coverage; the gate is 93%. Commit `uv.lock`.

## License

MIT. See [LICENSE](LICENSE).
