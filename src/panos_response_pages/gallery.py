"""The clickthrough preview gallery.

Self-contained: every page is inlined as an iframe srcdoc rather than loaded
by src, because file:// iframes are cross-origin in Chrome and the auto-height
measurement would be blocked.
"""

from __future__ import annotations

import html
import json
from collections.abc import Mapping, Sequence
from typing import Any

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
header{{padding:1.75rem 1.5rem 1.25rem;border-bottom:1px solid var(--line)}}
h1{{margin:0 0 .3rem;font-size:1.5rem;letter-spacing:-.02em;font-weight:650}}
header p{{margin:0;color:var(--mut);font-size:.92rem;max-width:48rem}}
.bars{{display:flex;flex-wrap:wrap;gap:1.5rem;padding:1rem 1.5rem;
border-bottom:1px solid var(--line);position:sticky;top:0;background:var(--bg);z-index:5}}
.grp{{display:flex;flex-direction:column;gap:.4rem}}
.grp>span{{font-size:.68rem;letter-spacing:.12em;text-transform:uppercase;color:var(--mut)}}
.opts{{display:flex;gap:.35rem;flex-wrap:wrap}}
button{{font:inherit;font-size:.86rem;font-weight:500;padding:.45rem .85rem;
border:1px solid var(--line);background:var(--srf);color:var(--fg);
border-radius:.6rem;cursor:pointer}}
button:hover{{border-color:var(--acct)}}
button[aria-pressed=true]{{background:var(--acc);border-color:var(--acc);color:var(--acci);
font-weight:650}}
button:focus-visible{{outline:3px solid var(--acct);outline-offset:2px}}
main{{padding:1.75rem 1.5rem 4rem;display:flex;justify-content:center}}
.stage{{display:flex;gap:2rem;align-items:flex-start;flex-wrap:wrap;justify-content:center}}
figure{{margin:0;display:flex;flex-direction:column;gap:.6rem;align-items:center}}
figcaption{{font-size:.78rem;color:var(--mut);letter-spacing:.03em}}
.dev{{background:var(--srf);border:1px solid var(--line);border-radius:.75rem;overflow:hidden;
box-shadow:0 1px 2px rgba(10,20,30,.05),0 10px 30px rgba(10,20,30,.08)}}
.dev.desktop{{width:min(74vw,900px)}}
.dev.mobile{{width:390px;max-width:92vw;border-radius:1.5rem;padding:.5rem}}
.dev.mobile iframe{{border-radius:1.1rem}}
iframe{{border:0;display:block;width:100%;background:var(--srf)}}
.note{{max-width:48rem;margin:0 auto;padding:0 1.5rem 3rem;color:var(--mut);font-size:.86rem}}
.note code{{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:.92em}}
"""


def build_gallery(
    themes: Sequence[Mapping[str, Any]],
    pages: Sequence[str],
    blobs: Mapping[tuple[str, str], str],
    cfg: Mapping[str, Any],
    palette: Mapping[str, Any],
) -> str:
    """Self-contained preview: every page inlined via iframe srcdoc.

    Frames are sized to their content after load, so nothing scrolls inside a
    frame -- the whole page is visible at once, which is the point of a preview.
    """

    def opts(name: str, items: Sequence[tuple[str, str]], cur: str) -> str:
        return "".join(
            f'<button role="radio" data-{name}="{v}" aria-pressed="{str(v == cur).lower()}">{lbl}</button>'
            for v, lbl in items
        )

    page_btns = opts("page", [(p, p) for p in pages], pages[0])
    view_btns = opts("view", [("both", "Desktop + Mobile"), ("desktop", "Desktop"), ("mobile", "Mobile")], "both")
    scheme_btns = opts("scheme", [("light", "Light"), ("dark", "Dark")], "light")

    # The style is fixed at build time, so there is nothing to choose between --
    # the selector only appears if this build actually produced more than one.
    theme_grp = ""
    if len(themes) > 1:
        theme_grp = (
            '<div class="grp"><span>Style</span><div class="opts" role="radiogroup">'
            + opts("theme", [(t["name"], t["label"]) for t in themes], themes[0]["name"])
            + "</div></div>"
        )

    data = {f"{t['name']}|{p}": blobs[(t["name"], p)] for t in themes for p in pages}
    payload = json.dumps(data).replace("</", "<\\/")
    css = GALLERY_CSS.format(**palette["colors"])

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Response page preview — {html.escape(cfg["company"])}</title>
<style>{css}</style></head><body>
<header>
  <h1>Response page preview</h1>
  <p>All {len(pages)} pages exactly as <code>dist/&lt;style&gt;/</code> will serve them, in the
     <strong>{html.escape(palette["label"])}</strong> palette. Sample data stands in for the PAN-OS
     tokens so the pages render; the deployable files keep the tokens intact.</p>
</header>
<div class="bars">
  {theme_grp}
  <div class="grp"><span>Page</span><div class="opts" role="radiogroup">{page_btns}</div></div>
  <div class="grp"><span>Viewport</span><div class="opts" role="radiogroup">{view_btns}</div></div>
  <div class="grp"><span>Scheme</span><div class="opts" role="radiogroup">{scheme_btns}</div></div>
</div>
<main><div class="stage" id="stage"></div></main>
<p class="note">Built from <code>config/</code>, <code>palettes/</code> and
   <code>templates/</code>. Re-run <code>python3 build.py</code> to refresh.</p>
<script>
var D={payload},S={{theme:"{themes[0]["name"]}",page:"{pages[0]}",view:"both",scheme:"light"}};
function fit(f){{
  try{{
    var d=f.contentDocument,h=0,n;
    // The pages pad with clamp(2rem,9vh,5rem), so their height depends on the
    // frame's height -- measuring once and setting it makes the padding grow and
    // the content overflow again. Iterate until it settles.
    f.style.height="0px";
    for(var k=0;k<4;k++){{
      n=Math.max(d.body.scrollHeight,d.documentElement.scrollHeight);
      if(n===h) break;
      h=n; f.style.height=h+"px";
    }}
  }}catch(e){{f.style.height="900px";}}
}}
function frame(kind){{
  var f=document.createElement("figure");
  var d=document.createElement("div"); d.className="dev "+kind;
  var i=document.createElement("iframe");
  i.setAttribute("srcdoc",D[S.theme+"|"+S.page]||"");
  i.setAttribute("title",S.page+" "+kind);
  i.addEventListener("load",function(){{
    // Set the scheme on the loaded document rather than rewriting the markup:
    // string surgery here has to survive heredoc, Python and f-string quoting.
    try{{i.contentDocument.documentElement.setAttribute("data-force-scheme",S.scheme);}}catch(e){{}}
    fit(i);
  }});
  d.appendChild(i); f.appendChild(d);
  var c=document.createElement("figcaption");
  c.textContent=kind==="mobile"?"390 px — mobile":"desktop";
  f.appendChild(c); return f;
}}
function render(){{
  var s=document.getElementById("stage"); s.innerHTML="";
  if(S.view!=="mobile") s.appendChild(frame("desktop"));
  if(S.view!=="desktop") s.appendChild(frame("mobile"));
}}
document.querySelectorAll(".bars button").forEach(function(b){{
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
