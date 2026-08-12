# Strata Cloud Manager import

How `import scm` talks to Strata Cloud Manager's config API, and why it is built
the way it is. The API involved is the UI API and may break in upcoming SCM Releases.

As of August 2026 this approach is working and will be adapted if API changes in the Future

## Two hosts, two auth headers, one token

An import needs two different APIs

| | instance discovery | config API |
|---|---|---|
| host | `api.apps.paloaltonetworks.com/mfe/instances` (fixed) | discovered per tenant, see below |
| auth header | `Authorization: Bearer <token>` | `x-auth-jwt: <token>` |

## `paas_api_url`

The config API's host is not a constant — it is discovered per tenant from the
instance list

| field | example | usable from this client? |
|---|---|---|
| `paas_api_url` | `paas-4.prod.panorama.paloaltonetworks.com` | **yes** |

`ScmClient.config_host()` reads `runtime_attributes.paas_api_url`.
Discovery is a real step with a real failure mode: no `prisma_access` instance in the tenant's
instance list means the service account has no access to Prisma Access, and
`config_host()` raises `ImportFailed` with that explanation rather than
producing a confusing downstream connection error.

## Folder and type are one unit

The config API's `type` query parameter is not a free choice alongside
`folder` — it is bound to it, and crossing them is a 400:

| folder | type | result |
|---|---|---|
| `Prisma Access` | `container` | 200 |
| `Mobile Users` | `cloud` | 200 |
| `Prisma Access` | `cloud` | 400 |
| `Mobile Users` | `container` | 400 |

`scope_type()` in `importer/scm/client.py` is the one place that maps a folder
to its type; `_params()` calls it rather than accepting `type` from a caller,
so there is no code path that can send a folder and a type that disagree. The
lookup table (`SCOPE_TYPES = {"Mobile Users": "cloud"}`) is deliberately an
exception table, not a folder registry: it holds only the one folder whose
type differs from the default, and iterating it to enumerate "known folders"
would be wrong — `Prisma Access` is the default `container` type and is not
listed. It is kept in sync by hand with `PORTAL_FOLDER` in
`importer/scm/target.py`; a mismatch between the two strings produces a loud
400 on the first Mobile Users write, not a silent one.

## Two read shapes: `info` versus `entry[0].page`

Response pages and portal pages are the same write call with different read
shapes, and reading the wrong one silently reports success for a write that
did not take effect:

| | response pages | portal pages |
|---|---|---|
| read path | `result.result.<page>.info` | `result.result.<page>.entry[0].page` |
| write semantics | overwrite, idempotent | creates a named object |
| name collision | none | unique across the whole folder tree |

A portal page's node also carries an *empty* `info` field (a
`predefined-snippet` placeholder next to the real content). A reader that only
looks at `info` sees that empty placeholder and reports a successful write as
a no-op. `ScmClient.get_page()` therefore checks `entry[]` first and falls
back to `info` only when `entry` is absent — not "if `info` is empty", because
falling back on emptiness would just move the same bug to a different
condition.

## Folder inheritance and why `@loc` is checked

`Mobile Users` is a child of `Prisma Access` in SCM's folder tree and inherits
whatever it does not locally override. A `GET` against the config API returns
the *effective* value for the folder queried, with provenance:

```
Mobile Users / url-block-page    @uuid=7f1b… @loc='Prisma Access' @type=container
                                 -> inherited, same uuid as the parent's
Mobile Users / virus-block-page  @loc='Mobile Users' @override=yes
                                 -> locally overridden
```

That means a read-back matching what was just written proves nothing about
*which folder* holds the value — a write to `Mobile Users` that never actually
landed there (rejected, or shadowed some other way) would still read back
looking correct, because the parent's value shows through unchanged.
`ScmTarget.upload()` treats a verified write as one that (a) is present, (b)
matches the encoded content sent, *and* (c) has `@loc` equal to the folder
written to — `PageState.inherited` is exactly that third check, and a write
that lands in the parent instead of the target folder is reported as a
failure rather than a false success.

## Why portal pages are locked to `Mobile Users`

Response pages are an overwritable value scoped by folder; nothing stops
retargeting them with `--folder`. Portal pages are different: they are named
objects (`global-protect-portal-custom-login-page`, `-home-page`), and their
name must be unique across the *entire* folder tree, not just within one
folder.

## Import never pushes

A write through this API lands in the tenant's *candidate* configuration
(the response carries a `@mutationid`) — not in the pushed, live configuration
that Prisma Access actually enforce. Making a write live is a separate action,
deliberately out of scope for this tool today (see the CLI's `import` section
in `docs/cli.md`). Two things in the implementation exist specifically so
nobody mistakes "imported" for "deployed":

- Every successful run's closing line states plainly that the pages are
  staged and have not been pushed (`importer/report.py`'s `STAGED` constant).
  That line only appears when something was actually written — a dry run
  never touched candidate config, and a run with any failure did not stage
  everything it reported, so neither prints it.
- Each page is one independent mutation; there is no batching and no
  transaction spanning the whole run. That is also why a run can partially
  succeed (a real example: 12 of 13 pages landing while a portal-page name
  collision fails the 13th) and why `import scm` reports per-page results and
  exits non-zero on any failure rather than only checking whether the process
  raised.
