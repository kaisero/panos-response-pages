# Customising

Run `panos-response-pages init` first, then edit `config/_defaults.json` in the
copied tree, or add `config/<customer>.json` with only the keys
that differ — it is deep-merged over the defaults. Keys prefixed `_` are inline
documentation and are ignored by the build.

| Key | Notes |
|---|---|
| `company` | Brand row, and the credential pages' "will never ask for your password" line |
| `supportEmail` | Target of every `mailto:` |
| `logoSvg` | **Inline SVG, ≤2 KB optimised.** A traced-path export can be 40 KB and will silently break the page. Use `currentColor` so it inherits the theme. |
| `continueGrantText` | Must match your URL Admin Override timeout |
| `palette` | Colour scheme: `cyber-orange`, `strata-yellow` or `prisma-blue`. Override per build with `--palette` |
| `categories` | `category → {tone, gloss}`; tone is `calm`, `warn` or `critical` |
| `defaultGloss` | Used for any category not in the map — keep it true of every category |

Each page declares its own `<!--@MARK-->` — an inline SVG shown as a large
indicator beside the heading, tinted by severity. `marks.warning` in config is a
separate icon used by the warning callouts.

The category map is applied **client-side**, by reading the substituted
`<category/>` value from the DOM. PAN-OS exposes no severity variable and serves
one page per type, so per-category messaging cannot happen server-side.

The two credential pages set `<!--@COPY_LOCK-->1<!--/@COPY_LOCK-->`, which pins
their tone and gloss to what the template declares. A phishing interstitial must
not be repainted calm because of how its category happens to map.
