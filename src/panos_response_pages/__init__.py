"""Self-contained PAN-OS response pages, generated from templates."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("panos-response-pages")
except PackageNotFoundError:  # pragma: no cover - running from a checkout, not installed
    # Reporting a sentinel beats crashing on --version for someone who cloned
    # the repo and ran it without `uv sync`.
    __version__ = "0.0.0.dev0"

__all__ = ["__version__"]
