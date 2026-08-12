# panos-response-pages

[![CI](https://github.com/kaisero/panos-response-pages/actions/workflows/ci.yml/badge.svg)](https://github.com/kaisero/panos-response-pages/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Modern, responsive response pages for PAN-OS. Generate response pages to delight users while protecting them from threats.

**[Full documentation →](https://kaisero.github.io/panos-response-pages/)**

## Table of Contents

- [Preview](#preview)
- [Features](#features)
- [Quickstart](#quickstart)
- [Development](#development)
- [License](#license)

## Preview

[![A blocked-application page rendered in the Beacon Field style](docs/assets/preview-beacon.png)](https://kaisero.github.io/panos-response-pages/preview/)

Full Preview available via [Github Pages](https://kaisero.github.io/panos-response-pages/preview/) pages.


## Features

Use `panos-response-pages` to generate response pages that

- Provide responsive design for desktop and mobile
- Automatically serve light or dark mode depending on OS settings
- Automatically redirect users to sanctioned apps based on URL category match
- Link to the IT service desk via mail or link
- Support 7 themes across 4 colour palettes

Utilise the `import` functionality to...

- Import Response Pages into Strata Cloud Manager (Prisma Access)

## Quickstart

Install it:

```bash
pip install panos-response-pages
```

Or, with [uv](https://docs.astral.sh/uv/):

```bash
uv tool install panos-response-pages
uvx panos-response-pages build          # or run it without installing
```

Build the pages:

```bash
panos-response-pages build              # every style, into ./out
panos-response-pages themes             # what styles exist
panos-response-pages palettes           # what colour palettes exist
```

`out/deploy/<style>/<palette>/` is what you import into PAN-OS.
`out/preview/index.html` is a clickthrough gallery for review — style, palette,
page, viewport and colour scheme — built with sample data standing in for the
PAN-OS tokens.

Seven styles ship, all supporting both colour schemes. Six wear any of the three
brand palettes: `assist`, `record`, `banner`, `glass`, `beacon`, `mesh`. `nyan`
pins a palette of its own. See [Styles].

### Import into Strata Cloud Manager

Point a service account at a built variant, preview it, then import:

```bash
export SCM_CLIENT_ID='automation@1234567890.iam.panserviceaccount.com'
export SCM_CLIENT_SECRET='...'
export SCM_TSG_ID='1234567890'

panos-response-pages import scm --from out/deploy/beacon/prisma-blue --dry-run
panos-response-pages import scm --from out/deploy/beacon/prisma-blue
```

`--dry-run` contacts nothing. It lists all 13 pages and the folder each would be
written to, so the plan can be checked before anything is sent:

```
  scm: tenant 1234567890 (not contacted)

  ok   application-block-page                    7,594 B  Prisma Access
  ok   credential-block-page                     8,123 B  Prisma Access
  ...
  ok   url-block-page                           10,681 B  Prisma Access
  ok   global-protect-portal-custom-home-page    6,550 B  Mobile Users
  ok   global-protect-portal-custom-login-page  12,119 B  Mobile Users

  would import 13/13 page(s)
  dry run: nothing was sent.
```

Because nothing is sent, the credentials only have to be *set* for a dry run —
they are never used, so it works before a service account exists.

Two things worth knowing before the first real run:

- **Import stages, it does not push.** Writes land in the tenant's *candidate*
  configuration. Making them live is a separate step outside this tool, so a
  successful import does not mean the firewalls are serving the new pages yet.
- **Portal pages ignore `--folder`.** The 11 response pages go to `Prisma Access`
  (or wherever `--folder` says); the two GlobalProtect portal pages always go to
  `Mobile Users`. That is deliberate — a portal page is a named object that must
  be unique across the whole folder tree, and writing one to the wrong folder
  succeeds and then blocks the right folder until it is removed by hand.

The exit code is `1` if any page failed, so a partial import fails a pipeline
rather than passing quietly. Use `--only <page>` to import a single page and
`--folder` to target a different folder; credentials can also live in
`settings.yaml` under `scm:` instead of the environment. See the
[CLI reference](https://kaisero.github.io/panos-response-pages/cli/) for the
full set.

### Customise

Copy the shipped shells, palettes, themes and config out, then edit them:

```bash
panos-response-pages init               # into ~/.panos_response_pages, which build finds on its own
```

Put your own settings in `config/<customer>.json`. It is deep-merged over
`config/_defaults.json`, so list only what differs:

```json
{
  "company": "Example Corp",
  "supportUrl": "https://servicedesk.example.com/new-ticket",
  "supportEmail": "",
  "supportLabel": "the Service Desk",
  "redirect": {
    "enabled": true,
    "categories": {
      "online-storage-and-backup": {
        "app": "Company Drive",
        "url": "https://drive.example.com/",
        "seconds": 5,
        "message": "Work files belong on {app}. Taking you there."
      }
    }
  }
}
```

- **`company`** is the wordmark on every page.
- **`supportUrl`** points "Report to IT" at a ticket system instead of a mailbox.
  It must be an absolute `https://` URL — a response page is served *as* the
  blocked site, so a relative path resolves against whatever host refused the
  user. `supportEmail` and `supportUrl` are mutually exclusive: set one and blank
  the other, or the build stops. `supportLabel` names the queue for the places
  that print the contact inline — in email mode those print the address itself,
  so it applies to `supportUrl` mode only.
- **`redirect`** hands a user over to a sanctioned app after a countdown when the
  blocked category has an approved equivalent. It applies to the URL block page
  only. A category needs no entry in `categories` to redirect — that map lists
  only the ones whose tone or wording differs, and anything absent from it is
  calm — but a category listed there as `warn` or `critical` is refused, because
  a user must never be forwarded off a security block. Make sure your security
  policy actually permits the target, or the redirect lands on another block page.

Then build against it:

```bash
panos-response-pages build --customer <name>
```

## Development

```bash
uv sync --all-groups
uv run pre-commit install
uv run nox                            # lint, type-check, tests, docs
```

`nox -s tests` runs the suite with coverage; the gate is 93%. Commit `uv.lock`.

## License

MIT. See [LICENSE](LICENSE).
