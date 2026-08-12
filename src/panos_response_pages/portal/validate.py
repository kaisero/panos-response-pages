"""Guards for the two GlobalProtect portal imports.

Size is the one failure PAN-OS reports properly -- it refuses the import and
quotes the encoded length back at you. Everything else here is silent: the
import succeeds, the commit succeeds, and the portal serves something other
than what you meant. A second form token hidden in a comment, or one stray '<'
in a script, costs a round-trip through the firewall to discover. This is the
only place they surface first.

Separate from validate.py on purpose. That module's MAX_BYTES = 17999 is a
SERVING-time limit for block pages injected into a blocked site's response.
This one is an IMPORT-time limit on a base64 field. They are different
mechanisms with different numbers and must never be conflated.
"""

from __future__ import annotations

import base64
import re
from collections.abc import Sequence

from panos_response_pages.validate import built_with, external_refs

# Measured, not guessed. PAN-OS rejected a 24_000 B import with:
#
#   page can be at most 21845 characters, but current length: 32422
#
# The limit is on the BASE64 form, not the file: 32422 is exactly
# len(base64.encodebytes(24_000 bytes)) -- standard base64 wrapped at 76
# columns with a trailing newline. So the usable file size is whatever still
# encodes inside 21845 characters, which binary-searches to 16_170 bytes.
# 16_171 encodes to 21848.
#
# 21845 is floor(65535 / 3), which reads like a 64 KB field cap divided by
# three rather than by the 4/3 base64 actually expands at -- but the observed
# behaviour is what matters, and it is exact.
#
# Two corrections to what was assumed before this was measured: the ceiling is
# not ~10_000 (that KB figure covers response pages generally), and it does NOT
# fail silently -- the import is refused with the message above.
MAX_ENCODED = 21_845
SOFT_MAX = 16_170
WARN_AT = 15_000

# Stock styling hooks the injected form and PAN-OS's own helpers look up.
REQUIRED_IDS = ("logo", "activearea", "heading", "formdiv")

# The two imports have different shapes and different rules.
#
#   login -- a BODY fragment. PAN-OS supplies <html> and an open <head>; the
#            file closes </head>, supplies the whole <body>, and carries the
#            form token.
#   home  -- SCRIPT-ONLY. PAN-OS embeds it verbatim in the <head> of logout.esp
#            and of the portal home page, and writes both bodies itself. No
#            </head>, no <body>, no </html>, and no form token -- there is no
#            form to place.
LOGIN_VARS = (
    "favicon",
    "logo",
    "bg_color",
    "gp_portal_name",
    "gp_portal_name_color",
    "error_text_color",
)
HOME_VARS = (
    "favicon",
    "logo",
    "navbar_text",
    "navbar_text_color",
    "navbar_bg_color",
    "dropdown_bg_color",
    "bg_color",
    "label_custom_app_url",
    "display_globalprotect_agent",
    "label_globalprotect_agent",
    "gp_portal_name",
    "gp_portal_name_color",
    "logout_text_array",
    "logout_text_color",
)

_FORM_TOKEN = re.compile(r"<pan_form\s*/>")
# A '<' not followed by a tag-ish character. In a script (`i < n`) or in text it
# reads as the start of a tag to a naive scanner, and the observed failure is
# that the form token stops being substituted.
_RAW_LT = re.compile(r"<(?![a-zA-Z/!])")


def encoded_size(text: str) -> int:
    """The length PAN-OS measures, and the only one it ever quotes back.

    encodebytes, not b64encode: the figure PAN-OS quoted matched the
    wrapped-at-76-columns form exactly, trailing newline included. The unwrapped
    length under-reports by around 1.4%, which is enough to call a file that
    will be refused a file that fits.
    """
    return len(base64.encodebytes(text.encode("utf-8")))


def detect_kind(text: str) -> str:
    """Which of the two imports this is.

    logout_text_array exists only in the Home Page import; it is the cleanest
    discriminator between the two file shapes.
    """
    return "home" if "logout_text_array" in text else "login"


# What a style over the portal ceiling can actually give back.
#
# NOT the block pages' recovery. That one offers the optional per-language
# `categories` block first and keeps the language; this dictionary has no
# optional block -- every key in it is a word the login form or the logout page
# renders -- so the only thing to drop is the whole feature. Quoting the
# categories block here would send a reader looking for a block that is not in
# the file.
#
# It matters more here than there. The block pages fit five extra languages
# before the warn band; the portal imports fit two.
RECOVERY = (
    ' A style with no room for them declares "i18n": false and ships the base language alone --'
    " this dictionary has no optional block to drop first."
)


def validate_portal(text: str, languages: Sequence[str] = ()) -> tuple[int, list[str], list[str]]:
    """Returns (size, errors, warnings), mirroring validate.validate().

    `languages` is what the import was BUILT with, which on a style declaring
    `"i18n": false` is not what the config lists. Like the block-page guard, it
    only ever appears in the two size messages: the file is too big, so what is
    in it that could come out. Optional for the same reason too -- the CLI runs
    this over already-built files where no config is in hand.
    """
    raw = text.encode("utf-8")
    errors: list[str] = []
    warnings: list[str] = []

    # Report the encoded length too -- that is the number PAN-OS quotes back.
    size = len(raw)
    encoded = encoded_size(text)
    langs = built_with(languages)
    recovery = RECOVERY if langs else ""
    if size > SOFT_MAX:
        errors.append(
            f"{size} B encodes to {encoded} chars, over the {MAX_ENCODED} limit "
            f"(max file size {SOFT_MAX} B) --{langs} PAN-OS will refuse the import.{recovery}"
        )
    elif size > WARN_AT:
        warnings.append(f"{size} B of {SOFT_MAX} B ({encoded}/{MAX_ENCODED} encoded){langs}{recovery}")

    kind = detect_kind(text)

    if text.lstrip().startswith(("<!DOCTYPE", "<html")):
        errors.append("starts a new document -- PAN-OS supplies <html> and an open <head>")

    if kind == "login":
        if "</head>" not in text:
            errors.append("never closes </head> -- PAN-OS leaves it open for this file")
        if not text.rstrip().endswith("</html>"):
            errors.append("does not end with </html>")
    else:
        # PAN-OS writes the body itself; anything structural lands mid-<head>.
        for tag in ("</head>", "<body", "</html>"):
            if tag in text:
                errors.append(f"{tag} in a script-only import -- it is embedded mid-<head>")

    # The form, and the live per-request CSRF token, only exist via this token.
    # It must appear exactly once. PAN-OS substitutes the FIRST literal
    # occurrence and is blind to context -- one written inside a CSS or HTML
    # comment wins, the form lands in the <style> block, and the real token is
    # never expanded.
    forms = _FORM_TOKEN.findall(text)
    if kind == "home":
        if forms:
            errors.append("form token in the Home Page import -- no form is placed here")
    elif not forms:
        errors.append("no <pan_form/> -- PAN-OS appends the form outside your layout")
    elif len(forms) > 1:
        errors.append(
            f"{len(forms)} form tokens -- only the first is substituted; "
            "the others (comments included) leave the form misplaced"
        )

    for m in _RAW_LT.finditer(text):
        line = text.count("\n", 0, m.start()) + 1
        errors.append(f"raw '<' outside a tag at line {line}: {text[m.start() : m.start() + 40]!r}")

    if "csrf-token" in text:
        errors.append("a csrf-token value is baked in -- it is per-request; logins will fail")

    # The portal's CSP blocks external CSS and JS. data: and same-origin are fine.
    # A navigational <a href> is not a subresource load and is not what the CSP
    # refuses -- so the contact link may point off-origin. That exemption is one
    # rule about one anchor and lives in validate.external_refs(), which the
    # block-page guard uses too; the reason for the refusal differs between the
    # two families, the exemption does not.
    for _ref, url in external_refs(text):
        errors.append(f"external reference blocked by the portal CSP: {url[:60]}")

    # PAN-OS's own ready handler dereferences every one; undeclared ones throw
    # and abort the handler, losing the whole customization.
    for var in HOME_VARS if kind == "home" else LOGIN_VARS:
        if not re.search(rf"\bvar\s+{var}\s*=", text):
            errors.append(f"var {var} is not declared -- PAN-OS's handler will throw")

    if kind == "login":
        for el in REQUIRED_IDS:
            if f'id="{el}"' not in text:
                warnings.append(f'id="{el}" missing -- stock styling hooks expect it')

    return size, errors, warnings
