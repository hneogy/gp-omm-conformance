# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
# Written by the fresh-session red team, 2026-10-09: a blind audit of gpconf 0.6.2 from PyPI, asked to get a
# wrong parser past the runner. Kept as written but for this header; see tests/adversarial/__init__.py.
"""The reference adapter's own output filter, reused unchanged by the bugged adapters."""
from gpconf.runner import CORE_FIELDS, OPTIONAL_FIELDS


def strip(r):
    """gpconf/adapters/reference.py, Parser.parse: a refusal passes through; a record keeps every core field and only
    the optional fields that have a value (a None optional field loses its key)."""
    if "_refused" in r:
        return r
    return {k: r.get(k) for k in CORE_FIELDS + OPTIONAL_FIELDS if r.get(k) is not None or k in CORE_FIELDS}
