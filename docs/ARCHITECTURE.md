# Architecture

```
 Firefox account (email + password)
        |  fxa.login -> OAuth token            (app/moxyvpn_gui.py, python package "foxyvpn")
        v
 Guardian API  -> short-lived proxy pass (JWT) + quota headers + entitlement
        v
 python -m foxyvpn  = local SOCKS5 proxy  127.0.0.1:<port>
        |   speaks HTTP/2 CONNECT with "Proxy-Authorization: Bearer <pass>" to Mozilla's edge
        v
 mihomo (optional)   - TUN adapter (Wintun)  -> whole-system tunnel + DNS hijack (fake-ip)
                     - mixed port            -> local HTTP proxy
                     - rules: split tunneling, .ir direct, python.exe direct (avoids a loop)
```

| File | Role |
|---|---|
| `app/moxyvpn_gui.py` | Main window, tray, connection control, login view, local control API (`127.0.0.1:47832`) |
| `app/settings_ui.py` | Slide-in Settings page, account dialog, prompts |
| `app/tunconf.py` | Generates the mihomo YAML (tun, dns, rules, upstream chaining) |
| `app/usage.py` | Reads quota/plan/email, caches them in `%APPDATA%\MoxyVPN\state.json` |
| `app/theme.py` | Dark/light palettes |
| `launcher/` | `MoxyVPN.exe`: sets TCL/TK paths, starts the bundled `pythonw.exe` elevated |
| `extension/` | MV3 extension: PAC script -> `SOCKS5 127.0.0.1:<port>`, usage view, per-site mode |

## Why the browser extension is not standalone
Mozilla's proxy only accepts `Proxy-Authorization: Bearer ...` (and answers `400`, not `407`, without it).
Chrome extensions can only supply Basic/Digest proxy credentials after a `407` challenge, so the extension
talks to the desktop app instead. `tools/proxy_auth_test.py` reproduces this check.

## Local control API (used by the extension)
`GET /status`, `POST /connect|/disconnect|/refresh` on `127.0.0.1:47832`. Requests must carry the right
`Host`, POSTs must come from a `chrome-extension://` origin and send `X-Moxy-Client: 1`, so ordinary web
pages cannot control the VPN.
