#!/usr/bin/env python3
"""
tools/derive_alpha5.py -- derive Alpha-5 TLE fixtures from real CelesTrak OMM (CSV) records.

CelesTrak serves no TLE rendering for catalog numbers >= 100000 (RESEARCH.md §2.2), so the
only way to obtain Alpha-5 lines without Space-Track data (DECISIONS D-001) is to render
CelesTrak's own OMM records into TLE layout with tools/tlerender.py, which reproduces
CelesTrak's rendering byte for byte on the 304 records that CelesTrak does render as TLE
(tools/validate_render.py: mantissa rounded half-up to 5 digits, eccentricity truncated to
7 digits). The catalog field is written in Alpha-5 per the Space-Track table.

Every output file gets a .provenance.json naming the source file, its SHA-256 and retrieval
time, the record ids, the renderer settings and the validation summary. Output files are
labelled DERIVED in their first line.
"""
import csv
import datetime as dt
import hashlib
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tlerender as R  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "derived", "alpha5-tle")
RENDER_SETTINGS = {"mantissa_mode": "round", "ecc_mode": "truncate", "epoch_rounding": "ROUND_HALF_UP"}
VALIDATION = "tools/validate_render.py: 304/304 CelesTrak TLE records reproduced exactly (lines 0, 1, 2) with these settings on 2026-09-21"

SOURCES = [
    # (source csv, output stem, filter, description)
    ("fixtures/six-digit-omm-saramago/raw/saramago-first.csv", "alpha5-A-100000-saramago-first",
     lambda i: 100000 <= i <= 339999, "First GP record of catalog 100000 (stable source, gp-first.php)"),
    ("fixtures/analyst-objects/raw/analyst-270449-first.csv", "alpha5-T-270449-analyst-first",
     lambda i: 100000 <= i <= 339999, "First GP record of Space Fence analyst id 270449 (stable source, gp-first.php)"),
    ("fixtures/tle-omits-six-digit-objects/raw/last-30-days.csv", "alpha5-A-last-30-days-snapshot",
     lambda i: 100000 <= i <= 339999, "All 6-digit objects in the last-30-days group at the snapshot time (live source)"),
    ("fixtures/analyst-objects/raw/analyst.csv", "alpha5-T-analyst-27xxxx-snapshot",
     lambda i: 270000 <= i <= 339999, "All Space Fence analyst objects (27xxxx) at the snapshot time (live source)"),
]


def main():
    os.makedirs(OUT, exist_ok=True)
    summary = []
    for src, stem, keep, desc in SOURCES:
        path = os.path.join(ROOT, src)
        raw = open(path, "rb").read()
        meta = json.load(open(path + ".meta.json"))
        rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8"))))
        lines = []
        ids = []
        letters = {}
        for r in rows:
            i = int(r["NORAD_CAT_ID"])
            if not keep(i):
                continue
            l0, l1, l2 = R.render(r, mantissa_mode="round", ecc_mode="truncate")
            lines += [l0, l1, l2]
            ids.append(i)
            letters[l1[2]] = letters.get(l1[2], 0) + 1
        body = "\r\n".join(lines) + "\r\n"  # CelesTrak convention: CRLF
        out = os.path.join(OUT, stem + ".tle")
        with open(out, "w", newline="") as f:
            f.write(body)
        prov = {
            "file": os.path.relpath(out, ROOT),
            "provenance": "derived",
            "label": "DERIVED: Alpha-5 TLE lines rendered from CelesTrak OMM records; not served by CelesTrak",
            "description": desc,
            "source_file": src, "source_sha256": meta["sha256"], "source_url": meta["url"],
            "source_retrieved_at": meta["retrieved_at"],
            "generator": "tools/derive_alpha5.py", "renderer": "tools/tlerender.py",
            "renderer_settings": RENDER_SETTINGS, "renderer_validation": VALIDATION,
            "catalog_field_encoding": "Alpha-5 (Space-Track table: A=10 ... Z=33, I and O skipped)",
            "record_count": len(ids), "norad_cat_ids": ids, "alpha5_letters": letters,
            "line_endings": "CRLF", "output_sha256": hashlib.sha256(body.encode()).hexdigest(),
            "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "line0_rule": "OBJECT_NAME is padded or cut to 24 characters (CelesTrak TLE format documentation: 'twenty-four character name'); one source name in the last-30-days snapshot (100465, 27 characters) is cut, a case that could not be checked against CelesTrak output because six-digit objects have no CelesTrak TLE",
            "known_differences_from_a_celestrak_tle": [
                "columns 3-7 of lines 1 and 2 hold an Alpha-5 code instead of five digits",
                "the checksum is computed over the Alpha-5 line (letters count 0, minus signs count 1)",
            ],
        }
        json.dump(prov, open(out[:-4] + ".provenance.json", "w"), indent=2)
        summary.append((stem, len(ids), letters))
        print(f"{stem}.tle: {len(ids)} records, letters {letters}")
    return summary


if __name__ == "__main__":
    main()
