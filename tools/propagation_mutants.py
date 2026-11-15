#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""tools/propagation_mutants.py -- the propagation tier's mutant adapters (Phase 3, item 7; lane C's design section 5;
D-414). Standard library and the corpus only; no propagator, no network.

The base is a correct propagate hook for the shipped propagation cases: it reads a set with the corpus's reference
reader, refuses an SGP4-XP set (ephemeris type 4), and answers the twins' reference vectors
(vectors/propagation-twins.json) for its catalog number. Each mutant changes one thing in that answer, as a wrong
propagator would; three answer SGP4's output under a wrong setting, shipped as test data
(tests/golden/propagation-mutant-vectors.json, tools/derive_mutant_vectors.py). Every mutant must fail at least one of
the shipped propagation cases, and the base must pass them: tools/mutant_fuzz.py runs this with every gate.

Usage: python3 tools/propagation_mutants.py [--root PATH]
"""
import argparse
import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from gpconf.adapters.reference import Parser as Ref  # noqa: E402
from gpconf.runner import Runner  # noqa: E402

CASES = ["propagation-tle-omm-twins", "ephemeris-type-4-refused"]   # the shipped propagation cases (Vallado's is not shipped)
MUTANTS = ["off-by-1e-6", "z-off-just-over-the-bar", "velocity-off-just-over-the-bar", "axes-swapped", "km-as-m",
           "constant-answer", "last-step-dropped", "wrong-error-code", "nan-with-code-0", "tle-and-omm-apart",
           "type-4-propagated", "type-4-codes-on-positions", "every-input-refused", "wgs84", "minutes-as-seconds",
           "bstar-ignored"]
OVER = 3e-7   # just over the 2e-7 bar: a grader whose bar has slipped past it lets these through (the review of D-414)
PHYSICS = {"wgs84", "minutes-as-seconds", "bstar-ignored"}


def tables(root):
    with open(os.path.join(root, "vectors", "propagation-twins.json"), encoding="utf-8") as f:
        ref = {s["norad_cat_id"]: s["steps"] for s in json.load(f)["sets"]}
    with open(os.path.join(root, "tests", "golden", "propagation-mutant-vectors.json"), encoding="utf-8") as f:
        sets = json.load(f)["sets"]
    wrong = {k: {s["norad_cat_id"]: s[k] for s in sets} for k in PHYSICS}
    return ref, wrong


def build(kind, root=ROOT):
    """The base (kind None) or one mutant, as a parser class with a propagate hook."""
    ref, wrong = tables(root)

    class Prop(Ref):
        def propagate(self, raw, fmt, tsince):
            (rec,) = [r for r in Ref.parse(self, raw, fmt) if isinstance(r, dict) and "norad_cat_id" in r]
            if kind == "every-input-refused":
                raise ValueError("refused")
            if rec.get("ephemeris_type") == 4 and kind not in ("type-4-propagated", "type-4-codes-on-positions"):
                raise ValueError("ephemeris type 4 (SGP4-XP): not an SGP4 element set")
            table = wrong[kind] if kind in PHYSICS else ref
            by_t = {s["t"]: s for s in table[rec["norad_cat_id"]]}
            out = [{"r": by_t[t].get("r"), "v": by_t[t].get("v"), "error": by_t[t]["error"]} for t in tsince]
            if kind == "off-by-1e-6":
                out = [dict(s, r=[s["r"][0] + 1e-6] + s["r"][1:]) for s in out]
            elif kind == "z-off-just-over-the-bar":
                out = [dict(s, r=s["r"][:2] + [s["r"][2] + OVER]) for s in out]
            elif kind == "velocity-off-just-over-the-bar":
                out = [dict(s, v=[s["v"][0], s["v"][1] + OVER, s["v"][2]]) for s in out]
            elif kind == "last-step-dropped":
                out = out[:-1]
            elif kind == "tle-and-omm-apart":   # each within the bar of the reference, the two 3e-7 apart
                half = OVER / 2 if fmt in ("tle", "2le") else -OVER / 2
                out = [dict(s, r=[s["r"][0] + half] + s["r"][1:]) for s in out]
            elif kind == "type-4-codes-on-positions" and rec.get("ephemeris_type") == 4:
                out = [dict(s, error=6) for s in out]
            elif kind == "axes-swapped":
                out = [dict(s, r=[s["r"][1], s["r"][0], s["r"][2]], v=[s["v"][1], s["v"][0], s["v"][2]]) for s in out]
            elif kind == "km-as-m":
                out = [dict(s, r=[x * 1000 for x in s["r"]], v=[x * 1000 for x in s["v"]]) for s in out]
            elif kind == "constant-answer":
                first = out[0]
                out = [dict(first) for _ in out]
            elif kind == "wrong-error-code" and out:   # the code alone wrong, beside correct values (the review of D-414)
                out[-1] = dict(out[-1], error=1)
            elif kind == "nan-with-code-0" and out:
                out[-1] = {"r": [math.nan] * 3, "v": [math.nan] * 3, "error": 0}
            return out
    Prop.__name__ = "Base" if kind is None else kind
    return Prop


def run(root=ROOT):
    """-> (base statuses, {mutant: statuses}); a mutant with no failing case is a survivor."""
    def statuses(kind):
        return {r.case_id: r.status for r in Runner(build(kind, root)(), root=root, fetch_hints=False).run(case_ids=CASES)}
    return statuses(None), {k: statuses(k) for k in MUTANTS}


def report(root=ROOT):
    """Print the result; True when the base passes every case and every mutant fails one."""
    base, muts = run(root)
    ok_base = all(s in ("pass", "pass-tolerance") for s in base.values())
    survivors = [k for k, st in muts.items() if not any(s == "fail" for s in st.values())]
    print(f"propagation mutants: base {'passes' if ok_base else 'DOES NOT PASS'} {json.dumps(base)}; "
          f"{len(MUTANTS) - len(survivors)} of {len(MUTANTS)} killed")
    for k in survivors:
        print(f"  SURVIVOR {k}: {json.dumps(muts[k])}")
    return ok_base and not survivors


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=ROOT)
    a = ap.parse_args(argv)
    return 0 if report(a.root) else 1


if __name__ == "__main__":
    sys.exit(main())
