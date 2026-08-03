"""Where a response page sends a user who needs a human.

Two modes, and the config picks exactly one. Every assertion here covers a
config mistake that would otherwise surface as a raw KeyError, a page that
silently names nobody, or an href the firewall's own policy would refuse.
"""

import pathlib
import unittest
from typing import ClassVar

import pytest

from _paths import DATA
from panos_response_pages import contact
from panos_response_pages.builder import load_themes
from panos_response_pages.config import load_config
from panos_response_pages.emit import strip_output
from panos_response_pages.errors import BuildError
from panos_response_pages.page import build_page
from panos_response_pages.palettes import load_palette
from panos_response_pages.portal.page import build_portal_page
from panos_response_pages.validate import PAGE_TOKENS

THEMES = load_themes(DATA)
PALETTE = load_palette("cyber-orange", DATA / "palettes")
TEMPLATES: pathlib.Path = DATA / "templates"
PAGES = sorted(PAGE_TOKENS)

# What a customer file must contain to switch modes. supportEmail has to be
# blanked explicitly: _defaults.json ships one, and the two documents are
# merged rather than replaced, so adding supportUrl alone sets both.
URL_CFG_KEYS = {"supportEmail": "", "supportUrl": "https://tickets.example.com/new"}


def shipped(**over):
    """The shipped config, with contact keys overridden."""
    cfg = load_config("contoso", DATA / "config")
    cfg.update(over)
    return cfg


def render(cfg, page="url-block-page", theme=None):
    return strip_output(build_page(page, theme or THEMES[0], cfg, PALETTE, False, TEMPLATES))


def portal(cfg, page="login", theme=None):
    return build_portal_page(page, theme or THEMES[0], cfg, PALETTE, preview=False, template_dir=TEMPLATES)


def rep_anchor(html):
    """The contact anchor, as source.

    Walked by index rather than matched with `<a[^>]*>`: the email-mode href
    contains <user/> and <url/>, so a negated-`>` class stops in the middle of
    the attribute. This is the same walk tests/test_layout_details.py uses.
    """
    i = html.index('id="rep"')
    return html[html.rindex("<a ", 0, i) : html.index(">", html.index('href="', i)) + 1]


@pytest.mark.unit
class TestMode(unittest.TestCase):
    def test_email_only_is_email_mode(self):
        assert contact.mode({"supportEmail": "it@example.com"}) == contact.EMAIL

    def test_url_only_is_url_mode(self):
        assert contact.mode({"supportUrl": "https://tickets.example.com/new"}) == contact.URL

    def test_both_set_is_an_error_naming_both_keys(self):
        with pytest.raises(BuildError) as err:
            contact.mode({"supportEmail": "it@example.com", "supportUrl": "https://t.example.com/"})
        message = str(err.value)
        assert "supportEmail" in message
        assert "supportUrl" in message

    def test_both_set_error_explains_the_merge(self):
        """The first person to hit this will have added supportUrl to a customer
        file and set nothing else. The message has to say why that is not enough."""
        with pytest.raises(BuildError) as err:
            contact.mode({"supportEmail": "it@example.com", "supportUrl": "https://t.example.com/"})
        assert "_defaults.json" in str(err.value)

    def test_neither_set_is_an_error(self):
        with pytest.raises(BuildError) as err:
            contact.mode({})
        assert "supportEmail" in str(err.value)

    def test_empty_string_counts_as_unset(self):
        """JSON has no comments, so blanking a value is how a key is turned off."""
        assert contact.mode({"supportEmail": "it@example.com", "supportUrl": ""}) == contact.EMAIL
        assert contact.mode({"supportEmail": "", "supportUrl": "https://t.example.com/"}) == contact.URL


@pytest.mark.unit
class TestCheck(unittest.TestCase):
    def test_https_url_passes(self):
        contact.check({"supportEmail": "", "supportUrl": "https://tickets.example.com/new"})

    def test_http_url_is_refused(self):
        with pytest.raises(BuildError) as err:
            contact.check({"supportEmail": "", "supportUrl": "http://tickets.example.com/new"})
        assert "https://" in str(err.value)

    def test_relative_url_is_refused(self):
        """The page is served AS the blocked site, so a relative path resolves there."""
        with pytest.raises(BuildError) as err:
            contact.check({"supportEmail": "", "supportUrl": "/servicedesk/new"})
        assert "https://" in str(err.value)

    def test_email_mode_needs_an_at_sign(self):
        with pytest.raises(BuildError) as err:
            contact.check({"supportEmail": "servicedesk"})
        assert "supportEmail" in str(err.value)


@pytest.mark.unit
class TestValues(unittest.TestCase):
    EMAIL_CFG: ClassVar = {"supportEmail": "it@example.com"}
    URL_CFG: ClassVar = {"supportEmail": "", "supportUrl": "https://tickets.example.com/new"}

    def test_href_is_the_page_mailto_in_email_mode(self):
        assert contact.href(self.EMAIL_CFG, "mailto:it@example.com?subject=X") == "mailto:it@example.com?subject=X"

    def test_href_is_the_url_in_url_mode(self):
        assert contact.href(self.URL_CFG, "mailto:ignored") == "https://tickets.example.com/new"

    def test_name_is_the_address_in_email_mode(self):
        assert contact.name(self.EMAIL_CFG) == "it@example.com"

    def test_name_falls_back_to_a_default_label_in_url_mode(self):
        assert contact.name(self.URL_CFG) == "IT support"

    def test_name_uses_the_configured_label_in_url_mode(self):
        cfg = {**self.URL_CFG, "supportLabel": "the Service Desk"}
        assert contact.name(cfg) == "the Service Desk"

    def test_a_blank_label_falls_back_to_the_default(self):
        """Blanking a key is how this project turns one off, so a blank label
        must mean "unset" rather than an anchor with no text."""
        cfg = {**self.URL_CFG, "supportLabel": "   "}
        assert contact.name(cfg) == "IT support"

    def test_the_label_is_ignored_in_email_mode(self):
        """Email mode prints the address, which is its own label."""
        cfg = {**self.EMAIL_CFG, "supportLabel": "the Service Desk"}
        assert contact.name(cfg) == "it@example.com"

    def test_data_to_attribute_only_exists_in_email_mode(self):
        assert contact.to_attr(self.EMAIL_CFG) == ' data-to="it@example.com"'
        assert contact.to_attr(self.URL_CFG) == ""

    def test_email_is_empty_in_url_mode(self):
        assert contact.email(self.URL_CFG) == ""


@pytest.mark.integration
class TestBuildRefusesBadConfig(unittest.TestCase):
    def test_both_keys_fails_the_build(self):
        cfg = shipped(supportUrl="https://tickets.example.com/new")
        with pytest.raises(BuildError) as err:
            build_page("url-block-page", THEMES[0], cfg, PALETTE, False, TEMPLATES)
        assert "mutually exclusive" in str(err.value)

    def test_http_url_fails_the_build(self):
        cfg = shipped(supportEmail="", supportUrl="http://tickets.example.com/new")
        with pytest.raises(BuildError) as err:
            build_page("url-block-page", THEMES[0], cfg, PALETTE, False, TEMPLATES)
        assert "https://" in str(err.value)

    def test_missing_both_fails_with_a_sentence_not_a_keyerror(self):
        cfg = shipped(supportEmail="")
        with pytest.raises(BuildError):
            build_page("url-block-page", THEMES[0], cfg, PALETTE, False, TEMPLATES)


@pytest.mark.integration
class TestRuntimeRewrite(unittest.TestCase):
    def test_email_mode_still_rebuilds_the_href(self):
        """The rebuild is what folds the fact table into the mail body."""
        assert "a.href='mailto:'" in render(shipped())

    def test_url_mode_does_not_rebuild_the_href(self):
        html = render(shipped(**URL_CFG_KEYS))
        assert "a.href=" not in html
        assert "getElementById('rep')" not in html

    def test_url_mode_still_fills_the_timestamp(self):
        """The rep block shares an IIFE with the clock; dropping one must not
        drop the other."""
        assert "getElementById('ts')" in render(shipped(**URL_CFG_KEYS))

    def test_url_mode_still_resolves_the_category(self):
        assert "getElementById('cat')" in render(shipped(**URL_CFG_KEYS))
