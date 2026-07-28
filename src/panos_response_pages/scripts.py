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


def category_js(categories: Mapping[str, Mapping[str, str]], default_gloss: str, lock_copy: bool) -> str:
    """Compact category -> [tone, gloss] map plus the client-side selector.

    PAN-OS exposes no severity or reason variable and serves one page per type,
    so per-category messaging can only happen in the browser.

    lock_copy pins BOTH the tone and the gloss to what the page template declares.
    The credential pages use it: a phishing interstitial must not be repainted calm
    because of how its category maps, and its tailored copy ("this page asked for
    your password") is more useful than the generic category sentence.
    """
    for name, v in categories.items():
        if v["tone"] not in TONE_CSS:
            raise BuildError(f"category '{name}' has tone '{v['tone']}'; expected one of {', '.join(TONE_CSS)}")

    compact = {k: [TONE_CSS[v["tone"]], v["gloss"]] for k, v in categories.items()}
    # A copy-locked page still needs its timestamp and reference filled in, so
    # only the category-driven tone/gloss block is omitted.
    lookup = (
        ""
        if lock_copy
        else (
            "var e=document.getElementById('cat'),g=document.getElementById('gloss');"
            # Guarded rather than early-returning: pages without a category token
            # (safe-search) still need their timestamp filled in below.
            "if(e){var k=(e.textContent||'').trim().toLowerCase(),m=M[k];"
            "if(m){document.documentElement.setAttribute('data-tone',m[0]);"
            "var v=document.querySelector('.sev');"
            "if(v)v.textContent=" + json.dumps(SEV_LABEL) + "[m[0]]||'';"
            "if(g)g.textContent=m[1];}"
            "else if(g)g.textContent=" + json.dumps(default_gloss) + ";}"
        )
    )
    return (
        "<script>(function(){"
        + ("" if lock_copy else "var M=" + json.dumps(compact, separators=(",", ":")) + ";")
        + lookup
        + "var t=document.getElementById('ts');"
        "if(t)t.textContent=new Date().toLocaleString();"
        "var a=document.getElementById('rep');"
        "if(a){var p=[];"
        "[].forEach.call(document.querySelectorAll('dl .f'),function(f){"
        "var k=f.querySelector('dt'),v=f.querySelector('dd');"
        "if(k&&v&&v.textContent.trim())p.push(k.textContent.trim()+': '+v.textContent.trim());});"
        "a.href='mailto:'+a.getAttribute('data-to')"
        "+'?subject='+encodeURIComponent(a.getAttribute('data-subject'))"
        "+'&body='+encodeURIComponent(a.getAttribute('data-intro')+'\\n\\n'"
        "+p.join('\\n')+'\\n\\n'+a.getAttribute('data-prompt')+'\\n');}"
        "})();</script>"
    )


FRAME_BUSTER = "<script>if(top!=window){top.location.replace(window.location.href)}</script>"
