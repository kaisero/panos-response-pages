"""The clickthrough preview gallery.

Self-contained: every page is inlined as an iframe srcdoc rather than loaded
by src, because file:// iframes are cross-origin in Chrome and the auto-height
measurement would be blocked.

The chrome is one sticky toolbar row. The point of this page is the frame
underneath it, and the controls used to cost ~500 px of a 900 px viewport --
more than half the screen spent on a header nobody reads twice. The two long
lists (style, page) are selects, which stay one line however many entries a
build produces; the short mutually-exclusive ones stay segmented buttons,
which show their state without being opened. The prose that was in the header
lives behind the About toggle.
"""

from __future__ import annotations

import html
import json
from collections.abc import Mapping, Sequence
from typing import Any

from panos_response_pages import redirect

GALLERY_CSS = """
:root{{--bg:{ground};--srf:{surface};--srf2:{surface_alt};--fg:{ink};--mut:{ink_muted};
--line:{surface_alt};--acc:{accent};--acci:{accent_ink};--acct:{accent_text}}}
@media(prefers-color-scheme:dark){{:root{{--bg:{d_ground};--srf:{d_surface};--srf2:{d_surface_alt};
--fg:{d_ink};--mut:{d_ink_muted};--line:{d_surface_alt};--acc:{d_accent};--acci:{d_accent_ink};
--acct:{d_accent_text}}}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--fg);
font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
-webkit-font-smoothing:antialiased}}
/* One row, and it stays one row: the controls are sized so a 1440 px viewport
   fits every group including the login states, and wrap rather than scroll
   below that. */
.bar{{display:flex;align-items:center;flex-wrap:wrap;gap:.4rem;
padding:.5rem .75rem;border-bottom:1px solid var(--line);
position:sticky;top:0;z-index:5;background:var(--bg);
background:color-mix(in oklab,var(--bg) 88%,transparent);
backdrop-filter:blur(12px) saturate(1.3);-webkit-backdrop-filter:blur(12px) saturate(1.3)}}
h1{{margin:0 .2rem 0 0;font-size:.88rem;font-weight:650;letter-spacing:-.01em;
white-space:nowrap}}
/* auto margin rather than a spacer element: on a line that has wrapped it
   simply stops applying, where a flex spacer would still claim a slot. */
.push{{margin-left:auto}}
/* A label wrapping its own select, so the caption is part of the hit area. */
.ctl{{position:relative;display:inline-flex;align-items:center;gap:.4rem;height:2rem;
padding:0 .5rem;border:1px solid var(--line);border-radius:.55rem;background:var(--srf);
cursor:pointer}}
.ctl:focus-within{{border-color:var(--acct)}}
.ctl>span,.seg>span{{font-size:.62rem;font-weight:600;letter-spacing:.1em;
text-transform:uppercase;color:var(--mut);white-space:nowrap}}
select{{appearance:none;-webkit-appearance:none;font:inherit;font-size:.8rem;font-weight:550;
color:var(--fg);background:none;border:0;padding:0 1rem 0 0;height:100%;cursor:pointer;
max-width:14rem}}
select:focus{{outline:0}}
/* A CSS caret rather than a background SVG: an <img>-style background is an
   isolated document, so it could not follow the scheme through currentColor. */
.ctl::after{{content:"";position:absolute;right:.5rem;top:50%;margin-top:-.12rem;
border:.26rem solid transparent;border-top-color:var(--mut);pointer-events:none}}
option{{background:var(--srf);color:var(--fg)}}
.seg{{display:inline-flex;align-items:center;gap:.15rem;height:2rem;padding:.15rem;
border:1px solid var(--line);border-radius:.55rem;background:var(--srf)}}
.seg>span{{padding:0 .3rem 0 .35rem}}
button{{font:inherit;font-size:.78rem;font-weight:550;height:100%;padding:0 .6rem;
border:0;background:none;color:var(--fg);border-radius:.4rem;cursor:pointer;
white-space:nowrap}}
.seg button:hover{{background:var(--srf2)}}
.seg button[aria-pressed=true]{{background:var(--acc);color:var(--acci);font-weight:650}}
button:focus-visible,select:focus-visible{{outline:3px solid var(--acct);outline-offset:2px}}
main{{padding:1.5rem 1.5rem 1rem;display:flex;justify-content:center}}
.stage{{display:flex;gap:2rem;align-items:flex-start;flex-wrap:wrap;justify-content:center}}
figure{{margin:0;display:flex;flex-direction:column;gap:.6rem;align-items:center}}
figcaption{{font-size:.78rem;color:var(--mut);letter-spacing:.03em}}
.dev{{background:var(--srf);border:1px solid var(--line);border-radius:.75rem;overflow:hidden;
box-shadow:0 1px 2px rgba(10,20,30,.05),0 10px 30px rgba(10,20,30,.08)}}
.dev.desktop{{width:min(74vw,900px)}}
.dev.mobile{{width:390px;max-width:92vw;border-radius:1.5rem;padding:.5rem}}
.dev.mobile iframe{{border-radius:1.1rem}}
iframe{{border:0;display:block;width:100%;background:var(--srf)}}
.seg[hidden]{{display:none}}
.foot{{margin:0 auto;padding:0 1.5rem 3rem;max-width:52rem;text-align:center;
color:var(--mut);font-size:.78rem;line-height:1.6}}
.foot code{{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:.94em}}
@media(max-width:900px){{h1{{width:100%;margin:0 0 .2rem}}.gap{{display:none}}}}
"""

# How each portal preview is labelled in the controls. The file names are keys
# and stay terse; these are what a reviewer reads.
# The url-block page built with the sanctioned-app handoff forced on. Keyed off
# the page list rather than in it: `pages` is PAGE_TOKENS, and this variant is not
# a page PAN-OS serves.
RX_KEY = f"{redirect.PAGE}{redirect.PREVIEW_SUFFIX}"

PORTAL_LABELS = {
    "login": "Login",
    "getsoftware": "Get software",
    "logout": "Logout",
    "default": "Default",
    "error": "Error",
    "challenge": "Challenge",
    "changepw": "Change password",
}


def build_gallery(
    themes: Sequence[Mapping[str, Any]],
    pages: Sequence[str],
    blobs: Mapping[tuple[str, str], str],
    cfg: Mapping[str, Any],
    palette: Mapping[str, Any],
    portal_blobs: Mapping[tuple[str, str], str] | None = None,
    portal_previews: Sequence[str] = (),
) -> str:
    """Self-contained preview: every page inlined via iframe srcdoc.

    Frames are sized to their content after load, so nothing scrolls inside a
    frame -- the whole page is visible at once, which is the point of a preview.

    The portal previews are spliced, not built: each is a PAN-OS prefix with an
    import concatenated onto it. They are here so a reviewer sees the page a
    visitor sees, and they are the only frames in this gallery that load
    anything from disk -- the prefixes pull jQuery from `portal/` beside this
    file, and srcdoc resolves that relative to this document.
    """

    def options(items: Sequence[tuple[str, str]], cur: str) -> str:
        return "".join(
            f'<option value="{v}"{" selected" if v == cur else ""}>{html.escape(lbl)}</option>' for v, lbl in items
        )

    def seg(
        name: str,
        label: str,
        items: Sequence[tuple[str, str]],
        cur: str,
        extra: str = "",
        caption: bool = True,
        push: bool = False,
    ) -> str:
        """One segmented control. `caption` prints the group name inside it.

        Off for viewport and scheme: Both/Desktop/Mobile and Light/Dark say what
        they are, and the caption is the difference between the bar fitting on
        one line at 1440 px and wrapping to two.
        """
        btns = "".join(
            f'<button role="radio" data-{name}="{v}" aria-pressed="{str(v == cur).lower()}">{lbl}</button>'
            for v, lbl in items
        )
        cap = f"<span>{label}</span>" if caption else ""
        cls = "seg push" if push else "seg"
        return f'<div class="{cls}" role="radiogroup" aria-label="{label}"{extra}>{cap}{btns}</div>'

    # The four login states are one import rendered four ways, so they get their
    # own control rather than four more entries in the page list -- a reviewer
    # picks a surface, then asks what the server said.
    states = [n.removeprefix("login-") for n in portal_previews if n.startswith("login-")]
    surfaces = ["login"] + [n for n in portal_previews if not n.startswith("login-")] if states else []

    # One list for both families. They were two button groups sharing one state
    # key, which meant neither could show a selection the other did not clear;
    # as optgroups of a single select the grouping survives and the selected
    # entry is always visible without opening anything.
    page_opts = f'<optgroup label="Block pages">{options([(p, p) for p in pages], pages[0])}</optgroup>'
    if surfaces:
        portal_items = [(f"portal:{s}", PORTAL_LABELS[s]) for s in surfaces]
        page_opts += f'<optgroup label="GlobalProtect portal">{options(portal_items, "")}</optgroup>'
    page_ctl = f'<label class="ctl"><span>Page</span><select data-page>{page_opts}</select></label>'

    state_seg = (
        seg("state", "Login state", [(s, PORTAL_LABELS[s]) for s in states], states[0], ' id="stategrp" hidden')
        if surfaces
        else ""
    )

    # Same shape as the login states: one page rendered two ways, so it composes
    # into the key rather than becoming an entry in the page list. Always built,
    # so the toggle demonstrates the handoff to someone whose config has not
    # enabled it -- which is every config until they opt in.
    # Offered only if the demo blob was actually built: the control is useless
    # without something to switch to, and an On that renders an empty frame reads
    # as a broken preview rather than as a feature nobody asked for.
    redirect_seg = (
        seg("redirect", "Redirect", [("off", "Off"), ("on", "On")], "off", ' id="rxgrp" hidden')
        if any((t["name"], RX_KEY) in blobs for t in themes)
        else ""
    )

    # The style is fixed at build time, so there is nothing to choose between --
    # the selector only appears if this build actually produced more than one.
    theme_ctl = ""
    if len(themes) > 1:
        theme_opts = options([(t["name"], t["label"]) for t in themes], themes[0]["name"])
        theme_ctl = f'<label class="ctl"><span>Style</span><select data-theme>{theme_opts}</select></label>'

    view_items = [("both", "Both"), ("desktop", "Desktop"), ("mobile", "Mobile")]
    view_seg = seg("view", "Viewport", view_items, "both", caption=False, push=True)
    scheme_seg = seg("scheme", "Colour scheme", [("light", "Light"), ("dark", "Dark")], "light", caption=False)

    data = {f"{t['name']}|{p}": blobs[(t["name"], p)] for t in themes for p in pages}
    data.update(
        {f"{t['name']}|portal:{p}": (portal_blobs or {})[(t["name"], p)] for t in themes for p in portal_previews}
    )
    # The redirect demo, keyed off the page list rather than in it -- `pages` is
    # PAGE_TOKENS, and this variant is not a page PAN-OS serves. Looked up rather
    # than assumed so a caller that built no demo simply gets no toggle payload.
    data.update({f"{t['name']}|{RX_KEY}": blobs[(t["name"], RX_KEY)] for t in themes if (t["name"], RX_KEY) in blobs})
    payload = json.dumps(data).replace("</", "<\\/")
    css = GALLERY_CSS.format(**palette["colors"])

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Response page preview — {html.escape(cfg["company"])}</title>
<style>{css}</style></head><body>
<div class="bar">
  <h1>Response page preview</h1>
  {theme_ctl}
  {page_ctl}
  {state_seg}
  {redirect_seg}
  {view_seg}
  {scheme_seg}
</div>
<main><div class="stage" id="stage"></div></main>
<p class="foot">Sample data stands in for the PAN-OS tokens so the pages render; the files under
   <code>deploy/</code> keep the tokens intact. The portal frames are spliced onto captured PAN-OS
   prefixes to show the whole served page — <strong>preview only, never importable</strong>.
   <strong>Redirect: On</strong> shows the sanctioned-app handoff on a calm category, and its countdown
   <strong>restarts</strong> so the motion stays visible — the served page hands over once and does not
   loop. It is shown whatever <code>redirect.enabled</code> says, so what ships still follows the config.</p>
<script>
var D={payload},S={{theme:"{themes[0]["name"]}",page:"{pages[0]}",view:"both",scheme:"light",
state:"{states[0] if states else ""}",redirect:"off"}};
var RXPAGE="{redirect.PAGE}",RXSUF="{redirect.PREVIEW_SUFFIX}";
// The login surface is one import in four server-driven states, and the url
// block page is one page built with and without the sanctioned-app handoff. Both
// controls compose into the key rather than selecting a page of their own.
function key(){{
  var p=S.page;
  if(p==="portal:login") p=p+"-"+S.state;
  if(p===RXPAGE&&S.redirect==="on") p=p+RXSUF;
  return S.theme+"|"+p;
}}
// A frame never shrinks below this. Block pages fill their frame and want to be
// shrink-wrapped, so their floor is 0. The portal pages are a small card centred
// in min-height:100vh, and shrink-wrapping one collapses the viewport it is
// centred in -- the card ends up jammed against the frame edges with none of the
// background it was designed to sit on, which reads as a broken thumbnail rather
// than a page. These are the heights of a real browser content area.
var FLOOR={{desktop:820,mobile:760}};
function fit(f){{
  var min=+f.getAttribute("data-min")||0;
  try{{
    var d=f.contentDocument,h=0,n;
    // The pages pad with clamp(2rem,9vh,5rem), so their height depends on the
    // frame's height -- measuring once and setting it makes the padding grow and
    // the content overflow again. Iterate until it settles.
    f.style.height=min?min+"px":"0px";
    for(var k=0;k<4;k++){{
      n=Math.max(d.body.scrollHeight,d.documentElement.scrollHeight,min);
      if(n===h) break;
      h=n; f.style.height=h+"px";
    }}
  }}catch(e){{f.style.height=(min||900)+"px";}}
}}
function frame(kind){{
  var f=document.createElement("figure");
  var d=document.createElement("div"); d.className="dev "+kind;
  var i=document.createElement("iframe");
  i.setAttribute("srcdoc",D[key()]||"");
  i.setAttribute("title",S.page+" "+kind);
  // Carried on the element so the resize handler, which only has the iframe,
  // does not have to work out which page produced it.
  if(S.page.indexOf("portal:")===0) i.setAttribute("data-min",FLOOR[kind]);
  i.addEventListener("load",function(){{
    // Set the scheme on the loaded document rather than rewriting the markup:
    // string surgery here has to survive heredoc, Python and f-string quoting.
    try{{i.contentDocument.documentElement.setAttribute("data-force-scheme",S.scheme);}}catch(e){{}}
    fit(i);
  }});
  d.appendChild(i); f.appendChild(d);
  var c=document.createElement("figcaption");
  c.textContent=kind;
  f.appendChild(c); return f;
}}
function render(){{
  var g=document.getElementById("stategrp");
  if(g) g.hidden = S.page!=="portal:login";
  var r=document.getElementById("rxgrp");
  if(r) r.hidden = S.page!==RXPAGE;
  var s=document.getElementById("stage"); s.innerHTML="";
  if(S.view!=="mobile") s.appendChild(frame("desktop"));
  if(S.view!=="desktop") s.appendChild(frame("mobile"));
}}
document.querySelectorAll(".bar select").forEach(function(sel){{
  sel.addEventListener("change",function(){{
    S[Object.keys(sel.dataset)[0]]=sel.value;
    render();
  }});
}});
// Cleared within the group: each segmented control is its own radiogroup, so
// the pressed state never has to be reasoned about across the whole bar.
document.querySelectorAll(".seg button").forEach(function(b){{
  b.addEventListener("click",function(){{
    var k=Object.keys(b.dataset)[0];
    S[k]=b.dataset[k];
    b.parentNode.querySelectorAll("button").forEach(function(o){{
      o.setAttribute("aria-pressed",String(o===b));}});
    render();
  }});
}});
addEventListener("resize",function(){{
  document.querySelectorAll("iframe").forEach(fit);
}});
render();
</script>
</body></html>
"""
