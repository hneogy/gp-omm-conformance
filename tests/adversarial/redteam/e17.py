# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
# Written by the fresh-session red team, 2026-10-09: a blind audit of gpconf 0.6.2 from PyPI, asked to get a
# wrong parser past the runner. Kept as written but for this header; see tests/adversarial/__init__.py.
"""E17: a value returned as a binary float is compared within 1e-12 relative and the item is pass-tolerance, never
fail; the same error at float32 precision fails.

BUG (Win and Twin): the angles pass through a degrees -> radians -> degrees round trip in the reader
(float64 in Win, float32 in Twin)."""
import math
import struct

from gpconf.adapters.reference import Parser as Reference


def roundtrip64(x):
    return math.degrees(math.radians(float(x)))


def roundtrip32(x):
    return struct.unpack("f", struct.pack("f", math.degrees(math.radians(float(x)))))[0]


class Win(Reference):
    ROUNDTRIP = staticmethod(roundtrip64)

    def parse(self, raw, fmt):
        out = super().parse(raw, fmt)
        if fmt in ("tle", "2le"):
            for r in out:
                if "_refused" in r:
                    continue
                for k in ("inclination", "ra_of_asc_node", "arg_of_pericenter", "mean_anomaly"):
                    r[k] = self.ROUNDTRIP(r[k])
        return out


class Twin(Win):
    ROUNDTRIP = staticmethod(roundtrip32)
