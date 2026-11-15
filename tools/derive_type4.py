#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""
tools/derive_type4.py -- the ephemeris-type-4 case's inputs (Phase 3, item 6; lane C's design section 4; the owner's
ruling of 2026-11-01: type 4 graded on EPHEMERIS_TYPE alone, with type-0 twins; D-409). Offline; no reference vectors
of its own: the type-0 twins are graded against the twins' vectors (vectors/propagation-twins.json, D-406).

One set the corpus already ships, 20453 (DELTA 2 R/B(1)) from derived/propagation-twins/twins.tle, a near-earth set
with a non-zero BSTAR, written six ways with ephemeris type 4 and six ways with type 0: the TLE (line 1 column 63 set,
the checksum recomputed), and OMM CSV, JSON, XML and KVN whose values are exactly the TLE's (the twins' CSV row), plus
a KVN that also says MEAN_ELEMENT_THEORY = SGP4-XP. That spelling is the corpus's, labelled synthetic: how a provider
writes it is [not read], and the case grades EPHEMERIS_TYPE alone. Each file holds one set. Every file is read back by
the corpus's reference reader and must give the twin's values and the type it was written with.
"""
import csv
import datetime as dt
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import gpref  # noqa: E402

ID = 20453
# the header filled, fixed, so a reader that requires it is not failed and the files are the same on every run (the review of D-409)
CREATED, ORIGINATOR = "2026-11-09T00:00:00", "GPCONF SYNTHETIC-DERIVED"
TWINS = os.path.join(ROOT, "derived", "propagation-twins")
OUT = os.path.join(ROOT, "derived", "ephemeris-type-4")
ORDER = ["OBJECT_NAME", "OBJECT_ID", "CENTER_NAME", "REF_FRAME", "TIME_SYSTEM", "MEAN_ELEMENT_THEORY", "EPOCH",
         "MEAN_MOTION", "ECCENTRICITY", "INCLINATION", "RA_OF_ASC_NODE", "ARG_OF_PERICENTER", "MEAN_ANOMALY",
         "EPHEMERIS_TYPE", "CLASSIFICATION_TYPE", "NORAD_CAT_ID", "ELEMENT_SET_NO", "REV_AT_EPOCH", "BSTAR",
         "MEAN_MOTION_DOT", "MEAN_MOTION_DDOT"]
META = ORDER[:6]
NUMBERS = {"MEAN_MOTION", "ECCENTRICITY", "INCLINATION", "RA_OF_ASC_NODE", "ARG_OF_PERICENTER", "MEAN_ANOMALY",
           "EPHEMERIS_TYPE", "NORAD_CAT_ID", "ELEMENT_SET_NO", "REV_AT_EPOCH", "BSTAR", "MEAN_MOTION_DOT", "MEAN_MOTION_DDOT"}
COMPARED = ("norad_cat_id", "epoch", "mean_motion", "eccentricity", "inclination", "ra_of_asc_node", "arg_of_pericenter",
            "mean_anomaly", "bstar", "mean_motion_dot", "mean_motion_ddot", "ephemeris_type")


def checksum(line68):
    return str(sum(int(c) if c.isdigit() else (1 if c == "-" else 0) for c in line68) % 10)


def the_set():
    lines = open(os.path.join(TWINS, "twins.tle"), encoding="ascii", newline="").read().split("\r\n")
    k = next(i for i in range(1, len(lines), 3) if lines[i][2:7] == str(ID))
    name, l1, l2 = lines[k - 1], lines[k], lines[k + 1]
    rows = list(csv.DictReader(io.StringIO(open(os.path.join(TWINS, "twins.csv"), encoding="utf-8", newline="").read())))
    (row,) = [r for r in rows if r["NORAD_CAT_ID"] == str(ID)]
    return name, l1, l2, row


def fields_for(row, etype, theory):
    f = dict(row)
    f.update(CENTER_NAME="EARTH", REF_FRAME="TEME", TIME_SYSTEM="UTC", MEAN_ELEMENT_THEORY=theory, EPHEMERIS_TYPE=str(etype))
    return {k: f[k] for k in ORDER}


def as_csv(f):
    s = io.StringIO()
    w = csv.writer(s, lineterminator="\r\n")
    w.writerow(ORDER)
    w.writerow([f[k] for k in ORDER])
    return s.getvalue()


def as_json(f):
    # numbers written as the TLE's own decimal text, so the twin's values are exactly the TLE's
    body = ",".join(f'"{k}":' + (f[k] if k in NUMBERS else json.dumps(f[k])) for k in ORDER)
    return "[{" + body + "}]\r\n"


def as_xml(f):
    esc = lambda v: v.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    meta = "".join(f"<{k}>{esc(f[k])}</{k}>" for k in META)
    mean = "".join(f"<{k}>{f[k]}</{k}>" for k in ORDER[6:13])
    tle = "".join(f"<{k}>{f[k]}</{k}>" for k in ORDER[13:])
    return ('<?xml version="1.0" encoding="UTF-8"?>\r\n<ndm><omm id="CCSDS_OMM_VERS" version="2.0">'
            f'<header><CREATION_DATE>{CREATED}</CREATION_DATE><ORIGINATOR>{ORIGINATOR}</ORIGINATOR></header><body><segment>'
            f'<metadata>{meta}</metadata><data><meanElements>{mean}</meanElements>'
            f'<tleParameters>{tle}</tleParameters></data></segment></body></omm></ndm>\r\n')


def as_kvn(f):
    head = f"CCSDS_OMM_VERS      = 2.0\r\nCREATION_DATE       = {CREATED}\r\nORIGINATOR          = {ORIGINATOR}\r\n\r\n"
    blocks = [META, ORDER[6:13], ORDER[13:]]
    return head + "\r\n".join("".join(f"{k:<20}= {f[k]}\r\n" for k in b) for b in blocks)


def main():
    name, l1, l2, row = the_set()
    vec = json.load(open(os.path.join(ROOT, "vectors", "propagation-twins.json"), encoding="utf-8"))
    if not any(s["line1"] == l1 and s["line2"] == l2 for s in vec["sets"]):
        sys.exit(f"{ID}: the twins' reference vectors hold no set with these lines")
    if l1[62] != "0":
        sys.exit(f"{ID}: line 1 column 63 is {l1[62]!r}, not 0")
    l1_4 = l1[:62] + "4" + l1[63:68]
    l1_4 += checksum(l1_4)
    os.makedirs(OUT, exist_ok=True)
    files = {}
    for etype, line1 in ((0, l1), (4, l1_4)):
        f = fields_for(row, etype, "SGP4")
        files[f"type{etype}.tle"] = f"{name}\r\n{line1}\r\n{l2}\r\n"
        files[f"type{etype}.csv"] = as_csv(f)
        files[f"type{etype}.json"] = as_json(f)
        files[f"type{etype}.xml"] = as_xml(f)
        files[f"type{etype}.kvn"] = as_kvn(f)
    files["type4-sgp4-xp.kvn"] = as_kvn(fields_for(row, 4, "SGP4-XP"))   # its twin is type0.kvn
    for n, body in files.items():
        with open(os.path.join(OUT, n), "w", newline="", encoding="utf-8") as fh:
            fh.write(body)
    # read back: every file gives the TLE's values, and the type it was written with
    want = gpref.parse_tle_lines(name, l1, l2)
    for n in sorted(files):
        _, recs, _ = gpref.read_file(os.path.join(OUT, n))
        if len(recs) != 1:
            sys.exit(f"{n}: {len(recs)} records read back")
        (r,) = recs
        etype = 4 if n.startswith("type4") else 0
        for k in COMPARED:
            w = etype if k == "ephemeris_type" else want.get(k)
            if str(r.get(k)) != str(w):
                sys.exit(f"{n}: {k} reads {r.get(k)!r}, the twin's is {w!r}")
        theory = "SGP4-XP" if n == "type4-sgp4-xp.kvn" else ("SGP4" if not n.endswith(".tle") else None)
        if theory and r.get("mean_element_theory") != theory:
            sys.exit(f"{n}: MEAN_ELEMENT_THEORY reads {r.get('mean_element_theory')!r}")
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(os.path.join(OUT, "type4.provenance.json"), "w", encoding="utf-8") as fh:
        json.dump({"files": [f"derived/ephemeris-type-4/{n}" for n in sorted(files)], "provenance": "derived",
                   "statement": ("One set the corpus already ships (20453, derived/propagation-twins/twins.tle), written with "
                                 "ephemeris type 4 and with type 0 as TLE and as OMM CSV, JSON, XML and KVN whose values are exactly "
                                 "the TLE's; the TLE's line 1 column 63 and checksum changed, nothing else. MEAN_ELEMENT_THEORY = "
                                 "SGP4-XP in one KVN is the corpus's spelling, synthetic: how a provider writes it is not read "
                                 "(the owner's ruling, 2026-11-01). No value is invented (D-409)."),
                   "sources": ["derived/propagation-twins/twins.tle", "derived/propagation-twins/twins.csv"],
                   "generator": "tools/derive_type4.py", "generated_at": stamp}, fh, indent=2)
        fh.write("\n")
    print(f"{len(files)} files for {ID}; line 1 with type 4: {l1_4}")


if __name__ == "__main__":
    main()
