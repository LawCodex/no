#!/usr/bin/env python3
"""Download Lovdata's free public bulk datasets (NLOD 2.0) and extract them.

Usage: python fetch.py [RAW_DIR]   (default: ../../_raw/no relative to this script)

Downloads gjeldende-lover.tar.bz2 and gjeldende-sentrale-forskrifter.tar.bz2 from
https://api.lovdata.no/v1/publicData/ into RAW_DIR/dl/, verifies the bzip2 stream and
extracts them into RAW_DIR/ex/ (subdirs nl/, sf/, del/, ins/, stv/).
"""
import bz2
import os
import sys
import tarfile
import time

import requests

API = "https://api.lovdata.no/v1/publicData"
FILES = ["gjeldende-lover.tar.bz2", "gjeldende-sentrale-forskrifter.tar.bz2"]
UA = {"User-Agent": "LawCodex/1.0 (+https://github.com/LawCodex)"}


def verify(path):
    try:
        with bz2.open(path) as f:
            while f.read(1 << 20):
                pass
        return True
    except Exception:
        return False


def download(name, dest, force=False):
    if os.path.exists(dest) and not force and verify(dest):
        print("cached", dest)
        return
    for attempt in range(5):
        try:
            with requests.get(f"{API}/get/{name}", headers=UA, stream=True, timeout=120) as r:
                r.raise_for_status()
                with open(dest + ".part", "wb") as f:
                    for chunk in r.iter_content(1 << 16):
                        f.write(chunk)
            os.replace(dest + ".part", dest)
            if verify(dest):
                print("downloaded", dest, os.path.getsize(dest))
                return
            print("corrupt archive, retrying", name)
        except requests.RequestException as e:
            print("error", name, e)
        time.sleep(2 ** attempt * 5)
    raise SystemExit(f"failed to download {name}")


def safe_extract(tar, path):
    base = os.path.realpath(path)
    for m in tar.getmembers():
        target = os.path.realpath(os.path.join(path, m.name))
        if not target.startswith(base + os.sep) or not (m.isfile() or m.isdir()):
            raise SystemExit(f"unsafe member {m.name}")
    tar.extractall(path)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    raw = sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, "..", "..", "_raw", "no")
    dl, ex = os.path.join(raw, "dl"), os.path.join(raw, "ex")
    os.makedirs(dl, exist_ok=True)
    os.makedirs(ex, exist_ok=True)
    listing = requests.get(f"{API}/list", headers=UA, timeout=60).json()
    for entry in listing:
        print("available:", entry["filename"], entry.get("lastModified"))
    for name in FILES:
        dest = os.path.join(dl, name)
        download(name, dest)
        with tarfile.open(dest, "r:bz2") as tar:
            safe_extract(tar, ex)
    print("extracted to", ex)


if __name__ == "__main__":
    main()
