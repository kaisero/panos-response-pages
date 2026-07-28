"""Customer configuration: the default document plus an optional override."""

from __future__ import annotations

import json
import pathlib
from collections.abc import Mapping
from typing import Any

from panos_response_pages.templates import read


def load_config(customer: str, config_dir: pathlib.Path) -> dict[str, Any]:
    cfg: dict[str, Any] = json.loads(read(config_dir / "_defaults.json"))
    override = config_dir / f"{customer}.json"
    if override.exists():
        deep_merge(cfg, json.loads(read(override)))
    return cfg


def deep_merge(base: dict[str, Any], extra: Mapping[str, Any]) -> dict[str, Any]:
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            deep_merge(base[k], v)
        else:
            base[k] = v
    return base
