"""Reading template files and filling their placeholders."""

from __future__ import annotations

import pathlib
import re
from collections.abc import Mapping

from panos_response_pages.errors import BuildError

SECTION_RE = re.compile(r"<!--@([A-Z_]+)-->(.*?)<!--/@\1-->", re.S)


def read(path: pathlib.Path) -> str:
    """Read a template as text.

    read_text, never read_bytes().decode(): the first applies universal-newline
    translation so a checkout and an installed wheel agree, the second would let
    a CRLF file through and shift every byte count under the size ceiling.
    """
    if not path.exists():
        raise BuildError(f"missing file: {path}")
    return path.read_text(encoding="utf-8")


def parse_sections(text: str) -> dict[str, str]:
    """Page templates declare named slots as <!--@NAME-->...<!--/@NAME-->."""
    return {m.group(1): m.group(2).strip() for m in SECTION_RE.finditer(text)}


def substitute(text: str, values: Mapping[str, object]) -> str:
    """Replace {{KEY}} placeholders. Unknown keys are an error, not a silent blank."""
    missing: list[str] = []

    def repl(m: re.Match[str]) -> str:
        key = m.group(1)
        if key not in values:
            missing.append(key)
            return m.group(0)
        return str(values[key])

    out = re.sub(r"\{\{([A-Z_0-9]+)\}\}", repl, text)
    if missing:
        raise BuildError(f"unknown placeholder(s): {', '.join(sorted(set(missing)))}")
    return out
