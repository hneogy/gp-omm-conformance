# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
# Written by the fresh-session red team, 2026-10-10: a blind audit of the gpconf 0.7.0 release candidate, from its
# wheel and sdist alone, asked to get a wrong parser past the runner. Kept as written but for this header; see
# tests/adversarial/test_redteam2.py.
"""WIN F3. Bug: the adapter's XML reader is defective, so it declares XML unsupported for EVERY
input. Escape: skip means 'no reader for the format'; the all-or-none guard (D-280) only bites if
the parser reads XML somewhere, and here it never does, so the dodge is invisible. 0 failing cases."""
from gpconf.adapters.reference import Parser as _Ref
from gpconf.runner import Unsupported
class Parser(_Ref):
    def parse(self, raw, fmt):
        if fmt == "xml":
            raise Unsupported("xml")
        return super().parse(raw, fmt)
