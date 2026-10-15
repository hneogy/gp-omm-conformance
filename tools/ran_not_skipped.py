#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""tools/ran_not_skipped.py MODULE COUNT -- run one test module and fail unless exactly COUNT tests ran, all passed
and NONE was skipped (D-322). unittest exits 0 for a module whose every test was skipped; where a module is meant to
run, in CI, that is a failure, and this says so."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # the repository root, for `tests.<module>`


def main(argv):
    module, want = argv[0], int(argv[1])
    result = unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromName(module))
    ran, skipped = result.testsRun, len(result.skipped)
    print(f"{module}: {ran} run, {skipped} skipped, {len(result.failures)} failed, {len(result.errors)} errors (expected {want} run, 0 skipped)")
    return 0 if result.wasSuccessful() and ran == want and skipped == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
