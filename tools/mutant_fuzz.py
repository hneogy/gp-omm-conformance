#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""tools/mutant_fuzz.py -- mutation fuzzing of the runner's grading (the SM-26 plan, PLAN.md v0.6.3; issue #1).

Each mutant is the reference parser with ONE seeded mutation applied -- a wrong parser by construction.
It runs against the no-data cases; a mutant that earns ZERO failing case statuses is a SURVIVOR: a bug
the grading let through. Survivors are grouped by mutation and printed with their seeds, so each one can
be rebuilt and inspected:  python3 tools/mutant_fuzz.py --one SEED

Usage: python3 tools/mutant_fuzz.py [--count N] [--seed S] [--jobs J] [--root PATH] [--one SEED]
Standard library plus the corpus only; no network; the cases run offline.
"""
import argparse
import hashlib
import json
import multiprocessing
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from decimal import Decimal  # noqa: E402

from gpconf.adapters.reference import Parser as Ref  # noqa: E402
from gpconf.runner import Runner, Unsupported  # noqa: E402

NO_DATA_CASES = ["alpha5-encoding-vectors", "alpha5-tle-derived", "kvn-syntax-variants", "tle-writer-alpha5", "corrupt-input"]
DEC_FIELDS = ["mean_motion", "eccentricity", "inclination", "ra_of_asc_node", "arg_of_pericenter", "mean_anomaly",
              "bstar", "mean_motion_dot", "mean_motion_ddot"]
ALL_FIELDS = DEC_FIELDS + ["norad_cat_id", "epoch", "object_name", "object_id", "classification_type",
                           "element_set_no", "rev_at_epoch"]
MUTATIONS = ["perturb-field", "change-type", "drop-records", "duplicate-records", "reorder-records",
             "unsupported-inputs", "unsupported-hook-subset", "stray-refusal", "extra-records", "writer-partway"]


def _epoch_dt(v):
    """An epoch the reference returned -> a datetime, whatever form the file wrote it in (calendar or
    day-of-year, with or without Z): a mutant must mutate, never crash on its own bookkeeping."""
    import datetime as _dt
    from gpconf import tle as _tle
    if isinstance(v, _dt.datetime):
        return v.replace(tzinfo=None)
    return _dt.datetime.strptime(_tle.iso_epoch(v), "%Y-%m-%dT%H:%M:%S.%f")


def _stable(seed, *parts):
    h = hashlib.sha256((str(seed) + "|" + "|".join(map(str, parts))).encode()).digest()
    return int.from_bytes(h[:8], "big") / 2**64


def plan(seed):
    """Draw one mutation and its parameters, deterministically from the seed."""
    rng = random.Random(seed)
    kind = rng.choice(MUTATIONS)
    p = {"kind": kind, "seed": seed}
    if kind == "perturb-field":
        p["field"] = rng.choice(ALL_FIELDS)
        p["frac"] = rng.choice([0.01, 0.1, 1.0])
        p["delta"] = rng.choice(["+1", "+1e-7", "*1.001", "last-digit"])
    elif kind == "change-type":
        p["field"] = rng.choice(["norad_cat_id", "element_set_no", "rev_at_epoch", "eccentricity", "mean_motion", "epoch"])
        p["to"] = rng.choice(["float", "str"])
    elif kind == "drop-records":
        p["frac"] = rng.choice([0.01, 0.1, 0.5])
        p["silent"] = rng.choice([True, False])
    elif kind == "duplicate-records":
        p["where"] = rng.choice(["head", "tail"])
        p["wrong"] = rng.choice([True, False])
        p["field"] = rng.choice(DEC_FIELDS)
    elif kind == "reorder-records":
        p["how"] = rng.choice(["reverse", "shuffle"])
    elif kind == "unsupported-inputs":
        p["prob"] = rng.choice([0.2, 0.5, 0.8])
    elif kind == "unsupported-hook-subset":
        p["hook"] = rng.choice(["alpha5_decode", "alpha5_encode", "two_digit_year", "parse_catalog_id", "write_tle"])
        p["prob"] = rng.choice([0.2, 0.5, 0.9])
    elif kind == "stray-refusal":
        p["also_drop"] = rng.choice([True, False])
    elif kind == "extra-records":
        p["known_id"] = rng.choice([True, False])
        p["n"] = rng.choice([1, 5])
    elif kind == "writer-partway":
        p["after"] = rng.choice([1, 100, 606])
        p["wrong"] = rng.choice([True, False])
        p["raise_kind"] = rng.choice(["unsupported", "error"])
    return p


def build(p):
    """-> an adapter class for the plan. Per-record and per-input choices hash the seed with stable keys,
    so a mutant behaves identically however many times a file is parsed."""
    seed, kind = p["seed"], p["kind"]

    class M(Ref):
        pass

    if kind in ("perturb-field", "change-type", "drop-records", "duplicate-records", "reorder-records",
                "unsupported-inputs", "stray-refusal", "extra-records"):
        base_parse = Ref.parse

        def parse(self, raw, fmt):
            if kind == "unsupported-inputs" and _stable(seed, "input", hashlib.sha256(raw).hexdigest()[:16]) < p["prob"]:
                raise Unsupported(f"{fmt} input declared unsupported")
            out = base_parse(self, raw, fmt)
            meta = [r for r in out if isinstance(r, dict) and ("_adapter" in r or "_refused" in r)]
            recs = [r for r in out if r not in meta]
            if kind == "perturb-field":
                f = p["field"]
                def mutate_value(v):
                    if f == "epoch":  # a real shift of one second, never a sub-microsecond string artefact
                        import datetime as _dt
                        return (_epoch_dt(v) + _dt.timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%S.%f")
                    if p["delta"] == "+1":
                        try:
                            return type(v)(Decimal(str(v)) + 1) if not isinstance(v, str) else str(Decimal(v) + 1)
                        except Exception:
                            return str(v) + "1"
                    if p["delta"] == "+1e-7":
                        try:
                            return str(Decimal(str(v)) + Decimal("1e-7"))
                        except Exception:
                            return str(v) + "1"
                    if p["delta"] == "*1.001":
                        try:
                            return str(Decimal(str(v)) * Decimal("1.001"))
                        except Exception:
                            return str(v) + "1"
                    s = str(v)  # last-digit
                    return s[:-1] + ("0" if s[-1] != "0" else "1") if s else "1"
                def usable(v):
                    if v in (None, ""):
                        return False
                    if p["delta"] in ("*1.001",) and str(v).strip("0.-+") == "":
                        return False  # multiplying zero changes nothing
                    return True
                candidates = [r for r in recs if usable(r.get(f))]
                chosen = [r for r in candidates if _stable(seed, "rec", r.get("norad_cat_id"), f) < p["frac"]]
                if candidates and not chosen:
                    chosen = [candidates[int(_stable(seed, "force") * len(candidates)) % len(candidates)]]
                for r in chosen:
                    r[f] = mutate_value(r[f])
            elif kind == "change-type":
                f, to = p["field"], p["to"]
                for r in recs:
                    v = r.get(f)
                    if v in (None, ""):
                        continue
                    if f == "epoch":  # the other form the protocol allows: a datetime for an ISO string
                        r[f] = _epoch_dt(v) if isinstance(v, str) else v.strftime("%Y-%m-%dT%H:%M:%S.%f")
                        continue
                    target = to
                    if target == "str" and isinstance(v, str):
                        target = "float"      # never a no-op: the type really changes
                    elif target == "float" and isinstance(v, float):
                        target = "str"
                    try:
                        r[f] = float(v) if target == "float" else str(v)
                    except (TypeError, ValueError):
                        r[f] = str(v)
            elif kind == "drop-records":
                kept, refs = [], []
                forced = recs[int(_stable(seed, "forcedrop") * len(recs)) % len(recs)].get("norad_cat_id") if recs else None
                for r in recs:
                    if r.get("norad_cat_id") == forced or _stable(seed, "drop", r.get("norad_cat_id")) < p["frac"]:
                        if not p["silent"]:
                            refs.append({"_refused": "not parseable by this build", "_field": str(r.get("norad_cat_id"))})
                        continue
                    kept.append(r)
                recs = kept + refs
                if refs:
                    meta = [{"_adapter": {"refusals": True}}] + meta
            elif kind == "duplicate-records":
                copies = []
                for r in recs:
                    c = dict(r)
                    if p["wrong"] and c.get(p["field"]) not in (None, ""):
                        try:
                            c[p["field"]] = str(Decimal(str(c[p["field"]])) + 1)
                        except Exception:
                            pass
                    copies.append(c)
                recs = copies + recs if p["where"] == "head" else recs + copies
            elif kind == "reorder-records":
                if p["how"] == "reverse":
                    recs = list(reversed(recs))
                else:
                    rng = random.Random(seed ^ 0xA5)
                    rng.shuffle(recs)
            elif kind == "stray-refusal":
                if p["also_drop"] and recs:
                    k = max(0, int(_stable(seed, "pick") * len(recs)) - 1)
                    recs = recs[:k] + recs[k + 1:]
                meta = [{"_adapter": {"refusals": True}}] + meta
                recs = [{"_refused": "skipped a non-data line", "_field": "#####"}] + recs
            elif kind == "extra-records":
                if recs:
                    for i in range(p["n"]):
                        c = dict(recs[int(_stable(seed, "x", i) * len(recs)) % len(recs)])
                        if not p["known_id"]:
                            c["norad_cat_id"] = 65000 + i
                        recs = recs + [c]
            return meta + recs

        M.parse = parse

    if kind == "unsupported-hook-subset" and p["hook"] != "write_tle":
        hook_name = p["hook"]
        base_hook = getattr(Ref, hook_name)
        hook_state = {"n": 0}

        def hook(self, value):
            hook_state["n"] += 1
            # the first vector is always declared unsupported, so no draw is the reference itself: the mutant is
            # either unsupported for every vector (a legitimate skip, D-205) or a mix (which must fail)
            if hook_state["n"] == 1 or _stable(seed, "hook", value) < p["prob"]:
                raise Unsupported(f"{hook_name} unsupported for this input")
            return base_hook(self, value)

        setattr(M, hook_name, hook)

    if kind == "writer-partway" or (kind == "unsupported-hook-subset" and p["hook"] == "write_tle"):
        base_write = Ref.write_tle
        state = {"n": 0}

        def write_tle(self, record):
            if kind == "unsupported-hook-subset":
                if _stable(seed, "w", record.get("norad_cat_id")) < p["prob"]:
                    raise Unsupported("tle-writing unsupported for this record")
                return base_write(self, record)
            state["n"] += 1
            if state["n"] > p["after"]:
                if p["raise_kind"] == "unsupported":
                    raise Unsupported("tle-writing")
                raise RuntimeError("writer gave up partway")
            if p["wrong"]:
                rec = dict(record)
                rec["mean_motion"] = str(Decimal(str(rec["mean_motion"])) + Decimal("0.1"))
                return base_write(self, rec)
            return base_write(self, record)

        M.write_tle = write_tle
    return M


# The reviewed allowlist (D-287): the only survivor categories CI accepts, each with the entry that reviewed it.
ALLOWLIST = {
    "reorder-records": "records are matched by id, never by position (D-288)",
    "change-type-benign": "decimal strings and binary floats are the protocol for element values (D-131, D-289)",
    "stray-refusal-no-drop": "a refusal crediting no record, with every record returned, stays an info item (D-290)",
    "hook-all-unsupported": "a hook unsupported for every vector is a legitimate skip (D-205)",
    "format-level-unsupported": "a parser with no reader for a whole format skips it legitimately (D-280, ADAPTERS.md); "
                                "a partial draw dies on the all-or-none rule, so only format-consistent draws survive",
}
INT_FIELDS_FUZZ = {"norad_cat_id", "ephemeris_type", "element_set_no", "rev_at_epoch"}


def classify(p):
    """A survivor's category. Anything not in ALLOWLIST is a grader escape and fails --ci."""
    kind = p["kind"]
    if kind == "reorder-records":
        return "reorder-records"
    if kind == "change-type" and p["field"] not in INT_FIELDS_FUZZ:
        return "change-type-benign"
    # an exact duplicate was allowlisted under D-281 until D-311: a record returned more often than the input holds
    # it fails, so a surviving duplicate is an escape again and falls through to its ESCAPE category below
    if kind == "stray-refusal" and not p["also_drop"]:
        return "stray-refusal-no-drop"
    if kind == "unsupported-hook-subset" and p["hook"] != "write_tle":
        return "hook-all-unsupported"   # only the all-calls-unsupported draw can survive: a mix fails (D-205)
    if kind == "unsupported-inputs":
        return "format-level-unsupported"  # with every input registered, only whole-format draws survive (D-280)
    return f"ESCAPE:{kind}"


def run_one(args):
    seed, root = args
    p = plan(seed)
    try:
        results = Runner(build(p)(), root=root, fetch_hints=False).run(case_ids=NO_DATA_CASES)
    except Exception as e:
        return {"seed": seed, "kind": p["kind"], "params": p, "outcome": "runner-error", "detail": f"{type(e).__name__}: {e}"}
    statuses = {r.case_id: r.status for r in results}
    fails = sum(1 for s in statuses.values() if s == "fail")
    out = {"seed": seed, "kind": p["kind"], "params": p, "outcome": "survivor" if fails == 0 else "killed",
           "statuses": statuses, "failing_cases": fails}
    if out["outcome"] == "survivor":
        out["category"] = classify(p)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--count", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--jobs", type=int, default=os.cpu_count() or 2)
    ap.add_argument("--root", default=ROOT)
    ap.add_argument("--one", type=int, default=None, help="run a single mutant seed verbosely")
    ap.add_argument("--ci", action="store_true", help="exit 1 on any survivor outside the reviewed allowlist")
    ap.add_argument("--json", dest="json_out", default=None, help="write every outcome to this file")
    a = ap.parse_args(argv)
    if a.one is not None:
        r = run_one((a.one, a.root))
        print(json.dumps(r, indent=1, default=str))
        return 0
    seeds = [(a.seed + i, a.root) for i in range(a.count)]
    if a.jobs > 1:
        with multiprocessing.Pool(a.jobs) as pool:
            rows = pool.map(run_one, seeds, chunksize=16)
    else:
        rows = [run_one(s) for s in seeds]
    survivors = [r for r in rows if r["outcome"] == "survivor"]
    errors = [r for r in rows if r["outcome"] == "runner-error"]
    by_kind, surv_kind = {}, {}
    for r in rows:
        by_kind[r["kind"]] = by_kind.get(r["kind"], 0) + 1
    for r in survivors:
        surv_kind.setdefault(r["kind"], []).append(r)
    print(f"{len(rows)} mutants (seed {a.seed}..{a.seed + a.count - 1}): {len(survivors)} survivors, "
          f"{len(rows) - len(survivors) - len(errors)} killed, {len(errors)} runner errors")
    for kind in MUTATIONS:
        n, s = by_kind.get(kind, 0), surv_kind.get(kind, [])
        print(f"  {kind:24s} {len(s):5d} of {n:5d} survive")
    for kind, rs in sorted(surv_kind.items()):
        eg = rs[0]
        print(f"-- {kind}: e.g. seed {eg['seed']} {json.dumps({k: v for k, v in eg['params'].items() if k not in ('kind', 'seed')})} "
              f"statuses {json.dumps(eg['statuses'])}")
    cats = {}
    for r in survivors:
        cats.setdefault(r["category"], []).append(r["seed"])
    for cat, seeds in sorted(cats.items()):
        mark = "allowlisted" if cat in ALLOWLIST else "NOT ALLOWLISTED"
        print(f"   {cat:26s} {len(seeds):5d} survivors ({mark}; e.g. seeds {seeds[:3]})")
    escapes = [r for r in survivors if r["category"] not in ALLOWLIST]
    if a.json_out:
        with open(a.json_out, "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=0, default=str)
    if errors:
        print(f"first runner error: seed {errors[0]['seed']}: {errors[0]['detail']}")
    if a.ci and (escapes or errors):
        print(f"CI GATE: {len(escapes)} survivor(s) outside the allowlist, {len(errors)} runner error(s)")
        for r in escapes[:10]:
            print(f"  ESCAPE seed {r['seed']}: {json.dumps(r['params'])}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
