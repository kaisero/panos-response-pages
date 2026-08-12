"""Read a built variant directory into the exact bytes an import will send.

Deliberately reads from disk rather than taking the build's in-memory output:
what gets imported must be what was reviewed, and `validate` already works on
the same directory. It also means an import can be re-run against a directory
built weeks ago without rebuilding it.
"""

from __future__ import annotations

import base64
import pathlib
from dataclasses import dataclass, field

from panos_response_pages import logs
from panos_response_pages.errors import BuildError, ImportFailed
from panos_response_pages.importer.catalogue import BY_LOCAL, BY_REMOTE, PORTAL, PageSpec
from panos_response_pages.portal.validate import validate_portal
from panos_response_pages.templates import read
from panos_response_pages.validate import validate


@dataclass
class ImportItem:
    """One page, loaded and ready to send."""

    spec: PageSpec
    path: pathlib.Path
    payload: bytes
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def encoded(self) -> str:
        """Base64 as the API wants it: unwrapped, ASCII.

        The browser payload this was reverse-engineered from wraps at 76
        characters. That is cosmetic -- unwrapped round-trips byte-exact.
        """
        return base64.b64encode(self.payload).decode("ascii")


def load(directory: pathlib.Path, *, only: set[str] | None = None, check: bool = True) -> list[ImportItem]:
    """Load every importable page under `directory`, in catalogue order.

    `only` filters by remote name. `check` runs the same PAN-OS guards the build
    runs; the findings ride on each item so the caller decides whether to refuse.
    """
    if not directory.is_dir():
        raise ImportFailed(f"{directory} is not a directory")

    if only:
        unknown = sorted(only - set(BY_REMOTE))
        if unknown:
            raise ImportFailed(f"unknown page(s): {', '.join(unknown)}. Available: {', '.join(sorted(BY_REMOTE))}")

    items: list[ImportItem] = []
    missing: list[str] = []
    for local, spec in BY_LOCAL.items():
        if only and spec.remote not in only:
            continue
        path = directory / local
        if not path.is_file():
            # Not an error: --only and a deliberately partial build directory
            # are both legitimate. But a stale or partial directory used to
            # yield a green "would import 1/1 page(s)" with no hint that 12 of
            # 13 catalogue entries were absent -- the denominator hid it. This
            # is what makes the absence visible instead.
            missing.append(spec.remote)
            continue

        try:
            text = read(path)
        except (OSError, UnicodeDecodeError, BuildError) as exc:
            # read() calls read_text(encoding="utf-8"), which raises
            # UnicodeDecodeError on a non-UTF-8 file and lets a plain OSError
            # (e.g. a permissions problem) through unchanged. cli.py only
            # catches ImportFailed, so either one would otherwise surface as a
            # raw traceback instead of the one-line error every other import
            # failure produces. BuildError is included for the same reason,
            # even though the is_file() check above makes read()'s own
            # "missing file" BuildError unreachable here -- catching it is
            # what actually retires that branch as a concern.
            raise ImportFailed(f"{path}: could not be read ({exc})") from exc
        item = ImportItem(spec=spec, path=path, payload=text.encode("utf-8"))
        if check:
            if spec.family == PORTAL:
                _size, errs, warns = validate_portal(text)
            else:
                _size, errs, warns = validate(spec.remote, text)
            item.errors, item.warnings = list(errs), list(warns)
        items.append(item)

    if missing:
        log = logs.get()
        log.warning("%d catalogue page(s) not found under %s and will not be imported", len(missing), directory)
        for name in sorted(missing):
            log.debug("missing: %s", name)

    if not items:
        if only:
            # Name the page(s) actually asked for rather than the generic
            # "no importable pages" message -- an operator who passed --only
            # for a page missing from this directory needs to see that name,
            # not guess which of the catalogue's ~20 pages was meant.
            raise ImportFailed(
                f"none of the requested page(s) were found under {directory}: "
                f"{', '.join(sorted(only))}. Run `build` first."
            )
        raise ImportFailed(
            f"no importable pages under {directory}. Expected files named like "
            f"url-block-page.html, or portal/home.html -- run `build` first."
        )
    return items
