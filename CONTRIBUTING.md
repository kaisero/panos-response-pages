# Contributing

## Setup

```bash
uv sync --all-groups
uv run pre-commit install
uv run nox                 # lint, type-check, tests, docs
```

| Session | Does |
|---|---|
| `nox -s lint` | ruff check, ruff format --check, codespell |
| `nox -s type_check` | mypy strict over `src/` |
| `nox -s tests` | pytest with coverage; the gate is 93% |
| `nox -s audit` | pip-audit |
| `nox -s docs` | `mkdocs build --strict` |
| `nox -s gate` | all of the fast ones, against the already-synced env |

Commit `uv.lock`. It pins the whole dependency tree and is what Dependabot's
`uv` ecosystem updates.

## What to know before changing anything

**PAN-OS accepts a broken response page without complaint.** The import reports
success, the commit succeeds, and users silently get the default page. Every
guard in this project exists because the firewall will not tell you. When adding
a check, prefer failing the build to warning.

**The generated pages are the product.** If a change could alter the bytes of a
built page, verify it did not:

```bash
uv run panos-response-pages build -o /tmp/before
# ...make the change...
uv run panos-response-pages build -o /tmp/after
diff -r /tmp/before/deploy /tmp/after/deploy
```

This has caught more than it should have — a formatter rewrapping a string
literal that turns out to be shipped HTML changes what a firewall serves without
changing any test.

**Adding a response page type** has its own checklist, including which
substitution tokens each PAN-OS page provides:
`.claude/skills/add-response-page/SKILL.md`.

**Adding a style** is documented under [Styles] — the shell contract there is
enforced by `tests/test_shells.py`, and every item on it fails silently if
ignored.

## Tests

New behaviour needs a test. New *guards* need two: one proving they catch the
bad case, one proving they pass the good one. A guard that cannot fail is worse
than no guard, because it reads as coverage.

## Releasing

1. Bump `version` in `pyproject.toml` (the only place it appears).
2. Add a `## [X.Y.Z]` section to `CHANGELOG.md`.
3. Commit, then tag `vX.Y.Z` and push the tag.

The release workflow checks the tag matches the packaged version, extracts the
changelog section, publishes to PyPI via trusted publishing and creates the
GitHub release. A missing changelog section fails before anything is built.

[Styles]: https://kaisero.github.io/panos-response-pages/styles/
