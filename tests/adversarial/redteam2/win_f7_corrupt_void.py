# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
# Written by the fresh-session red team, 2026-10-10: a blind audit of the gpconf 0.7.0 release candidate, from its
# wheel and sdist alone, asked to get a wrong parser past the runner. Kept as written but for this header; see
# tests/adversarial/test_redteam2.py.
"""WIN F7. Bug: the adapter silently drops catalog id 69999 from TLE input (the id every corrupt
TLE record carries). Escape: the corrupt-input case grades each edited record against THIS parser's
reading of the unedited file (D-175); since 69999 is dropped from the unedited TLE file too, the
runner says the comparison "says nothing about the edit" and marks the corrupt checks not-exercised
(cause=parser), never fail. TLE 69999 is value-graded nowhere offline, so 0 failing cases."""
from gpconf.adapters.reference import Parser as _Ref
class Parser(_Ref):
    def parse(self, raw, fmt):
        out = super().parse(raw, fmt)
        if fmt in ("tle", "2le"):
            out = [r for r in out if r.get("norad_cat_id") != 69999]
        return out
