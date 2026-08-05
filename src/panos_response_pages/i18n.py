"""Which words a page uses, and in which language.

PAN-OS serves one page per type per vsys, so a firewall with German and English
speakers behind it cannot import two pages -- the choice has to happen in the
browser. Every configured language is compiled into the page and one is selected
at load time from navigator.languages.

Two-letter primary subtags only. `de-AT`, `de-CH` and `de-DE` all resolve to
`de`; regional variants as distinct COPY are deliberately not supported, because
the fallback chain and the case-canonicalisation rule they need are untested
weight that German does not exercise.
"""

from __future__ import annotations

import json
import pathlib
import re
from collections.abc import Mapping
from typing import Any

from panos_response_pages.errors import BuildError

# Two-letter primary subtag, lowercase. Anchored: "de-AT" must be refused
# loudly rather than silently truncated to a file that does not exist.
LANG_RE = re.compile(r"^[a-z]{2}$")

DEFAULT_LANG = "en"


def base_language(cfg: Mapping[str, Any]) -> str:
    """The language rendered as real text into the markup.

    This is what a browser with JavaScript disabled shows, and what every
    unmatched browser falls back to. It is never shipped in the runtime
    dictionary as well -- it is already in the page.
    """
    return str(cfg.get("baseLanguage", DEFAULT_LANG))


def languages(cfg: Mapping[str, Any]) -> list[str]:
    """Every language compiled into the page, base included."""
    return [str(x) for x in cfg.get("languages", [DEFAULT_LANG])]


def strings_path(lang: str, data_dir: pathlib.Path) -> pathlib.Path:
    return data_dir / "strings" / f"{lang}.json"


def check(cfg: Mapping[str, Any], data_dir: pathlib.Path) -> None:
    """Refuse a language configuration that cannot produce a correct page.

    Called before any page is built rather than at first use, so a bad config
    names the config key the author got wrong instead of surfacing as a KeyError
    from inside substitution.
    """
    langs = languages(cfg)
    base = base_language(cfg)

    if not langs:
        raise BuildError("`languages` is empty; it must list at least the base language")

    for lang in langs:
        if not LANG_RE.match(lang):
            raise BuildError(
                f"language '{lang}' is not a two-letter primary subtag. "
                "Regional variants are not supported: use 'de', which matches de-AT, de-CH and de-DE."
            )

    if base not in langs:
        raise BuildError(f"baseLanguage '{base}' is not in `languages` ({', '.join(langs)})")

    for lang in langs:
        path = strings_path(lang, data_dir)
        if not path.exists():
            raise BuildError(f"language '{lang}' is configured but {lang}.json is missing from {path.parent}")


# The one block a language may omit. Per-language category glosses are ~1800 B
# on the two pages that carry the category map; absent, a non-base language
# shows the translated defaultGloss/riskGloss for that category's TONE, which
# still varies severity and colour per category because the tone map itself is
# never translated and never duplicated.
OPTIONAL_BLOCKS = ("categories",)


def load(lang: str, data_dir: pathlib.Path) -> dict[str, Any]:
    path = strings_path(lang, data_dir)
    if not path.exists():
        raise BuildError(f"missing strings file: {path}")
    doc: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return doc


def flat_keys(doc: Mapping[str, Any], prefix: str = "") -> set[str]:
    """Every leaf path in a strings document.

    Lists are indexed rather than counted, so a German `facts` array one entry
    short names the missing position instead of reporting a length mismatch the
    translator then has to locate by eye.
    """
    out: set[str] = set()
    for key, value in doc.items():
        if not prefix and key in OPTIONAL_BLOCKS:
            continue
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            out |= flat_keys(value, f"{path}.")
        elif isinstance(value, list):
            out |= {f"{path}[{i}]" for i in range(len(value))}
        else:
            out.add(path)
    return out


def check_complete(cfg: Mapping[str, Any], data_dir: pathlib.Path) -> None:
    """Every configured language carries exactly the base language's key set.

    Exactly, not merely at least: an extra key is a typo or a stale entry, and
    either way it is a string that will never reach a page. Reported rather than
    ignored, because both are real mistakes that are invisible in the output.
    """
    base = base_language(cfg)
    want = flat_keys(load(base, data_dir))
    for lang in languages(cfg):
        if lang == base:
            continue
        got = flat_keys(load(lang, data_dir))
        missing = sorted(want - got)
        extra = sorted(got - want)
        if missing or extra:
            parts = []
            if missing:
                parts.append(f"missing {len(missing)} key(s):\n  " + "\n  ".join(missing))
            if extra:
                parts.append(f"unknown {len(extra)} key(s):\n  " + "\n  ".join(extra))
            raise BuildError(f"{lang}.json is out of step with {base}.json -- " + "; ".join(parts))
