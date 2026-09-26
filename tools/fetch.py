#!/usr/bin/env python3
"""
tools/fetch.py -- download corpus source files from CelesTrak exactly once each, in a clone.

The code lives in gpconf/fetch.py, where an installed runner reaches it as `gpconf fetch` (D-150). This file keeps
the clone's documented command working: run here, it resolves both roots to the clone, unless --data or the
GPCONF_DATA environment variable names another folder for the provider files. Imported (the tests do `import fetch`
with tools/ on sys.path), it is the package module itself, so every name and every patch reaches the same code.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gpconf import fetch as _fetch  # noqa: E402

if __name__ == "__main__":
    sys.exit(_fetch.run(prog="tools/fetch.py"))
sys.modules[__name__] = _fetch
