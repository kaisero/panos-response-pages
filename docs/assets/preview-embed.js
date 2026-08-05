/* The inline preview on the home page.
 *
 * Loaded through extra_javascript rather than written inline in index.md:
 * navigation.instant swaps page content in over XHR and does NOT re-execute
 * inline <script> tags, so an inline version works on a hard load and silently
 * stops working the moment a reader arrives from another page in the site.
 * Material re-emits document$ after every such navigation, which is what this
 * subscribes to.
 *
 * The frames load from preview/<theme>/..., which nox -s docs generates into
 * docs/preview/. Same origin, so the scheme can be forced on the loaded
 * document; that attribute is the same one the standalone gallery uses.
 */
(function () {
  "use strict";

  var THEME = "beacon";

  // Kept in step with the templates by tests/test_docs.py, which reads this
  // file and compares the list against the page templates on disk.
  var PAGES = [
    { group: "Block pages", items: [
      "application-block-page",
      "credential-block-page",
      "credential-coach-text",
      "data-filter-block-page",
      "file-block-continue-page",
      "file-block-page",
      "safe-search-block-page",
      "ssl-cert-status-page",
      "url-block-page",
      "url-coach-text",
      "virus-block-page"
    ]},
    { group: "GlobalProtect portal", items: [
      ["portal/login-default", "portal — sign in"],
      ["portal/getsoftware", "portal — get software"],
      ["portal/logout", "portal — signed out"]
    ]}
  ];

  // A portal page is a small card centred in min-height:100vh. Shrink-wrapping
  // one collapses the viewport it is centred in and the card ends up jammed
  // against the frame edges, so those frames get a floor instead.
  var PORTAL_FLOOR = 680;

  function fit(frame, floor) {
    try {
      var d = frame.contentDocument, h = 0, n;
      // The pages pad with vh units, so their height depends on the frame's
      // height. Setting it once makes the padding grow and the content overflow
      // again; iterate until it settles.
      frame.style.height = floor ? floor + "px" : "0px";
      for (var i = 0; i < 4; i++) {
        n = Math.max(d.body.scrollHeight, d.documentElement.scrollHeight, floor);
        if (n === h) break;
        h = n;
        frame.style.height = h + "px";
      }
    } catch (e) {
      frame.style.height = (floor || 640) + "px";
    }
  }

  function init() {
    var root = document.getElementById("rp-embed");
    if (!root) return;

    // A DOM property, not an attribute, and that distinction is the whole point.
    // Returning to this page re-renders the authored markup -- so the switch's
    // label reads "Dark" again -- while the browser restores the checkbox's own
    // state, which may be light. The two then disagree. A property does not
    // survive that content swap, so a swapped-in embed rewires and re-syncs,
    // while a still-live one is only asked to re-render.
    if (root.rpRender) {
      root.rpRender();
      return;
    }

    var select = root.querySelector("#rp-page");
    var toggle = root.querySelector("#rp-scheme");
    var frame = root.querySelector("#rp-frame");
    if (!select || !toggle || !frame) return;

    if (!select.options.length) PAGES.forEach(function (section) {
      var g = document.createElement("optgroup");
      g.label = section.group;
      section.items.forEach(function (item) {
        var value = typeof item === "string" ? item : item[0];
        var text = typeof item === "string" ? item : item[1];
        var o = document.createElement("option");
        o.value = value;
        o.textContent = text;
        g.appendChild(o);
      });
      select.appendChild(g);
    });

    function floor() {
      return select.value.indexOf("portal/") === 0 ? PORTAL_FLOOR : 0;
    }

    // One function for both controls. Splitting "change the page" from "change
    // the scheme" left two paths that could disagree: the scheme is applied in
    // the frame's load handler, and setting src to the value it already holds
    // fires no load event, so a re-render with the same page selected would
    // leave the frame untouched.
    function render() {
      var src = "preview/" + THEME + "/" + select.value + ".html";
      var apply = function () {
        try {
          frame.contentDocument.documentElement.setAttribute(
            "data-force-scheme", toggle.checked ? "dark" : "light");
        } catch (e) { /* nothing to force; the frame still renders */ }
        fit(frame, floor());
      };
      frame.onload = apply;
      if (frame.getAttribute("src") === src) {
        apply();
      } else {
        frame.setAttribute("src", src);
      }
    }

    select.addEventListener("change", render);
    toggle.addEventListener("change", render);
    root.rpRender = render;
    render();
  }

  function resync() {
    var root = document.getElementById("rp-embed");
    if (root && root.rpRender) root.rpRender();
  }

  // Registered once at module scope. Inside init() these would stack another
  // listener every time the embed is rewired. pageshow covers a bfcache restore,
  // where the frame is handed back holding whatever it last rendered.
  addEventListener("resize", resync);
  addEventListener("pageshow", resync);

  if (window.document$ && typeof window.document$.subscribe === "function") {
    window.document$.subscribe(init);
  } else if (document.readyState !== "loading") {
    init();
  } else {
    document.addEventListener("DOMContentLoaded", init);
  }
})();
