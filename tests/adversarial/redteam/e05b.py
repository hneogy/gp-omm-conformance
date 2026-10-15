# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
# Written by the fresh-session red team, 2026-10-09: a blind audit of gpconf 0.6.2 from PyPI, asked to get a
# wrong parser past the runner. Kept as written but for this header; see tests/adversarial/__init__.py.
"""E5b: the type of norad_cat_id in parse() output is checked only by the check catalog-number-is-integer, which no
case that runs without fetched data lists (alpha5-tle-derived, kvn-syntax-variants and corrupt-input do not).

BUG: every catalog number parse() returns is a float."""
from gpconf.adapters.reference import Parser as Reference


class Win(Reference):
    def parse(self, raw, fmt):
        out = super().parse(raw, fmt)
        for r in out:
            if "_refused" not in r and r.get("norad_cat_id") is not None:
                r["norad_cat_id"] = float(r["norad_cat_id"])
        return out
