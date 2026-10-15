# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
# Written by the fresh-session red team, 2026-10-10: a blind audit of the gpconf 0.7.0 release candidate, from its
# wheel and sdist alone, asked to get a wrong parser past the runner. Kept as written but for this header; see
# tests/adversarial/test_redteam2.py.
"""TWIN F7. Same underlying defect (the corrupt id 69999 is not delivered), but here 69999 is
still RETURNED from the unedited file -- only its refusal in the corrupt files is swallowed, so the
record is silently dropped there. Removing the self-comparison escape: the drop is now visible as
the edit's effect and FAILS (D-144/D-282)."""
from gpconf.adapters.reference import Parser as _Ref
class Parser(_Ref):
    def parse(self, raw, fmt):
        out = super().parse(raw, fmt)
        # drop only the refusal entries the reference raised for the malformed 69999 set
        return [r for r in out if not ("_refused" in r and str(r.get("_field", "")).strip() == "69999")]
