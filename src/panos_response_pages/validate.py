"""PAN-OS guards.

Every check maps to a documented failure mode, and every one of them fails
SILENTLY on a firewall: the import reports success, the commit succeeds, and
users get the default page or nothing. This module is the only feedback loop
that will ever exist.
"""

from __future__ import annotations

import re

MAX_BYTES = 17999  # PAN-OS 8.1.3+ hard ceiling. Oversize fails SILENTLY.
WARN_BYTES = 16000  # headroom for serve-time <url/> expansion

# Page type -> substitution tokens PAN-OS actually provides on that page.
# Using a token outside this set renders it as inert markup: it shows nothing.
PAGE_TOKENS = {
    "url-block-page": {"user", "url", "category"},
    "url-coach-text": {"user", "url", "category", "pan_form"},
    "safe-search-block-page": {"user", "ssurl"},  # NO url, NO category
    "application-block-page": {"user", "appname"},
    "credential-block-page": {"user", "url", "category"},
    "credential-coach-text": {"user", "url", "category", "pan_form"},
    "virus-block-page": {"user", "fname"},
    "file-block-page": {"user", "fname"},
    "file-block-continue-page": {"user", "fname", "cookie"},
}

TOKEN_RE = re.compile(r"<(user|url|category|ssurl|pan_form|fname|cookie|appname)\s*/>")


# into whether data actually left the browser, and no visibility into which policy
# matched -- different users can match different rules. Neither class of statement
# can be made truthfully, so both fail the build rather than reaching a user.
BANNED_COPY = [
    ("nothing you typed", "asserts data was not transmitted"),
    ("was not sent", "asserts data was not transmitted"),
    ("left your device", "asserts data was not transmitted"),
    ("for everyone", "asserts the policy applies to all users"),
    ("everybody", "asserts the policy applies to all users"),
    ("not just you", "asserts the policy applies to all users"),
]


def audit_copy(html_text: str) -> list[str]:
    """Reject copy that states something the page has no way of knowing."""
    low = html_text.lower()
    return [f'copy claim "{phrase}" -- {why}' for phrase, why in BANNED_COPY if phrase in low]


def validate(page: str, theme_name: str, html_text: str) -> tuple[int, list[str], list[str]]:
    """Every check here maps to a documented PAN-OS failure mode."""
    errors: list[str] = []
    warnings: list[str] = []
    size = len(html_text.encode("utf-8"))

    if size > MAX_BYTES:
        errors.append(f"{size} B exceeds the {MAX_BYTES} B ceiling -- PAN-OS would silently serve the default page")
    elif size > WARN_BYTES:
        warnings.append(f"{size} B is within {MAX_BYTES - size} B of the ceiling; <url/> expands at serve time")

    if not html_text.lstrip().startswith("<!DOCTYPE html>"):
        errors.append("missing <!DOCTYPE html> -- browsers fall back to quirks mode")

    # Self-containment. The response page is injected into the BLOCKED site's
    # response, so its origin is the blocked site: relative paths do not resolve,
    # and any external fetch must survive the policy that produced this page.
    if "<base " in html_text:
        errors.append("<base> tag present -- resolves against the blocked site")
    if "<link " in html_text:
        errors.append("<link> tag present -- external stylesheet is not self-contained")
    for attr in ('src="http', "src='http", 'href="http', "href='http"):
        for m in re.finditer(re.escape(attr), html_text):
            tail = html_text[m.start() : m.start() + 200]
            if not tail.startswith(('href="mailto', "href='mailto")):
                errors.append(f"external reference found ({attr}...) -- not self-contained")
                break

    # Token legality. An unsupported token is not an error to PAN-OS; it simply
    # renders as nothing, leaving a blank field on a live page.
    allowed = PAGE_TOKENS[page]
    for m in TOKEN_RE.finditer(html_text):
        tok = m.group(1)
        if tok not in allowed:
            errors.append(f"<{tok}/> is not available on {page} (supported: {', '.join(sorted(allowed))})")

    errors.extend(audit_copy(html_text))

    if "initial-scale=1" not in html_text:
        warnings.append("viewport should use initial-scale=1")

    return size, errors, warnings
