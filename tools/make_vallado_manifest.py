#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""
tools/make_vallado_manifest.py -- the corpus's own manifest of Vallado's two verification files (D-388).

Reads the private copies in harnesses/vallado/reference/ (withheld from the export and the package, D-388), checks
them against their PROVENANCE.json, and writes
harnesses/vallado/reference-manifest.json: per file its bytes, SHA-256 and line count; per element set its catalog
number, run (start, stop, step), the number of steps the driver schedules and the number tcppver.out prints;
and, for each set whose block stops short, the expected error: the step it comes at and its code. The code is measured
here, by propagating the set with Vallado's C++ as python-sgp4's compiled extension carries it (`sgp4.api.Satrec`,
WGS-72), so it is the corpus's own measurement, not copied text; it is checked against python-sgp4's published list.
A set whose one printed line repeats the previous set's last line (the driver printed stale numbers) is marked so,
its error at t = 0. Offline; needs python-sgp4 (gpconf[sgp4]).
"""
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from gpconf import sgp4ver  # noqa: E402

REF = os.path.join(ROOT, "harnesses", "vallado", "reference")
OUT = os.path.join(ROOT, "harnesses", "vallado", "reference-manifest.json")
PYTHON_SGP4_CODES = [1, 1, 6, 6, 4, 3, 6]   # python-sgp4's tests.py, in file order: the cross-check, not the source


def main():
    from sgp4.api import Satrec, WGS72
    import importlib.metadata as md
    prov = json.load(open(os.path.join(REF, "PROVENANCE.json"), encoding="utf-8"))
    raw = {}
    for name, want in prov["files"].items():
        b = open(os.path.join(REF, name), "rb").read()
        got = {"bytes": len(b), "sha256": hashlib.sha256(b).hexdigest(), "lines": b.count(b"\n")}
        if got != want:
            sys.exit(f"{name}: {got} differs from PROVENANCE.json {want}")
        raw[name] = b
    sets = sgp4ver.parse_ver_tle(raw["SGP4-VER.TLE"].decode("ascii"))
    blocks = sgp4ver.parse_tcppver(raw["tcppver.out"].decode("ascii"))
    if [s["catalog"] for s in sets] != [b["catalog"] for b in blocks]:
        sys.exit("the two files list different element sets")
    out_sets, codes, prev_last = [], [], None
    for s, b in zip(sets, blocks):
        times = sgp4ver.schedule(s["start"], s["stop"], s["step"])
        entry = {"catalog": s["catalog"], "start": s["start"], "stop": s["stop"],   # no comment: Vallado's words stay in his file
                 "step": s["step"], "steps_scheduled": len(times), "steps_printed": len(b["rows"])}
        sat = Satrec.twoline2rv(s["line1"], s["line2"], WGS72)
        stale = len(b["rows"]) == 1 and prev_last is not None and b["rows"][0][1:] == prev_last[1:]
        if stale or len(b["rows"]) < len(times):
            at = 0.0 if stale else times[len(b["rows"])]
            e, _, _ = sat.sgp4_tsince(at)
            if e == 0:
                sys.exit(f"{s['catalog']}: the block stops short but no error at t = {at}")
            # no earlier step may err (a false decay): measured, every printed step returns 0
            for t in times[:0 if stale else len(b["rows"])]:
                e0, _, _ = sat.sgp4_tsince(t)
                if e0 != 0:
                    sys.exit(f"{s['catalog']}: error {e0} at t = {t}, before the expected step")
            entry["error"] = {"code": e, "at_minutes": at, "step_index": 0 if stale else len(b["rows"]),
                              **({"stale_line": "the one line printed repeats the previous set's last line; not graded"} if stale else {})}
            codes.append(e)
        elif len(b["rows"]) != len(times):
            sys.exit(f"{s['catalog']}: {len(b['rows'])} lines printed for {len(times)} steps")
        out_sets.append(entry)
        prev_last = b["rows"][-1]
    if codes != PYTHON_SGP4_CODES:
        sys.exit(f"measured codes {codes} differ from python-sgp4's {PYTHON_SGP4_CODES}")
    manifest = {
        "what": "the corpus's own manifest of Vallado's SGP4 verification files (AIAA 2006-6753); the files themselves are not shipped (D-388)",
        "files": prov["files"],
        "measured_with": f"python-sgp4 {md.version('sgp4')} (sgp4.api.Satrec, Vallado's C++, WGS-72), tools/make_vallado_manifest.py",
        "error_codes_cross_check": "equal to python-sgp4's published list for this file, in file order",
        "set_count": len(out_sets), "sets": out_sets,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(json.dumps(manifest, indent=1) + "\n")
    print(f"{len(out_sets)} sets, {len(codes)} ending in an error: {codes}")


if __name__ == "__main__":
    main()
