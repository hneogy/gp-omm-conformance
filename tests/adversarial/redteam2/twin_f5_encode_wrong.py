# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
# Written by the fresh-session red team, 2026-10-10: a blind audit of the gpconf 0.7.0 release candidate, from its
# wheel and sdist alone, asked to get a wrong parser past the runner. Kept as written but for this header; see
# tests/adversarial/test_redteam2.py.
"""TWIN F5. Same defect exposed: alpha5_encode answers, but wrong. Removing the escape: the
encode vectors are graded and FAIL."""
from gpconf.adapters.reference import Parser as _Ref
from gpconf import tle as tlemod
class Parser(_Ref):
    def alpha5_encode(self, n):
        return tlemod.to_alpha5(n + 1)   # off by one
