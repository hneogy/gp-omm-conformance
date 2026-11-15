#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""tools/export_fuzz_seeds.py OUT_DIR -- the corpus's shipped inputs as seed corpora for coverage-guided fuzzers
(0.9.0 item d3, D-433), in the layout OSS-Fuzz reads: one `<prefix>_<format>_seed_corpus.zip` per format and one
`<prefix>_<format>.dict` of the format's tokens, for a project's fuzz target of that format to take.

The seeds are `derived/**` only, the inputs gpconf fuzz mutates (gpconf/fuzz.py's seeds()): files the corpus makes and
ships under its own licence. The provider files a user fetches are never included. The zips are reproducible: entries
in sorted order with a fixed timestamp and fixed permissions, so the same corpus gives the same bytes.

Which OSS-Fuzz projects would take them, and under what name, is not decided here (the plan: "[not read: which
are]"); `--prefix` names the fuzz target (default `gpconf`)."""
import argparse
import hashlib
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from gpconf.fuzz import FORMATS, seeds  # noqa: E402

STAMP = (2026, 1, 1, 0, 0, 0)   # zip times must be 1980 or later; one fixed time keeps the bytes the same

# libFuzzer's dictionary syntax: one quoted token per line, escapes as \xNN (https://llvm.org/docs/LibFuzzer.html)
TOKENS = {
    "tle": ["1 ", "2 ", "U", "C", "S", "+0", "-0", " 00000+0", " 00000-0", "-.", " .", "0 ", "99999", "A0000", "Z9999",
            "\r\n"],
    "csv": ["OBJECT_NAME", "OBJECT_ID", "EPOCH", "MEAN_MOTION", "ECCENTRICITY", "INCLINATION", "RA_OF_ASC_NODE",
            "ARG_OF_PERICENTER", "MEAN_ANOMALY", "EPHEMERIS_TYPE", "CLASSIFICATION_TYPE", "NORAD_CAT_ID",
            "ELEMENT_SET_NO", "REV_AT_EPOCH", "BSTAR", "MEAN_MOTION_DOT", "MEAN_MOTION_DDOT", ",", "\"", "\r\n", "E-", "T"],
    "json": ["{", "}", "[", "]", "\"NORAD_CAT_ID\":", "\"EPOCH\":", "\"MEAN_MOTION\":", "\"ECCENTRICITY\":",
             "\"BSTAR\":", "null", "true", "false", "1e999", "\"\""],
    "xml": ["<ndm", "</ndm>", "<omm", "</omm>", "<header>", "<body>", "<segment>", "<metadata>", "<data>",
            "<meanElements>", "<EPOCH>", "<NORAD_CAT_ID>", "<MEAN_MOTION>", "<?xml version=\"1.0\"?>", "&amp;", "<![CDATA["],
    "kvn": ["CCSDS_OMM_VERS", " = ", "COMMENT", "OBJECT_NAME", "OBJECT_ID", "CENTER_NAME", "REF_FRAME", "TIME_SYSTEM",
            "MEAN_ELEMENT_THEORY", "EPOCH", "MEAN_MOTION", "ECCENTRICITY", "NORAD_CAT_ID", "BSTAR", "[rev/day]", "[deg]",
            "TEME", "UTC", "SGP4", "\n"],
}


def dict_line(token):
    out = []
    for b in token.encode("utf-8"):
        out.append(chr(b) if 0x20 <= b < 0x7f and chr(b) not in "\"\\" else f"\\x{b:02X}")
    return '"' + "".join(out) + '"'


def export(out_dir, prefix="gpconf", root=ROOT):
    """-> {format: (zip path, number of seeds, sha256 of the zip)}."""
    os.makedirs(out_dir, exist_ok=True)
    by_fmt = {f: [] for f in FORMATS}
    for path, fmt in seeds(root):
        by_fmt[fmt].append(path)
    done = {}
    for fmt, paths in by_fmt.items():
        if not paths:
            continue
        zpath = os.path.join(out_dir, f"{prefix}_{fmt}_seed_corpus.zip")
        with zipfile.ZipFile(zpath, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for p in sorted(paths):
                info = zipfile.ZipInfo(p.replace("/", "__"), date_time=STAMP)   # flat: OSS-Fuzz unpacks into one folder
                info.external_attr = 0o644 << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                with open(os.path.join(root, p), "rb") as f:
                    z.writestr(info, f.read())
        with open(os.path.join(out_dir, f"{prefix}_{fmt}.dict"), "w", encoding="ascii", newline="\n") as f:
            f.write(f"# {fmt} tokens for a gpconf seed corpus (tools/export_fuzz_seeds.py)\n")
            for t in TOKENS[fmt]:
                f.write(dict_line(t) + "\n")
        with open(zpath, "rb") as f:
            done[fmt] = (zpath, len(paths), hashlib.sha256(f.read()).hexdigest())
    return done


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("out_dir")
    ap.add_argument("--prefix", default="gpconf", help="the fuzz target's name in the file names (default gpconf)")
    a = ap.parse_args(argv)
    for fmt, (path, n, h) in export(a.out_dir, a.prefix).items():
        print(f"{fmt}: {n} seeds -> {os.path.relpath(path)} (sha256 {h[:16]}...)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
