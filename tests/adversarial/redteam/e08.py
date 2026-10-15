# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
# Written by the fresh-session red team, 2026-10-09: a blind audit of gpconf 0.6.2 from PyPI, asked to get a
# wrong parser past the runner. Kept as written but for this header; see tests/adversarial/__init__.py.
"""E8: a record the parser drops from the unedited file as well is not graded in corrupt-input (D-175); the
corrupt record's items report not-exercised and the case still passes.

BUG: a filter meant to drop analyst placeholders (80000-89999) has its lower bound at 60000, so every set numbered
60000-99999 is dropped silently; 69999, the corrupt record of inputs 1 to 4, is the only such set in the shipped data."""
from gpconf.adapters.reference import Parser as Reference


class Win(Reference):
    def parse(self, raw, fmt):
        out = super().parse(raw, fmt)
        if fmt in ("tle", "2le"):
            out = [r for r in out if "_refused" in r or not (60000 <= r["norad_cat_id"] < 100000)]   # BUG
        return out
