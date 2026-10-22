#!/usr/bin/env python3
"""Rebrand the official FoxyVPN Android APK (MIT) as "MoxyVPN": new name + fox icon, signed with YOUR key.

Needs on PATH: java, apktool, zipalign, apksigner, keytool      (Ubuntu: sudo apt install apktool zipalign apksigner default-jre-headless)
Needs Python:  pip install pillow
Run:           python3 android/rebrand_apk.py            ->  dist/MoxyVPN.apk
The signing key is created once in android/moxyvpn.keystore (password in android/keystore-password.txt).
KEEP BOTH FILES PRIVATE and back them up: you need the same key to publish updates.
"""
import argparse
import glob
import hashlib
import os
import re
import secrets
import shutil
import struct
import subprocess
import urllib.request
import zlib

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_URL = "https://github.com/Vauth/FoxyVPN/releases/download/v1.0.7/app-release.apk"
WORK = os.path.join(ROOT, "build", "android")


def run(*cmd):
    subprocess.run(cmd, check=True)


def ensure_keystore(path, pass_file):
    if os.path.exists(path):
        return open(pass_file).read().strip()
    pw = secrets.token_urlsafe(12)
    run("keytool", "-genkeypair", "-keystore", path, "-alias", "moxyvpn", "-keyalg", "RSA", "-keysize", "4096",
        "-validity", "10000", "-storepass", pw, "-keypass", pw, "-dname", "CN=MoxyVPN")
    with open(pass_file, "w") as f:
        f.write(pw + "\n")
    print(f"created new signing key: {path}  (password saved in {pass_file})")
    return pw


def patch_dex(path):
    """Replace the UI name inside classes.dex (same length, so offsets stay valid) and fix the checksums."""
    data = bytearray(open(path, "rb").read())
    count = 0
    for m in re.finditer(rb"FoxyVPN", bytes(data)):
        i = m.start()
        if bytes(data[max(0, i - 13):i]) == b"Proxy-Agent: ":   # keep the network header untouched
            continue
        data[i:i + 7] = b"MoxyVPN"
        count += 1
    data[12:32] = hashlib.sha1(bytes(data[32:])).digest()
    data[8:12] = struct.pack("<I", zlib.adler32(bytes(data[12:])) & 0xFFFFFFFF)
    open(path, "wb").write(bytes(data))
    return count


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apk-url", default=DEFAULT_URL)
    ap.add_argument("--out", default=os.path.join(ROOT, "dist", "MoxyVPN.apk"))
    ap.add_argument("--keystore", default=os.path.join(ROOT, "android", "moxyvpn.keystore"))
    a = ap.parse_args()
    pass_file = os.path.join(os.path.dirname(a.keystore), "keystore-password.txt")

    shutil.rmtree(WORK, ignore_errors=True)
    os.makedirs(WORK)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    src, dec = os.path.join(WORK, "original.apk"), os.path.join(WORK, "dec")
    print("downloading", a.apk_url)
    urllib.request.urlretrieve(a.apk_url, src)

    run("apktool", "d", "-f", "-s", src, "-o", dec)

    # 1) visible name (resources)
    for f in glob.glob(f"{dec}/res/values*/*.xml"):
        s = open(f, encoding="utf-8").read()
        if "FoxyVPN" in s:
            open(f, "w", encoding="utf-8").write(s.replace("FoxyVPN", "MoxyVPN"))

    # 2) launcher icon: fox with "M" inside the adaptive-icon safe zone
    fox = Image.open(os.path.join(ROOT, "branding", "moxy_1024.png")).convert("RGBA")
    os.remove(f"{dec}/res/drawable/ic_launcher_foreground.xml")
    for dens, px in (("mdpi", 108), ("hdpi", 162), ("xhdpi", 216), ("xxhdpi", 324), ("xxxhdpi", 432)):
        canvas = Image.new("RGBA", (px, px), (0, 0, 0, 0))
        size = int(px * 0.60)
        small = fox.resize((size, size), Image.LANCZOS)
        canvas.paste(small, ((px - size) // 2, (px - size) // 2), small)
        d = f"{dec}/res/drawable-{dens}"
        os.makedirs(d, exist_ok=True)
        canvas.save(f"{d}/ic_launcher_foreground.png")

    # 3) names compiled into the code
    print("dex strings changed:", patch_dex(f"{dec}/classes.dex"))

    # 4) rebuild, align, sign
    unsigned, aligned = os.path.join(WORK, "unsigned.apk"), os.path.join(WORK, "aligned.apk")
    run("apktool", "b", dec, "-o", unsigned)
    run("zipalign", "-p", "-f", "4", unsigned, aligned)
    pw = ensure_keystore(a.keystore, pass_file)
    run("apksigner", "sign", "--ks", a.keystore, "--ks-key-alias", "moxyvpn", "--ks-pass", f"pass:{pw}",
        "--key-pass", f"pass:{pw}", "--v2-signing-enabled", "true", "--v3-signing-enabled", "true",
        "--out", a.out, aligned)
    run("apksigner", "verify", a.out)
    print("done:", a.out)


if __name__ == "__main__":
    main()
