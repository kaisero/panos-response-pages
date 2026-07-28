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
