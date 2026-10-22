<p align="center"><img src="branding/moxy_1024.png" width="140" alt="MoxyVPN fox"></p>

# MoxyVPN

An unofficial desktop client for the VPN that comes with a Firefox / Mozilla VPN account.
Sign in with your own account and route either **the whole PC** or **selected apps** through it, or
just use the local SOCKS5 / HTTP proxy.

> **Disclaimer** - MoxyVPN is an independent, unofficial project. It is not affiliated with Mozilla.
> Use it only with your own account and in line with Mozilla's terms. Mozilla may change or block
> third-party access at any time. No warranty.

## Features

- Email + password sign-in (with email / authenticator code step), tokens stored locally, password never saved
- **Whole-system tunnel** (Wintun + mihomo) or **proxy-only mode** (SOCKS5 + optional HTTP proxy)
- **Split tunneling**: bypass chosen apps, or send only chosen apps through the VPN
- Dark / light / follow-system theme, system-tray icon, single-instance
- Account email, plan and **data usage** (used / limit / reset date), remembered between runs
- Settings: verify exit location, encrypted DNS (DoH) / custom DNS, local address & port, custom edge
  address, upstream-proxy chaining, sign-in proxy (for networks where Firefox Accounts is blocked)
- Chrome / Edge **extension** that connects the browser and shows usage (needs the desktop app)
- Android build: `android/rebrand_apk.py` rebrands the official open-source FoxyVPN APK

## Download / build

Pre-built installer: see **Releases**. To build it yourself (no Windows required) read
[BUILDING.md](BUILDING.md) (Persian: [BUILDING.fa.md](BUILDING.fa.md)). In short:

```bash
sudo apt install mingw-w64 nsis unzip curl python3-pip     # Ubuntu / Debian / WSL
bash tools/build_windows.sh                                # -> dist/MoxyVPN-Setup.exe
```

or push a tag (`git tag v1.3.0 && git push --tags`) and let GitHub Actions build and attach it.

## Repository layout

| Path | What it is |
|---|---|
| `app/` | The Windows app (Python + Tkinter): UI, settings, usage, tunnel config |
| `launcher/` | Tiny C launcher -> `MoxyVPN.exe` (fox icon, asks for Administrator) |
| `installer/` | NSIS installer script |
| `extension/` | Chrome / Edge extension (Manifest V3) |
| `android/` | Script that rebrands the open-source FoxyVPN APK |
| `tools/` | Build scripts, icon generator, proxy-auth diagnostic |
| `branding/` | Source artwork |
| `docs/` | Architecture notes |

## Run from source (Windows)

```powershell
py -3.12 -m pip install -r requirements.txt
# put mihomo.exe and wintun.dll into the tun\ folder if you want the whole-system tunnel
py -3.12 app\moxyvpn_gui.py --tun
```

## License

MIT for this project's own code - see [LICENSE](LICENSE). Third-party components and their licenses
(notably **mihomo: GPL-3.0**): [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
