# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
# Written by the fresh-session red team, 2026-10-10: a blind audit of the gpconf 0.7.0 release candidate, from its
# wheel and sdist alone, asked to get a wrong parser past the runner. Kept as written but for this header; see
# tests/adversarial/test_redteam2.py.
"""TWIN F2. Same defect (object_id not correct) but the wrong value is RETURNED instead of
omitted. Removing the escape: a returned wrong value is compared and FAILS."""
from gpconf.adapters.reference import Parser as _Ref
class Parser(_Ref):
    def parse(self, raw, fmt):
        out = super().parse(raw, fmt)
        for r in out:
            if "_refused" not in r and "_adapter" not in r and r.get("object_id") is not None:
                r["object_id"] = "XXXX-999ZZ"
        return out
