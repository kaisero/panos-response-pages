# Styles

Seven styles ship. `assist` is the default and the most conservative; the rest
are the same ten pages under different layouts. Six of them wear any of the
three brand palettes; `nyan` pins a palette of its own. All support both colour
schemes.

| Style | Layout |
|---|---|
| `assist` | Assistive Panel — single column, indicator beside the heading |
| `record` | Record Panel — flat accent rule, header bar, facts as a register |
| `banner` | Accent Banner — full-bleed accent band, oversized heading, facts in a sidebar |
| `glass` | Glass Panel — layered panel over an ambient field, facts as cards |
| `beacon` | Beacon Field — drifting dot field with an animated seal |
| `mesh` | Mesh Panel — masked hairline grid under a glass card |
| `nyan` | Nyan Runway — pixel cat flying a bending rainbow across a star field, glass notice beside the lane |

## A style that owns its colour

Layout and colour are separate axes on purpose: swapping an accent must not mean
forking a shell, which is why six shells × three palettes is nine files rather
than eighteen. `nyan` is the exception that proves where the axis ends. Its
colour *is* the style — a spectrum trail over a night sky is not a thing you
render in a customer's cyan — so it ships a palette and pins it:

```json
{ "name": "nyan", "shell": "nyan", "palette": "nyan" }
```

Palettes declare which sort they are:

| `kind` | Meaning |
|---|---|
| `brand` | The customer axis. Any style may wear it, and it is what `--palette` chooses between |
| `style` | Belongs to one shell, which pins it. Not a choice offered to a customer |

The pin is the weakest of four inputs, and all four now settle a smaller
question than they used to: every style is built in every palette regardless,
so none of this decides what gets built any more, only which palette the
preview gallery opens on — the CLI report calls that one out as
`gallery opens on:`. In order:

1. `--palette` on the command line — the one exception: passing it also
   narrows the build itself to that single palette, rather than just picking
   which one is shown first
2. `palette` in `config/<customer>.json` — the customer's own document
3. the theme's pin
4. the shipped default

Rung 2 reads the customer file directly rather than the merged config, because
`_defaults.json` ships a `palette` and the merged view therefore always carries
one. Counting that as a choice would mean a pin could never fire.

Only one guard differs by kind. `test_dark_grounds_are_tinted_not_saturated`
caps a dark ground's saturation, so that a brand hue stays a whisper behind an
interface; a style palette's dark ground is artwork, not a tinted neutral, and is
exempt.

## Adding one

A style is a shell plus a theme, both discovered by glob, so adding one needs no
code change.

```bash
panos-response-pages init                  # get a writable copy of the data
cd ~/.panos_response_pages
cp templates/shells/assist.html templates/shells/mystyle.html
cp themes/assist.json themes/mystyle.json   # set "name" and "shell" to mystyle
panos-response-pages build --theme mystyle
```

Colour is a separate axis from layout, so an accent change never forks a
shell.

### What a shell must do

`tests/test_shells.py` enforces all of this against every file in
`templates/shells/` in the data directory, because every item fails **silently**:
the build errors only
on *unknown* placeholders, never on a missing or misplaced one.

- Render all twelve placeholders: `{{TITLE}} {{HEADLINE}} {{GLOSS}} {{FACTS}}
  {{ACTIONS}} {{EXTRA}} {{MARK}} {{TONE}} {{SEVERITY}} {{COMPANY}} {{LOGO_SVG}}
  {{SCRIPTS}}`.
- **Wrap `{{FACTS}}` in a literal `<dl>`.** The mailto rebuild is
  `querySelectorAll('dl .f')`. A `<div class="facts">` renders identically and
  then overwrites the working `href` with one carrying no fields at all.
- Give the gloss element `id="gloss"`, or `url-block-page` and `url-coach-text`
  show the generic sentence instead of the per-category one.
- Put `{{SCRIPTS}}` **after** the content. It is a bare IIFE with no
  `DOMContentLoaded` guard; in `<head>` it loses the timestamp, the mailto
  rebuild, the gloss rewrite and the severity label.
- Keep `{{EXTRA}}` in the same column or panel as `{{ACTIONS}}` — it is the
  callout, and a shell that closes its panel first strands it on the background.
- Declare **all four** colour blocks — `:root`, `@media(prefers-color-scheme:dark)`,
  `html[data-force-scheme=light]`, `html[data-force-scheme=dark]` — with the
  **same token names** in each. The preview gallery forces a scheme, so a token
  declared in one block and forgotten in another renders one colour in review and
  a different one in production.
- Any decoration that varies by scheme (orb opacity, glass fill) must be a token
  in those four blocks, never an element rule overridden per scheme: an element
  override has no way back when the gallery forces *light* on a dark-OS machine.
- Style what the pages emit: `.f dt dd dd.mono .btn .plain .infobox .warnline
  .note`, plus `.acts input[type=submit]` and `.acts button` for the PAN-OS
  injected `<pan_form/>`/`<cookie/>` controls. Keep `overflow-wrap:anywhere` on
  `dd` — only `anywhere` contributes to min-content sizing, which is what lets a
  long URL fit a narrow column.
- Handle 2, 3 and 4 fact rows. `safe-search-block-page` has two, the file and
  virus pages three, the rest four.
- Render `{{SEVERITY}}` somewhere, and hide it when empty with `.sev:empty` placed
  **after** the rule that paints it — the two have equal specificity, so source
  order alone decides whether a calm page shows a bare coloured chip.

How a shell *expresses* severity is its own business: `assist`, `banner`,
`glass`, `beacon`, `mesh` and `nyan` use a pill, `record` uses an eyebrow, and `beacon`
additionally tints its seal rings. What no shell may do is repaint the brand row
or the primary action by tone — the logo is the customer's and the action is the
brand's.

The corollary is easy to get wrong: **anything decorating the indicator takes the
tone colour too.** `glass`'s pulse and `beacon`'s rings are the indicator's own
halo, so on a caution page they are the caution yellow the icon is, not the
palette accent. This one is not testable — a blanket "everything around the mark
is tone" rule would fail `banner`, whose watermark is correctly drawn in the
band's ink — so it is a convention to hold by eye.

### Three rules the shells argued out

**`color-mix` needs a fallback.** It is newer than the CSS this project assumes,
and an unsupported declaration is dropped whole — a translucent panel would lose
its background entirely and its text would land on whatever is behind it. Always
write the solid value first:

```css
background:var(--gr);
background:color-mix(in oklab,var(--gr) 88%,transparent);
```

Nothing can measure ink contrast through a translucent panel, so the mix stays at
88–92%: opaque enough that the palette's guarantees approximately hold.

**Radial gradients are texture only.** Radial fills are not used. A
1.4 px dot at 24 px spacing is not a fill, so `beacon`'s drifting field keeps it,
and `mesh` uses one in a `mask-image`, which paints nothing. Ambient orbs do
*not* need it: a blurred flat disc is indistinguishable from a blurred radial
gradient and stays inside the rule.

**No animation may imply an activity the page cannot substantiate.** The
prototype's scan sweep — a line travelling down the page every few seconds — was
cut for the same reason `BANNED_COPY` exists: it reads as scanning happening now,
and the page has no way to know that. Ambient drift and pulses claim nothing and
stay.

Ambient fields are `position:fixed`. Hung off the page edge with absolute
positioning they count as scrollable overflow, which gives the real page a
scrollbar and every preview frame a few hundred pixels of dead space.
