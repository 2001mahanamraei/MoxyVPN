# Building MoxyVPN

Everything is cross-compiled from Linux, so you never need Visual Studio. On Windows use **WSL**
(`wsl --install` in an admin PowerShell, then open "Ubuntu").

## 1. Windows installer (`MoxyVPN-Setup.exe`)

```bash
sudo apt update
sudo apt install -y mingw-w64 nsis unzip curl python3-pip git
git clone https://github.com/<you>/MoxyVPN.git && cd MoxyVPN
bash tools/build_windows.sh
```
Result: `dist/MoxyVPN-Setup.exe` (about 31 MB). The script

1. downloads (and caches in `build/cache/`) mihomo, wintun.dll, a standalone Python 3.12 and the Windows wheels from `requirements.txt`;
2. assembles `build/stage/MoxyVPN/` (app, bundled Python, tunnel engine, extension);
3. compiles `launcher/launcher.c` into `MoxyVPN.exe` with the fox icon and an admin manifest;
4. builds the installer with NSIS.

### Without installing anything: GitHub Actions
Push the repo, open **Actions -> Build Windows installer -> Run workflow**, then download the
`MoxyVPN-Setup` artifact. Pushing a tag such as `v1.3.0` also attaches the installer to a Release.

## 2. Android APK

```bash
sudo apt install -y apktool zipalign apksigner default-jre-headless
pip install pillow
python3 android/rebrand_apk.py          # -> dist/MoxyVPN.apk
```
A signing key is created in `android/moxyvpn.keystore` the first time. **Back it up and never commit
it** (it is in `.gitignore`); you need the same key for every future update.

## 3. Chrome extension
No build step: open `chrome://extensions`, enable *Developer mode*, *Load unpacked*, choose `extension/`.
To publish on the Chrome Web Store zip the contents of `extension/`.

## 4. Change things
| I want to... | Edit |
|---|---|
| change the version | `VERSION` in `app/moxyvpn_gui.py` (installer picks it up) |
| change the app name / colors | `APP_NAME`, `app/theme.py`, `installer/installer.nsi` |
| change the icon | edit `tools/make_icon.py`, run it, rebuild |
| change tunnel rules or DNS | `app/tunconf.py` |
| change a setting's default | `DEFAULT_SETTINGS` in `app/moxyvpn_gui.py` |
| update mihomo / Python | version variables at the top of `tools/fetch_deps.sh` |

## Troubleshooting
- `missing tool: x86_64-w64-mingw32-gcc` -> install `mingw-w64`.
- Download fails -> the script resumes; re-run it.
- Windows SmartScreen warns on your build: the installer is not code-signed (a certificate costs money).
