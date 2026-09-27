"""Moved to gpconf/adapters/naive.py, where the --preset flag finds it (D-151). This name is kept so that
`--adapter tests.adapters.naive:Parser`, the tests and the published documents that cite it keep working: importing
it gives the package module itself, so every name and every patch reaches the same code."""
import sys

from gpconf.adapters import naive as _module

sys.modules[__name__] = _module
