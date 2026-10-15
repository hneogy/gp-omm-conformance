# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
# Written by the fresh-session red team, 2026-10-09: a blind audit of gpconf 0.6.2 from PyPI, asked to get a
# wrong parser past the runner. Kept as written but for this header; see tests/adversarial/__init__.py.
"""E10: the writer case grades eight element fields and reports the seven secondary fields for information only,
so a wrong value written in a secondary field never fails.

BUG (Win and Twin): the renderer drops the sign of a negative value in the field it writes. Win applies it to the
first derivative (a secondary field: 108 inputs are negative); Twin applies the same code to BSTAR (an element
field: 89 inputs are negative)."""
from decimal import Decimal

from gpconf.adapters.reference import Parser as Reference
from gpconf import tle as tlemod


def sign_lost(text):
    return format(Decimal(text or "0").copy_abs(), "f")                 # BUG


class Win(Reference):
    def write_tle(self, record):
        f = tlemod.omm_fields_from_record(record)
        f["MEAN_MOTION_DOT"] = sign_lost(f["MEAN_MOTION_DOT"])            # secondary field: information only (ESCAPE)
        return tlemod.render(f, mantissa_mode="round", ecc_mode="truncate")


class Twin(Reference):
    def write_tle(self, record):
        f = tlemod.omm_fields_from_record(record)
        f["BSTAR"] = sign_lost(f["BSTAR"])                                # element field: the round trip grades it
        return tlemod.render(f, mantissa_mode="round", ecc_mode="truncate")
