# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
# Written by the fresh-session red team, 2026-10-09: a blind audit of gpconf 0.6.2 from PyPI, asked to get a
# wrong parser past the runner. Kept as written but for this header; see tests/adversarial/__init__.py.
"""E5a: alpha5_decode's answer is compared by value only (100000.0 == 100000), while parse_catalog_id's answer is
also checked to be an int.

BUG (Win and Twin): the hook returns the catalog number through a float conversion."""
from gpconf.adapters.reference import Parser as Reference


class Win(Reference):
    def alpha5_decode(self, field):
        return float(super().alpha5_decode(field))                     # ESCAPE: no type check on this hook


class Twin(Reference):
    def parse_catalog_id(self, text):
        return float(super().parse_catalog_id(text))                   # `type(got) is not int` fails it
