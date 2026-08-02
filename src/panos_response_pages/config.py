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


def customer_keys(customer: str, config_dir: pathlib.Path) -> set[str]:
    """Which top-level keys this customer's own file sets.

    load_config() merges the customer document over the defaults, so a value's
    presence in the result says nothing about who chose it -- and _defaults.json
    ships a `palette`, which means every build looks like it asked for one.

    A theme that pins its own palette has to tell "the shipped default" apart
    from "this customer said so", because only the second outranks the pin.
    That distinction is the whole of what this answers.
    """
    override = config_dir / f"{customer}.json"
    return set(json.loads(read(override))) if override.exists() else set()


def deep_merge(base: dict[str, Any], extra: Mapping[str, Any]) -> dict[str, Any]:
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            deep_merge(base[k], v)
        else:
            base[k] = v
    return base
