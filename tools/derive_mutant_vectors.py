#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""
tools/derive_mutant_vectors.py -- the wrong answers three of the propagation tier's mutant adapters give (Phase 3,
item 7; lane C's design section 5; D-414). Maintainer-only: it needs python-sgp4 (2.27 here). Offline.

The grader's mutant gate (tools/mutant_fuzz.py --ci) runs on the standard library alone, with no propagator, so the
mutants that are wrong in the physics -- a WGS-84 propagator, one that reads the minutes as seconds, one that ignores
BSTAR -- answer SGP4's output under that wrong setting, computed here once for each set of
derived/propagation-twins/twins.tle at the twins' times and shipped as test data in
tests/golden/propagation-mutant-vectors.json. These are wrong answers by construction; nothing grades against them.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "tests", "golden", "propagation-mutant-vectors.json")


def checksum(line68):
    return str(sum(int(c) if c.isdigit() else (1 if c == "-" else 0) for c in line68) % 10)


def main():
    import importlib.metadata as md
    from sgp4.api import Satrec, WGS72, WGS84
    vec = json.load(open(os.path.join(ROOT, "vectors", "propagation-twins.json"), encoding="utf-8"))
    times = vec["times"]

    def steps(s, scale=1.0):
        out = []
        for t in times:
            e, r, v = s.sgp4_tsince(t * scale)
            out.append({"t": t, "error": int(e), "r": list(r), "v": list(v)} if e == 0 else {"t": t, "error": int(e)})
        return out
    sets = []
    for st in vec["sets"]:
        l1, l2 = st["line1"], st["line2"]
        nob = l1[:53] + " 00000+0" + l1[61:68]   # BSTAR, columns 54-61, written as zero
        nob += checksum(nob)
        sets.append({"norad_cat_id": st["norad_cat_id"],
                     "wgs84": steps(Satrec.twoline2rv(l1, l2, WGS84)),
                     "minutes-as-seconds": steps(Satrec.twoline2rv(l1, l2, WGS72), 1 / 60),
                     "bstar-ignored": steps(Satrec.twoline2rv(nob, l2, WGS72))})
    out = {"what": "wrong answers by construction, for the propagation tier's physics mutants (D-414): SGP4's output for each "
                   "twins set under WGS-84, at tsince/60 (minutes read as seconds), and with BSTAR written as zero; test data, "
                   "never a reference",
           "generated_with": f"python-sgp4 {md.version('sgp4')} (Satrec.twoline2rv, sgp4_tsince)",
           "times": times, "sets": sets}
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(json.dumps(out, indent=1) + "\n")
    print(f"{len(sets)} sets, {len(times)} times, three wrong settings -> {os.path.relpath(OUT, ROOT)}")


if __name__ == "__main__":
    sys.exit(main())
