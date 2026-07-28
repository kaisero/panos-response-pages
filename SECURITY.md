# Security policy

## Supported versions

Pre-1.0: only the latest release is supported.

## Reporting a vulnerability

Report privately through
[GitHub Security Advisories](https://github.com/kaisero/panos-response-pages/security/advisories/new),
or by email to oliver.kaiser@outlook.com if you cannot use that.

Please do not open a public issue for a vulnerability. Expect an initial
response within a week, and coordinated disclosure once a fix is available.

## Scope worth knowing about

This tool generates HTML that a firewall injects into a blocked site's response.
Two properties matter more than they might look:

- **Generated pages must stay self-contained.** They are served from the blocked
  site's origin, so any external reference either fails to resolve or has to
  survive the very policy that produced the page. The build rejects `<base>`,
  `<link>`, and `http(s)` `src`/`href` outside of `mailto:`.
- **Substituted values are attacker-influenced.** `<url/>` and `<appname/>` come
  from the request that was blocked. They are rendered as text, and the emitted
  script rebuilds the report mailto with `encodeURIComponent` rather than string
  concatenation. Changes near either should keep that property.
