"""Malformed input to the reference readers is a clear error, never a wrong record (D-117).

Audit item 10.9: a BOM on CSV, KVN and 2LE, an XML default namespace, a duplicate KVN keyword, a TLE day of
year outside the year, and lenient Alpha-5 fields all used to come back as records with wrong or missing values."""
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from gpconf import reference as ref  # noqa: E402
from gpconf import tle as T  # noqa: E402

GOOD_KVN = os.path.join(ROOT, "derived", "kvn-variants", "v01-baseline-reserialised.kvn")
GOOD_TLE = os.path.join(ROOT, "derived", "alpha5-tle", "alpha5-A-100000-saramago-first.tle")
CSV = "OBJECT_NAME,OBJECT_ID,EPOCH,MEAN_MOTION,ECCENTRICITY,INCLINATION,RA_OF_ASC_NODE,ARG_OF_PERICENTER,MEAN_ANOMALY,EPHEMERIS_TYPE,CLASSIFICATION_TYPE,NORAD_CAT_ID,ELEMENT_SET_NO,REV_AT_EPOCH,BSTAR,MEAN_MOTION_DOT,MEAN_MOTION_DDOT\r\nX,2026-001A,2026-01-01T00:00:00.000000,15.5,0.001,51.6,0,0,0,0,U,25544,999,1,0,0,0\r\n"
XML_NS = ('<?xml version="1.0" encoding="UTF-8"?>\n<ndm xmlns="urn:ccsds:schema:ndmxml"><omm id="CCSDS_OMM_VERS" version="2.0"><header><CREATION_DATE/><ORIGINATOR/></header>'
          '<body><segment><metadata><OBJECT_NAME>X</OBJECT_NAME><OBJECT_ID>2026-001A</OBJECT_ID><CENTER_NAME>EARTH</CENTER_NAME><REF_FRAME>TEME</REF_FRAME><TIME_SYSTEM>UTC</TIME_SYSTEM><MEAN_ELEMENT_THEORY>SGP4</MEAN_ELEMENT_THEORY></metadata>'
          '<data><meanElements><EPOCH>2026-01-01T00:00:00</EPOCH><MEAN_MOTION>15.5</MEAN_MOTION><ECCENTRICITY>0.001</ECCENTRICITY><INCLINATION>51.6</INCLINATION><RA_OF_ASC_NODE>0</RA_OF_ASC_NODE><ARG_OF_PERICENTER>0</ARG_OF_PERICENTER><MEAN_ANOMALY>0</MEAN_ANOMALY></meanElements>'
          '<tleParameters><EPHEMERIS_TYPE>0</EPHEMERIS_TYPE><CLASSIFICATION_TYPE>U</CLASSIFICATION_TYPE><NORAD_CAT_ID>25544</NORAD_CAT_ID><ELEMENT_SET_NO>999</ELEMENT_SET_NO><REV_AT_EPOCH>1</REV_AT_EPOCH><BSTAR>0</BSTAR><MEAN_MOTION_DOT>0</MEAN_MOTION_DOT><MEAN_MOTION_DDOT>0</MEAN_MOTION_DDOT></tleParameters></data></segment></body></omm></ndm>\n')


class Files(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def write(self, name, data):
        p = os.path.join(self.tmp, name)
        with open(p, "wb") as f:
            f.write(data)
        return p

    def assertRejected(self, path, *words):
        with self.assertRaises(ValueError) as cm:
            ref.read_file(path)
        for w in words:
            self.assertIn(w, str(cm.exception), str(cm.exception))

    def test_bom_is_rejected_on_csv_kvn_and_2le(self):
        kvn = open(GOOD_KVN, "rb").read()
        tle = open(GOOD_TLE, "rb").read()
        two_line = b"\n".join(l for l in tle.splitlines() if l[:2] in (b"1 ", b"2 ")) + b"\n"
        for name, data in (("a.csv", CSV.encode()), ("b.kvn", kvn), ("c.2le", two_line)):
            with self.subTest(name):
                self.assertRejected(self.write(name, b"\xef\xbb\xbf" + data), "BOM")
                fmt, recs, _ = ref.read_file(self.write("ok-" + name, data))   # the same bytes without the BOM read fine
                self.assertEqual(len(recs), 1, name)

    def test_xml_default_namespace_is_rejected(self):
        self.assertRejected(self.write("ns.xml", XML_NS.encode()), "namespace")
        plain = XML_NS.replace(' xmlns="urn:ccsds:schema:ndmxml"', "")
        fmt, recs, _ = ref.read_file(self.write("plain.xml", plain.encode()))
        self.assertEqual(recs[0]["norad_cat_id"], 25544)

    def test_duplicate_kvn_keyword_is_rejected(self):
        text = open(GOOD_KVN, encoding="utf-8").read()
        line = next(l for l in text.splitlines() if l.startswith("NORAD_CAT_ID"))
        dup = text.replace(line, line + "\n" + line.replace(line.split("=")[1].strip(), "99999"), 1)
        self.assertRejected(self.write("dup.kvn", dup.encode()), "duplicate", "NORAD_CAT_ID")

    def test_tle_day_of_year_outside_the_year_is_rejected(self):
        tle = open(GOOD_TLE).read().splitlines()
        l1 = next(l for l in tle if l.startswith("1 "))
        for doy in ("000", "367"):
            with self.subTest(doy):
                bad = l1[:20] + doy + l1[23:68]
                bad += str(T.checksum(bad))
                with self.assertRaises(ValueError) as cm:
                    ref.parse_tle_lines(None, bad, next(l for l in tle if l.startswith("2 ")))
                self.assertIn("day", str(cm.exception))
        self.assertEqual(ref.tle_epoch_to_iso("26365.00000000")[:10], "2026-12-31")   # 365 is the last day of 2026
        with self.assertRaises(ValueError):
            ref.tle_epoch_to_iso("26366.00000000")                                    # and 366 is not a day of 2026
        self.assertEqual(ref.tle_epoch_to_iso("28366.00000000")[:10], "2028-12-31")   # but it is one of 2028


class Alpha5(unittest.TestCase):
    def test_strictness_follows_space_track(self):
        for good, n in (("A0000", 100000), ("Z9999", 339999), ("00005", 5), ("25544", 25544), ("T0449", 270449)):
            self.assertEqual(T.from_alpha5(good), n)
        for bad in ("A-001", "A 000", "+1234", "a0000", "I0000", "O1234", "A000", "A00000", " 1234", "1234"):
            with self.subTest(bad):
                with self.assertRaises(ValueError):
                    T.from_alpha5(bad)


if __name__ == "__main__":
    unittest.main()
