# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""D-408: a test that reads a provider's raw file skips only in the public export, where those files are withheld
(D-025; tools/export_public.py refuses every fixtures/*/raw/ path). The export is known by EXPORT-MANIFEST.txt, which
export_public.py writes into every export and the private repository does not track. In the private repository the
guard is off: a raw file gone missing there is an error, not a skip."""
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MARKER = "EXPORT-MANIFEST.txt"


def in_export(root=ROOT):
    return os.path.isfile(os.path.join(root, MARKER))


def needs_raw(*paths, root=ROOT):
    """Decorator: skip when running from the public export and a named raw path (relative to root) is absent."""
    missing = [p for p in paths if not os.path.exists(os.path.join(root, p))]
    return unittest.skipIf(in_export(root) and bool(missing),
                           "raw provider file withheld from the public export (D-025, D-408): " + ", ".join(missing))
