# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
# Written by the fresh-session red team, 2026-10-10: a blind audit of the gpconf 0.7.0 release candidate, from its
# wheel and sdist alone, asked to get a wrong parser past the runner. Kept as written but for this header; see
# tests/adversarial/test_redteam2.py.
"""WIN F5. Bug: the Alpha-5 encoder is defective, so alpha5_encode declares the operation
unsupported for every vector. Escape: all-vectors Unsupported makes the alpha5-encode item `skip`
(D-205). 0 failing cases."""
from gpconf.adapters.reference import Parser as _Ref
from gpconf.runner import Unsupported
class Parser(_Ref):
    def alpha5_encode(self, n):
        raise Unsupported("no alpha5 encoder")
