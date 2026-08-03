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
