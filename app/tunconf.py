"""Builds the mihomo (Clash.Meta) config used for the whole-system tunnel and the HTTP proxy."""
import json
from urllib.parse import unquote, urlparse

# Fallback plain DNS (also used to resolve DoH/upstream host names).
BOOTSTRAP_DNS = ["8.8.8.8", "1.1.1.1"]

# DNS used by mihomo itself for DIRECT traffic (foxyvpn's own connections, .ir sites, bypassed apps).
DNS_PRESETS = {
    "auto": ["https://1.1.1.1/dns-query", "https://8.8.8.8/dns-query", "1.1.1.1", "8.8.8.8"],
    "cloudflare": ["https://1.1.1.1/dns-query"],
    "google": ["https://8.8.8.8/dns-query"],
    "quad9": ["https://9.9.9.9/dns-query"],
    "off": ["8.8.8.8", "1.1.1.1"],
}

# Domain suffixes that skip the VPN and go out directly.
DIRECT_SUFFIXES = ["ir"]

# Domains that must resolve to real IPs (never fake IPs).
REAL_IP_DOMAINS = [
    "+.mozilla.org", "+.mozilla.com", "+.mozilla.net", "+.firefox.com",
    "+.fastly-masque.net", "+.ir", "+.lan", "+.local", "+.localhost",
]


def q(text):
    """JSON strings are valid YAML double-quoted strings."""
    return json.dumps(text)


def parse_upstream(url):
    """'socks5://user:pass@host:1080' / 'http://host:8080' -> mihomo proxy dict (or None)."""
    try:
        u = urlparse(url.strip())
        if u.scheme not in ("socks5", "socks5h", "socks", "http", "https") or not u.hostname or not u.port:
            return None
        p = {"name": "upstream", "type": "socks5" if u.scheme.startswith("socks") else "http",
             "server": u.hostname, "port": u.port}
        if u.username:
            p["username"] = unquote(u.username)
            p["password"] = unquote(u.password or "")
        if u.scheme == "https":
            p["tls"] = True
        return p
    except ValueError:
        return None


def dns_servers(opts):
    if opts.get("custom_dns_on") and opts.get("custom_dns", "").strip():
        items = [x for x in opts["custom_dns"].replace(",", " ").split() if x]
        if items:
            return items
    return DNS_PRESETS.get(opts.get("dns_mode", "auto"), DNS_PRESETS["auto"])


def build(port, python_paths, split_mode="off", split_apps=(), opts=None):
    """opts: tun(bool), http_port(int|0), lan(bool), socks_host, dns_mode, custom_dns_on,
    custom_dns, upstream(str)"""
    opts = opts or {}
    tun = opts.get("tun", True)
    http_port = int(opts.get("http_port") or 0)
    lan = bool(opts.get("lan"))
    upstream = parse_upstream(opts["upstream"]) if opts.get("upstream") else None
    py_target = "upstream" if (upstream and tun) else "DIRECT"

    out = [
        "mode: rule",
        "log-level: info",
        "ipv6: false",
        f"allow-lan: {'true' if lan else 'false'}",
        "find-process-mode: always",
    ]
    if http_port:
        bind = "'*'" if lan else "127.0.0.1"
        out += [f"mixed-port: {http_port}", f"bind-address: {bind}"]
    if tun:
        out += [
            "tun:",
            "  enable: true",
            "  device: MoxyTun",
            "  stack: mixed",
            "  auto-route: true",
            "  auto-detect-interface: true",
            "  strict-route: false",
            "  dns-hijack:",
            "    - any:53",
            "    - tcp://any:53",
        ]
    out += [
        "dns:",
        "  enable: true",
        "  ipv6: false",
        f"  enhanced-mode: {'fake-ip' if tun else 'normal'}",
    ]
    if tun:
        out += ["  fake-ip-range: 198.18.0.1/16", "  fake-ip-filter:"]
        out += [f"    - {q(d)}" for d in REAL_IP_DOMAINS]
    out += ["  default-nameserver:"] + [f"    - {s}" for s in BOOTSTRAP_DNS]
    out += ["  nameserver:"] + [f"    - {q(s)}" for s in dns_servers(opts)]

    out += [
        "proxies:",
        "  - name: foxy",
        "    type: socks5",
        f"    server: {opts.get('socks_host', '127.0.0.1')}",
        f"    port: {int(port)}",
        "    udp: false",
    ]
    if upstream:
        out.append("  - name: upstream")
        for k, v in upstream.items():
            if k == "name":
                continue
            out.append(f"    {k}: {q(v) if isinstance(v, str) else (str(v).lower() if isinstance(v, bool) else v)}")
    out.append("rules:")

    rules = []
    # foxyvpn's own traffic must NOT enter the tunnel (it would loop).
    for p in python_paths:
        rules.append(f"PROCESS-PATH,{p},{py_target}")
    rules += [
        f"PROCESS-NAME,python.exe,{py_target}",
        f"PROCESS-NAME,pythonw.exe,{py_target}",
        "PROCESS-NAME,mihomo.exe,DIRECT",
    ]
    apps = [a for a in split_apps if a and "," not in a]
    if split_mode == "exclude":            # these apps skip the VPN
        rules += [f"PROCESS-NAME,{a},DIRECT" for a in apps]
    rules += [
        "IP-CIDR,127.0.0.0/8,DIRECT,no-resolve",
        "IP-CIDR,10.0.0.0/8,DIRECT,no-resolve",
        "IP-CIDR,172.16.0.0/12,DIRECT,no-resolve",
        "IP-CIDR,192.168.0.0/16,DIRECT,no-resolve",
        "IP-CIDR,169.254.0.0/16,DIRECT,no-resolve",
        "IP-CIDR,224.0.0.0/4,DIRECT,no-resolve",
        "IP-CIDR,255.255.255.255/32,DIRECT,no-resolve",
    ]
    rules += [f"DOMAIN-SUFFIX,{s},DIRECT" for s in DIRECT_SUFFIXES]
    if split_mode == "include" and tun:    # only these apps use the VPN
        rules += [f"PROCESS-NAME,{a},foxy" for a in apps]
        rules.append("MATCH,DIRECT")
    else:
        rules.append("MATCH,foxy")
    out += [f"  - {q(r)}" for r in rules]
    return "\n".join(out) + "\n"
