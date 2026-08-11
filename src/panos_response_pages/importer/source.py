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

from panos_response_pages.errors import ImportFailed
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
    for local, spec in BY_LOCAL.items():
        if only and spec.remote not in only:
            continue
        path = directory / local
        if not path.is_file():
            continue

        text = read(path)
        item = ImportItem(spec=spec, path=path, payload=text.encode("utf-8"))
        if check:
            if spec.family == PORTAL:
                _size, errs, warns = validate_portal(text)
            else:
                _size, errs, warns = validate(spec.remote, text)
            item.errors, item.warnings = list(errs), list(warns)
        items.append(item)

    if not items:
        raise ImportFailed(
            f"no importable pages under {directory}. Expected files named like "
            f"url-block-page.html, or portal/home.html -- run `build` first."
        )
    return items
