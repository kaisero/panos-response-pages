"""Assembling one page from a shell, a page template, a config and a palette."""

from __future__ import annotations

import pathlib
import re
from collections.abc import Mapping
from typing import Any

from panos_response_pages import contact, i18n, redirect
from panos_response_pages.errors import BuildError
from panos_response_pages.scripts import FRAME_BUSTER, category_js
from panos_response_pages.templates import assert_resolved, parse_sections, read, substitute
from panos_response_pages.validate import TOKEN_RE

# The shell's `html[data-force-scheme=light|dark]` blocks, which exist so the
# preview gallery can show a page in the scheme the reviewer is not currently in.
#
# PREVIEW ONLY, and worth 519-603 B on every page of every theme. The attribute
# is written in exactly one place in this project -- the gallery's own script,
# on the preview iframe's document -- so on a firewall these blocks are 4 KB of
# stylesheet per theme that nothing can ever select. They stay in the shell
# SOURCE, where the suite reads them and holds their token sets in step with
# :root; they are dropped on the way into a deploy build.
SCHEME_RE = re.compile(r"<!--@SCHEME-->\n?(.*?)<!--/@SCHEME-->\n?", re.S)

# Sample values used only in preview builds.
# A mailto that is actually a link, as opposed to the word appearing in prose.
MAILTO_HREF = re.compile(r"""href\s*=\s*["']\s*mailto:""", re.I)

SAMPLE = {
    "user": "ACME\\jdoe",
    "url": "https://example.com/promo/spring-sale?ref=email&id=88213",
    "category": "command-and-control",
    "ssurl": "https://www.bing.com/account/general",
    "pan_form": ('<form method="post" action="#"><input type="submit" value="Continue"></form>'),
    "fname": "Q4-forecast-final.xlsm",
    "appname": "bittorrent",
    # <cookie/> is the File Blocking Continue mechanism: PAN-OS injects markup
    # that sets a cookie and reloads to resume the download.
    "cookie": ('<form method="post" action="#"><input type="submit" value="Continue"></form>'),
    # <direction/> is the transfer direction on the data filtering page. The
    # shipped PAN-OS default uses it sentence-initially, so a capitalised word is
    # expected -- unverified on a live firewall.
    "direction": "Upload",
    # The SSL certificate status page. Shaped like real PAN-OS output: certname
    # and issuer are DNs, status and reason are its own short verdicts. The
    # issuer is deliberately long -- it is the value most likely to overflow a
    # fact cell, and the preview is where that has to show.
    "certname": "*.example.com",
    "issuer": "CN=Example Intermediate CA, O=Example Corp, C=US",
    "status": "untrusted-issuer",
    "reason": "The issuing certificate authority is not in the trusted store",
}

# Sample overrides for pages where a token does not render what it renders
# elsewhere. Preview-only, like SAMPLE itself.
#
# <url/> is the case this exists for: it is one token, but on the decryption path
# PAN-OS substitutes the destination IP rather than a URL -- which is why the
# shipped ssl-cert-status-page default labels that row "IP:". Left on the shared
# sample, the gallery would show a long URL in a row that will hold an address,
# and the gallery's whole job is judging whether a row fits. RFC 5737
# documentation address, so the preview never points at a real host.
PAGE_SAMPLE = {
    "ssl-cert-status-page": {"url": "192.0.2.24"},
}


def build_page(
    page: str,
    theme: Mapping[str, Any],
    cfg: Mapping[str, Any],
    palette: Mapping[str, Any],
    preview: bool,
    template_dir: pathlib.Path,
    redirect_demo: bool = False,
) -> str:
    shell = read(template_dir / "shells" / f"{theme['shell']}.html")
    # Kept whole for the gallery, dropped for the firewall. Either way the
    # markers themselves go: strip_output would remove them later as HTML
    # comments, but only after validate() had already measured them.
    shell = SCHEME_RE.sub((lambda m: m.group(1)) if preview else "", shell)
    parts = parse_sections(read(template_dir / "pages" / f"{page}.html"))

    for required in ("TITLE", "HEADLINE", "GLOSS", "FACTS", "ACTIONS"):
        if required not in parts:
            raise BuildError(f"{page}.html is missing its <!--@{required}--> section")

    # Page sections may themselves contain {{COMPANY}} / {{SUPPORT_EMAIL}}, so they
    # must be resolved BEFORE being inserted into the shell -- re.sub does not
    # rescan replacement text, which would otherwise emit a literal
    # "mailto:{{SUPPORT_EMAIL}}" into every page.
    # Refused here rather than at first use: a contradictory contact config
    # otherwise surfaces as a KeyError from inside substitution, naming a
    # template token instead of the config key the author got wrong.
    contact.check(cfg)
    # The base language is written into the markup as real text. Resolved before
    # the sections are substituted, because a translated string may itself carry
    # {{COMPANY}} or {{CONTINUE_GRANT}} -- re.sub does not rescan replacement
    # text, so a value inserted in a later pass would ship as literal braces.
    strings = i18n.load(i18n.base_language(cfg), template_dir.parent)
    base = {
        "COMPANY": cfg["company"],
        # Empty in URL mode. The token still has to resolve: it appears in
        # sections URL mode discards, and substitute() raises on an unknown key
        # whether or not the text survives.
        "SUPPORT_EMAIL": contact.email(cfg),
        "LOGO_SVG": cfg["logoSvg"],
        # The Continue/Override grant duration is administrator-configurable per
        # firewall (PAN-OS only defaults to 15 minutes), so the page must not
        # hardcode it -- that would assert a fact it cannot know.
        "CONTINUE_GRANT": cfg["continueGrantText"],
        "WARN_MARK": cfg["marks"]["warning"],
        "INFO_MARK": cfg["marks"]["info"],
    }
    # Copy is resolved against the values above, not alongside them: a
    # placeholder inside a translated string has to be substituted BEFORE that
    # string becomes a replacement, because re.sub will not rescan it.
    #
    # Unconditional: a page with no entry in the strings document has no copy at
    # all, and page_values says which page rather than letting the build fail
    # later as an unresolved {{T_TITLE}} that names a token instead.
    base.update(i18n.page_values(strings, page, base))
    # The two contact sections are resolved first and on their own: they carry
    # {{SUPPORT_EMAIL}} and nothing else, and their results ARE the values the
    # {{CONTACT_*}} tokens in ACTIONS and EXTRA resolve to. Folding them into
    # `base` keeps this to one pass over the sections -- and one pass is not a
    # nicety. substitute() raises on any key it does not recognise, so a section
    # containing {{CONTACT_HREF}} cannot be run through a dict that lacks it.
    # In email mode CONTACT_MAILTO section IS the href; a template that omits it
    # would otherwise build clean and ship an anchor that reloads the blocked
    # site. In URL mode the section is genuinely unused, so absence there is
    # fine -- the check only runs where the value is actually needed.
    if "CONTACT_MAILTO" not in parts and contact.mode(cfg) == contact.EMAIL:
        raise BuildError(f"{page}.html is missing its <!--@CONTACT_MAILTO--> section, needed in email mode")
    mailto = substitute(parts.pop("CONTACT_MAILTO", ""), base)
    alt = substitute(parts.pop("CONTACT_ALT", ""), base)
    base.update(
        {
            "CONTACT_HREF": contact.href(cfg, mailto),
            "CONTACT_TO": contact.to_attr(cfg),
            "CONTACT_ALT": alt if contact.mode(cfg) == contact.EMAIL else "",
            "CONTACT_NAME": contact.name(cfg),
        }
    )
    parts = {k: substitute(v, base) for k, v in parts.items()}

    # The gallery's Redirect toggle, which shows the handoff on a config that has
    # not enabled it yet. Preview-only and asserted so: `redirect_demo` reaching a
    # deploy build would ship a countdown that loops instead of handing over.
    demo = redirect_demo and page == redirect.PAGE and redirect.supported(theme)
    if demo and not preview:
        raise BuildError("redirect_demo is a preview-only build; it must never reach deploy/")
    # Everything downstream reads the demo config, not just the redirect: the
    # category the notice keys on needs a tone and a gloss from the same map, or
    # the page renders a redirect for a category it cannot describe.
    eff = redirect.demo_config(cfg) if demo else cfg

    # Three empty strings unless this is the URL block page, the style declares
    # room for the notice, and a customer opted in -- so every other page, every
    # style without it, and every build with the feature off is byte-identical to
    # one from before it existed.
    redirect_css, redirect_html, redirect_js = redirect.emit(eff, page, theme, loop=demo)

    # One read, two uses: the static tone and the label derived from it must not
    # be able to disagree about what the template declared.
    tone = parts.get("TONE", "calm")

    # The severity labels are `shared` copy like every other string in the file,
    # so they get the same treatment: resolved against the fully-populated
    # `base`, once, and used resolved at both sites below. Skipping this would
    # not fail loudly -- a label reaches the page as a {{SEVERITY}} replacement
    # and as JSON handed to textContent, and re.sub does not rescan replacement
    # text, so a `{{COMPANY}}` written into a severity label would ship to a
    # user as literal braces with a clean build behind it. Today's three labels
    # carry no placeholder, which is exactly why the asymmetry has to be closed
    # here rather than relied upon to surface later.
    severity = i18n.resolve(strings["shared"]["severity"], base)

    values = dict(base)
    values.update(
        {
            "TITLE": parts["TITLE"],
            "HEADLINE": parts["HEADLINE"],
            "GLOSS": parts["GLOSS"],
            "FACTS": parts["FACTS"],
            "ACTIONS": parts["ACTIONS"],
            "EXTRA": parts.get("EXTRA", ""),
            "TONE": tone,
            "SEVERITY": severity.get(tone, ""),
            "MARK": parts.get("MARK", cfg["marks"]["shield"]),
            "REDIRECT_CSS": redirect_css,
            "REDIRECT": redirect_html,
            # The frame-buster is correct on a live page -- a response page rendered
            # inside a third-party iframe is a broken state. But it must not ship in
            # preview builds, or every gallery iframe would replace the gallery itself.
            # Emit the category map only where it can actually be used: a page that
            # declares no id="cat" (safe-search has no <category/> token) would carry
            # ~1.7 KB of dead JSON.
            # The redirect script runs LAST: it reads the tone the category
            # lookup resolved, and a calm-only guard against an attribute that
            # has not been set yet would arm on every page.
            "SCRIPTS": ("" if preview else FRAME_BUSTER)
            + category_js(
                eff["categories"],
                eff["defaultGloss"],
                eff["riskGloss"],
                lock_copy=parts.get("COPY_LOCK", "").strip() == "1",
                severity=severity,
                has_category='id="cat"' in parts["FACTS"],
                email_mode=contact.mode(cfg) == contact.EMAIL,
            )
            + redirect_js,
        }
    )
    values.update({f"C_{k.upper()}": v for k, v in palette["colors"].items()})
    # Gradients are linear and run the 500 stop to the 1000 stop.
    # Radial variants and mixed hues are not used, so only these two
    # stops and one angle are exposed.
    grad = palette.get("gradient", {})
    values.update(
        {
            "C_GRAD_FROM": grad.get("from", palette["colors"]["accent"]),
            "C_GRAD_TO": grad.get("to", palette["colors"]["accent"]),
            "C_GRAD_ANGLE": grad.get("angle", "135deg"),
        }
    )

    out: str = substitute(shell, values)
    assert_resolved(out, page)

    # URL mode is otherwise enforced only by the templates cooperating: a stale
    # template directory would still substitute cleanly and ship a mailto href
    # with the rebuild script stripped out from under it -- a silently broken
    # contact, no error. This is the loud failure that promise depends on.
    #
    # Matched as an href rather than as a bare substring. Half this page is
    # customer-authored free text -- gloss, category descriptions,
    # continueGrantText -- and a config whose prose happens to mention "mailto:"
    # would otherwise fail a build whose contact link was perfectly correct.
    # Refusing right output over unrelated copy is a worse failure than the
    # silent one this exists to catch.
    if contact.mode(cfg) == contact.URL and MAILTO_HREF.search(out):
        raise BuildError(f"{page} contains a mailto: link in URL mode; its template is out of date with cfg")

    if preview:
        sample = {**SAMPLE, **PAGE_SAMPLE.get(page, {})}
        if demo:
            # The sample category is command-and-control, which is critical, and
            # the redirect refuses a category that is not calm. Standing in the
            # mapped one is what arms the notice -- and it is honest about it:
            # this is the page a user hitting that category actually gets, gloss
            # and tone included, not the usual sample with a banner bolted on.
            sample["category"] = redirect.demo_category(eff)
        out = TOKEN_RE.sub(lambda m: sample[m.group(1)], out)

    return out
