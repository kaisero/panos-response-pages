"""Command line interface.

Themes, palettes and customer configs are discovered from the data directory at
runtime, and the data directory itself is selected by --config-dir, which is
parsed in the same pass. A static Enum therefore cannot express the choices
honestly. Instead: completion callbacks for the shell, and validation that
reports what was actually found rather than just rejecting the input.
"""

from __future__ import annotations

import pathlib
import shutil
from typing import Annotated

import typer

from panos_response_pages import __version__, datadir, logs, settings
from panos_response_pages.builder import build_all, format_report, load_themes
from panos_response_pages.errors import BuildError
from panos_response_pages.palettes import load_palette
from panos_response_pages.portal.validate import HOME_VARS, LOGIN_VARS, detect_kind, validate_portal
from panos_response_pages.templates import read
from panos_response_pages.validate import PAGE_TOKENS, validate

# What the two GlobalProtect imports are called on disk, and what each one is.
# The file name is the routing key for `validate`, so it is stated once here
# rather than spelled out at both call sites.
PORTAL_PAGES = {
    "login": ("global-protect-portal-custom-login-page", "login.esp, getsoftwarepage.esp", LOGIN_VARS),
    "home": ("global-protect-portal-custom-home-page", "logout.esp, portal home page", HOME_VARS),
}

app = typer.Typer(
    name="panos-response-pages",
    help="Generate self-contained PAN-OS URL Filtering and Anti-Phishing response pages.",
    no_args_is_help=True,
    add_completion=True,
)


# ---- discovery --------------------------------------------------------------


def _names(subdir: str, suffix: str, data_dir: pathlib.Path | None = None) -> list[str]:
    root = data_dir if data_dir is not None else datadir.resolve()[0]
    try:
        return sorted(p.stem for p in (root / subdir).glob(f"*{suffix}"))
    except OSError:  # pragma: no cover - an unreadable data dir is reported by the build
        return []


def _customers(data_dir: pathlib.Path | None = None) -> list[str]:
    return [n for n in _names("config", ".json", data_dir) if not n.startswith("_")]


def _complete_theme(incomplete: str) -> list[str]:
    return [n for n in _names("themes", ".json") if n.startswith(incomplete)]


def _complete_palette(incomplete: str) -> list[str]:
    return [n for n in _names("palettes", ".json") if n.startswith(incomplete)]


def _complete_customer(incomplete: str) -> list[str]:
    return [n for n in _customers() if n.startswith(incomplete)]


def _require(value: str | None, found: list[str], label: str) -> None:
    """Reject an unknown name by showing what the resolved data dir does have.

    "unknown palette 'lilac'" is a bad error. "unknown palette 'lilac'.
    Available: cyber-orange, prisma-blue, strata-yellow" is the whole answer.
    """
    if value is not None and value not in found:
        raise typer.BadParameter(f"unknown {label} {value!r}. Available: {', '.join(found) or 'none'}")


# ---- global options ---------------------------------------------------------


def _version(value: bool) -> None:
    if value:
        typer.echo(f"panos-response-pages {__version__}")
        raise typer.Exit


@app.callback()
def main(
    ctx: typer.Context,
    verbose: Annotated[int, typer.Option("--verbose", "-v", count=True, help="-v for info, -vv for debug.")] = 0,
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Errors only.")] = False,
    log_json: Annotated[
        bool,
        typer.Option(
            "--log-json", help="Emit JSON lines instead of the report, so there is one machine-readable stream."
        ),
    ] = False,
    _version_flag: Annotated[
        bool, typer.Option("--version", callback=_version, is_eager=True, help="Show the version and exit.")
    ] = False,
) -> None:
    """Generate self-contained PAN-OS response pages."""
    cfg = settings.load()
    logs.configure(cfg, verbose=verbose, quiet=quiet, json_output=log_json)
    ctx.obj = {"settings": cfg, "json": log_json}


# ---- commands ---------------------------------------------------------------


@app.command()
def build(
    ctx: typer.Context,
    customer: Annotated[
        str,
        typer.Option("--customer", "-c", autocompletion=_complete_customer, help="Config merged over the defaults."),
    ] = "contoso",
    theme: Annotated[
        str | None,
        typer.Option("--theme", "-t", autocompletion=_complete_theme, help="Build one style only."),
    ] = None,
    palette: Annotated[
        str | None,
        typer.Option("--palette", "-p", autocompletion=_complete_palette, help="Override the config's palette."),
    ] = None,
    out: Annotated[pathlib.Path, typer.Option("--out", "-o", help="Where to write.")] = pathlib.Path("out"),
    config_dir: Annotated[
        pathlib.Path | None,
        typer.Option("--config-dir", help="Use this data directory instead of the resolved one."),
    ] = None,
    preview: Annotated[bool, typer.Option("--preview/--no-preview", help="Also build the review gallery.")] = True,
) -> None:
    """Build every page of every style.

    Run `themes` and `palettes` to see what the resolved data directory offers;
    an unknown name is rejected with the list.
    """
    log = logs.get()
    data_dir, reason = datadir.resolve(config_dir)
    log.info("data directory %s (%s)", data_dir, reason)

    _require(theme, _names("themes", ".json", data_dir), "theme")
    _require(palette, _names("palettes", ".json", data_dir), "palette")

    try:
        result = build_all(
            data_dir=data_dir,
            out_dir=out,
            customer=customer,
            theme=theme,
            palette_name=palette,
            preview=preview,
            data_reason=reason,
        )
    except BuildError as exc:
        log.error("%s", exc)
        raise typer.Exit(1) from exc

    for r in result.results:
        for w in r.warnings:
            log.warning("%s/%s: %s", r.theme, r.page, w)
        for e in r.errors:
            log.error("%s/%s: %s", r.theme, r.page, e)
        log.debug("%s/%s: %d B", r.theme, r.page, r.size)

    for pr in result.portal_results:
        for w in pr.warnings:
            log.warning("%s/portal/%s: %s", pr.theme, pr.page, w)
        for e in pr.errors:
            log.error("%s/portal/%s: %s", pr.theme, pr.page, e)
        log.debug("%s/portal/%s: %d B (%d encoded)", pr.theme, pr.page, pr.size, pr.encoded)

    if not ctx.obj["json"]:
        typer.echo(format_report(result))
        if preview:
            typer.echo(f"\n  gallery: {out / 'preview' / 'index.html'}")
        typer.echo(f"  palette: {result.palette['name']}  ({result.palette['label']})")
        typer.echo(f"  data:    {data_dir} ({reason})")
        typer.echo(f"  deploy:  {out / 'deploy'}/<style>/<page>.html")
        typer.echo(f"  portal:  {out / 'deploy'}/<style>/portal/<login|home>.html\n")

    if result.failed:
        log.error("one or more pages would fail silently on PAN-OS")
        raise typer.Exit(1)


@app.command()
def init(
    path: Annotated[
        pathlib.Path | None,
        typer.Argument(help="Where to copy. Defaults to ~/.panos_response_pages, which build finds on its own."),
    ] = None,
    force: Annotated[bool, typer.Option("--force", help="Overwrite an existing directory.")] = False,
) -> None:
    """Copy the shipped shells, palettes, themes and config out for editing."""
    log = logs.get()
    target = (path or datadir.USER_DIR).expanduser()
    if target.exists() and not force:
        typer.secho(f"{target} already exists. Pass --force to overwrite.", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    shutil.copytree(datadir.PACKAGED, target, dirs_exist_ok=force)
    log.info("copied packaged data to %s", target)
    typer.echo(f"Copied the shipped data to {target}")
    if target != datadir.USER_DIR:
        typer.echo(f"Build against it with: panos-response-pages build --config-dir {target}")


@app.command()
def themes(config_dir: Annotated[pathlib.Path | None, typer.Option("--config-dir")] = None) -> None:
    """List the available styles."""
    data_dir, reason = datadir.resolve(config_dir)
    typer.echo(f"{data_dir} ({reason})\n")
    for t in load_themes(data_dir):
        typer.echo(f"  {t['name']:10} {t['label']}")


@app.command()
def palettes(config_dir: Annotated[pathlib.Path | None, typer.Option("--config-dir")] = None) -> None:
    """List the available colour palettes."""
    data_dir, reason = datadir.resolve(config_dir)
    typer.echo(f"{data_dir} ({reason})\n")
    for name in _names("palettes", ".json", data_dir):
        typer.echo(f"  {name:16} {load_palette(name, data_dir / 'palettes')['label']}")


@app.command()
def pages() -> None:
    """List the PAN-OS page types and the tokens each one provides."""
    typer.echo("Block pages -- one import object each, tokens expanded at serve time:\n")
    for page, tokens in sorted(PAGE_TOKENS.items()):
        typer.echo(f"  {page:26} {' '.join(f'<{t}/>' for t in sorted(tokens))}")

    # A different mechanism, so a different list. These carry no serve-time
    # tokens at all: the customization is JS variables PAN-OS' own ready handler
    # reads, and every one of them must be declared or the handler throws and
    # the whole customization is lost.
    typer.echo("\nGlobalProtect portal -- customization variables, all of them required:\n")
    for page, (obj, serves, variables) in PORTAL_PAGES.items():
        typer.echo(f"  portal/{page:19} {len(variables)} variables  serves {serves}")
        typer.echo(f"  {'':26} {obj}")


@app.command(name="validate")
def validate_cmd(
    directory: Annotated[pathlib.Path, typer.Argument(help="A directory of built pages.")],
) -> None:
    """Re-run the PAN-OS guards over already-built pages.

    The guards only help if they run on what is actually about to be imported,
    which is not always what this tool just produced.
    """
    log = logs.get()
    checked = failed = 0
    for path in sorted(directory.rglob("*.html")):
        # Two families, two sets of guards, routed by file name. Before this
        # existed the portal imports fell through the block-page test and were
        # skipped with a debug line -- reported as nothing, which reads exactly
        # like a pass.
        if path.stem in PORTAL_PAGES:
            text = read(path)
            kind = detect_kind(text)
            if kind != path.stem:
                # Checked rather than trusted: detect_kind looks for
                # logout_text_array, so a home import that lost its variable
                # block would be validated as a login page and every message
                # would be about the wrong file shape.
                log.warning("%s: reads as the %s import, not %s -- checking it as %s", path, kind, path.stem, kind)
            _size, errors, warnings = validate_portal(text)
        elif path.stem in PAGE_TOKENS:
            _size, errors, warnings = validate(path.stem, path.parent.name, read(path))
        else:
            log.debug("skipping %s: not a known page type", path)
            continue
        checked += 1
        for w in warnings:
            log.warning("%s: %s", path, w)
        for e in errors:
            log.error("%s: %s", path, e)
        failed += bool(errors)

    if not checked:
        typer.secho(f"No recognised page types found under {directory}", fg=typer.colors.YELLOW, err=True)
        raise typer.Exit(1)
    typer.echo(f"checked {checked} page(s), {failed} would fail on PAN-OS")
    if failed:
        raise typer.Exit(1)
