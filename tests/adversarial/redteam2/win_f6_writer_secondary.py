# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
# Written by the fresh-session red team, 2026-10-10: a blind audit of the gpconf 0.7.0 release candidate, from its
# wheel and sdist alone, asked to get a wrong parser past the runner. Kept as written but for this header; see
# tests/adversarial/test_redteam2.py.
"""WIN F6. Bug: the writer drops/zeroes the first derivative, element-set number and revolution
number in its output lines. Escape: these are SECONDARY_FIELDS, reported for information and never
failed by the writer case (D per ADAPTERS.md writer section). 0 failing cases."""
from gpconf.adapters.reference import Parser as _Ref
class Parser(_Ref):
    def write_tle(self, record):
        rec = dict(record)
        rec["mean_motion_dot"] = 0
        rec["element_set_no"] = 0
        rec["rev_at_epoch"] = 0
        return super().write_tle(rec)
