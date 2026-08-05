# Test suite cleanup — dead and low-quality tests

Audit of `tests/` against `src/`. Baseline: **5,381 lines / 28 files / 458 tests
+ 1,199 subtests, 5.6 s**. Three known failures (nyan over the 16,000 B budget)
are expected and are not the subject of this document.

Runtime is not the motivation. The suite finishes in under six seconds and the
slowest single test is 0.43 s. Everything below is about maintenance cost: tests
that cannot fail, tests that must be hand-edited when unrelated copy changes, and
rules asserted in three places so a change has to be made in three places.

Estimated outcome: **−211 lines, −31 tests**, no reduction in what the suite
catches.

---

## 0. Do this one first — it is a bug, not a smell

`tests/test_layout_details.py:191` and `tests/test_redirect.py:491` both place

```python
if __name__ == "__main__":
    unittest.main()
```

**before** further class definitions. Measured:

| file | direct run | pytest collects |
|---|---:|---:|
| `test_layout_details.py` | 18 | 32 |
| `test_redirect.py` | 50 | 52 |

16 tests do not exist for anyone running a file directly. Move both blocks to
end of file. Zero risk.

---

## 1. Delete

### 1.1 `tests/test_portal_splice.py:125-126` — re-executes the production expression

```python
def test_every_state_has_a_preview_file_name(self):
    self.assertEqual(LOGIN_PREVIEWS, tuple(f"login-{s}" for s in STATES))
```

`src/panos_response_pages/portal/splice.py:95`:

```python
LOGIN_PREVIEWS = tuple(f"login-{state}" for state in STATES)
```

The right-hand side is the definition, verbatim. No source change can make it
fail — renaming a state changes both sides identically, deleting `STATES` breaks
the import rather than the assertion.

### 1.2 `tests/test_palette_pinning.py:45-48` — literal duplicate of `:36-37`

Same call, same argument, same expected value as
`test_a_pin_decides_when_nothing_else_speaks`. The docstring documents a real
regression (`_defaults.json` always carries a palette, so a naive `cfg['palette']`
would mean a pin could never fire) — keep the docstring by merging it into the
first test, drop the second.

### 1.3 `tests/test_palette_pinning.py:50-54` — covered elsewhere, and costs a build

`test_a_pin_does_not_remove_anything_from_the_build` spins a full `build_all` to
assert what `test_palette_matrix.py:54-60` already asserts off the shared matrix
build. `test_palette_matrix.py` should own it — it is the file about the matrix.

### 1.4 `tests/test_severity.py` — five rules already enforced across all shells

`test_shells.py` loops all 7 shells; these assist-only copies can only fail after
the all-shells version already has.

| `test_severity.py` (assist only) | Already in `test_shells.py` (all shells) |
|---|---|
| `:44` primary button uses palette accent | `:307` — same assertions plus `var(--tt)`/`var(--tw)` |
| `:63` no text sits on a gradient | `:388` — same selector set, plus a conic ban |
| `:73` gradient is linear only | `:393` + `:398` |
| `:83` empty severity pill is hidden | `:327` — stronger, also checks source order |
| `:88` every link context is palette-coloured | `:371` — same contexts, same token |

`:30 test_brand_stays_on_accent` is a near-duplicate of `test_shells.py:317`;
fold its two extra tokens (`var(--tone)`, `var(--ti)`) into the all-shells
version and delete it.

One is worse than redundant — `:73`:

```python
self.assertIn("linear-gradient(", SHELL)
```

This pins a *design decision*, that assist has a gradient at all. `test_shells.py`'s
module docstring states the opposite rule: *"Design choices — where the mark sits,
how the callout is drawn, whether there is a gradient — are deliberately not
asserted."*

**Keep** `:54-61` (severity still visible somewhere), `:79-81` (the `.brand .sev`
specificity rule) and all of `TestSeverityAtRuntime` `:101-120` — genuinely
assist-specific or about emitted output.

### 1.5 `tests/test_layout_details.py:91-94` — bans something never present

```python
def test_no_color_mix_dependency(self):
    self.assertNotIn("color-mix", SHELL)
```

`SHELL` is assist, which has never contained `color-mix`. Three shells do
(`mesh`, `glass`, `nyan`) and `test_shells.py:412` **permits** it there provided a
solid fallback precedes it. So this assist-only blanket ban states a rule the
project does not hold. `test_shells.py:412` is the real rule.

### 1.6 `tests/test_layout_details.py:184-188` — assist-only copy of an all-shells rule

`test_pan_form_controls_are_styled` duplicates `test_shells.py:350-355`, which
asserts the same two patterns for every shell — with the same docstring, copied
verbatim between the files.

### 1.7 `tests/test_layout.py:53-57` — third copy of "every theme emitted a directory"

Subsumed twice, by stronger assertions: `test_shells.py:440-446` compares the full
`theme/palette/page.html` path list against the expected product set, and
`test_palette_matrix.py:62-68` walks every cell and compares its file list to
`PAGE_TOKENS`.

### 1.8 `tests/test_layout.py:48-51` — tests a config file, not the code

`test_gitignore_excludes_artifacts` reads `.gitignore` and asserts three entries.
No production behaviour reads `.gitignore`; it fails only when someone edits it,
which is the same act as intending the change.

Note `test_docs.py:122` separately asserts `docs/preview/` is ignored for a reason
that *is* load-bearing (codespell) — that one stays.

### 1.9 `tests/test_redirect.py:181-184` — two of three lines assert constants

```python
self.assertEqual(redirect.DEFAULT_SECONDS, 10)              # redirect.py:45 says = 10
self.assertEqual(shipped()["redirect"]["seconds"], 10)      # config == literal
self.assertIn("var S=10,", script_of(render(configured()))) # the real assertion
```

Keep the third, and prefer `f"var S={redirect.DEFAULT_SECONDS},"` so the constant
is stated once.

### 1.10 `tests/test_portal_splice.py:92` and `:111` — constant-shape assertions

`assertEqual(STATES["default"], {})` and
`assertEqual(STATES["changepw"]["respStatus"], '"Error"')` restate `splice.py:75-92`.
The behavioural halves of those tests (`:93` and `:112`) are what catch a
re-capture drifting — keep those, drop the constant lines.

### 1.11 `tests/test_build_guards.py:90-101` — historical-string guards

`test_no_prototype_era_strings_remain` greps for `"Three directions"`,
`"--theme calm"` and `"B · "`. Removed many commits ago and nobody will retype
them. `test_layout_details.py:290-293` already guards the user-visible half (the
gallery must not say "prototype").

### 1.12 `tests/test_gallery_payload.py:108-131` — four assertions weaker than the fifth

The class docstring at `:146` says it out loud: *"The four tests above only check
that a selector exists and that something hex-shaped follows it — they cannot tell
one palette's colours from another's."* `test_each_palette_s_chrome_carries_its_own_colours`
(`:146-166`) parses each block and compares it to the palette's actual values.

Delete `:108`, `:113`, `:126`. Keep `:121` only if the `:root`-without-attribute
fallback is worth stating separately — it is not covered by `:146`.

---

## 2. Consolidate

### 2.1 Shell CSS contract → `test_shells.py` owns it

Three files assert shell CSS rules: `test_shells.py` (all shells),
`test_severity.py` (assist), `test_layout_details.py` (assist). The split is by
history, not by concern.

**Rule:** anything phrased as *"a shell must…"* belongs in `test_shells.py`,
looping every shell. Anything phrased as *"assist draws it this way"* stays in the
assist files. Moves are the deletions in §1.4 and §1.6. **~55 lines.**

### 2.2 Deploy-tree shape → `test_palette_matrix.py` owns it

| Where | What |
|---|---|
| `test_layout.py:53` | one directory per theme |
| `test_shells.py:440` | `<theme>/<default-palette>/<page>.html` for every theme × page |
| `test_palette_matrix.py:62` | every cell holds exactly `PAGE_TOKENS` |
| `test_portal_build.py:35` | the block-page glob sees only block pages |

`test_palette_matrix.py:62` is strongest — it walks both axes. Fold the first two
into it. Leave `test_portal_build.py:35`: it is about the seam between the two
page families, which is that file's subject. **~15 lines.**

### 2.3 `test_gallery_payload.py` → one build, one fixture

Four independent `build_all(..., preview=True)` calls reading the same
`index.html`: `:32`, `:100`, `:217` (inline), `:234` (inline). `tests/_build.py:22-30`
already caches exactly this build behind an `lru_cache` and `preview_dir()` hands
back the directory. The last two are one-line string checks with no reason to
build at all.

`test_palette_matrix.py:44` and `:132` are two further full matrix builds that
`built()` could serve. Net: **7 `build_all` calls collapse to 1, ~20 lines.**

### 2.4 Portal encoded-size ceiling → `test_portal_budget.py` owns the number

`test_portal_budget.py:15` and `test_portal_build.py:52` both assert
`encoded <= MAX_ENCODED`. `test_portal_build.py:52` should keep only the seam
assertions (`encoded > size`, and the count matching themes × palettes ×
`PORTAL_PAGES`). **~4 lines.**

### 2.5 CLI build fan-out

`test_cli.py:104` and `:112` each run a full theme × palette build to inspect one
line of stdout. Adding `--theme glass --palette cyber-orange` narrows each to
1/28th of the work and changes nothing asserted.

---

## 3. Repair, don't delete

### 3.1 `test_palette_matrix.py:169-174` — the hardcoded page size

```python
self.assertIn("16334", row)
```

Git-confirmed churn: introduced as `assertIn("15558", row)`, hand-edited since.
The stated intent is *"the row names the largest page"* — assert the relationship:

```python
worst = max((r for r in self.result.results
             if r.theme == "nyan" and r.palette == "cyber-orange"),
            key=lambda r: r.size)
row = next(ln for ln in self.text.splitlines()
           if "nyan" in ln and "cyber-orange" in ln)
self.assertIn(worst.page, row)
self.assertIn(str(worst.size), row)
```

Now no copy edit anywhere can break it, and it tests what it claims.

### 3.2 `test_palette_matrix.py:186-187` — currently failing, and mis-scoped

```python
def test_a_clean_build_says_so(self):
    self.assertIn("no page warns or fails", self.text)
```

The intent is *"`format_report` prints the all-clear branch when there is nothing
to flag"* — a formatting behaviour. As written it is a second, weaker byte-budget
assertion bolted onto the real build, and reports a size problem as a
report-formatting problem. Build a synthetic `BuildResult` with no warnings, or
assert the branch directly.

The other two current failures, in `test_shells.py:454`, *are* the correct place
for a byte overage to surface. Leave those alone.

### 3.3 `test_copy.py:21-28` — verbatim copy of production data

`BANNED` is byte-identical to `validate.BANNED_COPY` (verified, 6/6 entries
including the "why" strings). The module docstring defends duplicating the *lint
pass* (templates vs rendered output), which is right — but not duplicating the
*phrase table*. A phrase added to `BANNED_COPY` silently never gets linted in
templates. Replace with an import.

### 3.4 JavaScript-source snapshots — assert intent, not emitted characters

```python
test_gallery_payload.py:220  assertIn("functionchoose(i){at=i;", squeezed)
test_redirect.py:231         assertIn("for(var k in R){h.href=R[k][1];if(h.host===location.host)return}", ...)
test_redirect.py:380         assertIn("function go(){l=t;w()}", script)
test_redirect.py:215         assertIn(".split('{app}').join(n)", ...)
```

Each pins exact minified source. Renaming a one-letter variable — a routine
byte-saving edit in this codebase — breaks all four and teaches nothing.

`:231` is the loop guard and genuinely matters: assert its components (`h.host`,
`location.host`, `for(var k in R)`) rather than the concatenation. `:380` is better
as `assertNotIn("location.replace", script)` (which the next line already does)
plus a check that the loop path is taken.

`test_redirect.py:433-455` already shows the better pattern for this class — it
runs `node --check` over the emitted script.

### 3.5 `test_docs.py:116-122` — asserts noxfile source text

```python
self.assertIn('PREVIEW_DEST = pathlib.Path("docs/preview")', noxfile)
```

A string match against another file's source; reformatting `noxfile.py` breaks it.
`import noxfile; assert noxfile.PREVIEW_DEST == pathlib.Path("docs/preview")`
tests the same fact and survives formatting.

### 3.6 `test_nyan_flight.py:133` — magic count

```python
self.assertEqual(PORTAL.count("radial-gradient(var(--star)"), 4)
```

Four is the current number of starfield layers. The intent is "the portal has a
starfield to blur", which `assertGreater(..., 0)` states without a hand-edit when
a layer is added. The adjacent `assertIn("backdrop-filter:blur(", text)` is the
load-bearing half.

### 3.7 `test_contact.py:249, 270-272` — exact copy strings

```python
assert 'data-subject="Blocked site report"' in anchor
assert 'data-intro="Please review this block."' in anchor
assert 'data-prompt="Why I need access:"' in anchor
```

Break on any copy edit to `url-block-page.html`. The load-bearing facts are *"the
href is a mailto to the configured address"* and *"the three metadata attributes
survive URL mode"*, both statable without quoting copy. `test_layout_details.py:226-237`
already asserts the attributes by name with a `found == expected` counter — the
better formulation.

### 3.8 `test_nyan_flight.py:50-58` — the one genuine vacuous-loop risk

```python
for page, text in nyan_pages():
    for value in set(re.findall(r"--star:([^;}]+)", text)):
        with self.subTest(page=page, star=value):
            self.assertRegex(value.strip(), r"^#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
```

If `--star` ever stops reaching built output, `findall` returns `[]` and the test
passes green. Partly covered by `:101-108`, which asserts `--star:` exists in the
shell *source* — but this test's subject is the built page. Add a `found` counter
and `assertGreater(found, 0)`, matching `test_layout_details.py:45, :109, :264`.

Every `for` loop in the suite was swept for this pattern; this is the only one
where the guarding assertion is absent from both the test and its siblings.
`test_portal_shells.py:110-115` and `test_portal_download.py:100-107` are thin but
each is backed by a sibling test asserting the collection is non-empty.

---

## 4. Keep — do not touch

These guard the project's actual failure mode: PAN-OS accepting something and then
silently serving its own default page.

| Test | Failure mode it protects |
|---|---|
| `test_shells.py:448-460` | **The 16,000 B budget.** Source of 2 of the 3 current failures — working as designed. |
| `test_redirect.py:148-163` | A theme claiming `redirect: true` that no longer fits with the 3,347 B notice. |
| `test_redirect.py:165-177` | The inverse. Its docstring says *"do not delete it to make the suite green"* — heed that. |
| `test_redirect.py:98-101` | A feature that is "off" and still costs bytes on every page. |
| `test_errors.py:132-145` | End-to-end proof an oversize page sets `result.failed`; the comment explains why the padding must not be a comment. |
| `test_portal_budget.py` (all 3) | The base64 import ceiling and the `SOFT_MAX` derivation. |
| `test_portal_validate.py:128-138` | The import-time limit at unit level. |
| `test_build_guards.py:46-81`, `:116-141` | Every silent PAN-OS guard, plus the `xid="rep"` near-miss on the one link allowed to leave the page. |
| `test_portal_shape.py:19-23` | The guard set over every built import in every theme. |
| `test_portal_build.py:151-168` | Preview bytes escaping into a tree an upload script globs. Asserted against the filesystem. |
| `test_portal_splice.py:165-193` | The guards reject the splice *because of what splicing adds*. |
| `test_shells.py:142-145` | `assert cls.shells` — stops all 24 shell tests passing vacuously. |
| `test_palettes.py:135-159` | 4.5:1 AA across every palette × scheme × pairing. |
| `test_palettes.py:162-204` | A palette whose `name` disagrees with its filename. |
| `test_nyan_sprite.py:70-78` | Compiled artwork vs its generator — the correct kind of snapshot. |
| `test_contact.py:302-307` | The only place URL mode's page sizes are measured. |
| `test_gallery_payload.py:86-89` | The palette-split regression: all four inlined takes `index.html` from 1.59 MB to ~5.9 MB, and the gallery still *works*. |
| `test_datadir.py:79-116` | An `init`-era data directory silently degrading a family the user never asked about. |

---

## 5. Numbers

| File | Lines | Tests | After | Tests after | Action |
|---|---:|---:|---:|---:|---|
| `test_shells.py` | 464 | 24 | ~475 | 24 | grows — absorbs assist rules |
| `test_redirect.py` | 561 | 52 | ~555 | 51 | constants, JS snapshots, `unittest.main` |
| `test_contact.py` | 446 | 60 | ~440 | 58 | merge `both_set`, relax copy strings |
| `test_layout_details.py` | 356 | 32 | ~345 | 30 | −2 duplicated rules, `unittest.main` |
| `test_gallery_payload.py` | 241 | 18 | ~200 | 15 | −3 weak chrome tests, share build |
| `test_cli.py` | 227 | 20 | 227 | 20 | narrow two builds |
| `test_palettes.py` | 208 | 9 | 208 | 9 | — |
| `test_docs.py` | 197 | 19 | 197 | 19 | repair noxfile assertion |
| `test_portal_splice.py` | 197 | 20 | ~190 | 19 | −1 tautology, −2 constant lines |
| `test_palette_matrix.py` | 191 | 17 | ~190 | 17 | repair `:174`, re-scope `:187` |
| `test_portal_build.py` | 172 | 15 | ~168 | 15 | drop duplicated ceiling |
| `test_errors.py` | 145 | 14 | 145 | 14 | — |
| `test_build_guards.py` | 145 | 18 | ~133 | 17 | −prototype-era strings |
| `test_nyan_flight.py` | 144 | 12 | ~146 | 12 | +counter, relax magic 4 |
| `test_portal_validate.py` | 138 | 17 | 138 | 17 | — |
| `test_portal_config.py` | 135 | 12 | 135 | 12 | — |
| `test_portal_shells.py` | 128 | 11 | 128 | 11 | — |
| `test_settings_and_logs.py` | 127 | 17 | 127 | 17 | — |
| `test_severity.py` | 127 | 12 | ~80 | 6 | −5 duplicated rules, −1 design pin |
| `test_datadir.py` | 116 | 10 | 116 | 10 | — |
| `test_portal_download.py` | 107 | 10 | 107 | 10 | — |
| `test_nyan_sprite.py` | 100 | 7 | 100 | 7 | — |
| `test_copy.py` | 95 | 5 | ~88 | 5 | import `BANNED_COPY` |
| `test_portal_shape.py` | 78 | 7 | 78 | 7 | — |
| `test_palette_pinning.py` | 69 | 6 | ~58 | 4 | −1 duplicate, −1 covered |
| `test_layout.py` | 61 | 6 | ~50 | 4 | −gitignore, −theme-dir |
| `test_emit.py` | 44 | 6 | 44 | 6 | — model unit test |
| `test_portal_budget.py` | 28 | 3 | 28 | 3 | — |
| `_build.py` / `_paths.py` / `_nyan_sprite.py` | 334 | — | 334 | — | — |
| **Total** | **5,381** | **458** | **~5,170** | **~427** | **−211 lines, −31 tests** |

Subtest count is essentially unchanged (~1,199 → ~1,150): the deletions are
duplicated *rules*, not duplicated *cases*, and the surviving all-shells versions
already iterate every shell.

`build_all` invocations: 22 today (1 shared in `_build.built()` + 21 in test
bodies) → ~14, of which the 8 remaining independent ones each exercise a distinct
code path (stale data dir, unknown palette from config, unknown theme pin,
oversize page, narrowing, CLI init round-trip).
