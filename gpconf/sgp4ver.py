# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""
gpconf/sgp4ver.py -- readers for Vallado's two SGP4 verification files, `SGP4-VER.TLE` and `tcppver.out` (the code
accompanying AIAA 2006-6753), and the time schedule the verification driver follows.

gpconf ships neither file (D-388): they are located on the user's machine and checked against the corpus's manifest
(harnesses/vallado/reference-manifest.json) before anything is graded. Standard library only; written from the
files' layout as the corpus measured it, nothing copied.

`SGP4-VER.TLE`: `#` comment lines, then for each element set its line 1 and a line 2 that carries, after column 69,
the start, stop and step of the run in minutes since epoch. `tcppver.out`: for each set a header `NNNNN xx`, then
one line per step: minutes since epoch, TEME position (km) and velocity (km/s); lines after a block's first carry
osculating elements and the calendar time too, which are not read here.
"""
import re

HEADER = re.compile(r"^\s*(\d+)\s+xx\s*$")


def parse_ver_tle(text):
    """SGP4-VER.TLE -> [{'catalog', 'comment', 'line1', 'line2', 'start', 'stop', 'step'}] in file order; the comment
    is the last '#' line before the set, as the file names the branch each set exercises."""
    sets, comment = [], None
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("#"):
            comment = line[1:].strip()
        elif line.startswith("1 "):
            if i + 1 >= len(lines) or not lines[i + 1].startswith("2 "):
                raise ValueError(f"line {i + 1}: a line 1 with no line 2 after it")
            l2 = lines[i + 1]
            run = l2[69:].split()
            if len(run) != 3:
                raise ValueError(f"line {i + 2}: expected start, stop and step after column 69, found {run!r}")
            sets.append({"catalog": int(line[2:7]), "comment": comment, "line1": line[:69], "line2": l2[:69],
                         "start": float(run[0]), "stop": float(run[1]), "step": float(run[2])})
            comment = None
            i += 1
        elif line.strip():
            raise ValueError(f"line {i + 1}: neither a comment nor an element line: {line[:40]!r}")
        i += 1
    return sets


def parse_tcppver(text):
    """tcppver.out -> [{'catalog', 'rows': [(t, x, y, z, vx, vy, vz)]}] in file order."""
    blocks: list = []
    for n, line in enumerate(text.splitlines(), 1):
        m = HEADER.match(line)
        if m:
            blocks.append({"catalog": int(m.group(1)), "rows": []})
            continue
        if not line.strip():
            continue
        if not blocks:
            raise ValueError(f"line {n}: a data line before any header")
        f = line.split()
        if len(f) < 7:
            raise ValueError(f"line {n}: {len(f)} fields where 7 or more are expected")
        blocks[-1]["rows"].append(tuple(float(x) for x in f[:7]))
    return blocks


def schedule(start, stop, step):
    """The minutes since epoch the verification driver propagates to, in order: 0 first; then from start by step while
    not past stop, 0 not twice; then stop itself when the stepping ended more than a microminute short of it."""
    times = [0.0]
    t = start
    while t <= stop:
        if not (t == start == 0.0):
            times.append(t)
        t += step
    if t - stop < step - 1e-6:
        times.append(stop)
    return times
