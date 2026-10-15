# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
# Written by the fresh-session red team, 2026-10-10: a blind audit of the gpconf 0.7.0 release candidate, from its
# wheel and sdist alone, asked to get a wrong parser past the runner. Kept as written but for this header; see
# tests/adversarial/test_redteam2.py.
"""GUARD for F3. Reads ordinary TLE but declares `Unsupported` for TLE files that contain id 69999
(the corrupt-input TLE files). Confirms the D-280 all-or-none guard fires: because other TLE inputs
are read in the run, these skips are flipped to fail. This is why the F3 escape only works for a
format read NOWHERE in the run."""
from gpconf.adapters.reference import Parser as _Ref
from gpconf.runner import Unsupported
class Parser(_Ref):
    def parse(self, raw, fmt):
        if fmt in ("tle", "2le") and b"69999" in raw:
            raise Unsupported("tle")
        return super().parse(raw, fmt)
