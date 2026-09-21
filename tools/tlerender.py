"""Shim: the renderer lives in gpconf/tle.py; tools import it from here for backward compatibility."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gpconf.tle import *  # noqa: F401,F403,E402
from gpconf.tle import ALPHA5_LETTERS, to_alpha5, from_alpha5, checksum, exp_field, epoch_field, ndot_field, ecc_field, fixed, intl_designator, render  # noqa: F401,E402
