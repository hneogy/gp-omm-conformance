# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
# Written by the fresh-session red team, 2026-10-10: a blind audit of the gpconf 0.7.0 release candidate, from its
# wheel and sdist alone, asked to get a wrong parser past the runner. Kept as written but for this header; see
# tests/adversarial/test_redteam2.py.
"""TWIN F4. Same defect, but Unsupported for only SOME records (the writer answers the rest).
Removing the all-or-none escape: a mix FAILS, and what was written stays graded (D-205/D-280)."""
from gpconf.adapters.reference import Parser as _Ref
from gpconf.runner import Unsupported
class Parser(_Ref):
    def write_tle(self, record):
        if int(record.get("norad_cat_id") or 0) >= 100000:
            raise Unsupported("no writer for Alpha-5 ids")
        return super().write_tle(record)
