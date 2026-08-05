# SSL Certificate Status Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Add `ssl-cert-status-page` — the eleventh block-page type — so the certificate-error interstitial a user hits on a decrypted session is served in the project's house style instead of the PAN-OS default.

**Architecture:** The same "add a page type" path as `data-filter-block-page`: register the type and its tokens in `validate.py`, add preview samples in `page.py`, write one template, update the places that enumerate pages by hand.

**What makes this one different from the other ten:**

1. **Four new tokens at once** — `certname`, `issuer`, `status`, `reason`. `TOKEN_RE` must learn all four or `validate()` never scans them.
2. **It is not a policy block.** Every existing page says "your organisation stopped this". This one says "the server you asked for presented a certificate we could not trust". The subject of the sentence changes, and so does the right action for the user — which is *not* "ask IT to allow it".
3. **It is the first page where `<url/>` is not a URL.** On the decryption path PAN-OS substitutes the destination **IP**; the vendor default labels that row `IP:`, not `URL:`.
4. **It is the first page to carry `<category/>` without wanting the category to drive the copy.** See Design Decision 5 — this is the `id="cat"` + `COPY_LOCK` pairing, which is both more correct *and* ~1.5 KB smaller than either alone.

**Tech Stack:** Python 3.11+, stdlib only for this change. pytest + unittest-style classes, `uv` for running.

## Source material

`tmp/pages/ssl-cert-status-page.html` is the shipped PAN-OS default — a complete `<!DOCTYPE html>` document with no form and no injected control, so it is squarely in this skill's family rather than the portal one.

```
$ grep -o '<[a-z_]*/>' tmp/pages/ssl-cert-status-page.html | sort -u
<category/>  <certname/>  <issuer/>  <reason/>  <status/>  <url/>  <user/>
```

Its body is a flat seven-row list, and the labels it chooses are the evidence for what each token renders:

```html
<h1>Certificate Error</h1>
<p>There is an issue with the SSL certificate of the server you are trying to contact.</p>
<p><b>Certificate Name:</b> <certname/></p>
<p><b>IP:</b> <url/></p>
<p><b>Category:</b> <category/></p>
<p><b>Issuer:</b> <issuer/></p>
<p><b>Status:</b> <status/></p>
<p><b>Reason:</b> <reason/></p>
<p><b>User:</b> <user/></p>
```

Corroboration for the four new tokens: the LIVEcommunity "Customize Your Response Pages" list — the fullest that exists anywhere — names `<certname/>`, `<issuer/>`, `<status/>` and `<reason/>` as a group. It also names `<badcert/>`, which is **absent from this default and therefore not registered** (see Design Decision 3).

## Global Constraints

- **`PAGE_TOKENS` and the template directory must change in the same commit.** `tests/test_layout.py:45` asserts they agree.
- **Four tokens must reach `TOKEN_RE`, not just `PAGE_TOKENS`.** A token missing from the regex is never scanned, so the legality check passes on a page that renders blank fields. This is the failure the whole project exists to catch, and it is four times as easy to half-do here.
- **Four `SAMPLE` entries.** A missing one raises `KeyError` during the preview build.
- **17,999-byte ceiling**, warning at 16,000. Comfortable: the ten-page build tops out at 12,207 B (`nyan`/`data-filter-block-page`) and this page adds ~3 rows over that one while `id="cat"` + `COPY_LOCK` *removes* the 1.7 KB category map. Verify anyway at Task 5; do not golf preemptively.
- **`BANNED_COPY` risk is different here and lower.** The "was data sent?" phrases are not tempting on a certificate page. The live one is `for everyone` / `not just you`: "this certificate is untrusted for everyone" is exactly the reassurance an author reaches for, and the page cannot know it.
- **Commit message style:** short imperative subject, capitalised, no trailing period, ≤ 60 chars. No `feat:`/`fix:` prefixes, no emoji, no AI/tool attribution of any kind.
- **Never `git add` or `git commit` anything under `docs/` (Markdown), `README.md`, `CHANGELOG.md`, or `SECURITY.md`** unless the user asks in this session. `docs/plans/` is gitignored working material and is never committed. `docs/assets/preview-embed.js` is a test-enforced JS asset — it belongs with the code commit; flag it and let the user decide.

## Design Decisions (settled — do not re-litigate)

1. **API category is `ssl-cert-status-page`**, taken verbatim from the default's filename. Do **not** check this against the XML API "Import/Export Files" reference: that list is PAN-OS 6-era and omits five categories that plainly exist. `ssl-cert-status-page` does appear in it, which is corroboration, but its absence would have meant nothing either way.
2. **Registered tokens are exactly `{user, url, category, certname, issuer, status, reason}`** — read out of the shipped default.
3. **`<badcert/>` is not registered.** It appears in the community variable list and *not* in the vendor default for this page. That is the direction of evidence that loses: an unsupported token renders blank, silently. Same ruling as `<threatname/>`.
4. **Tone is `warn`, not `crit`.** A certificate error is frequently mundane — an expired cert, a corporate root the firewall does not have. Rendering every one as `Security risk` trains users to click through the ones that matter. `warn` is honest about "stop and look at this" without asserting an attack the page cannot diagnose.
5. **`id="cat"` **and** `COPY_LOCK=1`, together.** They are independent, and the pair is exactly right here:
   - `COPY_LOCK` pins tone and gloss, so the category map cannot overwrite "this server's certificate could not be verified" with a sentence about web categories. The reason the user is looking at this page is the certificate, not the category.
   - `id="cat"` still rewrites the raw slug into a friendly label (`online-storage-and-backup` → `Online Storage and Backup`).
   - `category_js` emits the ~1.7 KB map only when `has_category and not lock_copy`, so the pair costs ~0.2 KB of label code and no map. It is the cheapest of the three options as well as the most correct.
6. **The `<url/>` row is labelled `Server`, not `URL`.** PAN-OS substitutes the destination IP on the decryption path — the vendor default labels it `IP:`. `Server` covers it whether an IP or a hostname arrives, and does not promise a scheme-and-path the row will not contain. `mono`, since it is a machine value.
7. **Eight fact rows: Server, Certificate, Issuer, Status, Reason, Category, User, Time.** Every token surfaced. This is the longest fact list in the project by three rows and the layout risk of the change; Task 5 checks it in `banner` (sidebar) and `glass` (cards) specifically. **If it reads as a form rather than a summary, the fallback is to move `Issuer` into the `EXTRA` callout** — not to drop it, since it is the row that distinguishes "our own corporate root" from "someone else's".
8. **Ordering is diagnosis-first.** `Status` and `Reason` are what tells a user whether this is boring or alarming, so they sit above `Category`, which is the least relevant row on this page and is present mainly because the token exists.
9. **`mono` on Server, Certificate and Issuer; not on Status, Reason, Category.** The first three are machine values a user may have to read back to IT — a CN or a full issuer DN. `Status`/`Reason` are PAN-OS's own words and `Category` is rewritten to a friendly label by the script, so monospacing them would fight the rewrite.
10. **The action is still `Report to IT`, and the copy must not tell the user to proceed.** PAN-OS decides whether a continue is offered, and no `<pan_form/>` appears in this default, so the page has no mechanism to offer one. `data-subject` is `Certificate error`.
11. **One `.warnline`, not an `.infobox`.** The other pages inform ("send the report and IT will review it"). Here there is something the user should actually not do — retry until it works, or enter credentials — and `warnline` is the register for that. **Correction made during execution:** an earlier draft of this decision claimed this was the project's first `warnline`. It is not — `virus-block-page` and `credential-coach-text` already use it, which is reassuring rather than otherwise: this page belongs in that group.

## File Structure

**Created:**
- `src/panos_response_pages/data/templates/pages/ssl-cert-status-page.html`

**Modified:**
- `src/panos_response_pages/page.py` — **added during execution, not in the original plan:** a `PAGE_SAMPLE` per-page override map. Task 5 found the preview rendering the shared long-URL sample in the `Server` row, where a live firewall puts a short IP. That is precisely the judgement Step 5 asks a reviewer to make, so the sample had to stop lying. `{"ssl-cert-status-page": {"url": "192.0.2.24"}}`, an RFC 5737 documentation address.
- `src/panos_response_pages/validate.py` — `PAGE_TOKENS` entry, four `TOKEN_RE` alternatives, the `10 pages` comment.
- `src/panos_response_pages/page.py` — four `SAMPLE` entries.
- `src/panos_response_pages/contact.py` — the "all ten templates" comment.
- `tests/test_build_guards.py` — a guard for the new tokens.
- `docs/assets/preview-embed.js` — the dropdown (test-enforced).
- `docs/architecture/url-filtering-response-pages.md` — token table row, meanings, the `<url/>`-is-an-IP note, "ten" → "eleven".
- `docs/architecture/general.md`, `docs/styles.md`, `docs/customising.md` — "ten" → "eleven".
- `CHANGELOG.md` — under the existing `## [Unreleased]`.
- `.claude/skills/add-response-page/SKILL.md` — add the verified row to **Known page types**.

**Deliberately NOT modified:**
- `docs/styles.md` line ~21 — "six shells × three palettes is nine files" counts files, not pages.
- Any test asserting a page count; they all derive.

---

## Task 1: Register the page type

- [x] **Step 1.** In `validate.py`, add to `PAGE_TOKENS`:

  ```python
      "ssl-cert-status-page": {"user", "url", "category", "certname", "issuer", "status", "reason"},
  ```

- [x] **Step 2.** Extend `TOKEN_RE` with all four new names in one edit:

  ```python
  TOKEN_RE = re.compile(
      r"<(user|url|category|ssurl|pan_form|fname|cookie|appname|direction"
      r"|certname|issuer|status|reason)\s*/>"
  )
  ```

  Check the result against `grep -o '<[a-z_]*/>' tmp/pages/ssl-cert-status-page.html | sort -u` before moving on — four is enough to miss one.

- [x] **Step 3.** In `page.py`, add four `SAMPLE` entries. Values should look like real PAN-OS output, since they are what a reviewer judges the layout on:

  ```python
      # The SSL certificate status page. Values shaped like real PAN-OS output:
      # certname/issuer are DNs, status and reason are its own short verdicts.
      "certname": "*.example.com",
      "issuer": "CN=Example Intermediate CA, O=Example Corp, C=US",
      "status": "untrusted-issuer",
      "reason": "The issuing certificate authority is not in the trusted store",
  ```

- [x] **Step 4.** Update the `x 10 pages` count in `validate.py`'s `external_refs` docstring to `x 11 pages`.

- [x] **Step 5.** Run `uv run pytest -q tests/test_layout.py`. It **must fail** on `templates and PAGE_TOKENS disagree`. That failure is the proof registration took effect.

## Task 2: Write the template

- [x] **Step 1.** Copy `data-filter-block-page.html` to `ssl-cert-status-page.html` as the starting point — it is the most recent and has the closest fact-row shape. Do not start from the PAN-OS default.

- [x] **Step 2.** Header comment, recording the category, the tokens, the two judgement calls a later reader will otherwise re-litigate, and the verification debt:

  ```html
  <!--
    SSL Certificate Status Page
    API category: ssl-cert-status-page
    Tokens available: <user/> <url/> <category/> <certname/> <issuer/> <status/> <reason/>

    <url/> IS THE DESTINATION IP HERE, not a URL. This is the decryption path;
    the shipped PAN-OS default labels the row "IP:". The row is labelled "Server"
    so it reads correctly whichever arrives.

    id="cat" AND COPY_LOCK together, deliberately. COPY_LOCK stops the category
    map repainting the tone and overwriting the gloss -- the reason for this page
    is the certificate, not the category -- while id="cat" still rewrites the raw
    slug into a friendly label. category_js emits the ~1.7 KB map only when
    has_category and NOT lock_copy, so the pair is also the cheapest option.

    Tone is warn, not crit: an expired certificate and an active interception
    reach this page identically, and rendering every one as "Security risk"
    teaches users to click through the ones that matter.

    <badcert/> appears in the community variable list but NOT in this default, so
    it is not registered. An unsupported token renders blank, silently.

    VERIFY ON A LIVE FIREWALL: that all seven render, and what <status/> and
    <reason/> actually contain -- no published source documents their values, and
    the fact rows are sized on a guess at their length.
  -->
  ```

- [x] **Step 3.** Slots. `TITLE`/`HEADLINE` stay close to the vendor's "Certificate Error" so a user who has seen the stock page recognises this one, and the gloss names the server as the subject rather than the organisation:

  ```html
  <!--@TITLE-->Certificate problem<!--/@TITLE-->

  <!--@TONE-->warn<!--/@TONE-->

  <!--@COPY_LOCK-->1<!--/@COPY_LOCK-->

  <!--@HEADLINE-->This site's certificate could not be verified<!--/@HEADLINE-->

  <!--@GLOSS-->The server presented a certificate that could not be checked, so the connection was stopped before any data was exchanged.<!--/@GLOSS-->
  ```

  **Careful with that gloss.** "before any data was exchanged" is a claim about transmission — check it against `BANNED_COPY` in `validate.py` and against `audit_copy`. If it trips, or if review judges it a claim the page cannot substantiate, cut the clause to `...so the connection was stopped.` The shorter form is safe and says enough.

- [x] **Step 4.** A distinct `<!--@MARK-->` SVG. **Took three rounds; the first two were wrong.**

  The original — a landscape document with a seal on its bottom-right corner — was rejected by the user as unclear. The cause was specific and worth recording: the seal circle **crossed the document's border**, and in a stroke-only icon set there is no fill to resolve the crossing. At the size the mark actually renders (`1.9rem` ≈ 30px desktop, `1.55rem` ≈ 25px mobile, per `.hd .ind svg`) it collapsed into a smudge. It looked fine at 4rem, which is exactly how it passed review on paper.

  Six candidates were then rendered at all three sizes with headless Chrome (`/Applications/Google Chrome.app/Contents/MacOS/Google Chrome --headless --screenshot`) and compared as images. Two findings generalise beyond this page:
  - **A check mark inside the seal was ruled out on *meaning*, not looks.** It reads "verified" on a page whose headline is "could not be verified".
  - **Plain rosettes read as medals or awards**, not certificates.

  **The user chose candidate E: a portrait document with a folded corner, two text lines, and a ribboned seal at the bottom right.** The document outline is deliberately left open where the seal sits, so no strokes cross. Verified in the built page at the real indicator size.

  One geometry bug caught along the way: an intermediate candidate's ribbon tails reached `y=23.2`, and with `stroke-linecap="round"` at `stroke-width="1.8"` that extends to 24.1 — past the `0 0 24 24` viewBox edge. **Budget 0.9 units of clearance inside the viewBox for the stroke.**

- [x] **Step 5.** The fact rows, diagnosis-first, with the `User` row verbatim and `id="cat"` on Category:

  ```html
  <!--@FACTS-->
  <div class="f"><dt>Server</dt><dd class="mono"><url/></dd></div>
  <div class="f"><dt>Certificate</dt><dd class="mono"><certname/></dd></div>
  <div class="f"><dt>Issuer</dt><dd class="mono"><issuer/></dd></div>
  <div class="f"><dt>Status</dt><dd><status/></dd></div>
  <div class="f"><dt>Reason</dt><dd><reason/></dd></div>
  <div class="f"><dt>Category</dt><dd id="cat"><category/></dd></div>
  <div class="f"><dt>User</dt><dd><user/></dd></div>
  <div class="f"><dt>Time</dt><dd id="ts"></dd></div>
  <!--/@FACTS-->
  ```

- [x] **Step 6.** Actions and contact sections. Bare address in the mailto section, on one line, no query, no tokens:

  ```html
  <!--@ACTIONS-->
  <a class="btn" id="rep"{{CONTACT_TO}} data-subject="Certificate error"
     data-intro="A certificate could not be verified on this connection." data-prompt="What I was trying to reach:"
     href="{{CONTACT_HREF}}">Report to IT</a>
  {{CONTACT_ALT}}
  <!--/@ACTIONS-->

  <!--@CONTACT_MAILTO-->mailto:{{SUPPORT_EMAIL}}<!--/@CONTACT_MAILTO-->

  <!--@CONTACT_ALT--><p class="plain">Or email <a href="mailto:{{SUPPORT_EMAIL}}">{{SUPPORT_EMAIL}}</a> with the details above.</p><!--/@CONTACT_ALT-->
  ```

- [x] **Step 7.** The callout — a `warnline`, opening with `{{WARN_MARK}}`, all text in one `<span>`:

  ```html
  <!--@EXTRA-->
  <p class="warnline">{{WARN_MARK}}<span>Do not sign in or enter personal details on this site until IT has looked at it.</span></p>
  <!--/@EXTRA-->
  ```

  Do not add an `.infobox` as well — `test_no_page_mixes_a_warnline_and_an_infobox` forbids it, and two callouts read as competing alerts.

- [x] **Step 8.** `uv run pytest -q tests/test_layout.py tests/test_copy.py tests/test_layout_details.py`. All green. If the gloss trips `audit_copy`, fix the copy, not the guard.

## Task 3: Guard the new tokens

- [x] **Step 1.** In `tests/test_build_guards.py`, add a guard covering **all four** new tokens, not one of them — the plausible mistake is adding three of four to `TOKEN_RE`:

  ```python
      def test_certificate_tokens_are_rejected_off_the_ssl_page(self):
          """The four certificate tokens are provided only on ssl-cert-status-page.

          All four, because the plausible slip is a partial edit to TOKEN_RE: a
          token missing from it is never scanned, so its page would pass while
          rendering a blank row.
          """
          for token in ("certname", "issuer", "status", "reason"):
              with self.subTest(token=token):
                  page = self.HEAD.format(f"<p><{token}/></p>")
                  _size, errors, _warnings = build.validate("url-block-page", page)
                  self.assertTrue(any("not available on url-block-page" in e for e in errors), errors)
  ```

- [x] **Step 2.** Prove it can fail: temporarily drop one token from `TOKEN_RE`, confirm that subtest fails, restore it.

- [x] **Step 3.** `uv run pytest -q`. Expect exactly one failure — `test_docs.py::test_the_embed_offers_every_page` — which Task 4 fixes. Any other failure is a real problem; fix by deriving, never by bumping a count.

## Task 4: Documentation

Nothing here is committed by an agent unless the user asks in-session.

- [x] **Step 1.** `docs/assets/preview-embed.js` — add `"ssl-cert-status-page",` in alphabetical order (after `safe-search-block-page`, before `url-block-page`).

- [x] **Step 2.** `docs/architecture/url-filtering-response-pages.md`:
  - table row: `| \`ssl-cert-status-page\` | \`<user/>\` \`<url/>\` \`<category/>\` \`<certname/>\` \`<issuer/>\` \`<status/>\` \`<reason/>\` |`
  - extend the token-meanings sentence with the four new ones.
  - add a short note that `<url/>` renders the **destination IP** on this page, per the vendor default's `IP:` label, and mark `<certname/>`/`<issuer/>`/`<status/>`/`<reason/>` `[unverified]` — in the default, corroborated by the community list, absent from official docs.
  - "The ten page types" → eleven, "ten near-identical files" → eleven.

- [x] **Step 3.** `docs/architecture/general.md`, `docs/styles.md` line 4, `docs/customising.md` — "ten" → "eleven". Re-read each hit; leave `docs/styles.md` line ~21 alone.

- [x] **Step 4.** `src/panos_response_pages/contact.py` — "all ten templates" → eleven. (Source; committable.)

- [x] **Step 5.** `CHANGELOG.md` — add to the existing `## [Unreleased]` `### Added` block. Cover: the page, the four new tokens and their evidence status, `<badcert/>` deliberately omitted, and that `<url/>` is an IP here.

- [x] **Step 6.** `.claude/skills/add-response-page/SKILL.md` — add to **Known page types**:

  ```
  | `ssl-cert-status-page` | SSL Certificate Status | `user url category certname issuer status reason` |
  ```

  and extend the meanings sentence. This is the row the next page starts from.

## Task 5: Verify

- [x] **Step 1.** `uv run panos-response-pages build` — expect `no page warns or fails`.

- [x] **Step 2.** `uv run pytest -q` — whole suite green.

- [x] **Step 3.** `uv run panos-response-pages validate out/deploy` — `0 would fail`, and `checked 364 page(s)` (28 combinations × (11 pages + 2 portal)). Confirm the page itself landed 28 times:

  ```bash
  find out/deploy -name 'ssl-cert-status-page.html' | wc -l   # must be 28
  ```

- [x] **Step 4.** Byte check. Eight fact rows is the most of any page, so confirm rather than assume — and confirm the map really is absent, which is the claim Design Decision 5 rests on:

  ```bash
  find out/deploy -name 'ssl-cert-status-page.html' -exec wc -c {} + | grep -v total | sort -n | tail -3
  grep -c 'var M=' out/deploy/assist/prisma-blue/ssl-cert-status-page.html   # must be 0
  grep -c "getElementById('cat')" out/deploy/assist/prisma-blue/ssl-cert-status-page.html  # must be 1
  ```

- [x] **Step 5.** DONE, and it earned its place. Neither MCP browser server is configured here, but **headless Chrome renders the built preview files directly** — use it rather than reporting a page as verified on structure alone:

  ```bash
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --disable-gpu \
    --force-device-scale-factor=2 --window-size=1100,900 --screenshot=/tmp/pg.png \
    "file://$PWD/out/preview/banner/prisma-blue/ssl-cert-status-page.html"
  ```

  Findings:
  - **The eight-row worry was unfounded — it reads as a summary, not a form, in all three layouts.** The Design Decision 7 fallback (moving `Issuer` into the callout) is NOT needed. `glass` lays the rows out as a 2×4 card grid and `banner` as a sidebar that balances the left column; both are arguably better homes for a long fact list than `assist`'s single column.
  - The long `issuer` sample wraps to two lines in `banner` and `glass` without overflowing.
  - `Category` renders `Command and Control`, confirming the `id="cat"` label rewrite runs while `COPY_LOCK` holds the certificate gloss — Design Decision 5 verified end to end.
  - Dark scheme checked; `mono` lands on Server/Certificate/Issuer only.
  - `banner` (facts in a sidebar) and `glass` (facts as cards), not just `assist`.
  - Dark scheme.
  - Judge whether it reads as a summary or as a form. If it reads as a form, apply the Design Decision 7 fallback: move `Issuer` into the callout. Do not silently drop a row.
  - Check the long `issuer` sample does not overflow its cell, and that the `Category` row shows the friendly label rather than the raw slug.

  If no browser tooling is available, **say so and hand over the paths** rather than reporting it verified. `out/preview/<style>/<palette>/ssl-cert-status-page.html`.

- [x] **Step 6.** Record the live-firewall debt in the handover: that all seven tokens render, and specifically what `<status/>` and `<reason/>` contain — no published source documents their values, and the layout is sized on a guess at their length.

## Out of scope

- `ssl-optout-text.html` — the SSL decrypt opt-out. It is a **fragment**: no doctype, no `<head>`, five lines of markup, and it needs a proceed mechanism this project has no token for. Different file shape, different contract; not this plan.
- `captive-portal-text.html`, `mfa-login-page.html`, `saml-auth-internal-error-page.html` — forms and auth flows; the `add-portal-page` route, each needing its file shape established against a live firewall first.
