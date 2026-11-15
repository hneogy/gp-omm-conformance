#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""
tools/derive_twins.py -- the propagation tier's TLE/OMM exact twins and their reference vectors (Phase 3, item 5;
lane C's design section 3; the owner's ruling on question 3, 2026-11-01; D-406). Maintainer-only: it needs the
recipe's build of tools/sgp4_reference_vectors.cpp against Vallado's SGP4.cpp, and python-sgp4 for the
cross-check. Offline.

Seven TLE sets the corpus already ships (derived/corrupt-input/unedited-sets.tle: 25544 at its 1998 epoch, 20453, 69999;
derived/alpha5-tle: 100000, 100686, 100530 and 270354), copied byte for byte into derived/propagation-twins/twins.tle;
for each, an OMM CSV row whose values are exactly the TLE's as the corpus's reference reader reads them (eccentricity
to seven digits, BSTAR and the derivatives as the line's mantissas, the epoch's eight-digit day fraction, a whole
number of 864 microseconds, written to the microsecond), in derived/propagation-twins/twins.csv. The reference
vectors are SGP4's output for each TLE at the twins' times (WGS-72, opsmode 'i'), written to
vectors/propagation-twins.json; each is checked against python-sgp4 2.27 within 2e-7 and the run stops if one is not.
"""
import csv
import datetime as dt
import hashlib
import io
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import gpref  # noqa: E402

SOURCES = [("derived/corrupt-input/unedited-sets.tle", [25544, 20453, 69999]),
           ("derived/alpha5-tle/alpha5-A-100000-saramago-first.tle", [100000]),
           ("derived/alpha5-tle/alpha5-A-last-30-days-snapshot.tle", [100686, 100530]),
           ("derived/alpha5-tle/alpha5-T-analyst-27xxxx-snapshot.tle", [270354])]
TIMES = [-1440.0, -60.0, 0.0, 60.0, 1440.0, 10080.0]   # minutes since epoch: a day and an hour either side, and a week ahead
OUT = os.path.join(ROOT, "derived", "propagation-twins")
VECTORS = os.path.join(ROOT, "vectors", "propagation-twins.json")
BAR = 2e-7
CSV_KEYS = ["OBJECT_NAME", "OBJECT_ID", "EPOCH", "MEAN_MOTION", "ECCENTRICITY", "INCLINATION", "RA_OF_ASC_NODE",
            "ARG_OF_PERICENTER", "MEAN_ANOMALY", "EPHEMERIS_TYPE", "CLASSIFICATION_TYPE", "NORAD_CAT_ID", "ELEMENT_SET_NO",
            "REV_AT_EPOCH", "BSTAR", "MEAN_MOTION_DOT", "MEAN_MOTION_DDOT"]


def sets_of(path, ids):
    """The three lines of each named set, as the file holds them."""
    lines = open(os.path.join(ROOT, path), encoding="utf-8").read().splitlines()
    out = {}
    for i, l in enumerate(lines):
        if l.startswith("1 ") and i + 1 < len(lines):
            rec = gpref.parse_tle_lines(lines[i - 1] if i and not lines[i - 1].startswith(("1 ", "2 ")) else None, l, lines[i + 1])
            if rec["norad_cat_id"] in ids:
                out[rec["norad_cat_id"]] = (lines[i - 1], l, lines[i + 1], rec)
    missing = set(ids) - set(out)
    if missing:
        sys.exit(f"{path}: no set for {sorted(missing)}")
    return [out[k] for k in ids]


def text(v):
    return "" if v is None else str(v)


def main(binary):
    picked = [s for path, ids in SOURCES for s in sets_of(path, ids)]
    os.makedirs(OUT, exist_ok=True)
    tle = "".join(f"{n}\r\n{a}\r\n{b}\r\n" for n, a, b, _ in picked)
    rows = io.StringIO()
    w = csv.writer(rows, lineterminator="\r\n")
    w.writerow(CSV_KEYS)
    for _, _, _, r in picked:
        w.writerow([text(r.get(k.lower())) for k in CSV_KEYS])
    for name, body in (("twins.tle", tle), ("twins.csv", rows.getvalue())):
        with open(os.path.join(OUT, name), "w", newline="", encoding="utf-8") as f:
            f.write(body)
    # the CSV read back must give the TLE's values exactly
    _, from_csv, _ = gpref.read_file(os.path.join(OUT, "twins.csv"))
    _, from_tle, _ = gpref.read_file(os.path.join(OUT, "twins.tle"))
    for a, b in zip(from_tle, from_csv):
        for k in ("norad_cat_id", "epoch", "mean_motion", "eccentricity", "inclination", "ra_of_asc_node", "arg_of_pericenter",
                  "mean_anomaly", "bstar", "mean_motion_dot", "mean_motion_ddot"):
            if str(a.get(k)) != str(b.get(k)):
                sys.exit(f"{a['norad_cat_id']}: {k} reads {a.get(k)!r} from the TLE and {b.get(k)!r} from the CSV twin")
    p = subprocess.run([binary] + [repr(t) for t in TIMES], input="".join(f"{a}\n{b}\n" for _, a, b, _ in picked),
                       capture_output=True, text=True, check=True)
    ref = [json.loads(l) for l in p.stdout.splitlines()]
    from sgp4.api import Satrec, WGS72
    worst = 0.0
    for v in ref:
        s = Satrec.twoline2rv(v["line1"], v["line2"], WGS72)
        for st in v["steps"]:
            e, r, vv = s.sgp4_tsince(st["t"])
            if e != st["error"]:
                sys.exit(f"{v['line1'][2:7]} t={st['t']}: error {st['error']} by Vallado's C++, {e} by python-sgp4")
            if e == 0:
                d = max(abs(x - y) for x, y in zip(list(r) + list(vv), st["r"] + st["v"]))
                worst = max(worst, d)
                if d > BAR:
                    sys.exit(f"{v['line1'][2:7]} t={st['t']}: python-sgp4 differs by {d:.3g}")
    import importlib.metadata as md
    out = {"what": "the corpus's own reference vectors for the TLE/OMM twins: SGP4's TEME position (km) and velocity (km/s) for each set of derived/propagation-twins/twins.tle (D-406)",
           "generated_with": "tools/sgp4_reference_vectors.cpp built against Vallado's SGP4.cpp at the recipe's pin (harnesses/vallado/README.md), WGS-72, opsmode 'i'",
           "cross_check": f"python-sgp4 {md.version('sgp4')} (Satrec, sgp4_tsince, WGS-72): the same error code at every step and within {BAR:g} at every step that propagated; largest difference {worst:.3g}",
           "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "files": {n: hashlib.sha256(open(os.path.join(OUT, n), "rb").read()).hexdigest() for n in ("twins.tle", "twins.csv")},
           "times": TIMES, "bar_km_and_km_s": BAR,
           "sets": [{"norad_cat_id": r["norad_cat_id"], "from_file": path, "line1": a, "line2": b, "steps": v["steps"]}
                    for (path, ids) in SOURCES for k in ids
                    for (_, a, b, r), v in [next(((x, y) for x, y in zip(picked, ref) if x[3]["norad_cat_id"] == k))]]}
    with open(VECTORS, "w", encoding="utf-8") as f:
        f.write(json.dumps(out, indent=1) + "\n")
    with open(os.path.join(OUT, "twins.provenance.json"), "w", encoding="utf-8") as f:
        json.dump({"files": ["derived/propagation-twins/twins.tle", "derived/propagation-twins/twins.csv"],
                   "provenance": "derived",
                   "statement": "Seven TLE sets the corpus already ships, copied byte for byte, and an OMM CSV twin of each whose values are exactly the TLE's as the corpus's reference reader reads them; no value is invented (D-406).",
                   "sources": [p for p, _ in SOURCES], "generator": "tools/derive_twins.py",
                   "generated_at": out["generated_at"]}, f, indent=2)
    print(f"{len(picked)} twins, {len(TIMES)} times each; python-sgp4 within {worst:.3g} of Vallado's C++")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: tools/derive_twins.py PATH-TO-THE-BUILT-reference_vectors")
    main(sys.argv[1])
