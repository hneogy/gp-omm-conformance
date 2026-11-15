#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""A gpconf adapter template for a parser in Python, run by command:

    python3 -m gpconf run --cmd "python3 templates/python/adapter.py {fmt}"

gpconf writes one file to standard input and reads a JSON array of records from standard output (docs/ADAPTERS.md,
"The command protocol"). Replace `toy_parse` with a call to your library; keep the rest. The toy parser reads TLE
only and is here so the template runs as it stands; it is not a parser to use. A Python library can also be loaded
in-process with `--adapter module:Class` (docs/ADAPTERS.md, "The Python protocol")."""
import json
import sys

ALPHA5 = "ABCDEFGHJKLMNPQRSTUVWXYZ"   # I and O are skipped


def alpha5(field):
    """Space-Track's Alpha-5: a digit or an uppercase letter other than I and O, then four digits."""
    if len(field) != 5 or not field[1:].isdigit() or not field[1:].isascii():
        raise ValueError(f"invalid catalog field {field!r}")
    c = field[0]
    if c in "0123456789":
        return int(field)
    if c not in ALPHA5:
        raise ValueError(f"invalid catalog field {field!r}")
    return (ALPHA5.index(c) + 10) * 10000 + int(field[1:])


def checksum(line):
    return sum(int(c) if c in "0123456789" else c == "-" for c in line[:68]) % 10


def exponent(field):
    """' 12345-3' -> '0.12345e-3' as text, so it is compared exactly."""
    f = field.strip()
    sign = "-" if f.startswith("-") else ""
    f = f.lstrip("+-")
    return f"{sign}0.{f[:5]}e{f[5:]}"


def toy_parse(text):
    """The toy: name line optional, two element lines, fixed columns, the checksum checked. Values are returned as
    the file's own digits, as text, so gpconf compares them exactly."""
    lines = [l.rstrip("\r") for l in text.split("\n")]
    out, i = [], 0
    while i < len(lines):
        l1 = lines[i]
        if l1.startswith("1 ") and i + 1 < len(lines) and lines[i + 1].startswith("2 "):
            l2 = lines[i + 1]
            name = lines[i - 1].strip() if i > 0 and lines[i - 1].strip() and not lines[i - 1].startswith("2 ") else None
            try:
                out.append(record(name, l1, l2))
            except (ValueError, ArithmeticError) as e:   # the refusal channel: the record was dropped, and why (docs/ADAPTERS.md, "Refusals")
                out.append({"_refused": f"ValueError: {e}", "_field": l1[2:7], "_input": l1[:80]})
            i += 2
            continue
        if l1.startswith(("1 ", "2 ")):
            out.append({"_refused": "an element line that pairs with nothing", "_field": l1[2:7], "_input": l1[:80]})
        i += 1
    return out


def record(name, l1, l2):
    if len(l1) != 69 or len(l2) != 69:
        raise ValueError(f"line lengths {len(l1)}/{len(l2)}, not 69")
    if l1[68] != str(checksum(l1)) or l2[68] != str(checksum(l2)):
        raise ValueError("checksum")
    if l1[2:7] != l2[2:7]:
        raise ValueError("line 2's catalog number is not line 1's")
    if not l1[18:20].isdigit() or not l1[18:20].isascii():
        raise ValueError(f"epoch year {l1[18:20]!r} is not two digits")
    yy, day = int(l1[18:20]), l1[20:32]
    year = 1900 + yy if yy >= 57 else 2000 + yy
    return {
        "norad_cat_id": alpha5(l1[2:7]),
        "object_name": name,
        # an epoch your parser built: here the year and the day of year, which gpconf reads as "YYYY-DDD.ddd..."
        "epoch": epoch_text(year, day),
        "mean_motion": l2[52:63].strip(),
        "eccentricity": "0." + l2[26:33],
        "inclination": l2[8:16].strip(),
        "ra_of_asc_node": l2[17:25].strip(),
        "arg_of_pericenter": l2[34:42].strip(),
        "mean_anomaly": l2[43:51].strip(),
        "bstar": exponent(l1[53:61]),
        "mean_motion_dot": l1[33:43].strip().replace(" ", ""),
        "mean_motion_ddot": exponent(l1[44:52]),
    }


def epoch_text(year, day):
    """'DDD.DDDDDDDD', the TLE's day of year -> 'YYYY-MM-DDThh:mm:ss.ffffff'. Eight decimals of a day are a whole
    number of microseconds (1e-8 day is 864 us), so the arithmetic is exact in integers."""
    import datetime as dt
    if len(day) != 12 or day[3] != "." or not (day[:3] + day[4:]).isdigit() or not day.isascii():
        raise ValueError(f"epoch day {day!r} is not DDD.DDDDDDDD")
    us = (int(day[:3]) - 1) * 86_400_000_000 + int(day[4:]) * 864
    t = dt.datetime(year, 1, 1) + dt.timedelta(microseconds=us)
    return t.strftime("%Y-%m-%dT%H:%M:%S.%f")


def main():
    fmt = sys.argv[1] if len(sys.argv) > 1 else "tle"
    if fmt not in ("tle", "2le"):
        sys.exit(3)   # exit 3: this format is not supported; the file is reported as a skip
    text = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    try:
        records = toy_parse(text)
    except Exception as e:   # anything unexpected: say so on standard error and exit 1, never crash with a signal
        print(f"adapter: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
    json.dump(records, sys.stdout)


if __name__ == "__main__":
    main()
