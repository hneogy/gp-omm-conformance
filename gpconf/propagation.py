# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""
gpconf/propagation.py -- the propagation tier's reference and grading (Phase 3 of 0.9.0; lane C's design, with the
owner's rulings of 2026-10-25 and 2026-11-01).

The reference is Vallado's verification pair, `SGP4-VER.TLE` and `tcppver.out` (AIAA 2006-6753). gpconf ships neither
file (D-388): `locate` finds them on the user's machine and checks their bytes against the corpus's manifest
(`harnesses/vallado/reference-manifest.json`) before anything is graded. gpconf has no propagator of its own: it
compares the numbers a parser's `propagate` hook gives with the numbers in the located file.

The grading, as ruled: TEME position (km) and velocity (km/s), each component on its own, within 2e-7 absolute
(python-sgp4's own bar; the largest difference always printed); WGS-72 and opsmode 'i' only, so WGS-84 or 'a' is a
wrong answer for this reference; SGP4 error codes matched exactly, at the step after a block's last printed line
(at t = 0 for the set whose one printed line repeats the previous set's last, which is not graded for its values);
a non-zero code before that step is a false decay; values on an error step are not compared.
"""
import hashlib
import importlib.util
import json
import math
import os

from . import sgp4ver

BAR = 2e-7   # km and km/s, each component, absolute (the owner's ruling on question 5, 2026-11-01)
FILES = ("SGP4-VER.TLE", "tcppver.out")


def manifest(root):
    with open(os.path.join(root, "harnesses", "vallado", "reference-manifest.json"), encoding="utf-8") as f:
        return json.load(f)


def _candidates(root, explicit, data=None):
    if explicit:
        yield explicit, "the directory given with --sgp4-ver"
        return
    try:
        spec = importlib.util.find_spec("sgp4")
    except (ImportError, ValueError):
        spec = None
    for d in (spec.submodule_search_locations or []) if spec else []:
        yield d, "the installed python-sgp4 package"
    if data:   # what `gpconf fetch --include-propagation` downloaded, beside the provider data (D-455)
        yield os.path.join(data, "propagation"), "the copy gpconf fetch --include-propagation downloaded"
    yield os.path.join(root, "harnesses", "vallado", "reference"), "the corpus's private copy (a private checkout only, D-388)"


def locate(root, explicit=None, data=None):
    """-> (directory, where, None) for the first candidate holding both files with the manifest's bytes, or
    (None, None, why) when none does; a candidate whose bytes differ is named in `why`, never used."""
    want = manifest(root)["files"]
    seen = []
    for d, where in _candidates(root, explicit, data):
        if not all(os.path.isfile(os.path.join(d, f)) for f in FILES):
            seen.append(f"{where}: not found")
            continue
        bad = []
        for f in FILES:
            with open(os.path.join(d, f), "rb") as fh:
                b = fh.read()
            if hashlib.sha256(b).hexdigest() != want[f]["sha256"]:
                bad.append(f)
        if bad:
            seen.append(f"{where}: {', '.join(bad)} differ from the corpus's manifest, not used")
            continue
        return d, where, None
    return None, None, "; ".join(seen)


def reference(directory, root):
    """The graded reference, one entry per element set, in file order: catalog, the two lines, the minutes the driver
    propagates to, the printed rows (t, x, y, z, vx, vy, vz) and, where the block ends in an error, its code and step,
    from the corpus's manifest (measured, D-388)."""
    man = manifest(root)
    with open(os.path.join(directory, "SGP4-VER.TLE"), encoding="ascii") as f:
        sets = sgp4ver.parse_ver_tle(f.read())
    with open(os.path.join(directory, "tcppver.out"), encoding="ascii") as f:
        blocks = sgp4ver.parse_tcppver(f.read())
    out = []
    for s, b, m in zip(sets, blocks, man["sets"]):
        if not (s["catalog"] == b["catalog"] == m["catalog"]):
            raise ValueError(f"the files and the manifest list different element sets at {s['catalog']}")
        times = sgp4ver.schedule(s["start"], s["stop"], s["step"])
        err = m.get("error")
        out.append({"catalog": s["catalog"], "line1": s["line1"], "line2": s["line2"], "times": times,
                    "rows": b["rows"], "error": err, "stale": bool(err and err.get("stale_line"))})
    return out


def _vector(v):
    """Three finite numbers (bool is no number) -> a tuple of floats, else None."""
    if not isinstance(v, (list, tuple)) or len(v) != 3:
        return None
    if any(type(x) not in (int, float) for x in v):
        return None
    f = tuple(float(x) for x in v)
    return f if all(math.isfinite(x) for x in f) else None


def grade_set(ref, answers):
    """One element set's answers -> (problems, stats). problems: {"values": [...], "codes": [...]}, what is wrong in
    words (both empty: the set passes); stats: {"compared", "max_r", "max_v"} over the steps compared."""
    times, rows, err = ref["times"], ref["rows"], ref["error"]
    if not isinstance(answers, (list, tuple)) or len(answers) != len(times):   # the guard hands a list back as a tuple
        n = len(answers) if isinstance(answers, (list, tuple)) else None
        return ({"values": [f"{len(times)} steps asked, {'no list' if n is None else n} answered"], "codes": []},
                {"compared": 0, "max_r": 0.0, "max_v": 0.0})
    vals, codes, compared, max_r, max_v = [], [], 0, 0.0, 0.0
    last = err["step_index"] if err else len(times) - 1   # the step whose code is graded, or the last step
    for i in range(last + 1):
        a = answers[i]
        if not isinstance(a, dict):
            vals.append(f"t = {times[i]:g}: the answer is no object")
            continue
        code = a.get("error", 0)
        if type(code) is not int:
            codes.append(f"t = {times[i]:g}: error {code!r} is no integer")
            continue
        if err and i == err["step_index"]:
            if code != err["code"]:
                codes.append(f"t = {times[i]:g}: error {code} where the reference ends the run with error {err['code']}"
                                + (" (a silent propagation)" if code == 0 else ""))
            continue
        if code != 0:
            codes.append(f"t = {times[i]:g}: error {code} where the reference propagates (a false decay)")
            continue
        r, v = _vector(a.get("r")), _vector(a.get("v"))
        if r is None or v is None:
            vals.append(f"t = {times[i]:g}: r and v must each be three finite numbers")
            continue
        want = rows[i]
        dr = max(abs(x - y) for x, y in zip(r, want[1:4]))
        dv = max(abs(x - y) for x, y in zip(v, want[4:7]))
        compared += 1
        max_r, max_v = max(max_r, dr), max(max_v, dv)
        if dr > BAR or dv > BAR:
            vals.append(f"t = {times[i]:g}: position off by {dr:.3g} km, velocity by {dv:.3g} km/s (the bar {BAR:g})")
    return {"values": vals, "codes": codes}, {"compared": compared, "max_r": max_r, "max_v": max_v}


def raw_of(ref):
    """The element set as a two-line TLE file's bytes, as the parse hook gets a file."""
    return (ref["line1"] + "\r\n" + ref["line2"] + "\r\n").encode("ascii")


def twins(root):
    """The TLE/OMM twins' reference (D-406): vectors/propagation-twins.json, the corpus's own SGP4 output for each set
    of derived/propagation-twins/twins.tle, with the files' SHA-256 it was made from."""
    with open(os.path.join(root, "vectors", "propagation-twins.json"), encoding="utf-8") as f:
        return json.load(f)


def grade_steps(steps, answers):
    """One set's answers against the twins' reference steps -> (problems, stats), as grade_set: every step compared,
    the code exactly, the position and velocity within BAR where the reference propagated."""
    if not isinstance(answers, (list, tuple)) or len(answers) != len(steps):
        n = len(answers) if isinstance(answers, (list, tuple)) else None
        return ({"values": [f"{len(steps)} steps asked, {'no list' if n is None else n} answered"], "codes": []},
                {"compared": 0, "max_r": 0.0, "max_v": 0.0})
    vals, codes, compared, max_r, max_v = [], [], 0, 0.0, 0.0
    for st, a in zip(steps, answers):
        t = st["t"]
        if not isinstance(a, dict):
            vals.append(f"t = {t:g}: the answer is no object")
            continue
        code = a.get("error", 0)
        if type(code) is not int:
            codes.append(f"t = {t:g}: error {code!r} is no integer")
            continue
        if code != st["error"]:
            codes.append(f"t = {t:g}: error {code} where the reference gives {st['error']}")
            continue
        if code:
            continue
        r, v = _vector(a.get("r")), _vector(a.get("v"))
        if r is None or v is None:
            vals.append(f"t = {t:g}: r and v must each be three finite numbers")
            continue
        dr = max(abs(x - y) for x, y in zip(r, st["r"]))
        dv = max(abs(x - y) for x, y in zip(v, st["v"]))
        compared += 1
        max_r, max_v = max(max_r, dr), max(max_v, dv)
        if dr > BAR or dv > BAR:
            vals.append(f"t = {t:g}: position off by {dr:.3g} km, velocity by {dv:.3g} km/s (the bar {BAR:g})")
    return {"values": vals, "codes": codes}, {"compared": compared, "max_r": max_r, "max_v": max_v}


def both_propagated(a, b):
    """How many steps both answers propagated to a position and a velocity with no error (D-459: an agreement over no
    step is no agreement)."""
    n = 0
    for x, y in zip(a or [], b or []):
        if isinstance(x, dict) and isinstance(y, dict) and x.get("error", 0) == 0 == y.get("error", 0) \
                and None not in (_vector(x.get("r")), _vector(x.get("v")), _vector(y.get("r")), _vector(y.get("v"))):
            n += 1
    return n


def agree(a, b):
    """The largest difference between two answers' positions and velocities, step by step, over steps both
    propagated, and the steps whose codes differ -> (max_r, max_v, [t...])."""
    max_r = max_v = 0.0
    differ = []
    for i, (x, y) in enumerate(zip(a or [], b or [])):
        if not (isinstance(x, dict) and isinstance(y, dict)):
            continue
        if x.get("error", 0) != y.get("error", 0):
            differ.append(i)
            continue
        rx, vx, ry, vy = _vector(x.get("r")), _vector(x.get("v")), _vector(y.get("r")), _vector(y.get("v"))
        if None in (rx, vx, ry, vy):
            continue
        max_r = max(max_r, max(abs(p - q) for p, q in zip(rx, ry)))
        max_v = max(max_v, max(abs(p - q) for p, q in zip(vx, vy)))
    return max_r, max_v, differ
