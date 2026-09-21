#!/usr/bin/env python3
"""
tools/export_public.py -- copy the public subset of this repository into a fresh directory.

Reads PUBLIC_ALLOWLIST.txt, refuses raw provider files and anything matching the Space-Track
name guard, and writes EXPORT-MANIFEST.txt (path, bytes, SHA-256) into the destination. The
destination is meant to become a new repository (git init there); this repository's history
is never pushed because it contains raw provider bytes (DECISIONS D-025).

Usage: python3 tools/export_public.py --dest /path/to/empty/dir [--exclude GLOB ...]
"""
import argparse
import fnmatch
import glob
import hashlib
import json
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from public_scrub import scrub_expected, scrub_audit_md  # noqa: E402
RAW = re.compile(r"(^|/)fixtures/[^/]+/raw(/|$)")
SPACETRACK = re.compile(r"space[-_ .]?track", re.I)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", required=True)
    ap.add_argument("--exclude", action="append", default=[], help="extra glob to leave out (e.g. 'fixtures/nine-digit-*/*')")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if os.path.exists(a.dest) and os.listdir(a.dest):
        sys.exit("destination must be empty or absent")
    patterns = [l.strip() for l in open(os.path.join(ROOT, "PUBLIC_ALLOWLIST.txt")) if l.strip() and not l.startswith("#")]
    files = set()
    for p in patterns:
        for m in glob.glob(os.path.join(ROOT, p), recursive=True):
            if os.path.isfile(m):
                files.add(os.path.relpath(m, ROOT))
    refused = []
    out = []
    for rel in sorted(files):
        if RAW.search(rel):
            refused.append((rel, "raw provider file"))
            continue
        if (SPACETRACK.search(os.path.basename(rel)) or SPACETRACK.search(rel)) and rel != "tools/verify_against_spacetrack.py":
            refused.append((rel, "matches the Space-Track name guard"))
            continue
        if any(fnmatch.fnmatch(rel, g) for g in a.exclude):
            refused.append((rel, "excluded by --exclude"))
            continue
        if "/.venv/" in "/" + rel or rel.startswith(".venv") or "__pycache__" in rel or "/_out/" in "/" + rel:
            continue
        out.append(rel)
    lines = []
    scrubbed = []
    for rel in out:
        src = os.path.join(ROOT, rel)
        data = open(src, "rb").read()
        if rel.startswith("fixtures/") and rel.endswith("/expected.json"):
            exp, changed = scrub_expected(json.loads(data.decode("utf-8")))
            if changed:
                data = (json.dumps(exp, indent=1) + "\n").encode("utf-8")
                scrubbed.append(rel)
        elif rel == "AUDIT.md":
            text, removed = scrub_audit_md(data.decode("utf-8"))
            if removed:
                data = text.encode("utf-8")
                scrubbed.append(rel)
        lines.append(f"{rel}\t{len(data)}\t{hashlib.sha256(data).hexdigest()}")
        if not a.dry_run:
            dst = os.path.join(a.dest, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if rel in scrubbed:
                open(dst, "wb").write(data)
            else:
                shutil.copy2(src, dst)
    if not a.dry_run:
        with open(os.path.join(a.dest, "EXPORT-MANIFEST.txt"), "w") as f:
            f.write("# path\tbytes\tsha256\n" + "\n".join(lines) + "\n")
    print(f"{'would copy' if a.dry_run else 'copied'} {len(out)} file(s); refused {len(refused)}; scrubbed {len(scrubbed)}: {scrubbed}")
    for rel, why in refused:
        print(f"  refused: {rel} ({why})")


if __name__ == "__main__":
    main()
