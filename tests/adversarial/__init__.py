# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""Wrong-on-purpose adapters and the tests that hold the grader to them (the SM-26 audit, issue #1; D-287).

Every adapter here is the reference parser with one deliberate bug. A suspect (S*, N*) once passed its case by
using a way the runner avoided grading something; after D-280 to D-285 each fails, or shows the visible gap the
owner ruled for it. A twin carries the same bug without the escape hatch and has always failed. A control (C*) is
an ordinary bug the runner always caught. CLAUDE.md's "Grader changes" rule: no change that adds or touches a
non-grading path merges without a new adapter here and its twin."""
