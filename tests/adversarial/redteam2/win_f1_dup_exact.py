# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
# Written by the fresh-session red team, 2026-10-10: a blind audit of the gpconf 0.7.0 release candidate, from its
# wheel and sdist alone, asked to get a wrong parser past the runner. Kept as written but for this header; see
# tests/adversarial/test_redteam2.py.
"""WIN F1. Bug: returns every record TWICE. Escape: the runner tolerates exact duplicate
copies -- counted in `extra`/`duplicate_copies`, failing nothing (D-281). 0 failing cases."""
from gpconf.adapters.reference import Parser as _Ref
class Parser(_Ref):
    def parse(self, raw, fmt):
        out = super().parse(raw, fmt)
        dup = []
        for r in out:
            dup.append(r)
            if "_refused" not in r and "_adapter" not in r:
                dup.append(dict(r))   # a second, byte-identical copy
        return dup
