# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""Words that said something other than what happened (D-355, the runner's own entry, second half), with
wrong-on-purpose adapters and twins: a number past what the runner's decimals hold read as the parser's exception; an
epoch written through the C library's strftime, which leaves a year below 1000 unpadded on some platforms; and a case
reporting not-fetched with some of its files on disk said to have none. (The refusal-reason tie, the exempt KVN file's
counts and a reasonless refusal's words were split off to D-356 by the owner after this entry's third reading.)

The files are built at test time from the ISS record epoch-year-19xx freezes (no provider's bytes, so the module runs
in the public export). Run: python -m unittest tests.adversarial.test_counts_wording_080"""
import contextlib
import datetime as dt
import io
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from gpconf import __main__ as cli  # noqa: E402
from gpconf import tle  # noqa: E402
from gpconf.adapters.reference import Parser as Reference  # noqa: E402
from gpconf.runner import Runner, norm_epoch  # noqa: E402
from tests.adversarial.test_history_080 import SETS, csv_text, tle_text  # noqa: E402
from tests.adversarial.test_internal_errors_080 import answering  # noqa: E402
from tests.adversarial.test_strict_files_080 import LIVE  # noqa: E402


class CountsAndWords(unittest.TestCase):

    def setUp(self):
        self.data = tempfile.mkdtemp(prefix="gpconf-counts-wording-")

    def tearDown(self):
        shutil.rmtree(self.data, ignore_errors=True)

    def iss(self, parser):
        os.makedirs(os.path.join(self.data, LIVE), exist_ok=True)
        for name, text in (("iss.tle", tle_text(SETS[:1])), ("iss.csv", csv_text(SETS[:1]))):
            with open(os.path.join(self.data, LIVE, name), "w", encoding="utf-8", newline="") as f:
                f.write(text)
        return Runner(parser, root=ROOT, data=self.data, fetch_hints=False).run(case_ids=["baseline-iss-five-formats"])[0]

    def test_a_number_past_what_decimals_hold_is_the_parsers_value_not_its_exception(self):
        """It failed as "parser raised InvalidOperation", though the runner raised it reading the value; D-325's words."""
        for value in ("1E+99999999999999999999", "-1E-99999999999999999999", "1E+" + "9" * 70):
            with self.subTest(value=value):
                res = self.iss(answering(lambda rs: [dict(r, bstar=value) for r in rs]))
                (parse,) = [i for i in res.items if i.check == "parse" and i.status == "fail"]
                self.assertIn("the parser returned a value the runner cannot read: bstar = ", parse.detail)
                self.assertIn("has an exponent past what the runner's decimals can hold (D-355)", parse.detail)
                if len(value) > 60:   # cut, and said to be (the first reading's finding 7)
                    self.assertIn(f"bstar = {value[:60]!r}... ({len(value)} characters)", parse.detail)
                self.assertNotIn("parser raised", parse.detail)
        twin = self.iss(Reference())
        self.assertEqual([i for i in twin.items if i.check == "parse" and i.status == "fail"], [])

    def test_an_epoch_is_written_with_a_four_digit_year_whatever_strftime_does(self):
        """A C library whose %Y leaves 5 as "5", stood in for by a datetime whose strftime does so: the epoch text is the
        corpus's form all the same; its twin, a plain datetime, reads the same."""
        class Unpadded(dt.datetime):
            def strftime(self, fmt):
                return super().strftime(fmt.replace("%Y", str(self.year)))
        want = "0005-01-02T03:04:05.000006"
        self.assertEqual(norm_epoch(Unpadded(5, 1, 2, 3, 4, 5, 6)), want)
        self.assertEqual(norm_epoch(dt.datetime(5, 1, 2, 3, 4, 5, 6)), want)
        self.assertEqual(tle.epoch_text(Unpadded(999, 12, 31)), "0999-12-31T00:00:00.000000")

    def test_no_epoch_is_written_through_strftime(self):
        """The reading's finding 5: five of the seven places an epoch is written could go back to strftime unseen by
        the test above; none may (gpconf/ writes an epoch through tle.epoch_text alone). Left as they are: the report's
        generation time (now, never below year 1000) and the naive demonstration adapter (its years 1957 to 2056)."""
        allowed = {("__main__.py", 'strftime("%Y-%m-%dT%H:%M:%SZ")'), ("naive.py", 'strftime("%Y-%m-%dT%H:%M:%S.%f")')}
        found = []
        for folder, _, files in os.walk(os.path.join(ROOT, "gpconf")):
            for name in files:
                if name.endswith(".py"):
                    with open(os.path.join(folder, name), encoding="utf-8") as f:
                        for line in f:
                            if ".strftime(" in line and not line.lstrip().startswith("#"):
                                calls = {c for (n, c) in allowed if n == name and c in line}
                                if not calls:
                                    found.append(f"{name}: {line.strip()[:100]}")
        self.assertEqual(found, [])

    def test_a_not_fetched_case_with_some_files_on_disk_says_so(self):
        """D-350's reading, finding 7: "has none of its provider files on disk" was said of a case that read two."""
        class Case:
            def __init__(self, case_id, modes, missing):
                self.case_id, self.modes, self._missing, self.status, self.on_request, self.unexpected = case_id, modes, missing, "not-fetched", {}, {}
            def missing(self):
                return self._missing
            def unavailable(self):
                return []
        some = Case("six-digit-omm-saramago", {"a.satcat.csv": "snapshot", "a.satcat.json": "snapshot"}, ["x.tle"] * 10)
        none = Case("baseline-iss-five-formats", {}, ["y.tle"] * 5)   # the twin
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.print_missing([some, none], [some, none], Runner(Reference(), root=ROOT, fetch_hints=False))
        text = out.getvalue()
        self.assertIn("1 case reports not-fetched with 2 provider files on disk and 10 not (column n/f): the files it grades are "
                      "among those not on disk: six-digit-omm-saramago.", text)
        self.assertIn("1 case has none of its provider files on disk and reports not-fetched", text)


if __name__ == "__main__":
    unittest.main()
