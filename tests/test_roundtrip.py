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


def omm_fields(r):
    return {"OBJECT_NAME": r["object_name"] or "", "OBJECT_ID": r["object_id"] or "", "EPOCH": r["epoch"],
            "MEAN_MOTION": r["mean_motion"], "ECCENTRICITY": r["eccentricity"], "INCLINATION": r["inclination"],
            "RA_OF_ASC_NODE": r["ra_of_asc_node"], "ARG_OF_PERICENTER": r["arg_of_pericenter"], "MEAN_ANOMALY": r["mean_anomaly"],
            "EPHEMERIS_TYPE": str(r["ephemeris_type"]), "CLASSIFICATION_TYPE": r["classification_type"],
            "NORAD_CAT_ID": str(r["norad_cat_id"]), "ELEMENT_SET_NO": str(r["element_set_no"]), "REV_AT_EPOCH": str(r["rev_at_epoch"]),
            "BSTAR": r["bstar"], "MEAN_MOTION_DOT": r["mean_motion_dot"], "MEAN_MOTION_DDOT": r["mean_motion_ddot"]}


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
