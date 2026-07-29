"""One build, shared by every test that needs built output.

Five test classes each used to shell out to the build as a subprocess. That cost
five full builds per run, and -- more importantly -- meant coverage saw none of
the code they exercised, because the work happened in another interpreter. The
suite was thorough and the coverage number said 31%.
"""

import functools
import pathlib
import tempfile

from _paths import DATA
from panos_response_pages.builder import BuildResult, build_all


@functools.lru_cache(maxsize=1)
def built() -> tuple[pathlib.Path, BuildResult]:
    """Build everything once, into a temp directory.

    Deliberately not the repository's own out/: a test run must neither depend
    on nor clobber whatever the developer last built by hand.
    """
    out = pathlib.Path(tempfile.mkdtemp(prefix="panos-rp-tests-"))
    return out, build_all(DATA, out, preview=True)


@functools.lru_cache(maxsize=1)
def portal_pages() -> dict[tuple[str, str], str]:
    """Every portal page in every theme, as the firewall would receive it."""
    from _paths import DATA
    from panos_response_pages.builder import load_themes
    from panos_response_pages.config import load_config
    from panos_response_pages.palettes import load_palette
    from panos_response_pages.portal.page import build_portal_page

    cfg = load_config("contoso", DATA / "config")
    palette = load_palette("cyber-orange", DATA / "palettes")
    out: dict[tuple[str, str], str] = {}
    for theme in load_themes(DATA):
        for page in ("login", "home"):
            out[(theme["name"], page)] = build_portal_page(
                page, theme, cfg, palette, preview=False, template_dir=DATA / "templates"
            )
    return out


def deploy_dir() -> pathlib.Path:
    return built()[0] / "deploy"


def preview_dir() -> pathlib.Path:
    return built()[0] / "preview"
