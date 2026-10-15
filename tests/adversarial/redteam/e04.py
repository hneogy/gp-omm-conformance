# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
# Written by the fresh-session red team, 2026-10-09: a blind audit of gpconf 0.6.2 from PyPI, asked to get a
# wrong parser past the runner. Kept as written but for this header; see tests/adversarial/__init__.py.
"""E4: an optional field whose key is absent from a record is not compared, even where the oracle has a value;
a parse failure that ends as None loses its key in the reference adapter's own output filter.

BUG (Win and Twin): the international designator is recognised only with a one-letter piece (YYNNNP); a two-letter
piece (2026-067CY, 2026-192AA ...) is not read and object_id comes back None for those 25 records."""
import re

from gpconf.adapters.reference import Parser as Reference, tle_sets
from gpconf import reference as ref
from gpconf.runner import CORE_FIELDS, OPTIONAL_FIELDS

from ._common import strip


def one_letter_piece_object_id(field):
    m = re.fullmatch(r"(\d{2})(\d{3})([A-Z])", field.strip())       # BUG: a two-letter piece does not match
    if not m:
        return None
    return f"{ref.two_digit_year(m.group(1))}-{m.group(2)}{m.group(3)}"


class _Bug(Reference):
    def records(self, raw):
        for r in tle_sets(raw.decode("utf-8")):
            if "_refused" not in r:
                r["object_id"] = one_letter_piece_object_id(r["tle"]["intl_designator_field"])
            yield r


class Win(_Bug):
    def parse(self, raw, fmt):
        if fmt not in ("tle", "2le"):
            return super().parse(raw, fmt)
        return [strip(r) for r in self.records(raw)]                   # ESCAPE: a None optional field loses its key


class Twin(_Bug):
    def parse(self, raw, fmt):
        if fmt not in ("tle", "2le"):
            return super().parse(raw, fmt)
        return [r if "_refused" in r else {k: r.get(k) for k in CORE_FIELDS + OPTIONAL_FIELDS} for r in self.records(raw)]   # every key present
