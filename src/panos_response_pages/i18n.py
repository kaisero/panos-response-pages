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
