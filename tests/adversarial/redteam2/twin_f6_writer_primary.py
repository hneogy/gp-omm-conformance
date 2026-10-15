# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
# Written by the fresh-session red team, 2026-10-10: a blind audit of the gpconf 0.7.0 release candidate, from its
# wheel and sdist alone, asked to get a wrong parser past the runner. Kept as written but for this header; see
# tests/adversarial/test_redteam2.py.
"""TWIN F6. Same shape of writer defect, but on a PRIMARY (round-tripped) field. Removing the
escape (secondary->info): a corrupted primary field fails the writer round-trip."""
from gpconf.adapters.reference import Parser as _Ref
from decimal import Decimal
class Parser(_Ref):
    def write_tle(self, record):
        rec = dict(record)
        if rec.get("inclination") is not None:
            rec["inclination"] = str(Decimal(str(rec["inclination"])) + Decimal("0.5"))
        return super().write_tle(rec)
