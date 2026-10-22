const API = "http://127.0.0.1:47832";
const DEFAULTS = {
  enabled: false, port: 1080, mode: "all", sites: [],
  bypassIr: true, bypassExtra: [], failClosed: true
};
const $ = (id) => document.getElementById(id);
let cfg = { ...DEFAULTS };
let app = null;                       // last /status from the desktop app (or null)
let exit = { at: 0, data: undefined }; // cached exit-IP check

// ---------- helpers ----------
const lines = (t) => t.split(/\n/).map((x) => x.trim()).filter(Boolean);
function fmtBytes(n) {
  if (n == null) return "-";
  const gb = n / 1024 ** 3;
  if (gb >= 1) return gb >= 100 ? gb.toFixed(0) + " GB" : gb.toFixed(2) + " GB";
  return Math.round(n / 1024 ** 2) + " MB";
}
function fmtReset(ts) {
  if (!ts) return "";
  const d = new Date(ts * 1000);
  const days = Math.ceil((d - Date.now()) / 86400000);
  const when = d.toLocaleDateString("en", { month: "short", day: "numeric" });
  return "resets " + when + (days > 0 ? ` (${days}d)` : "");
}
async function save(patch) {
  cfg = { ...cfg, ...patch };
  await chrome.storage.local.set(patch);
}
async function getApp() {
  try {
    const r = await fetch(API + "/status", { cache: "no-store" });
    return r.ok ? await r.json() : null;
  } catch (e) { return null; }
}
async function appPost(path) {
  try { await fetch(API + path, { method: "POST", headers: { "X-Moxy-Client": "1" } }); } catch (e) { /* ignore */ }
}
async function checkExit(force) {
  if (!cfg.enabled) return null;
  if (!force && Date.now() - exit.at < 20000) return exit.data;
  try {
    const ctl = new AbortController();
    const t = setTimeout(() => ctl.abort(), 7000);
    const r = await fetch("https://www.cloudflare.com/cdn-cgi/trace", { cache: "no-store", signal: ctl.signal });
    clearTimeout(t);
    const kv = Object.fromEntries((await r.text()).split("\n").map((l) => l.split("=")).filter((a) => a.length === 2));
    exit = { at: Date.now(), data: { loc: kv.loc, ip: kv.ip } };
  } catch (e) {
    exit = { at: Date.now(), data: null };
  }
  return exit.data;
}

// ---------- rendering ----------
function render() {
  const power = $("power"), title = $("title"), sub = $("sub");
  power.className = "power"; title.className = "";
  if (!cfg.enabled) {
    power.classList.add("off"); title.textContent = "Disconnected";
    sub.textContent = "Tap the power button";
  } else if (exit.data === undefined) {
    power.classList.add("connecting"); title.textContent = "Checking...";
    sub.textContent = "Testing the connection";
  } else if (exit.data) {
    power.classList.add("on"); title.classList.add("on"); title.textContent = "Protected";
    sub.textContent = `Exit: ${exit.data.loc || "?"}  \u2022  ${exit.data.ip || ""}`;
  } else {
    power.classList.add("bad"); title.classList.add("bad"); title.textContent = "Proxy not responding";
    sub.textContent = app ? "Press Connect on the MoxyVPN app row below"
                          : "Start the MoxyVPN app, then tap again";
  }

  const st = $("appState"), btnRow = $("appBtnRow");
  if (!app) {
    st.textContent = "not detected"; st.className = "val bad";
    btnRow.hidden = false; $("appBtn").hidden = true;
    $("appHint").textContent = "Open MoxyVPN on this PC (proxy 127.0.0.1:" + cfg.port + ")";
  } else {
    const label = { on: "Connected", connecting: "Connecting...", off: "Disconnected" }[app.state] || app.state;
    st.textContent = label; st.className = "val " + (app.state === "on" ? "good" : "");
    btnRow.hidden = false; $("appBtn").hidden = false;
    $("appHint").textContent = app.signed_in ? "" : "Sign in inside the app first";
    $("appBtn").textContent = app.state === "off" ? "Connect" : "Disconnect";
    $("appBtn").disabled = !app.signed_in && app.state === "off";
  }

  const u = app && app.usage;
  $("usageCard").hidden = !(u && u.used != null);
  if (u && u.used != null) {
    $("used").textContent = fmtBytes(u.used);
    $("of").textContent = u.limit ? "of " + fmtBytes(u.limit) : "";
    const frac = u.limit ? Math.min(u.used / u.limit, 1) : 0;
    $("barFill").style.width = Math.max(frac * 100, frac > 0 ? 3 : 0) + "%";
    $("barFill").classList.toggle("hot", frac >= 0.9);
    $("usageLine").textContent = [u.left != null ? fmtBytes(u.left) + " left" : "", fmtReset(u.reset)]
      .filter(Boolean).join("  \u2022  ");
  }

  document.querySelectorAll("#modeSeg button").forEach((b) => b.classList.toggle("active", b.dataset.mode === cfg.mode));
  $("sitesBox").hidden = cfg.mode !== "selected";
}

function fillSettings() {
  $("sites").value = cfg.sites.join("\n");
  $("bypassIr").checked = cfg.bypassIr;
  $("failClosed").checked = cfg.failClosed;
  $("bypassExtra").value = cfg.bypassExtra.join("\n");
  $("port").value = cfg.port;
}

async function refresh(forceExit) {
  app = await getApp();
  if (app && app.port && app.port !== cfg.port) { await save({ port: app.port }); $("port").value = cfg.port; }
  render();
  if (cfg.enabled) { await checkExit(forceExit); render(); }
}

// ---------- events ----------
$("power").onclick = async () => {
  if (!cfg.enabled) {
    exit = { at: 0, data: undefined };
    await save({ enabled: true });
    render();
    const a = await getApp();
    if (a && a.signed_in && a.state === "off") await appPost("/connect");
    setTimeout(() => refresh(true), a && a.state === "off" ? 4000 : 400);
  } else {
    await save({ enabled: false });
    exit = { at: 0, data: undefined };
    refresh();
  }
};
$("appBtn").onclick = async () => {
  await appPost(app && app.state === "off" ? "/connect" : "/disconnect");
  setTimeout(() => refresh(true), 1500);
};
$("refresh").onclick = async () => { await appPost("/refresh"); setTimeout(refresh, 2500); };
document.querySelectorAll("#modeSeg button").forEach((b) => {
  b.onclick = async () => { await save({ mode: b.dataset.mode }); render(); };
});
$("sites").onchange = () => save({ sites: lines($("sites").value) });
$("bypassExtra").onchange = () => save({ bypassExtra: lines($("bypassExtra").value) });
$("bypassIr").onchange = () => save({ bypassIr: $("bypassIr").checked });
$("failClosed").onchange = () => save({ failClosed: $("failClosed").checked });
$("port").onchange = async () => {
  const p = parseInt($("port").value, 10);
  if (p >= 1 && p <= 65535) { await save({ port: p }); exit = { at: 0, data: undefined }; refresh(true); }
};
$("addSite").onclick = async () => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  try {
    const host = new URL(tab.url).hostname.replace(/^www\./, "");
    if (host && !cfg.sites.includes(host)) await save({ sites: [...cfg.sites, host] });
    fillSettings();
  } catch (e) { /* not a web page */ }
};

// ---------- start ----------
(async () => {
  cfg = { ...DEFAULTS, ...(await chrome.storage.local.get(DEFAULTS)) };
  fillSettings();
  render();
  refresh();
  setInterval(() => refresh(), 3000);
})();
