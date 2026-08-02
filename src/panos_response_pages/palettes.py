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
