# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
# Written by the fresh-session red team, 2026-10-10: a blind audit of the gpconf 0.7.0 release candidate, from its
# wheel and sdist alone, asked to get a wrong parser past the runner. Kept as written but for this header; see
# tests/adversarial/test_redteam2.py.
"""WIN F4. Bug: the TLE writer is defective, so write_tle declares writing unsupported for every
record. Escape: an all-records Unsupported makes the whole writer case `skip` (D-205/D-280). 0 fails."""
from gpconf.adapters.reference import Parser as _Ref
from gpconf.runner import Unsupported
class Parser(_Ref):
    def write_tle(self, record):
        raise Unsupported("no TLE writer")
