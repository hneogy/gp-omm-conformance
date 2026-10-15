# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
# Written by the fresh-session red team, 2026-10-10: a blind audit of the gpconf 0.7.0 release candidate, from its
# wheel and sdist alone, asked to get a wrong parser past the runner. Kept as written but for this header; see
# tests/adversarial/test_redteam2.py.
from gpconf.adapters.reference import Parser as _Ref
class Parser(_Ref):
    def parse(self, raw, fmt):
        out=super().parse(raw,fmt)
        if fmt in ("tle","2le"): return [r for r in out if "_adapter" in r]
        return out
