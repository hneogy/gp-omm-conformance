# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
# Written by the fresh-session red team, 2026-10-10: a blind audit of the gpconf 0.7.0 release candidate, from its
# wheel and sdist alone, asked to get a wrong parser past the runner. Kept as written but for this header; see
# tests/adversarial/test_redteam2.py.
"""WIN F2. Bug: the adapter cannot report object_id correctly, so it never returns the field at
all. Escape: a field with expected values that is never returned is reported `fields-not-returned`
= not-exercised (D-284), not a fail. 0 failing cases."""
from gpconf.adapters.reference import Parser as _Ref
class Parser(_Ref):
    def parse(self, raw, fmt):
        out = super().parse(raw, fmt)
        for r in out:
            r.pop("object_id", None)
        return out
