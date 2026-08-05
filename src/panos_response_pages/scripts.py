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

# Where a PREVIEW build parks the language swap so the gallery can call it.
#
# Language is not CSS. The gallery sets `data-force-scheme` on the iframe's
# document after `load` and the page restyles, because a scheme is an attribute
# a stylesheet selects on. By `load` the runtime has already picked a language
# and rewritten the text, so no attribute can re-drive it -- the apply half has
# to be reachable from outside the closure that ran it.
#
# Long and prefixed on purpose: this lands on `window` of a page whose markup
# this project only half owns (PAN-OS injects <pan_form/> and <cookie/>), so the
# name has to be one nothing else could plausibly have taken.
#
# PREVIEW ONLY. build_page refuses the preview language list on a deploy build,
# which is what keeps this name off every page a firewall serves.
PREVIEW_SWAP = "__panosResponsePagesSetLanguage"


def category_js(
    categories: Mapping[str, Mapping[str, str]],
    default_gloss: str,
    risk_gloss: str,
    lock_copy: bool,
    *,
    severity: Mapping[str, str],
    has_category: bool,
    email_mode: bool,
    lang_dict: str = "",
    base_lang: str = "en",
    swap_global: str = "",
) -> str:
    """Compact category -> [tone, gloss] map plus the client-side selector.

    PAN-OS exposes no severity or reason variable and serves one page per type,
    so per-category messaging can only happen in the browser.

    An entry with an empty gloss falls back to `default_gloss`, or to
    `risk_gloss` when its tone is not calm. That is what lets a category be
    listed for its TONE alone: spelling the generic sentence out per category
    costs ~46 B each, and repeating it across the categories that need no
    tailored copy would not fit under the byte ceiling.

    severity is the tone -> label map, keyed by CSS tone. It is copy, so it
    comes from the strings document rather than a constant here: a page built in
    German must not have "Caution" compiled into its script. The same map fills
    the static {{SEVERITY}} slot -- PAN-OS gives the page no visibility into the
    tone, so the two must agree, or a page whose tone changes at runtime shows a
    stale label.

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

    lang_dict is the JSON runtime dictionary from i18n.runtime_dict(), or the
    empty string in a single-language build. Empty is not merely a size
    optimisation either: `t` is not declared at all without it, so every
    expression below that consults the selected language has to keep its
    pre-existing form or become a ReferenceError on every page.

    swap_global names the window property a PREVIEW build parks the apply half
    of the swap on, so the gallery can drive it from outside after `load`. Empty
    on every deploy build, and the emitted bytes are then exactly what they were
    before the gallery could ask -- which is what tests/_build.py's golden
    LANGUAGE_BLOCK pins. See PREVIEW_SWAP.
    """
    for name, v in categories.items():
        if v["tone"] not in TONE_CSS:
            raise BuildError(f"category '{name}' has tone '{v['tone']}'; expected one of {', '.join(TONE_CSS)}")

    compact = {k: [TONE_CSS[v["tone"]], v["gloss"]] for k, v in categories.items()}
    sev_map = json.dumps(severity, separators=(",", ":"))
    risk = json.dumps(risk_gloss)
    # The tone/gloss half. Omitted when the page pins its own copy, and when
    # there is no category row to read the key off in the first place.
    #
    # Every language-aware branch below is emitted ONLY when there is a
    # dictionary. In a single-language build this string has to be the bytes it
    # was before multi-language support existed -- that promise is asserted, and
    # `t` does not exist to be consulted anyway.
    tone_gloss = (
        ""
        if lock_copy
        else (
            "var g=document.getElementById('gloss'),m=M[k],d="
            + json.dumps(default_gloss)
            # The two generic fallbacks are rebound once rather than tested at
            # each of their three use sites: same result, fewer bytes on the two
            # pages that carry this block.
            + ((",r=" + risk + ";if(t){d=t.dg;r=t.rg}") if lang_dict else ";")
            + "if(m){document.documentElement.setAttribute('data-tone',m[0]);"
            # BLOCKER: this runs AFTER the language swap and re-sets .sev, so a
            # baked-in base-language map silently reverts the pill to English the
            # moment a category resolves -- on url-block-page and url-coach-text,
            # the only category-bearing pages without COPY_LOCK.
            "var v=document.querySelector('.sev');"
            "if(v)v.textContent="
            + (("(t?t.s:" + sev_map + ")") if lang_dict else sev_map)
            + "[m[0]]||'';"
            # An empty gloss means "no tailored copy": fall back to the generic
            # sentence, but not to the calm one on a warn/crit category -- the
            # banner would read "Security risk" over "restricted by policy".
            #
            # A per-category gloss is base-language text, so a selected language
            # may only use its own `c` block -- absent (the block is optional),
            # it takes the translated generic sentence for the category's tone
            # rather than showing one English sentence inside a German page.
            + (
                "if(g)g.textContent=(t?t.c&&t.c[k]:m[1])||(m[0]=='calm'?d:r);}"
                if lang_dict
                else "if(g)g.textContent=m[1]||(m[0]=='calm'?d:" + risk + ");}"
            )
            + "else if(g)g.textContent=d;"
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
    # Language selection. First, because everything after it reads the words it
    # chose: the category lookup rewrites the gloss, the timestamp formats to a
    # locale, and the mail rebuild folds the rendered rows into a body.
    #
    # The base language is absent from the dictionary -- it is the markup. A
    # browser whose languages do not match leaves the page exactly as served,
    # which is the only failure mode: never blank, never half-swapped.
    #
    # The base language also STOPS the search. A browser that ranks it above a
    # compiled language must keep the page it was served, or a user who prefers
    # English with German second would be handed German.
    #
    # Split into a SELECT half and an APPLY half. The split is what the preview
    # gallery needs: it can only reach the page after `load`, by which time the
    # select half has already run and settled on the served language, so the
    # apply half has to be callable a second time with a different one. On a
    # deploy build the two are concatenated back into the single `if(t){...}`
    # they have always been, byte for byte.
    select = (
        (
            "var T=" + lang_dict + ",LS=navigator.languages||[navigator.language||''],t,lk,i;"
            "for(i=0;i<LS.length;i++){lk=LS[i].slice(0,2).toLowerCase();"
            "if(lk==" + json.dumps(base_lang) + ")break;if(T[lk]){t=T[lk];break}}"
        )
        if lang_dict
        else ""
    )
    apply_lang = (
        (
            "var Q=function(s){return document.querySelector(s)};"
            # A sentence one child element splits in two: text, element, text.
            # The outer halves are always copy. The middle is copy only when the
            # caller passes `c`: .plain and .note wrap a build-time anchor
            # holding a configured address or name, which must be left exactly
            # as served, while url-coach's info box wraps a <strong> whose text
            # is the emphasised phrase itself. Returns truthy when it found the
            # three-node shape, so a caller can tell which shape it has.
            "var S=function(e,a,b,c){if(e&&e.childNodes.length>2){"
            "e.childNodes[0].nodeValue=a;e.childNodes[2].nodeValue=b;"
            "if(c!=null)e.childNodes[1].textContent=c;return 1}};"
            "document.documentElement.lang=lk;document.title=t.t;"
            "var H=Q('h1');if(H)H.textContent=t.h;"
            "var G0=Q('#gloss');if(G0)G0.textContent=t.g;"
            # Positional against `dl dt` in document order -- the same contract
            # the numbered {{T_FACT*}} placeholders are built on.
            "[].forEach.call(document.querySelectorAll('dl dt'),function(e,i){if(t.f[i])e.textContent=t.f[i]});"
            # The one element on the page whose text is a label. On ten pages it
            # IS #rep and its text is the report label; on safe-search it is the
            # settings link, which is why that page -- and only that page --
            # compiles an a2. Scoped to the button deliberately: safe-search's
            # #rep is an inline anchor inside a sentence whose text is the
            # configured contact name, and writing the report label into it
            # turns "Contact <address>" into "Contact Report to IT".
            #
            # The report button FIRST, and only then any a.btn. querySelector
            # returns the first match in document order, and three pages carry a
            # PAN-OS token -- <pan_form/> on the two coach pages, <cookie/> on
            # file-block-continue -- that the firewall expands into markup of
            # its own BEFORE the report anchor. Whether that markup contains an
            # a.btn cannot be established from this repository, so the bare
            # selector made the label's destination depend on serve-time
            # injection: on the very pages this feature exists for, the report
            # label could be written into PAN-OS's own Continue control. #rep is
            # ours and the firewall never injects it, so preferring it costs 14
            # bytes and removes the question. The fallback is what still finds
            # safe-search's settings link, which has no id.
            "var B=Q('a.btn#rep')||Q('a.btn');if(B)B.textContent=t.a2||t.rl;"
            # The three data-* fields the mailto rebuild below reads to compose
            # the body. They ARE copy, on every page that has a #rep at all --
            # safe-search's inline anchor included.
            "var R=Q('#rep');if(R){R.setAttribute('data-subject',t.rs);"
            "R.setAttribute('data-intro',t.ri);R.setAttribute('data-prompt',t.rp)}"
            "S(Q('.plain'),t.ca[0],t.ca[1]);"
            # `extra` is a string when the slot is one run of prose and a list
            # when the template interrupts it with markup. Assigned whole to
            # textContent a list stringifies, rendering the fragments
            # comma-joined into the callout and never swapping the rest.
            #
            # Which three nodes the fragments belong to is read off the callout
            # itself, never off the page name. If the callout span is already
            # the three-node shape it IS the split sentence -- url-coach wraps
            # its middle phrase in a <strong>, and the three fragments are that
            # span's own text, the <strong>'s text, and the tail -- so it is
            # filled in place and left alone below. Otherwise the callout holds
            # one run of prose (fragment 0) and the split sentence is the .note
            # beneath it, where fragments 1 and 2 straddle the contact anchor.
            "var X=Q('.infobox span,.warnline span'),x=t.x||'';"
            "if(x.pop){if(S(X,x[0],x[2],x[1]))X=0;else S(Q('.note'),x[1],x[2]);x=x[0]}"
            "if(X&&x)X.textContent=x;"
            # The static pill. Only swapped when it says something: a calm page
            # carries an empty one, and writing a label into it would invent a
            # severity the page never declared. The category lookup re-sets this
            # from t.s as well, for the pages where a category can change it.
            "var V=Q('.sev');if(V&&V.textContent)"
            "V.textContent=t.s[document.documentElement.getAttribute('data-tone')]||V.textContent;"
        )
        if lang_dict
        else ""
    )
    # Deploy: the two halves, joined exactly as they always were.
    #
    # Preview: the apply half becomes a function the gallery can call again with
    # a language the browser never asked for. `t` and `lk` are the same closure
    # variables either way, so the second call goes through the identical code
    # the first one did -- there is no preview-only copy of the swap to drift.
    #
    # The category gloss has to be resolved again, because the lookup that owns
    # it ran at load and cannot run twice -- it destroys the raw category name it
    # reads (see CATEGORY_KEY_ATTR). Without this the swap puts the page's own
    # gloss back over the category's, and the preview shows a generic sentence
    # where the served German page shows the tailored one: the exact difference a
    # reviewer opened the gallery to judge.
    #
    # The same expression the lookup emits, with `t` known truthy. It reads
    # `k`, `m` and `g`, which the lookup declares with `var` inside `if(e){...}`
    # -- function-scoped, so they are in scope here and simply undefined on a
    # page with no category row. Emitted only where the lookup declares them at
    # all: a copy-locked page pins its gloss on purpose and has no `m` to read.
    regloss = (
        "if(g)g.textContent=m?((t.c&&t.c[k])||(m[0]=='calm'?t.dg:t.rg)):t.dg;" if has_category and not lock_copy else ""
    )
    lang = (
        (
            "var AP=function(){" + apply_lang + "};if(t)AP();"
            "window." + swap_global + "=function(L){if(!T[L])return;t=T[L];lk=L;AP();" + regloss + "};"
            if swap_global
            else "if(t){" + apply_lang + "}"
        )
        if lang_dict
        else ""
    )
    # The timestamp. In a multi-language build it formats to whatever language
    # was selected; in a single-language build it keeps its exact previous form,
    # variable name included, because those bytes are asserted.
    ts = (
        (
            "var ts=document.getElementById('ts');"
            "if(ts)ts.textContent=new Date().toLocaleString(document.documentElement.lang||undefined);"
        )
        if lang_dict
        else ("var t=document.getElementById('ts');if(t)t.textContent=new Date().toLocaleString();")
    )
    return (
        "<script>(function(){"
        + select
        + lang
        + ("var M=" + json.dumps(compact, separators=(",", ":")) + ";" if has_category and not lock_copy else "")
        + lookup
        + ts
        + report
        + "})();</script>"
    )


FRAME_BUSTER = "<script>if(top!=window){top.location.replace(window.location.href)}</script>"
