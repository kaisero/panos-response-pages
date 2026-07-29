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
[Preview](preview/index.html){ target="_blank" } gallery adds the other five styles,
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
| `out/deploy/<style>/` | Deployable pages, PAN-OS tokens intact |
| `out/preview/<style>/` | The same pages with sample data, for visual review |
| `out/preview/index.html` | Clickthrough gallery — style, page, viewport, colour scheme |

Import from `out/deploy/`. The preview build substitutes sample values for the
PAN-OS tokens so the pages render in a browser; it is **not** deployable.

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
- [Styles](styles.md) — the six shells and the contract a new one must meet
- [Copy rules](copy-rules.md) — what the page is not allowed to claim
- [Customising](customising.md) — config keys
