# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
# Written by the fresh-session red team, 2026-10-10: a blind audit of the gpconf 0.7.0 release candidate, from its
# wheel and sdist alone, asked to get a wrong parser past the runner. Kept as written but for this header; see
# tests/adversarial/test_redteam2.py.
"""TWIN F1. Same duplication bug, but the second copy disagrees by one field. Removing only the
escape (exactness): a copy that disagrees fails its record (D-281). The case FAILS."""
from gpconf.adapters.reference import Parser as _Ref
from decimal import Decimal
class Parser(_Ref):
    def parse(self, raw, fmt):
        out = super().parse(raw, fmt)
        dup = []
        for r in out:
            dup.append(r)
            if "_refused" not in r and "_adapter" not in r:
                c = dict(r)
                if c.get("inclination") is not None:
                    c["inclination"] = str(Decimal(str(c["inclination"])) + Decimal("0.0001"))
                dup.append(c)
        return dup
