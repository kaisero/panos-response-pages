# CLI reference

```bash
panos-response-pages [-v|-vv|-q] [--log-json] <command>
```

## Global options

| Option | Effect |
|---|---|
| `-v`, `-vv` | Info, then debug. Overrides the settings file. |
| `-q` | Errors only. Overrides the settings file. |
| `--log-json` | JSON lines instead of the report table — one machine-readable stream rather than two interleaved formats. |
| `--version` | Print the version and exit. |
| `--install-completion` | Install shell completion, including live theme and palette names. |

## `build`

Build every page of every style.

| Option | Default | Notes |
|---|---|---|
| `--customer`, `-c` | `contoso` | Config merged over `_defaults.json`. |
| `--theme`, `-t` | all | One style only. An unknown name is rejected with the list of real ones. |
| `--palette`, `-p` | all | Build one palette only. Omit to build every palette. |
| `--out`, `-o` | `out` | Output root. `deploy/` and `preview/` are created inside it. |
| `--config-dir` | resolved | Use this data directory instead. |
| `--preview / --no-preview` | preview | Whether to build the review gallery. |

Exit code is `1` if any page would fail silently on PAN-OS.

## `init [PATH]`

Copy the packaged shells, palettes, themes and config out for editing. Defaults
to `~/.panos_response_pages`, which `build` finds on its own. Refuses to overwrite
an existing directory without `--force`.

## `themes` / `palettes` / `pages`

List what the resolved data directory offers. `pages` lists the PAN-OS page
types and the substitution tokens each one provides — useful when writing a new
page template, since using a token the page type does not provide renders as
nothing.

## `validate DIRECTORY`

Re-run the PAN-OS guards over pages that already exist. The guards only help if
they run on what is actually about to be imported, which is not always what this
tool just produced.

## `import scm`

Import a built variant into Strata Cloud Manager. Writes land in the tenant's
**candidate** configuration — `import` never pushes; making a write live is a
separate step outside this tool. See
[SCM import architecture](architecture/scm-import.md) for the reasoning behind
the API calls this makes.

```bash
panos-response-pages import scm --from out/deploy/beacon/prisma-blue [OPTIONS]
```

| Option | Default | Notes |
|---|---|---|
| `--from`, `-f` | required | A built variant directory, e.g. `out/deploy/beacon/prisma-blue`. |
| `--folder` | `Prisma Access` | Folder for the **response pages**. Portal pages always go to `Mobile Users` — see below. |
| `--only` | all pages | Import just this page. Repeatable. |
| `--client-id` | — | Service account. Prefer `SCM_CLIENT_ID`. |
| `--client-secret` | — | Prefer `SCM_CLIENT_SECRET`: a flag is visible in the process list. |
| `--tsg-id` | — | Tenant service group. Prefer `SCM_TSG_ID`. |
| `--dry-run` | off | Show what would be sent, one line per page and its folder. Contacts nothing — no network call is made, so credentials do not even need to be reachable for the preview to be useful. |
| `--skip-validate` | off | Import pages the PAN-OS guards would otherwise refuse, because the API accepts a page that then fails silently on the firewall. |

A run that imports 13 pages against a fresh tenant writes 11 response pages —
`application-block-page`, `credential-block-page`, `credential-coach-text`,
`data-filter-block-page`, `file-block-continue-page`, `file-block-page`,
`safe-search-block-page`, `ssl-cert-status-page`, `url-block-page`,
`url-coach-text`, `virus-block-page` — plus the two GlobalProtect portal
pages, `portal/home` and `portal/login`.

### Portal pages ignore `--folder`

GlobalProtect portal pages (`portal/home.html`, `portal/login.html`) are
always imported into `Mobile Users`, never the folder named by `--folder` or
`SCM_FOLDER`. This is not configurable, and it is deliberate: a portal page is
a named object whose name must be unique across the entire folder tree, and
this API has no working delete. Writing one to the wrong folder is not a
rejected write — it is a *successful* write that then permanently blocks the
correct folder until the stray object is removed by hand in the SCM UI. See
[SCM import architecture](architecture/scm-import.md#why-portal-pages-are-locked-to-mobile-users)
for the full reasoning.

### Exit code

Exit code is `1` if any page failed to import — a partial run is not a
success, even if most pages landed. `0` only when every requested page was
staged (or, for `--dry-run`, would have been).

### Credentials

Three credential fields are required: `client_id`, `client_secret`, `tsg_id`.
They are resolved in this order, same precedence as everywhere else in this
tool:

**CLI flag > environment > `settings.yaml` > built-in default**

```yaml
scm:
  client_id: automation@1234567890.iam.panserviceaccount.com
  client_secret: ...            # prefer the environment instead; see below
  tsg_id: "1234567890"
  folder: Prisma Access          # default shown; only affects response pages
  # auth_url and mfe_url are also settable here, for non-production tenants
```

Environment variables:

| Variable | Corresponds to |
|---|---|
| `SCM_CLIENT_ID` | `--client-id` / `scm.client_id` |
| `SCM_CLIENT_SECRET` | `--client-secret` / `scm.client_secret` |
| `SCM_TSG_ID` | `--tsg-id` / `scm.tsg_id` |
| `SCM_FOLDER` | `--folder` / `scm.folder` |
| `SCM_AUTH_URL` | `scm.auth_url` (default `https://auth.apps.paloaltonetworks.com`) |
| `SCM_MFE_URL` | `scm.mfe_url` (default `https://api.apps.paloaltonetworks.com/mfe/instances`) |

`SCM_CLIENT_SECRET` (or `--client-secret`) is preferred over
`scm.client_secret` in `settings.yaml`: a flag is visible in the process
list, and a secret at rest in a plaintext file is worse than one held only in
the environment for the run. Missing credentials fail with a message naming
exactly which environment variable or flag would supply each missing field.

## Settings

`~/.panos_response_pages/settings.yaml`, optional, every key optional:

```yaml
log:
  level: info          # debug | info | warning | error
  file: true           # default false
  dir: ~/.panos_response_pages/logs
  json: false          # JSON in the log file
  rotate:
    max_bytes: 1048576
    backups: 5
```

Precedence is **CLI flag > environment > settings file > default**, so a `-q` in
a script is never silently undone by a settings file someone left behind. An
unknown key is an error rather than a silent no-op — believing file logging is on
when it is not is exactly the sort of quiet failure this tool exists to prevent.

Note the name: `settings.yaml` is *tool* configuration. `config/*.json` inside
the data directory is *page content* per customer. Two different things.
