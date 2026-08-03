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
import re
from collections.abc import Mapping, Sequence
from typing import Any

from panos_response_pages import redirect
from panos_response_pages.errors import BuildError

GALLERY_CSS = """
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
/* Bare, exactly like the <select> inside a .ctl. The wrapper already carries the
   box, the height and the caret -- giving this button its own border, background
   and ::after drew a second bordered control inside the first, with two carets. */
.pal>button{{display:inline-flex;align-items:center;gap:.45rem;height:100%;
padding:0 1rem 0 0;border:0;background:none;color:var(--fg);
font-size:.8rem;font-weight:550;cursor:pointer}}
.sw{{flex:none;width:.85rem;height:.85rem;border-radius:50%;
box-shadow:inset 0 0 0 1px rgba(0,0,0,.25)}}
.pal ul{{position:absolute;z-index:10;top:calc(100% + .3rem);left:0;min-width:100%;margin:0;
padding:.25rem;list-style:none;border:1px solid var(--line);border-radius:.55rem;
background:var(--srf);box-shadow:0 .6rem 1.6rem rgba(10,20,30,.22)}}
.pal ul[hidden]{{display:none}}
.pal li{{display:flex;align-items:center;gap:.45rem;padding:.35rem .5rem;border-radius:.35rem;
font-size:.8rem;white-space:nowrap;cursor:pointer}}
.pal li:hover,.pal li[data-on]{{background:var(--srf2)}}
.pal li[aria-selected=true]::after{{content:"\\2713";margin-left:auto;padding-left:.6rem;color:var(--acct)}}
.pal li:focus-visible{{outline:3px solid var(--acct);outline-offset:-3px}}
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


# What is interpolated raw into GALLERY_CSS -- a `.format()` template -- and
# into the two hand-built selectors below it. None of that is escaped, so one
# `{`, `}` or `;` in a palette value corrupts every rule after it, and a `"`
# in a name breaks out of an attribute selector. Palette JSON is
# maintainer-controlled at build time, so this is not currently exploitable --
# it is fixed as robustness, in every place a palette value reaches the
# stylesheet, since it is one habit rather than three. Rejected outright
# rather than sanitised: a value that cannot be a plain CSS token has no
# business being one.
_UNSAFE_CSS = re.compile(r"""[{};"'<>\\\r\n]""")


def _css_safe(value: Any, what: str) -> str:
    text = str(value)
    if not text or _UNSAFE_CSS.search(text):
        raise BuildError(f"{what} {text!r} cannot be used as a plain CSS value")
    return text


CHROME_KEYS = (
    ("--bg", "ground"),
    ("--srf", "surface"),
    ("--srf2", "surface_alt"),
    ("--fg", "ink"),
    ("--mut", "ink_muted"),
    ("--line", "surface_alt"),
    ("--acc", "accent"),
    ("--acci", "accent_ink"),
    ("--acct", "accent_text"),
)


def _tokens(colors: Mapping[str, Any], dark: bool) -> str:
    prefix = "d_" if dark else ""
    return ";".join(
        f"{var}:{_css_safe(colors[prefix + key], f'palette colour {prefix + key!r}')}" for var, key in CHROME_KEYS
    )


def _chrome_tokens(palettes: Sequence[Mapping[str, Any]], opening: str) -> str:
    """The toolbar's own colours, one block per palette.

    The chrome follows the selection, so the whole window wears the palette
    being previewed rather than showing it only as a dot in a dropdown.

    The opening palette is emitted twice: once on bare `:root`, as a
    no-JavaScript fallback -- if the script fails to run, the toolbar still
    has colours instead of rendering unstyled -- and once under its own
    attribute so returning to it works like any other.
    """
    out = []
    for p in palettes:
        colors = p["colors"]
        light, dark = _tokens(colors, False), _tokens(colors, True)
        name = _css_safe(p["name"], "palette name")
        if p["name"] == opening:
            out.append(f":root{{{light}}}")
            out.append(f"@media(prefers-color-scheme:dark){{:root{{{dark}}}}}")
        sel = f':root[data-pal="{name}"]'
        out.append(f"{sel}{{{light}}}")
        out.append(f"@media(prefers-color-scheme:dark){{{sel}{{{dark}}}}}")
    return "\n".join(out)


def build_gallery(
    themes: Sequence[Mapping[str, Any]],
    pages: Sequence[str],
    blobs: Mapping[tuple[str, str, str], str],
    cfg: Mapping[str, Any],
    palette: Mapping[str, Any],
    palettes: Sequence[Mapping[str, Any]],
    portal_blobs: Mapping[tuple[str, str, str], str] | None = None,
    portal_previews: Sequence[str] = (),
) -> tuple[str, dict[str, str]]:
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

    def swatch(p: Mapping[str, Any]) -> str:
        accent = _css_safe(p["colors"]["accent"], "palette colour 'accent'")
        return f'<span class="sw" style="background:{html.escape(accent)}"></span>'

    pal_rows = "".join(
        f'<li role="option" data-palette="{html.escape(p["name"])}" '
        f'aria-selected="{str(p["name"] == palette["name"]).lower()}" tabindex="-1">'
        f"{swatch(p)}{html.escape(str(p['label']))}</li>"
        for p in palettes
    )
    # Only when there is a choice: a one-entry dropdown is a label pretending to
    # be a control, and `--palette` narrowing the build is a normal thing to do.
    palette_ctl = (
        f'<div class="ctl pal" id="palgrp"><span>Palette</span>'
        f'<button type="button" id="palbtn" aria-haspopup="listbox" aria-expanded="false">'
        f'{swatch(palette)}<span id="pallabel">{html.escape(str(palette["label"]))}</span></button>'
        f'<ul role="listbox" id="pallist" aria-label="Palette" hidden>{pal_rows}</ul></div>'
        if len(palettes) > 1
        else ""
    )

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
        if any((t["name"], palette["name"], RX_KEY) in blobs for t in themes)
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

    def blob_map(pname: str) -> dict[str, str]:
        """Every frame for one palette, keyed <style>|<palette>|<page>."""
        out = {f"{t['name']}|{pname}|{p}": blobs[(t["name"], pname, p)] for t in themes for p in pages}
        out.update(
            {
                f"{t['name']}|{pname}|{RX_KEY}": blobs[(t["name"], pname, RX_KEY)]
                for t in themes
                if (t["name"], pname, RX_KEY) in blobs
            }
        )
        out.update(
            {
                f"{t['name']}|{pname}|portal:{p}": (portal_blobs or {})[(t["name"], pname, p)]
                for t in themes
                for p in portal_previews
            }
        )
        return out

    def encode(obj: dict[str, str]) -> str:
        # </ would close the <script> that carries this, wherever it appears
        # inside a blob -- which it does, in every page that has a </style>.
        return json.dumps(obj).replace("</", "<\\/")

    opening = palette["name"]
    payload = encode(blob_map(opening))
    sidecars = {
        f"blobs-{p['name']}.js": f"PP({json.dumps(p['name'])},{encode(blob_map(p['name']))})"
        for p in palettes
        if p["name"] != opening
    }

    # The redirect demo, keyed off the page list rather than in it -- `pages` is
    # PAGE_TOKENS, and this variant is not a page PAN-OS serves. Looked up rather
    # than assumed so a caller that built no demo simply gets no toggle payload.
    rx_ok = json.dumps({t["name"]: 1 for t in themes if (t["name"], opening, RX_KEY) in blobs})
    css = _chrome_tokens(palettes, opening) + "\n" + GALLERY_CSS.format()

    gallery_html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Response page preview — {html.escape(cfg["company"])}</title>
<style>{css}</style></head><body>
<div class="bar">
  <h1>Response page preview</h1>
  {theme_ctl}
  {page_ctl}
  {palette_ctl}
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
var D={payload},LOADED={{}},S={{theme:"{themes[0]["name"]}",page:"{pages[0]}",
palette:"{palette["name"]}",view:"both",scheme:"light",
state:"{states[0] if states else ""}",redirect:"off"}};
LOADED[S.palette]=1;
document.documentElement.setAttribute("data-pal",S.palette);
// Each palette but the opening one arrives as a sibling classic script that
// calls this. A module would be CORS-checked and fail on file://, and fetch()
// is unavailable there for the same reason -- which is why this is a <script
// src> and not a request.
function PP(name,obj){{for(var k in obj)D[k]=obj[k];LOADED[name]=1}}
// One <script src> per palette, ever. Two renders of the same not-yet-loaded
// palette -- flipping the viewport while a sidecar is still in flight -- must
// not append a second element and re-fetch the file; the second caller queues
// behind the first and both run when it resolves.
var INFLIGHT={{}};
// A missing or interrupted sidecar used to mark itself loaded and settle with
// no further sign of anything wrong -- so the one frame that needed it just
// rendered blank, which reads as a page bug rather than a missing file. FAILED
// records which palette's sidecar did not load, so frame() can say so instead
// of rendering nothing; LOADED still gets set, on purpose, so a palette that
// failed once is not retried in a loop on every subsequent selection.
var FAILED={{}};
function need(pal,done){{
  if(LOADED[pal]) return done();
  if(INFLIGHT[pal]){{INFLIGHT[pal].push(done);return}}
  INFLIGHT[pal]=[done];
  var s=document.createElement("script");
  s.src="blobs-"+pal+".js";
  function settle(){{
    var q=INFLIGHT[pal];delete INFLIGHT[pal];
    for(var i=0;i<q.length;i++) q[i]();
  }}
  s.onload=settle;
  s.onerror=function(){{LOADED[pal]=1;FAILED[pal]=1;settle()}};
  document.head.appendChild(s);
}}
// Which styles have room for the notice. nyan does not -- its URL block page is
// 15558 B before a flat 3173 B notice, against a 17999 B ceiling -- so selecting
// it must take the control away rather than offer an On with nothing behind it.
var RXPAGE="{redirect.PAGE}",RXSUF="{redirect.PREVIEW_SUFFIX}",RXOK={rx_ok};
// The login surface is one import in four server-driven states, and the url
// block page is one page built with and without the sanctioned-app handoff. Both
// controls compose into the key rather than selecting a page of their own.
function key(){{
  var p=S.page;
  if(p==="portal:login") p=p+"-"+S.state;
  if(p===RXPAGE&&S.redirect==="on"&&RXOK[S.theme]) p=p+RXSUF;
  return S.theme+"|"+S.palette+"|"+p;
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
  var blob=D[key()];
  if(!blob&&FAILED[S.palette]){{
    blob="<p style='font:14px sans-serif;padding:2rem'>blobs-"+S.palette+".js failed to load "
      +"&mdash; this palette's preview is missing.</p>";
  }}
  i.setAttribute("srcdoc",blob||"");
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
function draw(){{
  var g=document.getElementById("stategrp");
  if(g) g.hidden = S.page!=="portal:login";
  var r=document.getElementById("rxgrp");
  if(r) r.hidden = S.page!==RXPAGE||!RXOK[S.theme];
  var s=document.getElementById("stage"); s.innerHTML="";
  if(S.view!=="mobile") s.appendChild(frame("desktop"));
  if(S.view!=="desktop") s.appendChild(frame("mobile"));
}}
function render(){{ need(S.palette,draw); }}
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
(function(){{
  var grp=document.getElementById("palgrp");
  if(!grp) return;
  var btn=document.getElementById("palbtn"),list=document.getElementById("pallist"),
      rows=[].slice.call(list.querySelectorAll("[role=option]")),at=0;
  rows.forEach(function(r,i){{if(r.getAttribute("aria-selected")==="true")at=i}});
  function mark(i){{
    at=(i+rows.length)%rows.length;
    rows.forEach(function(r,j){{
      if(j===at) r.setAttribute("data-on",""); else r.removeAttribute("data-on");
    }});
    rows[at].focus();
  }}
  function open(){{
    list.hidden=false;btn.setAttribute("aria-expanded","true");mark(at);
  }}
  function close(back){{
    list.hidden=true;btn.setAttribute("aria-expanded","false");
    if(back!==false) btn.focus();
  }}
  function choose(i){{
    at=i;
    var r=rows[i];
    rows.forEach(function(o){{o.setAttribute("aria-selected",String(o===r))}});
    S.palette=r.getAttribute("data-palette");
    btn.querySelector(".sw").style.background=r.querySelector(".sw").style.background;
    document.getElementById("pallabel").textContent=r.textContent;
    document.documentElement.setAttribute("data-pal",S.palette);
    close();render();
  }}
  btn.addEventListener("click",function(){{list.hidden?open():close()}});
  list.addEventListener("click",function(e){{
    var r=e.target.closest("[role=option]");
    if(r) choose(rows.indexOf(r));
  }});
  grp.addEventListener("keydown",function(e){{
    if(e.key==="Escape"){{if(!list.hidden){{e.preventDefault();close()}}return}}
    if(list.hidden){{
      if(e.key==="ArrowDown"||e.key==="Enter"||e.key===" "){{e.preventDefault();open()}}
      return;
    }}
    if(e.key==="ArrowDown"){{e.preventDefault();mark(at+1)}}
    else if(e.key==="ArrowUp"){{e.preventDefault();mark(at-1)}}
    else if(e.key==="Home"){{e.preventDefault();mark(0)}}
    else if(e.key==="End"){{e.preventDefault();mark(rows.length-1)}}
    else if(e.key==="Enter"||e.key===" "){{e.preventDefault();choose(at)}}
  }});
  // Tab moves focus out of the widget entirely (rows carry tabindex="-1", so
  // it lands on whatever toolbar control follows), and no keydown fires for
  // that -- only focusout does. relatedTarget is null when focus leaves the
  // document/page entirely, which we also treat as "left".
  grp.addEventListener("focusout",function(e){{
    if(!list.hidden&&(!e.relatedTarget||!grp.contains(e.relatedTarget))) close(false);
  }});
  // Pointer-down, not click: a click listener fires after the browser has
  // already moved focus, so the popup would close with focus somewhere else.
  document.addEventListener("pointerdown",function(e){{
    if(!list.hidden&&!grp.contains(e.target)) close(false);
  }});
}})();
render();
</script>
</body></html>
"""

    return gallery_html, sidecars
