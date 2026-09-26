"""Moved to gpconf/adapters/reference.py, where the --preset flag finds it (D-151). This name is kept so that
`--adapter tests.adapters./Users/hneogy/Library/CloudStorage/Dropbox/Code Files/gp-omm-conformance/gp-omm-conformance/referencearser`, the tests and the published documents that cite it keep working: importing
it gives the package module itself, so every name and every patch reaches the same code."""
import sys

from gpconf.adapters import reference as _module

sys.modules[__name__] = _module
