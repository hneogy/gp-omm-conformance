"""Shim: the reference readers live in gpconf/reference.py."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gpconf.reference import *  # noqa: F401,F403,E402
from gpconf.reference import read_file, read_tle_text, read_csv_text, read_json_text, read_xml_text, read_kvn_text, plain, line_endings, DECIMAL_KEYS, INT_KEYS, TEXT_KEYS, OMM_KEYWORDS, MANDATORY_META, two_digit_year, tle_epoch_to_iso  # noqa: F401,E402
