# Copy rules

Two classes of statement fail the build, because the page cannot substantiate
either:

1. **Whether data was transmitted** — *"nothing you typed was sent"*, *"before it
   left your device"*. The page has no visibility into what the browser already
   sent.
2. **That a policy applies to all users** — *"blocked for everyone"*, *"that fixes
   it for everyone"*. Different users can match different rules, and no PAN-OS
   variable exposes which one fired.

The phrase list is `BANNED_COPY` in `panos_response_pages/validate.py`; add to it as
new wording appears.

The same reasoning applies to anything administrator-configurable. The
Continue/Override grant duration is `continueGrantText` in config rather than
hardcoded copy, because PAN-OS only *defaults* to 15 minutes — set it to match
your actual URL Admin Override timeout.

## Why the build has guards

PAN-OS accepts an oversize or malformed response page **without complaint**. The
import reports success, the commit succeeds, and users silently get the default
page or nothing at all. There is no error and no log entry. This tool is the only
feedback loop that exists, so it fails the build on:

- **Size** — any page over **17,999 bytes**, warning above 16,000 to leave room for
  `<url/>` expanding at serve time.
- **External references** — `<base>`, `<link>`, `src="http`, `href="http`
  (`mailto:` excepted). A block page is injected into the *blocked site's*
  response, so its origin is the blocked site: relative paths do not resolve, and
  any external fetch has to survive the very policy that produced the page.
- **Illegal tokens** — a substitution token the page type does not provide. PAN-OS
  renders those as nothing, leaving a blank field on a live page.
- **Unverifiable copy** — see below.
- Missing `<!DOCTYPE html>`, which drops browsers into quirks mode.
