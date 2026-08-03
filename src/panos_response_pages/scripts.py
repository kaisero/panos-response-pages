"""The JavaScript emitted into every page.

PAN-OS exposes no severity variable and serves one page per type, so
per-category messaging can only happen in the browser.
"""

from __future__ import annotations

import json
from collections.abc import Mapping

from panos_response_pages.errors import BuildError

# Spelled out rather than abbreviated: "calm" and "critical" share a first letter,
# and collapsing them to one char silently rendered every critical page as calm.
TONE_CSS = {"calm": "calm", "warn": "warn", "critical": "crit"}

# Claims a response page cannot substantiate. PAN-OS gives the page no visibility

# into {{SEVERITY}} and the runtime lookup emitted into category_js -- the two must
# agree, or a page whose tone changes at runtime shows a stale label.
SEV_LABEL = {"calm": "", "warn": "Caution", "crit": "Security risk"}

# Slug words that must not be title-cased into the friendly category label.
# Acronyms map to their own casing; joining words to lowercase. Emitted as a JS
# object literal with bare keys, so every entry costs its own length and no more
# -- this table ships on four pages of every theme.
#
# Only the words the 90 PAN-OS categories actually contain. A word that is
# missing degrades to plain title case ("Ai Code Assistant"), which is wrong but
# not broken, so this is worth keeping to the observed set rather than padding
# it with joining words no category uses.
#
# Applied without an index guard, so a category whose FIRST word is one of the
# lowercase entries would render lowercase ("to-do-lists" -> "to Do Lists").
# None of the 90 starts with one, and the guard costs bytes on every page.
LABEL_WORDS = {"ai": "AI", "dns": "DNS", "ip": "IP", "and": "and", "to": "to"}

# Where the raw PAN-OS category name is parked once the Category row has been
# rewritten to a friendly label. The label is for the reader; anything that has
# to MATCH the category -- today the redirect table -- reads this instead.
#
# A shared constant rather than a literal at each end because the two ends are
# in different modules and the failure when they disagree is silent: the
# redirect notice ships `hidden` and just never un-hides.
CATEGORY_KEY_ATTR = "data-c"


def category_js(
    categories: Mapping[str, Mapping[str, str]],
    default_gloss: str,
    risk_gloss: str,
    lock_copy: bool,
    *,
    has_category: bool,
    email_mode: bool,
) -> str:
    """Compact category -> [tone, gloss] map plus the client-side selector.

    PAN-OS exposes no severity or reason variable and serves one page per type,
    so per-category messaging can only happen in the browser.

    An entry with an empty gloss falls back to `default_gloss`, or to
    `risk_gloss` when its tone is not calm. That is what lets a category be
    listed for its TONE alone: spelling the generic sentence out per category
    costs ~46 B each, and repeating it across the categories that need no
    tailored copy would not fit under the byte ceiling.

    lock_copy pins BOTH the tone and the gloss to what the page template declares.
    The credential pages use it: a phishing interstitial must not be repainted calm
    because of how its category maps, and its tailored copy ("this page asked for
    your password") is more useful than the generic category sentence.

    has_category says the page renders an id="cat" row. It is not the inverse of
    lock_copy: a copy-locked page still shows the category, and still wants it
    spelled as a friendly label rather than a raw slug.

    email_mode drops the mailto rebuild entirely. It is not a size optimisation:
    the rebuild assigns a.href unconditionally, so leaving it in would overwrite
    a configured ticket URL the moment the page finished loading.
    """
    for name, v in categories.items():
        if v["tone"] not in TONE_CSS:
            raise BuildError(f"category '{name}' has tone '{v['tone']}'; expected one of {', '.join(TONE_CSS)}")

    compact = {k: [TONE_CSS[v["tone"]], v["gloss"]] for k, v in categories.items()}
    # The tone/gloss half. Omitted when the page pins its own copy, and when
    # there is no category row to read the key off in the first place.
    tone_gloss = (
        ""
        if lock_copy
        else (
            "var g=document.getElementById('gloss'),m=M[k],d="
            + json.dumps(default_gloss)
            + ";"
            + "if(m){document.documentElement.setAttribute('data-tone',m[0]);"
            "var v=document.querySelector('.sev');"
            "if(v)v.textContent=" + json.dumps(SEV_LABEL, separators=(",", ":")) + "[m[0]]||'';"
            # An empty gloss means "no tailored copy": fall back to the generic
            # sentence, but not to the calm one on a warn/crit category -- the
            # banner would read "Security risk" over "restricted by policy".
            "if(g)g.textContent=m[1]||(m[0]=='calm'?d:" + json.dumps(risk_gloss) + ");}"
            "else if(g)g.textContent=d;"
        )
    )
    # The friendly label: "online-storage-and-backup" -> "Online Storage and
    # Backup". Derived rather than mapped because an explicit label for all 90
    # categories is ~3.3 KB of JSON against ~0.2 KB of code, and derivation also
    # covers whatever PAN-OS adds after this build.
    #
    # data-c FIRST, and it is not optional. This rewrite destroys the only copy
    # of the PAN-OS category name on the page, and the redirect script -- which
    # runs after this one, because it needs the tone this one resolves -- keys
    # its own table on that name. Without the attribute it looks up "Online
    # Storage and Backup", misses, and silently never arms: the notice ships
    # `hidden` and simply stays hidden. See CATEGORY_KEY_ATTR.
    label = (
        f"e.setAttribute('{CATEGORY_KEY_ATTR}',k);"
        "var A={" + ",".join(f"{k}:'{v}'" for k, v in LABEL_WORDS.items()) + "};"
        "e.textContent=k.split('-').map(function(w){"
        "return A[w]||w.charAt(0).toUpperCase()+w.slice(1)}).join(' ');"
    )
    # Guarded rather than early-returning: pages without a category token
    # (safe-search) still need their timestamp filled in below.
    lookup = (
        (
            "var e=document.getElementById('cat');"
            "if(e){var k=(e.textContent||'').trim().toLowerCase();" + tone_gloss + label + "}"
        )
        if has_category
        else ""
    )
    # The mailto rebuild, and only in email mode. It exists to fold the page's
    # own fact table into the mail body, which is something an href cannot carry.
    report = (
        (
            "var a=document.getElementById('rep');"
            "if(a){var p=[];"
            "[].forEach.call(document.querySelectorAll('dl .f'),function(f){"
            "var k=f.querySelector('dt'),v=f.querySelector('dd');"
            "if(k&&v&&v.textContent.trim())p.push(k.textContent.trim()+': '+v.textContent.trim());});"
            "a.href='mailto:'+a.getAttribute('data-to')"
            "+'?subject='+encodeURIComponent(a.getAttribute('data-subject'))"
            "+'&body='+encodeURIComponent(a.getAttribute('data-intro')+'\\n\\n'"
            "+p.join('\\n')+'\\n\\n'+a.getAttribute('data-prompt')+'\\n');}"
        )
        if email_mode
        else ""
    )
    return (
        "<script>(function(){"
        + ("var M=" + json.dumps(compact, separators=(",", ":")) + ";" if has_category and not lock_copy else "")
        + lookup
        + "var t=document.getElementById('ts');"
        "if(t)t.textContent=new Date().toLocaleString();" + report + "})();</script>"
    )


FRAME_BUSTER = "<script>if(top!=window){top.location.replace(window.location.href)}</script>"
