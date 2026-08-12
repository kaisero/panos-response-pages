# panos-response-pages

Modern, responsive response pages for PAN-OS. Generate response pages to delight users while protecting them from threats.

## Preview

`panos-response-pages` generates responsive response pages for Desktop and Mobile which
support both dark and light mode by default. For a full preview of all available themes
and options take a look at the dedicated
[Preview](preview/index.html){ target="_blank" } pages.

<div class="rp-embed" id="rp-embed">
  <div class="rp-bar">
    <label class="rp-field">
      <span>Page</span>
      <select id="rp-page"></select>
    </label>
    <label class="rp-switch">
      <input type="checkbox" id="rp-scheme" aria-label="Dark mode" checked>
      <span class="rp-track" aria-hidden="true"><span class="rp-thumb"></span></span>
      <span class="rp-switch-label" aria-hidden="true"></span>
    </label>
  </div>
  <div class="rp-screen">
    <iframe id="rp-frame" title="Live response page preview" scrolling="no"></iframe>
  </div>
</div>

*Shown in the **Beacon Field** style. The
[Preview](preview/index.html){ target="_blank" } gallery adds the other six styles,
mobile widths and the four GlobalProtect login states.*

## Install

```bash
pip install panos-response-pages
```

## Install (From Source)

```bash
uv tool install panos-response-pages
uvx panos-response-pages build          # or run it without installing
```

## Quickstart

```bash
panos-response-pages build              # every style, into ./out
panos-response-pages themes             # what styles are available
panos-response-pages palettes           # what colour schemes are available
```

Output lands in two places:

| Path | Contents |
|---|---|
| `out/deploy/<style>/<palette>/` | Deployable pages, PAN-OS tokens intact |
| `out/preview/<style>/<palette>/` | The same pages with sample data, for visual review |
| `out/preview/index.html` | Clickthrough gallery — style, palette, page, language, viewport, colour scheme |

Import from `out/deploy/`. The preview build substitutes sample values for the
PAN-OS tokens so the pages render in a browser; it is **not** deployable.

The preview gallery fetches what you ask for and nothing else. Switching palette
reloads the frames from a sibling `preview/blobs-<palette>.js`; switching language
pulls that language's dictionary from `preview/lang-<code>.js`. That is why
`preview/` holds one file per palette and one per non-base language — the base
language has no sidecar, being the text the frames are already served in.

The point of the split is that `index.html` stays the same size whatever you
ship: about 1.83 MB with two languages and about 1.83 MB with thirteen. Inlined,
it would be a 5.9 MB document, most of it never looked at.

Style and palette are independent. A style that pins its own palette (nyan does)
decides only which palette the gallery opens on; every style is still built in
every palette, because the point of building all of them is to choose.

### Import into Strata Cloud Manager

Point a service account at a built variant, preview it, then import:

```bash
export SCM_CLIENT_ID='automation@1234567890.iam.panserviceaccount.com'
export SCM_CLIENT_SECRET='...'
export SCM_TSG_ID='1234567890'

panos-response-pages import scm --from out/deploy/beacon/prisma-blue --dry-run
panos-response-pages import scm --from out/deploy/beacon/prisma-blue
```

`--dry-run` contacts nothing — it lists all 13 pages and the folder each would be
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
  `Mobile Users`. A portal page is a named object that must be unique across the
  whole folder tree, and writing one to the wrong folder succeeds and then blocks
  the right folder until it is removed by hand — so the destination is fixed
  rather than configurable.

The exit code is `1` if any page failed, so a partial import fails a pipeline
rather than passing quietly. See the [CLI reference](cli.md#import-scm) for
`--only`, `--folder`, the `settings.yaml` form and the full credential
precedence, and [SCM import architecture](architecture/scm-import.md) for why
the API calls look the way they do.

## Customising

The shipped shells, palettes, themes and default config are packaged with the
tool. To change any of them, copy them out first:

```bash
panos-response-pages init               # copies to ~/.panos_response_pages
panos-response-pages build              # picks that up automatically
```

Resolution order, first hit wins:

1. `--config-dir PATH`, or `$PANOS_RESPONSE_PAGES_DIR`
2. `~/.panos_response_pages`, if it exists
3. the data shipped inside the package

It resolves as a whole tree rather than per file. Themes and shells are coupled —
a local `themes/` over packaged `templates/shells/` could name a shell that is
not there — so it is all-or-nothing, and `init` makes copying everything cheap.
`build -v` reports which directory it used and which rule chose it.

## Where to go next

- [CLI reference](cli.md) — every command and flag
- [Styles](styles.md) — the seven shells and the contract a new one must meet
- [Customising](customising.md) — config keys
