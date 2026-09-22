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


if __name__ == "__main__":
    unittest.main()
