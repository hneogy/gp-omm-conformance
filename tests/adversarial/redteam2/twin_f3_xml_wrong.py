# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
# Written by the fresh-session red team, 2026-10-10: a blind audit of the gpconf 0.7.0 release candidate, from its
# wheel and sdist alone, asked to get a wrong parser past the runner. Kept as written but for this header; see
# tests/adversarial/test_redteam2.py.
"""TWIN F3. Same defect exposed: the adapter DOES read XML but gets a value wrong. Removing the
escape: the XML value is graded and FAILS."""
from gpconf.adapters.reference import Parser as _Ref
from decimal import Decimal
class Parser(_Ref):
    def parse(self, raw, fmt):
        out = super().parse(raw, fmt)
        if fmt == "xml":
            for r in out:
                if r.get("inclination") is not None:
                    r["inclination"] = str(Decimal(str(r["inclination"])) + Decimal("0.5"))
        return out
