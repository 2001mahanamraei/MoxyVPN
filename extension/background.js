// MoxyVPN extension - service worker.
// Points Chrome at the local MoxyVPN SOCKS5 proxy (127.0.0.1:<port>) with a PAC script.

const API = "http://127.0.0.1:47832";
const DEFAULTS = {
  enabled: false,
  port: 1080,
  mode: "all",          // "all" | "selected"
  sites: [],            // used when mode === "selected"
  bypassIr: true,       // .ir sites go direct
  bypassExtra: [],      // extra domains that always go direct
  failClosed: true      // block traffic if the proxy is down (no leaks)
};

async function getCfg() {
  return { ...DEFAULTS, ...(await chrome.storage.local.get(DEFAULTS)) };
}

function cleanDomain(d) {
  return String(d || "").trim().toLowerCase()
    .replace(/^[a-z]+:\/\//, "").replace(/^\*\./, "").replace(/^\./, "")
    .split(/[\/:?#]/)[0];
}

function buildPac(cfg) {
  const direct = ["localhost"];
  if (cfg.bypassIr) direct.push("ir");
  for (const d of cfg.bypassExtra.map(cleanDomain)) if (d) direct.push(d);
  const sites = cfg.sites.map(cleanDomain).filter(Boolean);
  const port = Number(cfg.port) || 1080;
  const proxy = "SOCKS5 127.0.0.1:" + port + (cfg.failClosed ? "" : "; DIRECT");
  return `function FindProxyForURL(url, host) {
  host = host.toLowerCase();
  var DIRECT_LIST = ${JSON.stringify(direct)};
  var SITES = ${JSON.stringify(sites)};
  var MODE = ${JSON.stringify(cfg.mode)};
  function inList(list) {
    for (var i = 0; i < list.length; i++) {
      var d = list[i];
      if (host === d) return true;
      if (host.length > d.length && host.substr(host.length - d.length - 1) === "." + d) return true;
    }
    return false;
  }
  if (isPlainHostName(host)) return "DIRECT";
  if (/^\\d{1,3}(\\.\\d{1,3}){3}$/.test(host)) {
    if (isInNet(host, "10.0.0.0", "255.0.0.0") || isInNet(host, "172.16.0.0", "255.240.0.0") ||
        isInNet(host, "192.168.0.0", "255.255.0.0") || isInNet(host, "127.0.0.0", "255.0.0.0") ||
        isInNet(host, "169.254.0.0", "255.255.0.0")) return "DIRECT";
  }
  if (inList(DIRECT_LIST)) return "DIRECT";
  if (MODE === "selected" && !inList(SITES)) return "DIRECT";
  return ${JSON.stringify(proxy)};
}`;
}

function setIcon(on) {
  const p = on ? "moxy" : "gray";
  chrome.action.setIcon({
    path: { 16: `icons/${p}-16.png`, 32: `icons/${p}-32.png`, 48: `icons/${p}-48.png`, 128: `icons/${p}-128.png` }
  });
}

async function applyProxy() {
  const cfg = await getCfg();
  if (cfg.enabled) {
    await chrome.proxy.settings.set({
      value: { mode: "pac_script", pacScript: { data: buildPac(cfg) } },
      scope: "regular"
    });
    try {
      // SOCKS5 has no UDP: stop WebRTC from leaking the real IP.
      await chrome.privacy.network.webRTCIPHandlingPolicy.set({ value: "disable_non_proxied_udp" });
    } catch (e) { /* ignore */ }
    chrome.action.setBadgeBackgroundColor({ color: "#35D69A" });
    chrome.action.setBadgeText({ text: "ON" });
  } else {
    await chrome.proxy.settings.clear({ scope: "regular" });
    try { await chrome.privacy.network.webRTCIPHandlingPolicy.clear({}); } catch (e) { /* ignore */ }
    chrome.action.setBadgeText({ text: "" });
  }
  setIcon(cfg.enabled);
}

async function health() {
  const cfg = await getCfg();
  if (!cfg.enabled) return;
  try {
    const r = await fetch(API + "/status", { cache: "no-store" });
    const s = await r.json();
    if (s.state !== "on") {
      chrome.action.setBadgeBackgroundColor({ color: "#FF5C6C" });
      chrome.action.setBadgeText({ text: "!" });
    } else {
      chrome.action.setBadgeBackgroundColor({ color: "#35D69A" });
      chrome.action.setBadgeText({ text: "ON" });
    }
  } catch (e) { /* app not reachable: keep current badge */ }
}

chrome.runtime.onInstalled.addListener(async () => {
  const cur = await chrome.storage.local.get(null);
  await chrome.storage.local.set({ ...DEFAULTS, ...cur });
  chrome.alarms.create("health", { periodInMinutes: 1 });
  applyProxy();
});
chrome.runtime.onStartup.addListener(() => {
  chrome.alarms.create("health", { periodInMinutes: 1 });
  applyProxy();
});
chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "local" && Object.keys(changes).some((k) => k in DEFAULTS)) applyProxy();
});
chrome.alarms.onAlarm.addListener((a) => { if (a.name === "health") health(); });
