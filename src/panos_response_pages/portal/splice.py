"""Reproduce what PAN-OS serves, for PREVIEW ONLY.

The portal imports are not documents. The Login Page import is a body fragment
that begins by closing a `<head>` somebody else opened; the Home Page import is
a bare `<script>` block that PAN-OS embeds mid-`<head>`. Neither renders in a
browser on its own, so there is nothing to look at and nothing to screenshot
until the surrounding page is put back. PAN-OS emits a fixed prefix and
concatenates the import onto it, so preview does the same with prefixes
captured from a live 11.x portal.

Spliced output must NEVER be imported and must never be passed to
validate_portal(). It carries PAN-OS' own prefix, a `<!DOCTYPE>` in two of the
three cases, and a captured form whose csrf-token has been neutralised --
every one of which validate_portal() correctly rejects in a real import.
validate_portal() runs on the raw import only. Keep preview output outside any
tree the `validate` command walks.

Three things this module exists to get right, each of which the lab got wrong
first and then had to be told about:

1. **The prefixes are asymmetric.** login.esp's is 8,394 B and carries
   loadPage(), submitClicked() and checkCapsLock(). getsoftwarepage.esp's is
   1,797 B and carries none of them -- it is the same imported file with a
   different form substituted in. Splicing the login prefix onto the download
   form invents a `document.login is undefined` error the real page never has.

2. **The assets are loaded by relative path.** Every prefix pulls jQuery from
   `portal/js/jquery.min.js`. Without it `$(document).ready` never runs, so
   `$('#logo img').attr('src', logo)` never fires -- and the login import ships
   its `<img>` with no src by design, because that handler is the only thing
   that should ever fill it. The result is an empty logo box in every preview:
   a failure of the simulator, presented as a failure of the page. `assets`
   re-points those references at wherever the captured tree was written.

3. **The four login states come from server-set values.** loadPage() reads
   variables PAN-OS writes into the prefix at request time -- respStatus,
   respMsg, isChangePasswdForm -- and branches on them. Rewriting those
   literals and letting the captured loadPage() run is the only way to see the
   real states; faking the DOM afterwards would preview markup this page never
   produces. The change-password state is the one that matters: it adds two
   inputs and a message box, is taller than the viewport, and in production
   only an expired password reveals it.
"""

from __future__ import annotations

import pathlib
import re
from collections.abc import Mapping

from panos_response_pages import datadir
from panos_response_pages.errors import BuildError
from panos_response_pages.templates import read

# Where the captured prefixes, forms and asset tree live by default.
FIXTURES = datadir.PACKAGED / "fixtures"

# The two surfaces the Login Page import serves, and which capture pairs with
# which. Getting this pairing wrong is silent in the output and loud in the
# console, so it is a table rather than an `if`.
SURFACES = {
    "login": ("panos-prefix-login.html", "pan_form-login.html"),
    "getsoftware": ("panos-prefix-getsoftware.html", "pan_form_getsoftware.html"),
}

# What PAN-OS writes into loadPage() for each outcome. Keys are JS variable
# names in the captured prefix; values are the literal source that replaces
# whatever the capture happened to contain.
#
# changepw sets respStatus to "Error" as well, and that is not an accident of
# this table: loadPage() only tests isChangePasswdForm inside its Error branch,
# so a change-password form with any other status is unreachable. in_change_passwd
# is the same value again, in submitClicked(), where it gates the
# "passwords did not match" check.
STATES: Mapping[str, Mapping[str, str]] = {
    "default": {},
    "error": {
        "respStatus": '"Error"',
    },
    "challenge": {
        "respStatus": '"Challenge"',
        "respMsg": '"Enter the six-digit code from your authenticator app."',
    },
    "changepw": {
        "respStatus": '"Error"',
        "respMsg": '"Your password has expired and must be changed before you can sign in."',
        "isChangePasswdForm": "1",
        "in_change_passwd": "1",
        "changePasswordMsg": '"Passwords must be at least 12 characters and cannot repeat your last five."',
        "valueUser": '"a.mercier"',
    },
}

# The file name each login state is previewed under.
LOGIN_PREVIEWS = tuple(f"login-{state}" for state in STATES)

_FORM_TOKEN = re.compile(r"<pan_form\s*/>")
# Only quoted references, so prose mentioning the directory is left alone.
_ASSET_REF = re.compile(r"""(["'])portal/""")


def _fixture(name: str, fixtures: pathlib.Path | None) -> str:
    return read((fixtures or FIXTURES) / name)


def _repoint(text: str, assets: str) -> str:
    """Point the captured `portal/...` asset references at `assets`.

    The captures were served from the portal root, where `portal/js/jquery.min.js`
    is correct. Preview files sit at a different depth, and the gallery's
    srcdoc frames resolve against the gallery's own URL, so the prefix that
    works differs per output and cannot be baked into the fixture.
    """
    return _ASSET_REF.sub(lambda m: m.group(1) + assets, text)


def _set_var(text: str, name: str, literal: str) -> str:
    """Replace the initialiser of one `var` in the captured prefix.

    Exactly one match is required. These captures are the record of what a
    firewall actually served; if a re-capture ever renames or duplicates one of
    these variables, a silent no-op here would show the default state under
    three different labels and look entirely plausible.
    """
    pattern = re.compile(rf"\bvar\s+{re.escape(name)}\s*=[^;]*;")
    out, count = pattern.subn(lambda _m: f"var {name} = {literal};", text)
    if count != 1:
        raise BuildError(f"captured login prefix has {count} declarations of var {name} -- expected exactly 1")
    return out


def splice_login(
    fragment: str,
    surface: str = "login",
    state: str = "default",
    *,
    assets: str = "portal/",
    fixtures: pathlib.Path | None = None,
) -> str:
    """Wrap a Login Page import in the prefix and form PAN-OS would serve it with.

    `surface` picks between login.esp and getsoftwarepage.esp -- one import,
    two forms, two different prefixes. `state` drives loadPage() and therefore
    only applies to login.esp; the download prefix has no loadPage() to drive.
    """
    if surface not in SURFACES:
        raise BuildError(f"unknown portal surface {surface!r} -- expected one of {', '.join(SURFACES)}")
    if state not in STATES:
        raise BuildError(f"unknown login state {state!r} -- expected one of {', '.join(STATES)}")
    if surface != "login" and state != "default":
        raise BuildError(
            f"the {surface} surface has no loadPage() to drive, so it has no {state!r} state -- "
            "the login states belong to login.esp alone"
        )
    if not _FORM_TOKEN.search(fragment):
        raise BuildError("no <pan_form/> in the fragment -- PAN-OS has nowhere to put the form")

    prefix_name, form_name = SURFACES[surface]
    prefix = _repoint(_fixture(prefix_name, fixtures), assets)
    for name, literal in STATES[state].items():
        prefix = _set_var(prefix, name, literal)

    form = _fixture(form_name, fixtures)
    return prefix + _FORM_TOKEN.sub(lambda _m: form, fragment)


# PAN-OS serves the Home Page import at /global-protect/logout.esp, and the
# import gates its own restyle on that path -- correctly, because the same file
# is also embedded in the portal home page, whose body has never been captured
# and must not be touched. A preview served from a file:// path or from a
# srcdoc frame has neither pathname, so the gate never fires and every logout
# preview would render as the stock page. What is missing there is the request
# URL, not the page logic, so the shim restores the request URL's effect and
# says so.
_LOGOUT_SHIM = """
<script>
if(location.pathname.indexOf('logout.esp')===-1){
document.documentElement.setAttribute('data-gp','logout');
[].forEach.call(document.getElementsByTagName('link'),function(l){if(l.rel==='stylesheet'){l.disabled=true;}});
}
</script>
"""


def splice_home(
    script: str,
    *,
    assets: str = "portal/",
    fixtures: pathlib.Path | None = None,
) -> str:
    """Wrap a Home Page import in the logout.esp page PAN-OS generates around it.

    logout.esp is built whole by the firewall; the only part that comes from
    the import is the customization block in its `<head>`. So the splice is a
    straight prefix/suffix sandwich rather than a token substitution.
    """
    prefix = _repoint(_fixture("logout-prefix.html", fixtures), assets)
    suffix = _repoint(_fixture("logout-suffix.html", fixtures), assets)
    return prefix + script + _LOGOUT_SHIM + suffix
