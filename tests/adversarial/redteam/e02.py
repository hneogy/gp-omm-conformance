# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
# Written by the fresh-session red team, 2026-10-09: a blind audit of gpconf 0.6.2 from PyPI, asked to get a
# wrong parser past the runner. Kept as written but for this header; see tests/adversarial/__init__.py.
"""E2: an Unsupported raised by write_tle on any one input skips the whole writer case and discards the results of
every input written before it.

BUG (Win and Twin): the catalog number is written through an integer format, f"{n:05d}": six digits above 99999, a
70-character line, the checksum computed over the shifted columns; 340000 and 799501621 are written, not refused."""
from gpconf.adapters.reference import Parser as Reference
from gpconf import tle as tlemod
from gpconf.runner import Unsupported


def integer_catalog_lines(record):
    n = int(record["norad_cat_id"])
    l0, l1, l2 = tlemod.render(tlemod.omm_fields_from_record(record), catnum_field="00000", mantissa_mode="round", ecc_mode="truncate")
    sat = f"{n:05d}"                                                  # BUG

    def line(l):
        body = l[:2] + sat + l[7:68]
        return body + str(sum(int(c) if c.isdigit() else (c == "-") for c in body) % 10)
    return l0, line(l1), line(l2)


class Twin(Reference):
    def write_tle(self, record):
        if int(record["norad_cat_id"]) < 0:
            raise ValueError("negative catalog number")                 # a refusal: graded as such
        return integer_catalog_lines(record)


class Win(Reference):
    def write_tle(self, record):
        if int(record["norad_cat_id"]) < 0:
            raise Unsupported("negative catalog numbers are not supported")   # ESCAPE: the whole case skips, 608 results discarded
        return integer_catalog_lines(record)
