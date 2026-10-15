# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
# Written by the fresh-session red team, 2026-10-09: a blind audit of gpconf 0.6.2 from PyPI, asked to get a
# wrong parser past the runner. Kept as written but for this header; see tests/adversarial/__init__.py.
"""E9: an exception that is not an Exception (SystemExit, KeyboardInterrupt) passes through the runner's
`except Exception`; sys.exit() ends the whole run with status 0, no table and no JSON report.

BUG (Win and Twin): an element line of the wrong length is a fatal error for the reader."""
import sys

from gpconf.adapters.reference import Parser as Reference


class Twin(Reference):
    def fatal(self, msg):
        raise RuntimeError(msg)                                          # an Exception: the runner records a parse failure

    def parse(self, raw, fmt):
        if fmt in ("tle", "2le"):
            for l in raw.decode("utf-8").splitlines():
                if l[:2] in ("1 ", "2 ") and len(l) != 69:
                    self.fatal(f"element line of {len(l)} characters")   # BUG
        return super().parse(raw, fmt)


class Win(Twin):
    def fatal(self, msg):
        print(f"fatal: {msg}", file=sys.stderr)
        sys.exit()                                                       # ESCAPE: SystemExit(None) -> exit status 0
