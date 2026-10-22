#!/usr/bin/env bash
# Builds dist/MoxyVPN-Setup.exe on Linux / WSL / macOS-with-brew (cross-compiled, no Windows needed).
# Needs: bash curl unzip tar python3 pip, mingw-w64 (x86_64-w64-mingw32-gcc + windres), makensis (NSIS)
#   Ubuntu/Debian/WSL:  sudo apt install mingw-w64 nsis unzip curl python3-pip
set -euo pipefail
cd "$(dirname "$0")/.."

for t in x86_64-w64-mingw32-gcc x86_64-w64-mingw32-windres makensis unzip tar curl python3; do
  command -v "$t" >/dev/null || { echo "missing tool: $t (see BUILDING.md)"; exit 1; }
done

VERSION="$(sed -n 's/^VERSION = "\(.*\)"/\1/p' app/moxyvpn_gui.py)"
echo "== building MoxyVPN $VERSION =="

bash tools/fetch_deps.sh

CACHE="build/cache"
STAGE="build/stage/MoxyVPN"
rm -rf build/stage build/tmp
mkdir -p "$STAGE/tun" "$STAGE/app" build/tmp dist

# 1) app sources, extension, readme
cp -r app/. "$STAGE/app/"
cp -r extension "$STAGE/extension"
cp installer/README.txt "$STAGE/README.txt"

# 2) tunnel engine + wintun driver library
unzip -q -o "$CACHE/mihomo.zip" -d build/tmp/mihomo
cp build/tmp/mihomo/*.exe "$STAGE/tun/mihomo.exe"
unzip -q -o "$CACHE/hev.zip" -d build/tmp/hev
cp build/tmp/hev/hev-socks5-tunnel/wintun.dll "$STAGE/tun/wintun.dll"

# 3) bundled Python + packages (no Python needed on the target PC)
tar xzf "$CACHE/python.tar.gz" -C "$STAGE"
SP="$STAGE/python/Lib/site-packages"
mkdir -p "$SP"
for w in "$CACHE"/wheels/*.whl; do
  case "$w" in *python_xlib*) continue;; esac     # X11 backend, not needed on Windows
  unzip -q -o "$w" -d "$SP"
done
rm -rf "$SP"/pip "$SP"/pip-*.dist-info
rm -rf "$STAGE"/python/include "$STAGE"/python/libs "$STAGE"/python/Scripts
rm -rf "$STAGE"/python/tcl/tcl8.6/tzdata
rm -rf "$STAGE"/python/Lib/test "$STAGE"/python/Lib/idlelib "$STAGE"/python/Lib/turtledemo \
       "$STAGE"/python/Lib/lib2to3 "$STAGE"/python/Lib/ensurepip
find "$STAGE" -name __pycache__ -prune -exec rm -rf {} +

# 4) MoxyVPN.exe launcher (fox icon + "run as administrator" manifest)
( cd launcher && x86_64-w64-mingw32-windres launcher.rc -O coff -o ../build/tmp/launcher_res.o )
x86_64-w64-mingw32-gcc -Os -s -mwindows launcher/launcher.c build/tmp/launcher_res.o -o "$STAGE/MoxyVPN.exe"

# 5) installer
makensis -V2 -DVERSION="$VERSION" -DSTAGE="$(pwd)/$STAGE" installer/installer.nsi

echo "== done: dist/MoxyVPN-Setup.exe =="
ls -lh dist/MoxyVPN-Setup.exe
