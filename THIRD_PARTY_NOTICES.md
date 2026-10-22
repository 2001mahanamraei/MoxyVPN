# Third-party software

MoxyVPN builds on the work of others. **None of the third-party binaries below are committed to this
repository** - `tools/fetch_deps.sh` downloads them from their official release pages at build time.
Check each upstream license before you redistribute a build.

| Component | Used for | License (verify upstream) |
|---|---|---|
| [foxyvpn](https://github.com/Vauth/FoxyVPN) by Vauth | Firefox VPN protocol client (PyPI `foxyvpn`), and the Android app that `android/rebrand_apk.py` rebrands | MIT |
| [mihomo](https://github.com/MetaCubeX/mihomo) (Clash.Meta) | Whole-system tunnel, split tunneling, HTTP proxy | **GPL-3.0** - if you distribute a build that bundles `mihomo.exe`, you must also offer its source and respect the GPL terms |
| [Wintun](https://www.wintun.net/) (`wintun.dll`) | Virtual network adapter | Wintun "Prebuilt Binaries License" (redistribution of the unmodified DLL with your software is allowed under its terms) |
| [hev-socks5-tunnel](https://github.com/heiher/hev-socks5-tunnel) | Only its release zip is used to obtain `wintun.dll` | MIT |
| [python-build-standalone](https://github.com/astral-sh/python-build-standalone) / CPython | Bundled Python runtime | PSF License |
| httpx, h2, aioquic, cryptography, cffi, pyOpenSSL, Pillow, pystray ... | Python dependencies | BSD / MIT / Apache-2.0 / HPND (see each package) |
| [Apktool](https://apktool.org/), NSIS, MinGW-w64 | Build tools only | Apache-2.0 / zlib / ZPL & GPL runtime exception |

"Firefox", "Mozilla" and "Mozilla VPN" are trademarks of the Mozilla Foundation.
MoxyVPN is an unofficial, independent project and is not affiliated with or endorsed by Mozilla.
