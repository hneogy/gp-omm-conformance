# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
# Written by the fresh-session red team, 2026-10-09: a blind audit of gpconf 0.6.2 from PyPI, asked to get a
# wrong parser past the runner. Kept as written but for this header; see tests/adversarial/__init__.py.
"""E0: two outcomes that do NOT escape, recorded for completeness. Empty: a reader that returns no record from a
file the reference reads records from. RefuseSome: a reader that refuses, with a reason, every set whose BSTAR is
negative (88 of the 604 derived sets)."""
from decimal import Decimal

from gpconf.adapters.reference import Parser as Reference
from gpconf import tle as tlemod


class Empty(Reference):
    def parse(self, raw, fmt):
        out = super().parse(raw, fmt)
        return [] if fmt in ("tle", "2le") else out


class RefuseSome(Reference):
    def parse(self, raw, fmt):
        out = super().parse(raw, fmt)
        if fmt in ("tle", "2le"):
            out = [r if "_refused" in r or Decimal(str(r["bstar"])) >= 0
                   else {"_refused": "negative BSTAR is not supported", "_field": tlemod.to_alpha5(r["norad_cat_id"]), "_input": ""}
                   for r in out]
        return out
