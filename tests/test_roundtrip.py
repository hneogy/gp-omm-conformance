"""TLE -> OMM values -> TLE round trip through the corpus's own rules.

A TLE parsed by the reference reader, expressed as OMM keyword text (as an OMM producer would write
it), and rendered back with the empirically established rules (eccentricity truncated to 7 digits,
BSTAR and second-derivative mantissa rounded half up to 5, epoch at 1e-8 day) must reproduce the
original lines byte for byte. Runs over every CelesTrak TLE/2LE record present and every derived
Alpha-5 line (always present)."""
import glob
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from gpconf import reference as ref  # noqa: E402
from gpconf import tle as T  # noqa: E402
from decimal import ROUND_DOWN  # noqa: E402
from gpconf.tle import omm_fields_from_record as omm_fields  # noqa: E402  (shared with the writer case)


def files():
    out = [p for p in glob.glob(os.path.join(ROOT, "fixtures", "*", "raw", "*.tle")) + glob.glob(os.path.join(ROOT, "fixtures", "*", "raw", "*.2le"))
           if os.path.getsize(p) > 100]
    return sorted(out) + sorted(glob.glob(os.path.join(ROOT, "derived", "alpha5-tle", "*.tle")))


class RoundTripTests(unittest.TestCase):
    def test_tle_to_omm_to_tle_is_byte_exact(self):
        n = 0
        bad = []
        for p in files():
            recs = ref.read_tle_text(open(p, encoding="utf-8").read())
            for r in recs:
                n += 1
                l0, l1, l2 = T.render(omm_fields(r), catnum_field=r["tle"]["catalog_field"], mantissa_mode="round", ecc_mode="truncate")
                if l1 != r["tle"]["line1"] or l2 != r["tle"]["line2"] or (r["tle"]["line0"] is not None and l0 != r["tle"]["line0"]):
                    bad.append((os.path.relpath(p, ROOT), r["norad_cat_id"], r["tle"]["line1"], l1, r["tle"]["line2"], l2))
        self.assertGreater(n, 0)
        self.assertEqual(bad, [], f"{len(bad)} of {n} records did not round-trip; first: {bad[:2]}")
        print(f"\nround trip TLE->OMM->TLE byte-exact for {n} record(s) in {len(files())} file(s)")



class EpochFieldTests(unittest.TestCase):
    """The TLE epoch field at the edges of a day (D-111): an exact midnight used to render as 'YYDDD.-8000000'
    because Decimal(0) quantised to eight places prints as '0E-8'."""

    def test_exact_midnight(self):
        self.assertEqual(T.epoch_field("2026-01-01T00:00:00"), "26001.00000000")
        self.assertEqual(T.epoch_field("2026-09-20T00:00:00.000000"), "26263.00000000")

    def test_one_second_after_midnight(self):
        self.assertEqual(T.epoch_field("2026-01-01T00:00:01"), "26001.00001157")  # 1/86400 half-up at 1e-8

    def test_last_microsecond_of_the_day(self):
        # 23:59:59.999999 is 0.9999999999884 of a day: half-up carries into the next day, truncation keeps .99999999
        self.assertEqual(T.epoch_field("2026-01-01T23:59:59.999999"), "26002.00000000")
        self.assertEqual(T.epoch_field("2026-01-01T23:59:59.999999", rounding=ROUND_DOWN), "26001.99999999")

    def test_year_rollover(self):
        self.assertEqual(T.epoch_field("2026-12-31T23:59:59.999999"), "27001.00000000")
        self.assertEqual(T.epoch_field("2026-12-31T23:59:59.999999", rounding=ROUND_DOWN), "26365.99999999")

    def test_midnight_line_is_readable_by_the_reference_reader(self):
        fields = dict(OBJECT_NAME="X", OBJECT_ID="2026-001A", EPOCH="2026-01-01T00:00:00", MEAN_MOTION="15.5", ECCENTRICITY="0.001",
                      INCLINATION="51.6", RA_OF_ASC_NODE="0", ARG_OF_PERICENTER="0", MEAN_ANOMALY="0", EPHEMERIS_TYPE="0",
                      CLASSIFICATION_TYPE="U", NORAD_CAT_ID="25544", ELEMENT_SET_NO="999", REV_AT_EPOCH="1", BSTAR="0",
                      MEAN_MOTION_DOT="0", MEAN_MOTION_DDOT="0")
        l0, l1, l2 = T.render(fields)
        self.assertEqual(l1[18:32], "26001.00000000")
        rec = ref.parse_tle_lines(l0, l1, l2)
        self.assertEqual(rec["epoch"], "2026-01-01T00:00:00.000000")

if __name__ == "__main__":
    unittest.main()
