"""Colour schemes.

A theme owns layout, a palette owns colour. Swapping accent colours must not
mean forking a shell, so the two are separate axes and separate files.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

from panos_response_pages.errors import BuildError
from panos_response_pages.templates import read


def load_palette(name: str, palette_dir: pathlib.Path) -> dict[str, Any]:
    path = palette_dir / f"{name}.json"
    if not path.exists():
        available = ", ".join(sorted(p.stem for p in palette_dir.glob("*.json")))
        raise BuildError(f"unknown palette '{name}'. Available: {available}")
    palette: dict[str, Any] = json.loads(read(path))
    # The filename is authoritative. build_all keys everything -- `loaded`,
    # `blobs[(theme, stem, page)]`, deploy/<style>/<stem>/ -- by this stem, while
    # build_gallery keys everything -- blob_map, the blobs-<name>.js sidecar,
    # data-pal, data-palette -- by the JSON's own `name` field. Nothing checks
    # the two agree, and when they do not the failure is either a raw KeyError
    # deep in build_gallery or a build that reports `ok` while silently writing
    # a gallery with two rows for the same palette and no sidecar for the new
    # one. Both are worse than refusing here, where there is still one name to
    # point at.
    if palette.get("name") != path.stem:
        raise BuildError(
            f"palette file {path.name} declares name '{palette.get('name')}', which does not match its "
            f"filename stem '{path.stem}'. Rename the file to '{palette.get('name')}.json', or change "
            f"'name' in it to '{path.stem}'."
        )
    return palette


def available(palette_dir: pathlib.Path) -> list[str]:
    return sorted(p.stem for p in palette_dir.glob("*.json"))


def select(palette_dir: pathlib.Path, only: str | None = None) -> list[str]:
    """Which palettes this run builds. Every one, unless narrowed to a single.

    Mirrors how `--theme` narrows the style axis, so the two axes of the matrix
    behave the same way and one flag does not have to be learned twice.
    """
    names = available(palette_dir)
    if not names:
        raise BuildError(f"no palettes found in {palette_dir}")
    if only is None:
        return names
    if only not in names:
        raise BuildError(f"unknown palette '{only}'. Available: {', '.join(names)}")
    return [only]
