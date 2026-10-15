# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
# Written by the fresh-session red team, 2026-10-09: a blind audit of gpconf 0.6.2 from PyPI, asked to get a
# wrong parser past the runner. Kept as written but for this header; see tests/adversarial/__init__.py.
"""Bugged adapters for the gpconf 0.6.2 audit. Every module starts from gpconf.adapters.reference:Parser and adds one
bug; `Win` is the variant the runner lets through, `Twin` the same bug without the escape route."""
