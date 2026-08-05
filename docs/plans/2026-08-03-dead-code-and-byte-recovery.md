# Dead code, byte recovery and complexity cleanup

> **STATUS: Phases 1-4 executed.** Phase 5 (`{{SCHEME_CSS}}`) and Phase 6
> (judgement calls) not started. See the execution record at the end for what
> shipped, what was skipped and why, and where this plan's estimates were wrong.

Holistic review of `src/` (Python) and `data/templates/` (HTML/CSS), plus the
follow-through plan. Two independent audits fed this; every headline number
below was re-measured against a real build before being written down.

---

## Executive summary

### What this buys

| Outcome | Now | After |
|---|---:|---:|
| `nyan/url-block-page` | 16,334 B (**over** the 16,000 B budget) | **15,868 B** |
| `nyan/url-coach-text` | 16,278 B (**over**) | **15,812 B** |
| Build report | 2 failing budget tests, 8 warning lines | **`no page warns or fails`** |
| Every other shell | 10,750–12,019 B | 10,358–11,627 B (−392 to −466 B each) |
| Python source | 3,480 lines | ~3,330 lines |

**The headline: the nyan overage is resolved entirely by deleting provably dead
CSS.** No artwork is touched, no budget is raised, no test is weakened. The
decision parked earlier — trim the cat, or raise `WARN_BYTES` — turns out to be
a false choice.

### The single decisive finding

Four CSS custom properties are declared in every scheme block of every shell and
referenced nowhere:

| token | declarations | `var()` references |
|---|---:|---:|
| `--wn`, `--wni`, `--ct`, `--cti` | 28 each | **0** |
| `--wnt`, `--ww`, `--ctt`, `--cw` | 28 each | 7 (one per shell) |

The sibling row is what makes this decisive rather than a guess: the warn/crit
path reaches the page through `--wnt`/`--ww`/`--ctt`/`--cw` only, aliased into
`--tt`/`--tw` by `html[data-tone=warn|crit]`. The other four are vestigial.
Removing all 112 declarations is a measured **216 B on every page of every
theme**, and it is the largest free win in the project.

### Cost and risk

Phase 1 is deletion of unreferenced declarations plus eight mechanical
substitutions. It was applied to a scratch copy of `data/` and rebuilt: 308
pages, **zero dangling `var()` references**, matrix clean. It needs no builder
change and no test change.

One finding is a **bug, not an optimisation**, and is worth doing regardless of
bytes: the PAN-OS-injected Continue button has no visible focus ring (§ Phase 2).

### Recommended order

1. **Phase 1** — byte recovery, unblocks nyan. Low risk, high value.
2. **Phase 2** — the focus-ring fix. 21 B, accessibility defect.
3. **Phase 3** — Python dead code. Mechanical.
4. **Phase 4** — Python complexity. Needs care; output must stay byte-identical.
5. **Phase 5** — `{{SCHEME_CSS}}`. Biggest remaining byte win, but touches tests.
6. **Phase 6** — judgement calls, deferred by default.

### Confidence

| Claim | Status |
|---|---|
| 4 tokens declared 28× / referenced 0× | **verified here** — grep, both directions |
| Phase 1 → nyan 15,868 B, matrix clean | **verified here** — scratch build |
| Phase 1 introduces no dangling `var()` | **verified here** — 308 pages parsed |
| `data-force-scheme` written only by `gallery.py:498` | **verified here** |
| Focus rule omits `input`; `appearance:none` present | **verified here** — all 7 shells |
| `theme_name` / `preview` params unused | **verified here** — `ruff --select ARG` |
| 4 `BuildResult` fields unread | **verified here** — grep, module-name collision excluded |
| `GALLERY_CSS.format()` is a no-op | **verified here** — 0 placeholders, 39 brace pairs |
| `format_report` collapse is byte-identical | agent-prototyped, **re-verify before merge** |
| `preview` == transform of `deploy` for 63/63 | agent-measured, **re-verify before merge** |
| Individual small-item byte counts | agent-measured per item; totals confirmed here |

---

## Phase 1 — Byte recovery (unblocks nyan)

Measured end state: nyan `url-block-page` **16,334 → 15,868 B**, 132 B of
margin under the 16,000 B budget, and `format_report` prints
`no page warns or fails`.

All edits are in `src/panos_response_pages/data/templates/shells/*.html` unless
noted.

### 1.1 Delete the four unreferenced tone tokens — 216 B/page, all shells

Remove `--wn:`, `--wni:`, `--ct:`, `--cti:` declarations from all four token
blocks (`:root`, `@media(prefers-color-scheme:dark)`, and both
`html[data-force-scheme=*]`) in all seven shells. 112 declarations total.

Do **not** touch the portal shells — `portal/login.html` genuinely uses
`var(--ct)`, and those are separate files with their own `:root`.

`test_declares_all_four_token_blocks_with_matching_names` compares the token
*sets* between the four blocks, so removing a name from all four keeps it green.

### 1.2 Drop the dead reduced-motion `transition` reset — 26 B/page

`transition:none!important;` inside `@media(prefers-reduced-motion:reduce)`.
No shell declares a `transition`, so it resets nothing.

- **beacon, glass, mesh, nyan** — remove the `transition` half; keep
  `animation:none!important`, which is live.
- **assist, banner, record** — these declare no `@keyframes`, no `animation:`
  and no `transition:` at all. Remove the whole media query (**93 B**).

The one thing the rule currently covers is `.rx-p span{transition:width 1s
linear}` from `redirect.CSS`, which ships only on a redirect-enabled build of
`url-block-page`. Move the guard to where it belongs — append to
`redirect.CSS` (`redirect.py:81`):

```css
@media(prefers-reduced-motion:reduce){.rx-p span{transition:none}}
```

49 B on the one page that has a countdown, against 93 B saved on the other 62
pages of those three shells. nyan cannot host the redirect at all
(`nyan.json` sets no `redirect` flag), so its removal is unconditional.

### 1.3 Remove the non-conforming cache meta — 46 B/page

```html
<meta http-equiv="pragma" content="no-cache">
```

`pragma` is not among the `http-equiv` pragma directives HTML defines, so the
document is non-conforming and no current browser acts on it. Cache behaviour
comes from the firewall's real response headers.

Evidence it is not a project convention: the portal shells do not carry it
(`grep -c http-equiv portal/shells/*.html` → 0 for all seven). It was copied
from the PAN-OS stock pages.

### 1.4 Modernise the font stack — 57 B/page

```
-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif   75 B
system-ui,sans-serif                                                            20 B
```

`system-ui` is Chrome 56+, Safari 11+, Firefox 92+ and resolves to exactly what
the long stack enumerates by hand on every platform those five names cover.

The mono stack is a **weaker case — take it separately**:
`ui-monospace,SFMono-Regular,Menlo,Consolas,monospace` →
`ui-monospace,Consolas,monospace` saves 21 B and keeps the Windows fallback that
`ui-monospace` does not provide outside Safari. Dropping `Consolas` too would
land Windows on Courier New; do not.

### 1.5 Remove `-webkit-font-smoothing:antialiased` — 35 B/page

Non-standard, WebKit/Blink only, purely cosmetic, and it thins glyph stems —
a small contrast loss on the already-muted `--im`/`--if` text.

### 1.6 Shorten the nyan card gradient — 33 B

```css
linear-gradient(180deg,rgba(255,255,255,.13),rgba(255,255,255,0) 45%)
linear-gradient(#ffffff21,#0000 45%)
```

`180deg` is the default gradient line. `#0000` and `rgba(255,255,255,0)`
interpolate identically — gradient interpolation is premultiplied in every
engine since ~2012, so a zero-alpha stop contributes no colour. `#ffffff21` is
alpha `.1294` against `.13`.

### 1.7 Small mechanical wins

| change | B/page | where |
|---|---:|---|
| `logoSvg`: drop `width="22" height="22"` | 23 | `config/_defaults.json` |
| info mark: drop `stroke-linejoin="round"` (it has no joins) | 24 | `config/_defaults.json` |
| nyan `<p class="mark">`: drop redundant `aria-hidden` | 19 | shell |
| nyan `#sky`: drop `display:block` | 14 | shell |
| nyan: `steps(1,end)` → `steps(1)` ×2 | 8 | shell |

`logoSvg`: all seven shells declare `.brand svg{width:1.25rem;height:1.25rem}`,
which wins over the presentation attributes. Update the `_logoSvg` doc comment
to tell customers to omit width/height.

nyan's `<p class="mark">`: its only child is an `<svg aria-hidden="true">` from
the MARK slot. Note banner's `.ghost` and beacon's `.seal` also carry
`aria-hidden`, but those wrap non-mark decoration — leave those two.

`#sky`: `position:fixed` blockifies (CSS Display 3 §2.7), so `display:block` is
already the computed value.

`steps(1)`: `end` is the initial `<step-position>` per CSS Easing L1 — same
timing function. The prose in `tests/_nyan_sprite.py` mentions `steps(1,end)`
and wants the same edit.

### 1.8 Hoist the nyan sprite fill — 60 B (do this in the generator)

`fill` is an inherited SVG presentation attribute and no CSS rule sets `fill` on
`.ny` or its ancestors. `fill="#000"` appears on 6 of 17 paths; hoisting it to
the root element removes 6 × 12 B and adds 12 B.

**This must be edited in `tests/_nyan_sprite.py`, not in the shell** —
`test_the_shell_carries_exactly_what_the_generator_produces` asserts the shell's
SVG is byte-identical to `compile_svg()`. Two lines:

```python
# paths(): skip the attribute for the hoisted colour
out += (f'<path d="{path_data(rects, ox, oy)}"/>' if hex_colour == PALETTE["k"]
        else f'<path fill="{hex_colour}" ...')
# compile_svg():
return (f'<svg class="ny" fill="{PALETTE["k"]}" viewBox="0 0 {WIDTH} {HEIGHT}" '
        f'shape-rendering="crispEdges">{body}</svg>')
```

Excluded from the measured 15,868 B figure above, so this is 60 B of additional
margin on top.

### 1.9 Explicitly rejected for nyan

- **Sprinkle paths as a dashed stroke** — measured −57 B and pixel-exact under
  `shape-rendering:crispEdges`, but it cannot be expressed by the
  rectangle-decomposer in `_nyan_sprite.py`, so it would need hand-patching into
  a generated string. Not worth breaking that invariant for bytes you no longer
  need.
- **Merging the `l0`/`l1` leg groups via a transform** — trades the deliberate
  frame-swap for a transform, which the shell comment explicitly says it is not
  doing.
- **`html{font-size:16px}`** (21 B) — dropping it is a *behaviour* change, not a
  cleanup: below 600px the page would then follow the reader's browser default.
  That is arguably more correct; see Phase 6.

### Phase 1 verification

```bash
uv run panos-response-pages build --out /tmp/p1
# expect: "no page warns or fails", largest page 15868 B
uv run pytest -q          # expect 0 failures
```

Plus the dangling-reference check that was run for this plan — parse every
built page's `<style>`, collect declared `--x:` against used `var(--x)`, assert
the difference is empty. 308 pages, currently zero.

---

## Phase 2 — The focus-ring bug (do regardless of bytes)

**The PAN-OS-injected Continue button has no visible focus ring.**

Verified in all seven shells. The focus rule is:

```css
a:focus-visible,.btn:focus-visible,button:focus-visible{outline:3px solid var(--tt);outline-offset:3px}
```

No `input`. Three rules earlier, in every shell:

```css
.acts input[type=submit],.acts input[type=button],.acts button{...appearance:none}
```

`input[type=submit]` matches the appearance reset — which is what removes
Safari's native focus ring — but not the focus rule. On `url-coach-text` and
`file-block-continue-page` that control is the **primary action**, injected by
`<pan_form/>`/`<cookie/>`. A keyboard user gets no focus indicator on it.

**Fix, 21 B:** add `,input:focus-visible` to the selector list in all seven
shells.

Cannot be caught by a template test, because the element only exists once PAN-OS
injects it. Worth an assertion in `test_shells.py` that the focus selector list
covers every selector in the `.acts` appearance-reset rule.

---

## Phase 3 — Python dead code

### 3.1 Two unused parameters

Both flagged by `uv run ruff check --select ARG src/`.

**`validate.py:64` — `theme_name`.** Never read in the body. Worse than unused:
`cli.py:271` passes `path.parent.name`, which under the current
`deploy/<style>/<palette>/<page>.html` layout is the **palette**, not the theme.
Removing it deletes a parameter that is actively lying about what the CLI knows.
Touches ~12 test call sites.

**`portal/page.py:87` — `preview: bool`.** All four call sites pass `False`
(`builder.py:288`, `tests/test_portal_config.py:121`, `tests/_build.py:47`,
`tests/test_contact.py:50`). The docstring already concedes "neither import
changes shape for preview". Symmetry with `build_page` does not justify a
parameter that has only ever received one value.

### 3.2 Four write-only `BuildResult` fields

`data_dir`, `data_reason`, `out_dir`, `palettes` (`builder.py:97-107`) are
populated at `builder.py:328-330` and never read. Verified by grep across
`src/`, `tests/`, `docs/`, `noxfile.py`; `.palettes` needed care because the
grep collides with the `palettes` *module*, and excluding module references it
is zero.

For contrast, the sibling fields *are* read — `.palette` at `cli.py:177`,
`.results`/`.portal_results` at `cli.py:159,166`, `.failed` at `cli.py:182`,
`.largest`/`.portal_largest` at `builder.py:369,437`.

Cascade: `build_all`'s `data_reason` parameter (`builder.py:170`) and
`cli.py:153`'s `data_reason=reason` go too — the CLI prints its own local
`reason` at `cli.py:178`, not the one it hands the builder.

### 3.3 `deploy_subdir` / `preview_subdir`

`builder.py:172-173`. No caller anywhere in `src/`, `tests/` or `noxfile.py`.
The docstring justifies them as "parameters only so the legacy `build.py` entry
point can keep emitting `dist/` and `preview/`" — there is no `build.py`, and
`tests/test_docs.py` exists specifically to assert the docs no longer describe
one. The stated condition for collapsing them has already been met.

### 3.4 Constants with only a test consumer

Not dead, but worth a decision rather than drift:

- `datadir.py:28 EXPECTED` — no consumer in `src/`; only
  `tests/test_datadir.py:56`. Either use it in `resolve()`/`portal_data()` or
  move it into the test.
- `settings.py:39 Settings.source` — assigned at `:79`, read only by
  `tests/test_settings_and_logs.py:31` (`assertIsNone`). It answers "which
  settings file did this come from", which nothing asks.

### 3.5 Every warning prints eight times

Observed directly in the build output: 8 `WARNING` lines for 2 distinct
problems, then all of it again in the report's flagged section.

Two causes in one loop (`cli.py:159-171`): the log key is `"%s/%s"` on
`(theme, page)` while rows are keyed `(theme, palette, page)`, so four palette
rows collapse into four indistinguishable lines; and the table below repeats it.

`--log-json` suppresses the table (`cli.py:173`), so the loop cannot simply be
deleted. Fix: `log.warning("%s/%s/%s: %s", r.theme, r.palette, r.page, w)` and
gate both loops on `ctx.obj["json"]`. No test asserts on these lines.

---

## Phase 4 — Python complexity

Output must stay byte-identical through this phase. Diff a full report and a
full `deploy/` tree before and after.

### 4.1 Collapse the duplicated report builders — ~117 lines → ~60

`builder.py:344-460`. `format_report` and `_portal_report` each contain the same
worst-row-per-cell fold, the same table skeleton, and a **verbatim-identical**
flagged-rows tail (`:372` and `:440`). `_worst_status` (`:387`) and
`_worst_portal_status` (`:450`) differ only in which list they filter.

Three private helpers taking a *row list* rather than a `BuildResult`:

```python
def _worst_rows(rows):              # the fold, once
def _status(rows, theme, palette):  # FAIL > warn > ok, once
def _flagged(rows):                 # the tail, once
```

Also collapses `PageResult.status` / `PortalResult.status` (`:65-67`, `:89-91`),
the same two lines twice — `PortalResult` can subclass `PageResult`. The comment
at `:101-103` defends keeping the two *lists* apart, which inheritance does not
disturb.

The audit prototyped this and reported a zero-line diff against a real 28-cell
build. **Re-verify that before merging.**

### 4.2 Un-escape `GALLERY_CSS` — ~39 brace pairs

`gallery.py:27-108` and `:385`. Measured: 5,376 chars, 39 `{{` pairs, **zero**
single-brace placeholders, and `GALLERY_CSS.format()` is exactly
`replace("{{","{").replace("}}","}")`. Every doubled brace exists only to
survive a `.format()` whose sole effect is to undo them.

The comment at `:128-136` describes palette values being "interpolated raw into
GALLERY_CSS — a `.format()` template". They are not; they are *concatenated* in
via `_chrome_tokens`. Update the comment with the code.

Use single braces and `+ GALLERY_CSS`. This also removes a live trap: anyone
editing that CSS today must remember to double every brace, and forgetting
raises at build time.

**Do not touch the `{{` in `gallery_html`** — that is a genuine f-string
carrying JavaScript.

### 4.3 Give the external-reference rule one home

`validate.py:98-105` and `portal/validate.py:173-179` implement the same rule —
walk back to the enclosing tag, exempt the one `id="rep"` contact anchor — and
the portal version reaches across the package boundary for two **private** names
(`from panos_response_pages.validate import _IS_ANCHOR, _IS_REP`,
`portal/validate.py:21`).

This is one security rule about one anchor living in two places: the shape where
copies drift and only one gets fixed. `validate.py` should own it (portal
already depends on validate, not the reverse):

```python
def external_refs(text: str) -> Iterator[re.Match[str]]:
    """Every src/href to an off-page origin, minus the one exempt contact anchor."""
```

Use the portal's URL-capturing regex — a superset of the block-page version.
Each caller keeps its own message and its own "break after first" vs "report
all" policy, so behaviour is preserved on both sides.

### 4.4 Small, mechanical

- `settings.py:42` — `bool(value) if isinstance(value, bool) else fallback`.
  Inside that arm `bool(value)` *is* `value`.
- `logs.py:32` — `set(vars(...).keys() | {...})`. `KeysView.__or__` already
  returns a `set`; the outer call is a copy for nothing.
- `builder.py:320`/`:329` — `[loaded[n] for n in palette_names]` built twice.
  Hoist above the loop.
- `page.py:123-124` — `parts.get("TONE", "calm")` evaluated twice on adjacent
  lines. One local.
- `page.py:162-164` vs `portal/page.py:210-212` — the same leftover-`{{` guard,
  but the portal version handles `{{` present yet matching no `[A-Z_0-9]` token
  and `page.py` does not, so a lowercase `{{foo}}` raises with an empty list.
  Better: one `assert_resolved(text, where)` in `templates.py` owning all three
  copies.
- `builder.py:162` is C901 21 / PLR0912 20, driven by six `if write:` arms.
  A closure at the top folds five into unconditional calls — keep the two
  `mkdir` blocks guarded, or you add ~750 syscalls.
- Three sources of truth for "the two portal pages": `builder.py:32`,
  `cli.py:29`, `portal/page.py:39 FRAMES`. `FRAMES` should own it.
- `cli.py:45 _names("palettes", ...)` re-implements `palettes.available()`.
- `builder.py:158` — `opening_palette`'s fourth fallback hardcodes
  `"cyber-orange"`, duplicating `_defaults.json`. Since `build_all:215` now
  raises for any name not in `loaded`, `cfg.get("palette")` says the same with
  one less name to keep in sync.

---

## Phase 5 — `{{SCHEME_CSS}}`: the biggest remaining win

`html[data-force-scheme=light|dark]` blocks are **519–603 B/page × 9 pages × 7
shells** and are preview-only.

Verified: the attribute is written in exactly one place in the repo —
`gallery.py:498`, `i.contentDocument.documentElement.setAttribute("data-force-scheme", S.scheme)`,
on the preview iframe's document. Nothing on a firewall sets it.

Implementation: a `{{SCHEME_CSS}}` token carrying the blocks in preview builds
and `""` in deploy — the same shape as `("" if preview else FRAME_BUSTER)` at
`page.py:136`.

Test changes needed:
- `test_shells.py:251` `test_declares_all_four_token_blocks_with_matching_names`
  requires the blocks to exist — read them from the token instead of the shell.
- `test_shells.py:299` iterates `html[data-force-scheme=...]` selectors.
- `test_docs.py:184` checks for `data-force-scheme` in preview output — still
  true, since preview keeps it.

Sequenced last because it is the only byte item that changes the builder and the
tests rather than deleting declarations. With Phase 1 already done, nyan does not
need it — this is headroom for future work, not a fix.

---

## Phase 6 — Judgement calls (deferred by default)

**The `marks` config has drifted.** Nine entries declared; `page.py` reads only
`warning`, `info` and `shield`, and `shield` is a fallback that never fires
because all nine page templates define their own `<!--@MARK-->`. `alert`, `key`,
`file`, `download`, `malware`, `search` are unreferenced. Zero output bytes, but
the `_marks` doc string describes a mechanism no page uses. *Decide: prune, or
fix the doc to describe what actually happens.*

**The mailto anchor ships its copy twice** — 355 B of a ~400 B element, on 8 of
9 pages in email mode. `category_js` overwrites `a.href` from the `data-*`
attributes on load, so the static href is a no-JS fallback and three strings
ship once plain and once percent-encoded. **This is a deliberate trade, not a
bug.** Only you can decide whether a JS-less browser is in scope.

**`html{font-size:16px}`** — 21 B, but removing it means readers below 600px get
their own browser default. Arguably correct; it is a behaviour change either
way.

**Desktop overrides the reader's font-size preference.**
`@media(min-width:600px){html{font-size:19–20px}}` pins the root size regardless
of the reader's setting. Zoom still works so it is not a WCAG failure, but
someone who set 24px gets 20px here.

**assist's brand row keeps the UA `<p>` top margin.** `.brand{...margin-bottom:2rem}`
— the other five shells using `<p class="brand">` write `margin:0 0 X`, so
assist alone inherits `margin-top:1em`, showing as ~20px of extra space above
the logo row. Very likely unintended.

**`<dd id="ts">` is empty without JS**, leaving a visible `<dt>Time</dt>` with a
blank value. Cheap to fix by not emitting the row; expensive in template
plumbing.

**Repeated work.** A full build is **0.31 s**, so none of this is a performance
problem — the argument is that "this fixture is read 224 times" and
"`category_js` is computed 528 times for 4 distinct answers" are facts a reader
of `build_all` cannot see, and they scale linearly with the matrix.

| what | now | distinct results |
|---|---:|---:|
| `fixtures/panos-prefix-login.html` (8.4 KB) | 224 reads | 1 |
| each shell / page template | 56–80 reads each | 1 |
| `splice._set_var` (regex over 8.4 KB) | 504 calls | 8 |
| `scripts.category_js` | 528 calls | 4 |
| `portal.page._values` | 56 calls | 4 |
| `contact.check` | 584 calls | 1 |

The structural one: `build_all:250` and `:260` build every page **twice**, and
the two outputs differ only by the frame-buster and sample-token substitution.
The audit verified the transform holds for 63/63 theme×page combinations —
**re-verify before acting.** Hoisting removes 252 of 528 `build_page` calls.
Caveat: the 24 redirect-demo builds use a *different* config and must stay
separate.

**Do not add a global `lru_cache` on `templates.read`.** It is worth ~13%
(0.312 s → 0.272 s), but several tests copy the data tree to a temp dir, edit a
file and rebuild in the same process — a path-keyed cache would serve stale
bytes and produce baffling failures. Scope any memo to a single `build_all`.

**Leave `redirect.check` alone.** It is called 528 times on an unchanging dict,
but `emit` validates before its early return so a bad redirect config fails the
build even on the 251 combinations that never render the notice. Moving it to
`build_all` would silently drop validation for direct `build_page` callers,
which is what the tests are. Low value, real risk.

---

## Leave-alone register

Confirmed live despite looking dead. Deleting any of these breaks something that
only appears on a real firewall, or removes a guard against a silent failure.

**CSS / markup**

- `.acts input[type=button]`, `.acts button`, `.acts button:hover`,
  `button:focus-visible` — nothing in `templates/` emits them; they exist for
  what `<pan_form/>` and `<cookie/>` inject on a live box.
- `html[data-warp] .ny` (nyan) — the attribute is set by nyan's own click
  handler for 900 ms.
- The `color-mix` fallback pairs in nyan, glass and mesh —
  `test_color_mix_always_has_a_fallback` enforces them, and correctly:
  unsupported, the whole declaration is dropped and a translucent panel loses
  its background entirely. Worth ~82 B in nyan *if* you ever decide `color-mix`
  is baseline; do not take it silently.
- `-webkit-backdrop-filter` (glass, mesh, nyan) — Safari only shipped the
  unprefixed property in 18.0.
- `-webkit-mask-image` (mesh) — same, Safari < 15.4.
- `inset:0` on `#sky` alongside `width/height:100%` — `canvas` is a replaced
  element, so `left:0;right:0` with `width:auto` uses intrinsic width rather
  than stretching. `inset:0` is also 6 B shorter than `top:0;left:0`.
- `.fly{top:22vh;right:8vw}` — the resting values, and what stands if the script
  never runs.
- The cross-shell duplication (537 B/page across 13 byte-identical rules) — each
  page must be self-contained, so a builder-emitted common block would still be
  written into every file. **Output bytes unchanged. Do not chase it.**

**Python**

- `validate.py:36,42` `_IS_REP`/`_IS_ANCHOR` as regexes — the comment names the
  exact hole (`xid="rep"`, `<area`) and is right.
- `scripts.py:16 TONE_CSS` spelling tones out in full — a real bug once rendered
  critical pages calm.
- `scripts.py` `LABEL_WORDS` and the derived label over a 3.3 KB label map —
  byte-ceiling trades, argued with numbers.
- `scripts.py:80-138` conditional JS assembly — four pages emitting only the JS
  they can use. `email_mode` is correctness, not size.
- `emit.py:24-25,34` — HTML comments stripped before CSS comments, and the
  `//`-only-whole-lines rule. Both prevent concrete corruption.
- `templates.py:14` `read_text`, `builder.py:257` `write_bytes` — newline
  translation would shift byte counts after `validate` measured them.
- `palettes.py:32-37` filename-vs-`name` check.
- `redirect.py:126-154` `supported()`/`declares()`; `:237-241` the `isinstance(value, bool)`
  rejection (`bool` is an `int`; without it `"seconds": true` is a 1-second
  countdown); `:294` host-loop guard; `:276` the `loop`/`go` split.
- `page.py:99-101` the `redirect_demo and not preview` raise — keeps a looping
  countdown out of `deploy/`.
- `page.py:177 MAILTO_HREF` matched as an href, not a substring.
- `portal/splice.py:117-129` `_set_var`'s `count != 1` assertion.
- `portal/page.py:127-151` `_css_string`/`_js_string`/`LOGO_SAFE` — one raw `<`
  stops PAN-OS substituting the form token.
- `portal/validate.py:91-99` `encodebytes` not `b64encode` — the 1.4%
  difference decides whether an import is refused.
- `datadir.py:54-80` `portal_data`'s loud fallback; `builder.py:224-234` the
  stale-redirect-flag warning.

---

## Verification plan

Per phase:

1. `uv run pytest -q` — 0 failures.
2. `uv run panos-response-pages build --out /tmp/vN` — expect
   `no page warns or fails`.
3. Dangling-reference sweep — parse every built page's `<style>`, assert
   `{var(--x) used} - {--x: declared}` is empty across all 308 pages.
4. For Phase 4 only: capture `format_report(result)` and the full `deploy/`
   tree before and after, and diff. Byte-identical is the acceptance bar.
5. For Phase 1 CSS deletions: render one page per shell in a browser at both
   schemes and both tones before calling it done — the tests assert selector
   *presence*, not visual result.

Step 5 matters because every automated check here is textual. The tone tokens
being unreferenced is proven; that the pages still *look* right after removing
93 B of media query from three shells is not something the suite can tell you.

---

## Execution record

Phases 1-4 executed. Suite: **443 passed, 0 failures** (was 442 passed / 2 failed
on the nyan budget; +1 is a new test, see below). Full build reports
`no page warns or fails`.

### Measured outcome

| page (nyan theme) | before | after | Δ |
|---|---:|---:|---:|
| `url-block-page` | 16,334 | **15,773** | −561 |
| `url-coach-text` | 16,278 | **15,717** | −561 |
| `credential-block-page` | 13,831 | **13,270** | −561 |

Every shell, `url-block-page`: assist 10,863→10,368 · banner 10,985→10,491 ·
beacon 11,711→11,284 · glass 12,019→11,592 · mesh 11,627→11,200 ·
record 10,750→10,256. nyan headroom under the 16,000 B budget: **227 B**.

### Where this plan's estimate was wrong

It predicted Python source would fall from 3,480 to ~3,330 lines. It **rose to
3,520**. The deletions were real, but the duplication they removed was replaced
by six documented helpers (`_worst_rows`, `_status`, `_flagged`,
`external_refs`, `assert_resolved`, `emit`), and this codebase documents *why*
at length. Net: one copy of each rule instead of two or three, at +40 lines.
The estimate counted deleted lines without costing the replacements.

Tests fell 5,381 → 5,323.

### Verification performed

- **Sprite hoist**: all 17 paths resolve to identical `(fill, d)` pairs after
  inheritance; group structure unchanged; −60 B exactly.
- **Report collapse**: the pre-refactor implementation was pasted in beside the
  new one and both run over five synthetic `BuildResult`s — clean, warn, FAIL,
  no-portal, mixed. **Byte-identical on all five**, including the FAIL and
  portal-flag branches a clean build never reaches.
- **`external_refs` consolidation**: 10 boundary cases run against both callers
  — exempt `id="rep"` anchor, the same anchor over http, `xid="rep"` and
  `data-id="rep"` near-misses, stray anchor, external stylesheet, external
  image, `<area>`, mailto, relative. **Exemption boundary identical on both
  sides.**
- **Phases 3-4 output neutrality**: full `deploy/` and `preview/` trees diffed
  against the post-Phase-2 build — **identical, byte for byte**.
- **`GALLERY_CSS`**: emitted stylesheet compared before/after un-escaping —
  identical; `index.html` byte-identical.
- **CSS integrity**: 308 built pages, **0 dangling `var()`**, 0 unbalanced
  stylesheets.
- **`write=False`**: still produces 252 page results and 56 portal results
  while writing **0 files**.

### Deviations from the plan

**Skipped — `opening_palette`'s `cyber-orange` literal (§4.4).** The plan wanted
`cfg.get("palette")` with no default. But the expression is a `str(a or b or c
or d)` chain: with every term absent it yields the string `"None"`, and the
build then raises `unknown palette 'None'`. That is a worse error than today's
silent fallback, and removing the literal would mean adding a guard to replace
it — complexity-neutral at best. Left as is.

**Skipped — merging `cli._names` into `palettes.available` (§4.4).** `_names`
carries an `OSError` guard that `palettes.available` does not, and it is used by
the shell-completion callbacks. Merging would either lose the guard (breaking
tab-completion against an unreadable data dir) or push it into the build path,
where swallowing an OSError is wrong. The duplication is justified; the audit
missed the guard.

**Changed — the `PORTAL_PAGES` agreement check.** The plan said "asserted
against it". `ruff` bans `assert` in `src/` (S101), and an import-time raise is
the wrong shape for this. It became a test instead —
`test_cli.py::TestPortalTablesAgree` — which is the +1 test in the count above.
`builder.PORTAL_PAGES` is now `tuple(FRAMES)` as planned.

**Partial — `build_all` complexity (§4.4).** Five `if write:` arms folded into
an `emit()` closure; C901 21→20, branches 20→17. The two `mkdir` guards stayed
guarded deliberately — folding them in would mean a `mkdir` per file rather than
per directory, ~750 extra syscalls per build. Still above the C901 threshold.

**Incidental — `loaded[n]` duplication (§4.4) resolved itself.** Removing the
dead `BuildResult.palettes` field left only one use.

**Also done, not in the plan:** the third copy of the unresolved-placeholder
guard (`portal/page.py:117`) was found during the work — the plan named two.
All three now call `templates.assert_resolved`, which keeps the `or '{{...}}'`
fallback that only one of the three had.

### Still outstanding

- **Phase 5** (`{{SCHEME_CSS}}`, 519-603 B/page × 63 pages) — not started. nyan
  no longer needs it; it is headroom for future work.
- **Phase 6** — untouched by design: the `marks` config drift, the mailto
  double-encoding, `html{font-size:16px}`, the desktop font-size override,
  assist's brand-row margin, the empty `<dd id="ts">`, and all the repeated-work
  items.
- **The browser pass (verification step 5) has NOT been done.** Every check run
  here is textual. That the four tone tokens were unreferenced is proven and
  that no page has a dangling `var()` is proven; that the pages still *look*
  right — particularly the three shells that lost a whole reduced-motion media
  query, and nyan's card gradient and hoisted sprite fill — is not something the
  suite can tell you. Open the gallery at both schemes and both tones before
  treating Phase 1 as finished.
