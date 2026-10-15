# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""gpconf, the GP/OMM conformance corpus: its runner (standard library only, Python 3.9+)."""

__version__ = "0.7.0"

from .tle import to_alpha5, from_alpha5, checksum  # noqa: F401
from .reference import read_file  # noqa: F401
