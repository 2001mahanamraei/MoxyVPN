#!/usr/bin/env bash
# Downloads everything that is NOT committed to git into build/cache/.
# Needs: bash, curl, python3 with pip.
set -euo pipefail
cd "$(dirname "$0")/.."

MIHOMO_VERSION="v1.19.32"        # tunnel engine (GPL-3.0, downloaded - never committed)
HEV_VERSION="2.19.0"             # only used to get wintun.dll
PY_TAG="20261013"                # python-build-standalone release
PY_VER="3.12.15"

CACHE="build/cache"
mkdir -p "$CACHE"

fetch() {  # url out
  if [ ! -s "$2" ]; then
    echo "-> downloading $(basename "$2")"
    curl -fL --retry 3 -o "$2" "$1"
  fi
}

fetch "https://github.com/MetaCubeX/mihomo/releases/download/${MIHOMO_VERSION}/mihomo-windows-amd64-v1-${MIHOMO_VERSION}.zip" "$CACHE/mihomo.zip"
fetch "https://github.com/heiher/hev-socks5-tunnel/releases/download/${HEV_VERSION}/hev-socks5-tunnel-win64.zip" "$CACHE/hev.zip"
fetch "https://github.com/astral-sh/python-build-standalone/releases/download/${PY_TAG}/cpython-${PY_VER}%2B${PY_TAG}-x86_64-pc-windows-msvc-install_only_stripped.tar.gz" "$CACHE/python.tar.gz"

if [ ! -d "$CACHE/wheels" ]; then
  echo "-> downloading Windows wheels (cp312, win_amd64)"
  mkdir -p "$CACHE/wheels"
  python3 -m pip download -q --only-binary=:all: --platform win_amd64 --python-version 3.12 \
    --implementation cp --abi cp312 --abi abi3 --abi none -d "$CACHE/wheels" -r requirements.txt
fi
echo "dependencies ready in $CACHE"
