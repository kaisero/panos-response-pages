"""The sanctioned-app handoff on the URL block page.

When a blocked category has a company-sanctioned equivalent -- personal file
storage against the corporate drive, consumer webmail against corporate mail --
the page can say so and hand the user over after a countdown.

Opt-in, and off unless a customer both sets `redirect.enabled` and maps at least
one category. Nothing here reaches a page otherwise: the CSS, the markup and the
script are all empty strings, and a build with the feature off is byte-identical
to one from before it existed.

Three rules are enforced here rather than left to the config author, because each
of them fails in a way the author would not see:

* **Only a `calm` category may carry a redirect.** Checked at build time, and
  again in the browser against the tone the category map resolved. Automatically
  forwarding a user off a malware or phishing block is indefensible, and a typo
  in a tone must not be able to cause it.
* **The target is an absolute https URL from config.** Never `<url/>` -- that
  value is chosen by whoever the user was trying to reach, and a redirect built
  from it would make every firewall serving this page an open redirector.
* **At most one hop, ever.** A response page is served *as* the blocked site, so
  `location.host` is the host the user was refused. If that is the host of any
  sanctioned app in the table, this page is a blocked sanctioned app and the hop
  that landed the user here was ours -- so it does not hop again. A hop only ever
  targets something in this table, which means every cycle passes through one of
  these hosts, including cycles that never repeat a host. What it cannot prevent
  is the first hop into a blocked app: the target still has to be permitted by
  the policy that produced the block, and only policy can do that.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from panos_response_pages.errors import BuildError

# Only this page. The other eight either have no <category/> token to key on, or
# already carry an action of their own that a countdown would race.
PAGE = "url-block-page"

DEFAULT_SECONDS = 10

# Copy that is not per-category, and so is not worth a config key each. Kept
# together here so it is findable when someone wants to change the wording.
STAY_LABEL = "Stay"
GO_LABEL = "Go now"
CANCELLED = "Staying on this page."
CANCELLED_ANNOUNCE = "Cancelled. You are staying on this page."

# The notice itself. Structural only -- every colour comes from the shell's own
# custom properties, so a theme styles this by existing rather than by opting in.
CSS = """
.rx{margin:0 0 1.4rem;max-width:31rem;border:1px solid var(--aw);border-left:3px solid var(--ac);
border-radius:.5rem;background:var(--sa);overflow:hidden}
.rx-b{display:flex;align-items:center;gap:.7rem;padding:.7rem .85rem;flex-wrap:wrap}
.rx-i{flex:none;width:1.9rem;height:1.9rem;border-radius:50%;background:var(--ac);color:var(--ai);
display:grid;place-items:center;font-style:normal;font-size:.8rem;font-weight:700;
font-variant-numeric:tabular-nums}
.rx-t{flex:1 1 12rem;min-width:0;font-size:.8rem;line-height:1.5;color:var(--ik)}
.rx-c{display:flex;gap:.5rem;align-items:center}
.rx-c .btn{min-height:2.2rem;padding:.4rem 1rem;font-size:.78rem;box-shadow:none}
.rx button{font:inherit;font-size:.76rem;min-height:2.2rem;padding:.4rem .9rem;border-radius:.45rem;
border:1px solid var(--aw);background:transparent;color:var(--im);cursor:pointer}
.rx-p{height:3px;background:var(--aw)}
.rx-p span{display:block;height:100%;width:0;background:var(--ac);transition:width 1s linear}
.rx-sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.rx[data-off] .rx-p span{background:var(--if)}
.rx[data-off] .rx-i,.rx[data-off] .rx-c{display:none}
"""

# hidden until the script has decided the category qualifies: an unstyled notice
# flashing before the countdown starts is worse than no notice.
HTML = f"""
<div class="rx" id="rx" hidden>
<div class="rx-b"><i class="rx-i" id="rxi" aria-hidden="true"></i>
<span class="rx-t"><span id="rxm"></span><span id="rxo" hidden>{CANCELLED}</span>
<span class="rx-sr" id="rxl" role="status" aria-live="polite"></span></span>
<span class="rx-c"><a class="btn" id="rxg" href="#">{GO_LABEL}</a>
<button type="button" id="rxs">{STAY_LABEL}</button></span></div>
<div class="rx-p"><span id="rxp"></span></div>
</div>
"""


def _entries(cfg: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    red = cfg.get("redirect") or {}
    return red.get("categories") or {}


def enabled(cfg: Mapping[str, Any]) -> bool:
    """Both halves must be true: a toggle with no mapping table does nothing."""
    red = cfg.get("redirect") or {}
    return bool(red.get("enabled")) and bool(_entries(cfg))


def check(cfg: Mapping[str, Any]) -> None:
    """Fail the build on a redirect config that would misbehave silently."""
    red = cfg.get("redirect")
    if not red:
        return
    if not isinstance(red.get("enabled", False), bool):
        raise BuildError("redirect.enabled must be true or false")

    seconds = red.get("seconds", DEFAULT_SECONDS)
    _check_seconds(seconds, "redirect.seconds")
    if not str(red.get("message", "")).strip() and _entries(cfg):
        raise BuildError("redirect.message is empty; it is the fallback for every category")

    tones = {name: entry.get("tone") for name, entry in (cfg.get("categories") or {}).items()}
    for name, entry in _entries(cfg).items():
        where = f"redirect.categories.{name}"
        for key in ("app", "url"):
            if not str(entry.get(key, "")).strip():
                raise BuildError(f"{where} has no {key}")
        if not str(entry["url"]).startswith("https://"):
            raise BuildError(
                f"{where}.url must be an absolute https:// URL -- a relative or http target "
                "resolves against the blocked site, which is not ours"
            )
        if name not in tones:
            raise BuildError(
                f"{where} is not in `categories`, so the page has no gloss and no tone for it. Add it there first."
            )
        if tones[name] != "calm":
            raise BuildError(
                f"{where} has tone '{tones[name]}'; only a calm category may redirect. "
                "A user must not be forwarded off a warning or a security block."
            )
        if "seconds" in entry:
            _check_seconds(entry["seconds"], f"{where}.seconds")


def _check_seconds(value: Any, where: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise BuildError(f"{where} must be a whole number of seconds")
    if not 1 <= value <= 60:
        raise BuildError(f"{where} is {value}; expected 1-60 seconds")


def _map(cfg: Mapping[str, Any]) -> dict[str, list[Any]]:
    """category -> [app, url] (+ seconds, + message) with defaults trimmed off.

    Trailing defaults are dropped rather than repeated: the message is the
    longest value in the table, and a customer who accepts the default one on
    every category should not pay for it once per category.
    """
    red = cfg["redirect"]
    default_seconds = red.get("seconds", DEFAULT_SECONDS)
    default_message = red["message"]
    out: dict[str, list[Any]] = {}
    for name, entry in _entries(cfg).items():
        row: list[Any] = [entry["app"], entry["url"]]
        seconds = entry.get("seconds", default_seconds)
        message = entry.get("message", default_message)
        if message != default_message:
            row += [0 if seconds == default_seconds else seconds, message]
        elif seconds != default_seconds:
            row.append(seconds)
        out[name] = row
    return out


def _script(cfg: Mapping[str, Any]) -> str:
    red = cfg["redirect"]
    return (
        "<script>(function(){"
        "var R=" + json.dumps(_map(cfg), separators=(",", ":")) + ";"
        "var S=" + str(red.get("seconds", DEFAULT_SECONDS)) + ",D=" + json.dumps(red["message"]) + ";"
        "var e=document.getElementById('cat'),b=document.getElementById('rx');"
        "if(!e||!b)return;"
        "var r=R[(e.textContent||'').trim().toLowerCase()];"
        # The tone the category map just resolved, not the one config claims: a
        # page repainted critical at runtime must not then forward anyone.
        "if(!r||document.documentElement.getAttribute('data-tone')!=='calm')return;"
        "var u=r[1],h=document.createElement('a');"
        # The loop guard. A response page is served AS the blocked site, so
        # location.host is the host the user was refused. If that is the host of
        # any sanctioned app -- not merely this category's -- then this page is a
        # blocked sanctioned app, and the hop that landed the user here was ours.
        # Since a hop only ever targets something in this table, every cycle
        # passes through one of these hosts, so stopping here stops all of them.
        "for(var k in R){h.href=R[k][1];if(h.host===location.host)return}"
        "var n=r[0],t=r[2]||S,l=t,z,d=false;"
        "var m=document.getElementById('rxm'),o=document.getElementById('rxo');"
        "var i=document.getElementById('rxi'),p=document.getElementById('rxp');"
        "var v=document.getElementById('rxl'),g=document.getElementById('rxg');"
        "m.textContent=(r[3]||D).replace('{app}',n);g.href=u;b.hidden=false;"
        "function w(){i.textContent=l;p.style.width=((t-l)/t*100)+'%'}"
        "function q(){if(z){clearInterval(z);z=null}}"
        "function go(){if(d)return;d=true;q();location.replace(u)}"
        "function no(){if(d)return;d=true;q();b.setAttribute('data-off','1');"
        "m.hidden=true;o.hidden=false;v.textContent=" + json.dumps(CANCELLED_ANNOUNCE) + "}"
        "w();"
        # Announced once, as a sentence. The per-second number is aria-hidden --
        # a screen reader must not be read a countdown.
        "v.textContent='You will be sent to '+n+' in '+t+' seconds. Choose "
        + STAY_LABEL
        + ", or press Escape, to remain on this page.';"
        # A hidden tab pauses rather than counting: a background tab that
        # navigates itself is indistinguishable from a hijack.
        "z=setInterval(function(){if(document.hidden)return;l--;w();if(l<=0)go()},1000);"
        "g.addEventListener('click',function(x){x.preventDefault();go()});"
        "document.getElementById('rxs').addEventListener('click',no);"
        "document.addEventListener('keydown',function(x){if(x.key==='Escape'||x.key==='Esc')no()});"
        "})();</script>"
    )


def emit(cfg: Mapping[str, Any], page: str) -> tuple[str, str, str]:
    """(css, markup, script) for this page. Three empty strings when it does not apply.

    Validation runs for every page, not just the one that renders the notice, so
    a bad redirect config fails the build rather than quietly doing nothing.
    """
    check(cfg)
    if page != PAGE or not enabled(cfg):
        return "", "", ""
    return CSS, HTML, _script(cfg)
