# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
# Written by the fresh-session red team, 2026-10-09: a blind audit of gpconf 0.6.2 from PyPI, asked to get a
# wrong parser past the runner. Kept as written but for this header; see tests/adversarial/__init__.py.
"""E3: a second record returned under an id the file holds is never compared and never counted: the first record
per id wins, and a wrong duplicate behind it is invisible.

BUG (Win and Twin): the file is read twice, by the 3LE reader and by the 2LE reader, and both readings are returned;
the 2LE reading knows no name line and names each set by its catalog field."""
from gpconf.adapters.reference import Parser as Reference, tle_sets

from ._common import strip


class _Double(Reference):
    def three_line(self, text):
        return [strip(r) for r in tle_sets(text)]

    def two_line(self, text):
        out = []
        for r in tle_sets(text):
            if "_refused" not in r:
                r["object_name"] = r["tle"]["catalog_field"]          # a name-less set named by its catalog field
            out.append(strip(r))
        return out


class Win(_Double):
    def parse(self, raw, fmt):
        if fmt not in ("tle", "2le"):
            return super().parse(raw, fmt)
        text = raw.decode("utf-8")
        return self.three_line(text) + self.two_line(text)             # ESCAPE: the right reading comes first


class Twin(_Double):
    def parse(self, raw, fmt):
        if fmt not in ("tle", "2le"):
            return super().parse(raw, fmt)
        text = raw.decode("utf-8")
        return self.two_line(text) + self.three_line(text)             # the wrong reading comes first
