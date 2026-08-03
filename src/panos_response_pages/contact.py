"""Where a response page sends a user who needs a human.

Two modes, and a config picks exactly one:

* `supportEmail` -- a `mailto:` the browser hands to a mail client. The page
  pre-fills subject and body, so IT receives the incident already described.
* `supportUrl` -- an absolute https link to a ticket system.

They are mutually exclusive rather than ranked. A config carrying both has an
author who believes one of them is doing something, and guessing which would
mean shipping the other one's wording to users who will never see it.

The URL mode loses the pre-filled body: an `<a href>` carries no payload the way
a mailto does. That is accepted. What is NOT dropped is the metadata the body was
built from -- each page still declares `data-subject`, `data-intro` and
`data-prompt`. A ticket-system adapter (ServiceNow, Jira Service Management) is
the reason: those fields are exactly what such a system wants as
`short_description` and `description`, and an adapter added later reads them from
the anchor rather than needing all nine templates edited again.

Why `supportUrl` must be absolute https, and never a relative path: a response
page is served AS the blocked site, so its origin is whatever the user was
refused. A relative link resolves against that host, and an http link is
strippable in transit on a page whose whole job is to be trusted.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

from panos_response_pages.errors import BuildError

EMAIL = "email"
URL = "url"

# What the link is called when there is no address to print, unless the customer
# says otherwise via `supportLabel`. A ticket queue has a name -- "Service Desk",
# "Helpdesk", "IT Support" -- and a page that calls it something else is telling
# the user to go somewhere they cannot find. The default is here rather than only
# in _defaults.json so that a config assembled without that document still names
# something, instead of rendering an anchor with no text.
DEFAULT_URL_LABEL = "IT support"


def _set(cfg: Mapping[str, Any], key: str) -> str:
    """The value of `key`, treating an empty string as absent.

    JSON has no comments, so the documented way to disable one of these keys is
    to blank it. That has to mean the same thing as deleting it, or "turn one
    off" would be advice that does not work.
    """
    return str(cfg.get(key) or "").strip()


def mode(cfg: Mapping[str, Any]) -> str:
    email, url = _set(cfg, "supportEmail"), _set(cfg, "supportUrl")
    if email and url:
        raise BuildError(
            "config sets both supportEmail and supportUrl; they are mutually exclusive. "
            "Blank the one you are not using and build again. Note that _defaults.json "
            "ships a supportEmail, so a customer file adding supportUrl must also set "
            '"supportEmail": "" -- the two documents are merged, not replaced.'
        )
    if url:
        return URL
    if email:
        return EMAIL
    raise BuildError("config sets neither supportEmail nor supportUrl; every page needs a way to reach IT")


_BAD_URL_CHARS = frozenset("\"'<> ")


def check(cfg: Mapping[str, Any]) -> None:
    """Validate the contact configuration. Raises BuildError, never returns a value."""
    if mode(cfg) == URL:
        url = _set(cfg, "supportUrl")
        if not url.startswith("https://"):
            raise BuildError(
                f"supportUrl is {url!r}; it must be an absolute https:// URL. A response page is "
                "served as the blocked site, so a relative path resolves against that host."
            )
        # substitute() does no escaping and CONTACT_HREF lands straight inside
        # href="{{CONTACT_HREF}}", so any of these breaks out of the attribute
        # (a quote), starts markup the anchor never closes (< or >), or is
        # whitespace/control noise that has no business inside a URL. This is
        # admin-authored config, not remote input -- the point is a loud
        # BuildError instead of a page that builds clean and ships broken.
        bad = sorted({c for c in url if c in _BAD_URL_CHARS or ord(c) < 0x20 or ord(c) == 0x7F})
        if bad:
            raise BuildError(
                f"supportUrl {url!r} contains {''.join(bad)!r}, which is not valid inside an href "
                "attribute; the anchor would break or carry attributes the config never asked for."
            )
        if not urlsplit(url).netloc:
            raise BuildError(
                f"supportUrl is {url!r}; it has no host. Something like 'https://' or 'https:///new' "
                "builds clean and ships a dead link -- give it a real ticket-system host."
            )
        label = _set(cfg, "supportLabel")
        if "<" in label or ">" in label:
            raise BuildError(
                f"supportLabel is {label!r}; it must not contain '<' or '>'. It is printed as the "
                "anchor's link text, and either character would open markup the page never closes."
            )
    elif "@" not in _set(cfg, "supportEmail"):
        raise BuildError(f"supportEmail is {_set(cfg, 'supportEmail')!r}; it must be an email address")


def href(cfg: Mapping[str, Any], mailto: str) -> str:
    """The `href` the contact anchor carries.

    `mailto` is the page's own pre-filled mailto string, which only the page
    template can supply -- the subject and body are page-specific copy.
    """
    return _set(cfg, "supportUrl") if mode(cfg) == URL else mailto


def name(cfg: Mapping[str, Any]) -> str:
    """Human-facing link text, for the places that print the contact inline.

    Email mode prints the address itself, which is both the label and the
    destination. URL mode has no such string, so it prints `supportLabel`, or a
    default when the customer has not named their queue.
    """
    if mode(cfg) == EMAIL:
        return _set(cfg, "supportEmail")
    return _set(cfg, "supportLabel") or DEFAULT_URL_LABEL


def to_attr(cfg: Mapping[str, Any]) -> str:
    """The `data-to` attribute, including its leading space, or nothing.

    Only the mailto rebuild in scripts.py reads it, and that rebuild does not
    run in URL mode -- so in URL mode this would be bytes with no reader.
    """
    return f' data-to="{_set(cfg, "supportEmail")}"' if mode(cfg) == EMAIL else ""


def reachable(cfg: Mapping[str, Any]) -> str:
    """The contact as plain prose, for somewhere that cannot carry a link.

    `name()` is anchor text -- it assumes something around it supplies the
    destination. The portal's logout messages have no such thing: PAN-OS fills
    that div with .text(), so markup would render as characters. Email mode has
    always printed the address itself and read fine; URL mode has to print the
    URL, or it names a queue and leaves the user to find it.
    """
    if mode(cfg) == EMAIL:
        return _set(cfg, "supportEmail")
    return f"{name(cfg)} at {_set(cfg, 'supportUrl')}"


def email(cfg: Mapping[str, Any]) -> str:
    """The address, or an empty string in URL mode.

    `{{SUPPORT_EMAIL}}` still has to resolve to something in URL mode: it appears
    in sections URL mode discards, and substitute() raises on an unknown key
    whether or not the text survives.
    """
    return _set(cfg, "supportEmail")
