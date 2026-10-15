# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
# Written by the fresh-session red team, 2026-10-09: a blind audit of gpconf 0.6.2 from PyPI, asked to get a
# wrong parser past the runner. Kept as written but for this header; see tests/adversarial/__init__.py.
"""E1: Unsupported is accepted per file, on content, so a reader can skip exactly the files its bug would fail.

BUG (Win and Twin): the TLE reader decodes the Alpha-5 letter by its position in the alphabet without skipping I and
O, so every letter from J on decodes 10000 too high (J0000 -> 190000, T0449 -> 290449; A-H are right by luck)."""
from gpconf.adapters.reference import Parser as Reference, tle_sets
from gpconf.runner import Unsupported

from ._common import strip


def alphabet_decode(field):
    c = field[0]
    if c.isdigit():
        return int(field)
    return (ord(c) - ord("A") + 10) * 10000 + int(field[1:])   # BUG: I and O are not skipped


class Twin(Reference):
    def parse(self, raw, fmt):
        if fmt not in ("tle", "2le"):
            return super().parse(raw, fmt)
        out = []
        for r in tle_sets(raw.decode("utf-8")):
            if "_refused" not in r:
                r["norad_cat_id"] = alphabet_decode(r["tle"]["catalog_field"])
            out.append(strip(r))
        return out


class Win(Twin):
    def parse(self, raw, fmt):
        if fmt in ("tle", "2le"):
            text = raw.decode("utf-8")
            if any(l.startswith("1 ") and l[2:3] and l[2:3] in "JKLMNPQRSTUVWXYZ" for l in text.splitlines()):
                raise Unsupported("Alpha-5 letters beyond H are not supported by this reader")   # ESCAPE: per-file skip
        return super().parse(raw, fmt)
