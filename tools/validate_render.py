#!/usr/bin/env python3
"""
tools/validate_render.py -- check that tools/tlerender.py reproduces CelesTrak's TLE lines.

For every (name.csv, name.tle) pair under fixtures/*/raw/, render each CSV record and compare
with the TLE CelesTrak served for the same catalog number. Reports exact-match counts per line
for each rendering variant, and prints the first mismatches as diffs.
"""
import csv
import glob
import io
import os
import sys
from decimal import ROUND_HALF_UP, ROUND_HALF_EVEN

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tlerender as R  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read_tle(path):
    lines = open(path, encoding="utf-8").read().splitlines()
    out = {}
    for i, l in enumerate(lines):
        if l.startswith("1 ") and i + 1 < len(lines) and lines[i + 1].startswith("2 "):
            name = lines[i - 1] if i > 0 and lines[i - 1][:2] not in ("1 ", "2 ") else None
            out[R.from_alpha5(l[2:7])] = (name, l, lines[i + 1])
    return out


def main():
    pairs = []
    for c in sorted(glob.glob(os.path.join(ROOT, "fixtures", "*", "raw", "*.csv"))):
        t = c[:-4] + ".tle"
        if os.path.exists(t) and os.path.getsize(t) > 100:
            pairs.append((c, t))
    variants = {
        "trunc/trunc/HALF_UP": dict(mantissa_mode="truncate", ecc_mode="truncate", epoch_rounding=ROUND_HALF_UP),
        "round/trunc/HALF_UP": dict(mantissa_mode="round", ecc_mode="truncate", epoch_rounding=ROUND_HALF_UP),
        "trunc/round/HALF_UP": dict(mantissa_mode="truncate", ecc_mode="round", epoch_rounding=ROUND_HALF_UP),
        "trunc/trunc/HALF_EVEN": dict(mantissa_mode="truncate", ecc_mode="truncate", epoch_rounding=ROUND_HALF_EVEN),
    }
    totals = {v: [0, 0, 0, 0] for v in variants}  # l0, l1, l2, n
    shown = 0
    for cpath, tpath in pairs:
        rows = list(csv.DictReader(io.StringIO(open(cpath, encoding="utf-8").read())))
        tles = read_tle(tpath)
        rel = os.path.relpath(cpath, ROOT)
        for v, kw in variants.items():
            m0 = m1 = m2 = n = 0
            for r in rows:
                cat = int(r["NORAD_CAT_ID"])
                if cat not in tles:
                    continue
                n += 1
                name, l1, l2 = tles[cat]
                try:
                    r0, r1, r2 = R.render(r, catnum_field=l1[2:7], **kw)
                except Exception as e:  # report but keep counting
                    if v == "trunc/trunc/HALF_UP" and shown < 5:
                        print(f"RENDER ERROR {rel} id {cat}: {e}")
                        shown += 1
                    continue
                m0 += (name == r0)
                m1 += (l1 == r1)
                m2 += (l2 == r2)
                if v == "trunc/trunc/HALF_UP" and (l1 != r1 or l2 != r2 or name != r0) and shown < 12:
                    shown += 1
                    print(f"\nMISMATCH {rel} id {cat}")
                    if name != r0:
                        print(f"  L0 celestrak: {name!r}\n  L0 rendered : {r0!r}")
                    for a, b, lab in ((l1, r1, "L1"), (l2, r2, "L2")):
                        if a != b:
                            print(f"  {lab} celestrak: {a}\n  {lab} rendered : {b}\n  {lab} diff     : " +
                                  "".join(" " if x == y else "^" for x, y in zip(a, b)))
            totals[v][0] += m0
            totals[v][1] += m1
            totals[v][2] += m2
            totals[v][3] += n
            if v == "trunc/trunc/HALF_UP":
                print(f"{rel}: {n} pairs; L0 {m0}/{n}, L1 {m1}/{n}, L2 {m2}/{n}")
    print("\n=== totals by variant (mantissa/ecc/epoch rounding) ===")
    for v, (a, b, c, n) in totals.items():
        print(f"{v:>24}: L0 {a}/{n}  L1 {b}/{n}  L2 {c}/{n}")


if __name__ == "__main__":
    main()
