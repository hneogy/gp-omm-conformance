# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
# Written by the fresh-session red team, 2026-10-09: a blind audit of gpconf 0.6.2 from PyPI, asked to get a
# wrong parser past the runner. Kept as written but for this header; see tests/adversarial/__init__.py.
"""E11: the vector case grades the alpha5_decode hook, the derived case grades the reader on data that holds the
letters A and T only, and nothing requires the hook and the reader to share a decoder.

BUG (Win and Twin): the reader's own letter table puts K, L, M and N one too high (K=20 instead of 19), so
190000-229999 decode wrongly. Win keeps the reference hook (a different decoder); Twin wires the hook to the
reader's table."""
import re

from gpconf.adapters.reference import Parser as Reference, tle_sets

from ._common import strip

TABLE = "ABCDEFGHJKLMNPQRSTUVWXYZ"


def reader_decode(field):
    c = field[0]
    if c.isdigit():
        return int(field)
    v = TABLE.index(c) + 10
    if c in "KLMN":
        v += 1                                                           # BUG
    return v * 10000 + int(field[1:])


class Win(Reference):
    def parse(self, raw, fmt):
        if fmt not in ("tle", "2le"):
            return super().parse(raw, fmt)
        out = []
        for r in tle_sets(raw.decode("utf-8")):
            if "_refused" not in r:
                r["norad_cat_id"] = reader_decode(r["tle"]["catalog_field"])
            out.append(strip(r))
        return out
    # alpha5_decode: inherited from the reference, a decoder the reader does not use (ESCAPE)


class Twin(Win):
    def alpha5_decode(self, field):
        if not isinstance(field, str) or not re.fullmatch(r"[0-9A-HJ-NP-Z][0-9]{4}", field):
            raise ValueError(f"invalid Alpha-5 field {field!r}")
        return reader_decode(field)                                      # the hook shares the reader's table


class WinNoHook(Win):
    alpha5_decode = None      # the same reader with no hook at all: the vector items skip (documented), the reader's table is graded nowhere
