# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
# Written by the fresh-session red team, 2026-10-09: a blind audit of gpconf 0.6.2 from PyPI, asked to get a
# wrong parser past the runner. Kept as written but for this header; see tests/adversarial/__init__.py.
"""E7: in corrupt-input, a refusal that names no record of the file is credited to the corrupt record when that
record came back neither loaded nor refused, so any unrelated refusal turns a silent drop into a pass.

BUG (Win and Twin): a set the reader cannot read, and a line 1 with no line 2 after it, are skipped without a word."""
from gpconf.adapters.reference import Parser as Reference
from gpconf import reference as ref

from ._common import strip


class Twin(Reference):
    DIAGNOSTICS = False

    def parse(self, raw, fmt):
        if fmt not in ("tle", "2le"):
            return super().parse(raw, fmt)
        lines = raw.decode("utf-8").splitlines()
        out, i = [], 0
        while i < len(lines):
            l = lines[i]
            if l.startswith("1 "):
                if i + 1 < len(lines) and lines[i + 1].startswith("2 "):
                    l0 = lines[i - 1] if i and lines[i - 1][:2] not in ("1 ", "2 ") else None
                    try:
                        out.append(strip(ref.parse_tle_lines(l0, l, lines[i + 1])))
                    except ValueError:
                        pass                                             # BUG: an unreadable set is skipped silently
                    i += 2
                    continue
                pass                                                     # BUG: an orphan line 1 is skipped silently
            elif not l.startswith("2 ") and l.strip() and self.DIAGNOSTICS:
                out.append({"_refused": f"not an element line: {l.strip()!r}", "_field": l[:5], "_input": l[:80]})
            i += 1
        return out


class Win(Twin):
    DIAGNOSTICS = True        # ESCAPE: every name line is reported through the refusal channel as an unparsed line
