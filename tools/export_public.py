#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""
tools/export_public.py -- copy the public subset of this repository into a fresh directory.

Reads PUBLIC_ALLOWLIST.txt, refuses raw provider files, anything matching the Space-Track
name guard and the files WITHHELD names with their reasons (D-367), and writes EXPORT-MANIFEST.txt (path, bytes, SHA-256) into the destination. The
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
from public_scrub import scrub_expected, scrub_audit_md, scrub_decisions_md, scrub_changelog_md, scrub_file_passages, _FILES, PRIVATE_NAMES, named_in  # noqa: E402
RAW = re.compile(r"(^|/)fixtures/[^/]+/raw(/|$)")
# The maintainer's private instruction files stay in the private repository (D-461, the owner's ruling of
# 2026-11-10): the two instruction files at any depth, and anything under the private settings folder, are refused
# whatever the allowlist says. The public tree never spells their names (D-545): a file is matched by the SHA-256 of
# its name, a folder by the SHA-256 of each folder's name, in lower case. The private names file, when present, adds
# the original pattern as a second check, and the export refuses that file itself.
INSTRUCTION_FILE_NAMES = {"bccc86317c281a19e56f3f941077ea61b3fb37d5bd527c518b92b188c4461251",
                    "b951327c37d8a1ed4d5ed18908681f6aca718ecdfe174aa39cf2237547f92fe7"}
INSTRUCTION_FOLDER_NAMES = {"e026f56c08dcdea441a2aa620ab410ce91162062609b2430f5a13bc9b7cf93f1"}
PRIVATE_NAMES_FILE = "tools/private-names.json"
PRIVATE_PASSAGES_FILE = "tools/private-passages.json"   # what the public copy withholds, with its hashes (D-613)


def _h(name):
    return hashlib.sha256(name.lower().encode("utf-8")).hexdigest()


def private_names_file(rel):
    """The private names file, refused whatever the allowlist says (D-545)."""
    return rel.replace(os.sep, "/").lstrip("./") in (PRIVATE_NAMES_FILE, PRIVATE_PASSAGES_FILE)


def instruction_file(rel):
    parts = [p for p in rel.replace(os.sep, "/").split("/") if p]
    if not parts:
        return False
    hit = _h(parts[-1]) in INSTRUCTION_FILE_NAMES or any(_h(p) in INSTRUCTION_FOLDER_NAMES for p in parts)
    if PRIVATE_NAMES:
        hit = hit or bool(re.search(PRIVATE_NAMES["instruction_file_regex"], "/".join(parts), re.I))
    return hit
SPACETRACK = re.compile(r"space[-_ .]?track", re.I)
# The one provider response that is exported (D-247): the provider's 16-byte answer to a query with nothing to return,
# by its exact bytes, and its provenance file. Anything else under recorded/ is refused.
RECORDED = {"recorded/celestrak-no-gp-data-found.txt": "000844fd5b7a7b64f14b58cc34f0016ad51b0982b0d38f915986560e4e217683",
            "recorded/celestrak-no-gp-data-found.provenance.json": None}
# Files the allowlist matches that stay private, each with its reason (D-367). SM-26's adapters were the one entry until
# SM-26 licensed them under Apache-2.0 (D-380); they are exported from D-382. Vallado's verification files stay private,
# for tests and the private repository only, kept out of the public copy (D-388); the package is staged from the
# export, so they never reach it either.
VALLADO_PRIVATE = "Vallado's verification file (AIAA 2006-6753), kept out of the public copy and the package (D-388)"
UNREPORTED = "a draft of a finding not yet reported upstream, held out of the public copy until it is filed (D-613)"
WITHHELD = {"harnesses/vallado/reference/SGP4-VER.TLE": VALLADO_PRIVATE,
            "harnesses/vallado/reference/tcppver.out": VALLADO_PRIVATE,
            "docs/upstream/python-sgp4-omm-initialize-drops-classification.md": UNREPORTED}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", required=True)
    ap.add_argument("--exclude", action="append", default=[], help="extra glob to leave out (e.g. 'fixtures/nine-digit-*/*')")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if os.path.exists(a.dest) and os.listdir(a.dest):
        sys.exit("destination must be empty or absent")
    patterns = [l.strip() for l in open(os.path.join(ROOT, "PUBLIC_ALLOWLIST.txt"), encoding="utf-8") if l.strip() and not l.startswith("#")]
    files = set()
    for p in patterns:
        for m in glob.glob(os.path.join(ROOT, p), recursive=True):
            if os.path.isfile(m):
                files.add(os.path.relpath(m, ROOT).replace(os.sep, "/"))   # matched as the allowlist writes paths (D-270)
    refused = []
    out = []
    for rel in sorted(files):
        if RAW.search(rel):
            refused.append((rel, "raw provider file"))
            continue
        if private_names_file(rel):
            refused.append((rel, "the private names file (D-545)"))
            continue
        if instruction_file(rel):
            refused.append((rel, "a maintainer-only instruction file, private (D-461)"))
            continue
        if rel.replace(os.sep, "/").startswith("recorded/"):
            want = RECORDED.get(rel.replace(os.sep, "/"), "")
            if want == "" or (want and hashlib.sha256(open(os.path.join(ROOT, rel), "rb").read()).hexdigest() != want):
                refused.append((rel, "not the one provider response the corpus ships (D-247)"))
                continue
        if (SPACETRACK.search(os.path.basename(rel)) or SPACETRACK.search(rel)) and rel != "tools/verify_against_spacetrack.py":
            refused.append((rel, "matches the Space-Track name guard"))
            continue
        if rel in WITHHELD:
            refused.append((rel, WITHHELD[rel]))
            continue
        if any(fnmatch.fnmatch(rel, g) for g in a.exclude):
            refused.append((rel, "excluded by --exclude"))
            continue
        if "/.venv/" in "/" + rel or rel.startswith(".venv") or "__pycache__" in rel or "/_out/" in "/" + rel:
            continue
        out.append(rel)
    lines = []
    scrubbed = []
    named = []
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
        elif rel == "CHANGELOG.md":   # two released lines that named private correspondence, shortened (D-612)
            text, n = scrub_changelog_md(data.decode("utf-8"))
            if n:
                data = text.encode("utf-8")
                scrubbed.append(rel)
        elif rel in {f[0] for f in _FILES}:   # named lines of other files, shortened in the public copy (D-613)
            text, n = scrub_file_passages(rel, data.decode("utf-8"))
            if n:
                data = text.encode("utf-8")
                scrubbed.append(rel)
        elif rel == "DECISIONS.md":   # private names reworded in the exported copy only (D-462)
            text, n = scrub_decisions_md(data.decode("utf-8"))
            if n:
                data = text.encode("utf-8")
                scrubbed.append(rel)
        found = named_in(rel + "\n" + data.decode("utf-8", "replace"))
        if found:   # a private name, or an instruction file's, would go public (D-545)
            named.append((rel, found))
            continue
        lines.append(f"{rel}\t{len(data)}\t{hashlib.sha256(data).hexdigest()}")
        if not a.dry_run:
            dst = os.path.join(a.dest, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if rel in scrubbed:
                open(dst, "wb").write(data)
            else:
                shutil.copy2(src, dst)
    if not a.dry_run:
        with open(os.path.join(a.dest, "EXPORT-MANIFEST.txt"), "w", encoding="utf-8") as f:
            f.write("# path\tbytes\tsha256\n" + "\n".join(lines) + "\n")
    print(f"{'would copy' if a.dry_run else 'copied'} {len(out) - len(named)} file(s); refused {len(refused)}; scrubbed {len(scrubbed)}: {scrubbed}")
    for rel, why in refused:
        print(f"  refused: {rel} ({why})")
    if named:   # the export stops: those files were not written, and the destination is incomplete
        for rel, found in named:
            print(f"  STOPPED: {rel} holds {len(found)} private name(s) (D-545)")
        sys.exit(f"export stopped: {len(named)} file(s) would put a private name in the public tree (D-545)")
    if not PRIVATE_NAMES:
        print("  note: the private names file is absent, so the private-name check did not run (D-545)")


if __name__ == "__main__":
    main()
