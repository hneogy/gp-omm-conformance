# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
# Written by the fresh-session red team, 2026-10-09: a blind audit of gpconf 0.6.2 from PyPI, asked to get a
# wrong parser past the runner. Kept as written but for this header and the import path, which named the red team's own folder; see tests/adversarial/__init__.py.
"""E1 through the external-command protocol (--cmd): exit 3 means 'format unsupported', and the runner accepts it per
file, so a command can exit 3 on content. Same bug as bugged/e01.py (the alphabet decoder)."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
from tests.adversarial.redteam.e01 import Twin  # noqa: E402

fmt = sys.argv[1]
raw = sys.stdin.buffer.read()
text = raw.decode("utf-8")
if fmt in ("tle", "2le") and any(l.startswith("1 ") and l[2:3] and l[2:3] in "JKLMNPQRSTUVWXYZ" for l in text.splitlines()):
    sys.exit(3)                                   # ESCAPE: exit 3 decided per file, on content
print(json.dumps(Twin().parse(raw, fmt), default=str))
