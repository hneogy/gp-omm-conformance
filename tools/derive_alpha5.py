#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
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
        meta = json.load(open(path + ".meta.json", encoding="utf-8"))
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
        with open(out, "w", newline="", encoding="utf-8") as f:
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
        json.dump(prov, open(out[:-4] + ".provenance.json", "w", encoding="utf-8"), indent=2)
        summary.append((stem, len(ids), letters))
        print(f"{stem}.tle: {len(ids)} records, letters {letters}")
    summary.append(synthetic_letters())
    summary.append(synthetic_years())
    return summary


SYNTHETIC_SOURCE = "fixtures/six-digit-omm-saramago/raw/saramago-first.csv"
SYNTHETIC_STATEMENT = ("synthetic-derived (D-096, D-125, D-286, D-300): SARAMAGO's first-record elements with the "
                       "catalog number replaced{extra}; each id is a specification vector, not a catalogued object. "
                       "D-016 stands: real records are the only source of real-id sets, and this file poses as no "
                       "catalog data.")


def _real_ids():
    """Every catalog number a real-derived file of this folder carries: a synthetic set never takes one of them."""
    ids = set()
    for _, stem, _, _ in SOURCES:
        prov = json.load(open(os.path.join(OUT, stem + ".provenance.json"), encoding="utf-8"))
        ids.update(prov["norad_cat_ids"])
    return ids


def _source_row():
    path = os.path.join(ROOT, SYNTHETIC_SOURCE)
    raw = open(path, "rb").read()
    meta = json.load(open(path + ".meta.json", encoding="utf-8"))
    row = next(r for r in csv.DictReader(io.StringIO(raw.decode("utf-8"))) if int(r["NORAD_CAT_ID"]) == 100000)
    return row, meta


def _write_synthetic(stem, rows, label, description, statement_extra, differences, extra_prov=None):
    lines, ids, letters = [], [], {}
    for r in rows:
        l0, l1, l2 = R.render(r, mantissa_mode="round", ecc_mode="truncate")
        lines += [l0, l1, l2]
        ids.append(int(r["NORAD_CAT_ID"]))
        letters[l1[2]] = letters.get(l1[2], 0) + 1
    body = "\r\n".join(lines) + "\r\n"
    out = os.path.join(OUT, stem + ".tle")
    with open(out, "w", newline="", encoding="utf-8") as f:
        f.write(body)
    _, meta = _source_row()
    prov = {
        "file": os.path.relpath(out, ROOT).replace(os.sep, "/"),
        "provenance": "synthetic-derived",
        "label": label, "description": description,
        "statement": SYNTHETIC_STATEMENT.format(extra=statement_extra),
        "source_file": SYNTHETIC_SOURCE, "source_sha256": meta["sha256"], "source_url": meta["url"],
        "source_retrieved_at": meta["retrieved_at"],
        "synthetic_source_norad_cat_id": 100000,
        "generator": "tools/derive_alpha5.py", "renderer": "tools/tlerender.py",
        "renderer_settings": RENDER_SETTINGS, "renderer_validation": VALIDATION,
        "catalog_field_encoding": "Alpha-5 (Space-Track table: A=10 ... Z=33, I and O skipped)",
        "record_count": len(ids), "norad_cat_ids": ids, "alpha5_letters": letters,
        "line_endings": "CRLF", "output_sha256": hashlib.sha256(body.encode()).hexdigest(),
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "known_differences_from_a_celestrak_tle": differences,
    }
    prov.update(extra_prov or {})
    json.dump(prov, open(out[:-4] + ".provenance.json", "w", encoding="utf-8"), indent=2)
    print(f"{stem}.tle: {len(ids)} records, letters {letters}")
    return (stem, len(ids), letters)


def synthetic_letters():
    """Two TLE sets per Alpha-5 letter, the lowest and the highest id the letter can carry (X0000 and X9999), for all
    24 letters, less the ids a real record of the corpus already holds: the parse path then reads the whole letter
    table and both ends of every letter's range, where the real derived files hold letters A and T only (D-286,
    widened by D-300 after the red team's E11). The elements are the SARAMAGO first record's; only the catalog
    number changes."""
    from gpconf.tle import ALPHA5_LETTERS
    row, _ = _source_row()
    real = _real_ids()
    rows = []
    for letter in ALPHA5_LETTERS:
        base = (ALPHA5_LETTERS.index(letter) + 10) * 10000
        for i in (base, base + 9999):
            if i in real:
                continue  # a real catalogued object's number is never given synthetic elements (D-016)
            r = dict(row)
            r["NORAD_CAT_ID"] = str(i)
            rows.append(r)
    return _write_synthetic(
        "alpha5-synthetic-letters", rows,
        "SYNTHETIC-DERIVED: the lowest and highest id of every Alpha-5 letter, rendered from one real CelesTrak record with the catalog number replaced; not served by any provider",
        "All 24 Alpha-5 letters at both ends of their ranges (X0000 and X9999), less the two ids real records hold (100000, 270000): specification vectors as readable TLE sets",
        "",
        ["the catalog numbers are specification vectors (X0000 and X9999 per letter), not catalogued objects",
         "columns 3-7 of lines 1 and 2 hold an Alpha-5 code instead of five digits",
         "the checksum is computed over the Alpha-5 line (letters count 0, minus signs count 1)"])


def synthetic_years():
    """One TLE set per two-digit epoch year, 00 to 99, so that a reader's pivot is graded on data wherever it sits:
    the real sets the corpus ships carry the years 26 and 98 only (D-300; the red team's E11, last paragraph). The
    elements are the SARAMAGO first record's; the epoch keeps its month, day and time and takes the year the
    two-digit value denotes under the pivot the format documents (57-99 are 1957-1999, 00-56 are 2000-2056); the
    catalog number is 330100 + the two-digit year (Z0100 to Z0199), so each set names the year it tests."""
    row, _ = _source_row()
    rows, years = [], {}
    for yy in range(100):
        year = 1900 + yy if yy >= 57 else 2000 + yy
        r = dict(row)
        r["NORAD_CAT_ID"] = str(330100 + yy)
        r["EPOCH"] = f"{year:04d}" + row["EPOCH"][4:]
        rows.append(r)
        years[f"{yy:02d}"] = year
    return _write_synthetic(
        "alpha5-synthetic-epoch-years", rows,
        "SYNTHETIC-DERIVED: one TLE set per two-digit epoch year (00-99), rendered from one real CelesTrak record with the epoch's year and the catalog number replaced; not served by any provider",
        "Every two-digit epoch year, 00 to 99, each under its own synthetic id (Z01yy): the pivot at 57 graded on data",
        " and the epoch's year replaced",
        ["the epoch years are specification vectors: the record was never observed at these epochs",
         "the catalog numbers (330100-330199, Z0100-Z0199) are specification vectors, not catalogued objects",
         "the checksum is computed over the Alpha-5 line (letters count 0, minus signs count 1)"],
        {"two_digit_year_to_year": years})


if __name__ == "__main__":
    main()
