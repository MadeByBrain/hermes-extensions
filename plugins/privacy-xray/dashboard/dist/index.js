/**
 * Privacy X-ray: dashboard tab with the live leak map.
 *
 * Plain IIFE, no build step. Polls /api/plugins/privacy-xray/report every 15 s and redraws the
 * self-contained report (inline CSS + SVG, no scripts) in a fully sandboxed iframe, only when its
 * content changed. Uses window.__HERMES_PLUGIN_SDK__ for React and fetchJSON (auth header).
 */
(function () {
  "use strict";

  var SDK = window.__HERMES_PLUGIN_SDK__;
  var REG = window.__HERMES_PLUGINS__;
  if (!SDK || !REG) return;

  var React = SDK.React;
  var h = React.createElement;
  var useState = SDK.hooks.useState;
  var useEffect = SDK.hooks.useEffect;
  var useRef = SDK.hooks.useRef;
  var C = SDK.components || {};
  var REFRESH_MS = 15000;
  var API = "/api/plugins/privacy-xray/report";

  function clock(ts) {
    if (!ts) return "";
    var d = new Date(ts);
    function p(n) { return (n < 10 ? "0" : "") + n; }
    return p(d.getHours()) + ":" + p(d.getMinutes()) + ":" + p(d.getSeconds());
  }

  function LeakMap() {
    var st = useState({ html: "", sig: "", error: "", checked: 0, lang: "" });
    var state = st[0];
    var setState = st[1];
    var sigRef = useRef("");
    var tick = useState(0);

    useEffect(function () {
      var alive = true;
      function load() {
        SDK.fetchJSON(API).then(function (r) {
          if (!alive) return;
          if (r && r.ok) {
            var changed = r.sig !== sigRef.current;
            sigRef.current = r.sig;
            setState(function (prev) {
              return {
                html: changed ? r.html : prev.html, sig: r.sig, error: "",
                checked: Date.now(), lang: r.lang || prev.lang
              };
            });
          } else {
            setState(function (prev) {
              return Object.assign({}, prev, { error: (r && r.error) || "error", checked: Date.now() });
            });
          }
        }).catch(function (err) {
          if (!alive) return;
          setState(function (prev) {
            return Object.assign({}, prev, { error: String((err && err.message) || err), checked: Date.now() });
          });
        });
      }
      load();
      var timer = setInterval(load, REFRESH_MS);
      return function () { alive = false; clearInterval(timer); };
    }, [tick[0]]);

    var de = state.lang === "de";
    var live = h("span", {
      style: {
        display: "inline-block", width: 9, height: 9, borderRadius: 9, marginRight: 8,
        background: state.error ? "#ff3d6e" : "#2ee59d",
        boxShadow: "0 0 10px " + (state.error ? "#ff3d6e" : "#2ee59d")
      }
    });
    var status = state.error
      ? (de ? "Fehler: " : "Error: ") + state.error
      : (de ? "Live, alle 15 s geprüft" : "Live, checked every 15 s") +
        (state.checked ? (de ? ", zuletzt " : ", last ") + clock(state.checked) : "");
    var Btn = C.Button || "button";
    var bar = h("div", {
      className: "flex items-center justify-between gap-3",
      style: { marginBottom: 10 }
    },
      h("div", { className: "text-sm text-muted-foreground", style: { display: "flex", alignItems: "center" } },
        live, status),
      h(Btn, {
        onClick: function () { sigRef.current = ""; tick[1](tick[0] + 1); },
        className: C.Button ? undefined : "text-sm"
      }, de ? "Neu laden" : "Refresh"));

    var body = state.html
      ? h("iframe", {
        title: "Privacy X-ray leak map",
        srcDoc: state.html,
        sandbox: "",
        referrerPolicy: "no-referrer",
        style: {
          width: "100%", height: "calc(100vh - 170px)", minHeight: 560, border: 0,
          borderRadius: 16, background: "#05070d", display: "block"
        }
      })
      : h("div", { className: "text-sm text-muted-foreground", style: { padding: 24 } },
        state.error ? status : (de ? "Lade die Datenfluss-Karte ..." : "Loading the leak map ..."));

    return h("div", { style: { padding: "4px 0" } }, bar, body);
  }

  REG.register("privacy-xray", LeakMap);
})();
