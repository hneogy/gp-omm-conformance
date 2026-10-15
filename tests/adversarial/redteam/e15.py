# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
# Written by the fresh-session red team, 2026-10-09: a blind audit of gpconf 0.6.2 from PyPI, asked to get a
# wrong parser past the runner. Kept as written but for this header; see tests/adversarial/__init__.py.
"""E15: no case that runs without fetched data grades a CSV, JSON or XML value against an oracle: the only OMM
files that ship are corrupt-input's, which the reference reader refuses whole before any value is read, and whose
unedited twins are compared with the parser's own reading, not with the frozen values.

BUG: the OMM readers lose the sign of the drag terms (BSTAR, MEAN_MOTION_DOT, MEAN_MOTION_DDOT)."""
from decimal import Decimal

from gpconf.adapters.reference import Parser as Reference


class Win(Reference):
    def parse(self, raw, fmt):
        out = super().parse(raw, fmt)
        if fmt in ("csv", "json", "xml"):
            for r in out:
                if "_refused" in r:
                    continue
                for k in ("bstar", "mean_motion_dot", "mean_motion_ddot"):
                    if r.get(k) is not None:
                        r[k] = format(Decimal(str(r[k])).copy_abs(), "f")   # BUG
        return out
