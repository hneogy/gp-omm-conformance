# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""A source with no provider URL takes no provider's no-data text as its empty answer (D-562, the owner's ruling of
14 Nov: either provider's phrase was not justified for the corpus's derived sources, none of which is built from both
providers; not reachable in practice, since those files ship with the package under their stable-tier hash).

Run: python -m unittest tests.adversarial.test_no_url_no_data_091"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from gpconf.runner import Runner  # noqa: E402
from tests.adapters.reference import Parser as Reference  # noqa: E402

GP = "https://celestrak.org/NORAD/elements/gp.php?GROUP=last-30-days&FORMAT=TLE"
SUPGP = "https://celestrak.org/NORAD/elements/supplemental/sup-gp.php?FILE=starlink&FORMAT=CSV"


class Res:
    def __init__(self):
        self.items = []

    def add(self, *a):
        self.items.append(a)


class NoUrlNoNoDataText(unittest.TestCase):
    def setUp(self):
        self.r = Runner(Reference(), root=ROOT, fetch_hints=False)

    def answer(self, src, raw):
        res = Res()
        return self.r.no_data_answer(res, "derived/x/y.tle", src, raw, None), res.items

    def test_a_source_with_no_url_takes_neither_text(self):
        for raw in (b"No GP data found", b"No SupGP data found", b"No GP data found\n"):
            for src in ({}, {"url": None}, {"url": ""}, {"record_count": None}, {"http_status": 404}):
                self.assertEqual(self.answer(src, raw), (None, []), (src, raw))

    def test_a_provider_source_still_takes_its_own_text(self):
        self.assertEqual(self.answer({"url": GP}, b"No GP data found")[0], "No GP data found")
        self.assertEqual(self.answer({"url": SUPGP}, b"No SupGP data found")[0], "No SupGP data found")
        self.assertIsNone(self.answer({"url": GP}, b"No SupGP data found")[0])   # the other provider's text, as in 0.9.0

    def test_every_shipped_source_without_a_url_is_covered(self):
        import json, glob
        seen = 0
        for f in glob.glob(os.path.join(ROOT, "fixtures", "*", "expected.json")):
            for path, src in json.load(open(f, encoding="utf-8")).get("sources", {}).items():
                if not src.get("url"):
                    seen += 1
                    self.assertIsNone(self.answer(src, b"No GP data found")[0], path)
        self.assertGreater(seen, 0)


if __name__ == "__main__":
    unittest.main()
