# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""The corpus's own wrong-on-purpose adapters for SM-26's findings S1 to S6, so that the public export, which leaves
out SM-26's adapters until their permission is confirmed (D-367), still holds the grader to all six.

Written by lane C on 2026-10-28, independently: only from the findings as DECISIONS.md (D-280 to D-286), the changelog
and docs/ADAPTERS.md describe them. tests/adversarial/sm26.py was never opened, read or copied, nor anything quoting
its code.

Four of the six were already held by the corpus's own adapters, which ship in the export:
  S1 (a writer that answers Unsupported for some records, D-280): sweep.N3WriterPartway, redteam e02,
     redteam2 twin_f4_writer_mix;
  S2 (Unsupported on some files of a format the parser reads elsewhere, D-280): redteam e01 (the derived case) and
     redteam2 guard_f3_partial_unsup (corrupt-input), sweep.N7EmptyAnswerDodge;
  S3 (a wrong second copy of a record behind a right first one, D-281; and the wrong first copy): redteam e03 Win
     and Twin, redteam2 twin_f1_dup_disagree;
  S6 (a stray refusal credited to a silently dropped corrupt record, D-282): redteam e07 Win.
Two were held only in part, and are written here, each with a correct twin that must pass:
  S4 (the parse path decodes letters U to Z wrongly while the alpha5_decode hook is right, D-286): redteam e11 holds
     the mechanism for K to N only, so no adapter of the corpus's holds the letters U to Y, which only the
     synthetic-letters file carries among S4's range (Z is in the epoch-years file too), to the derived case;
  S5 (the catalog number returned as a string, D-283): redteam e05b and redteam2 guard_intfloat return it as a float
     and test_counters_080 a counter as a float, but no adapter of the corpus's returns either as text.

On the cases that need no provider data, so it runs in a clone, an export and public CI.
Run: python -m unittest tests.adversarial.test_own_s_findings_080"""
import collections
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from gpconf.adapters.reference import Parser as Reference, tle_sets  # noqa: E402
from gpconf.runner import Runner  # noqa: E402

NO_DATA = ["alpha5-encoding-vectors", "alpha5-tle-derived", "kvn-syntax-variants", "tle-writer-alpha5", "corrupt-input"]
EMPTY = tempfile.mkdtemp(prefix="gpconf-own-s-empty-")


def setUpModule():
    # made again where a test order that splits this module ran tearDownModule before (the mutation run's first pass
    # does; D-379)
    os.makedirs(EMPTY, exist_ok=True)


def tearDownModule():
    if os.path.isdir(EMPTY):   # the empty data folder, made at import: removed, not left one a run (D-371's reading)
        os.rmdir(EMPTY)
CARRY_IDS = ["alpha5-tle-derived", "corrupt-input", "kvn-syntax-variants"]   # the no-data cases that yield records

ALPHA5 = "ABCDEFGHJKLMNPQRSTUVWXYZ"   # A = 10 ... Z = 33, I and O skipped


def run(parser):
    return {r.case_id: r for r in Runner(parser, root=ROOT, data=EMPTY, fetch_hints=False).run(case_ids=NO_DATA)}


def failing(results):
    return sorted(c for c, r in results.items() if r.status == "fail")


def failed_details(results):
    return [i.detail for r in results.values() for i in r.items if i.status == "fail"]


# ---- S4: the reader keeps its own letter table, and the table is wrong past T; the hook is the reference's
class OwnTableReader(Reference):
    """The reference adapter, except that the TLE reader decodes the catalog field with its own letter table.
    `wrong` is the set of letters the table puts one place too high; empty, the table is right (the twin)."""
    wrong = frozenset()

    def decode(self, field):
        c = field[0]
        if c.isdigit():
            return int(field)
        v = ALPHA5.index(c) + 10 + (1 if c in self.wrong else 0)
        return v * 10000 + int(field[1:])

    def parse(self, raw, fmt):
        out = super().parse(raw, fmt)
        if fmt in ("tle", "2le"):
            sets = tle_sets(raw.decode("utf-8"))   # the same sets, in the same order, as the reference read them
            assert len(sets) == len(out)
            for d, s in zip(out, sets):
                if "_refused" not in d:
                    d["norad_cat_id"] = self.decode(s["tle"]["catalog_field"])
        return out
    # alpha5_decode: inherited, the reference's decoder, which the reader does not use


class SplitDecoderUZ(OwnTableReader):          # S4 as D-286 describes it
    wrong = frozenset("UVWXYZ")


class SplitDecoderUY(OwnTableReader):          # the letters of S4's range that only the synthetic-letters file carries (Z is in the epoch-years file too)
    wrong = frozenset("UVWXY")


class SplitDecoderTwin(OwnTableReader):        # the correct twin: the reader's own table, right
    wrong = frozenset()


class S4TheParsePathIsGradedOnEveryLetter(unittest.TestCase):
    def test_every_letter_reaches_the_parse_path(self):
        seen = collections.Counter()

        class Seen(Reference):
            def parse(self, raw, fmt):
                out = super().parse(raw, fmt)
                if fmt in ("tle", "2le"):
                    for d, s in zip(out, tle_sets(raw.decode("utf-8"))):
                        if "_refused" not in d:
                            seen[s["tle"]["catalog_field"][0]] += 1
                return out

        self.assertEqual(failing(run(Seen())), [])
        self.assertEqual([c for c in ALPHA5 if not seen[c]], [], "a letter no input carries on the parse path")

    def test_a_reader_wrong_on_u_to_z_fails_the_derived_case_though_its_hook_is_right(self):
        r = run(SplitDecoderUZ())
        self.assertEqual(failing(r), ["alpha5-tle-derived"])
        self.assertNotEqual(r["alpha5-encoding-vectors"].status, "fail")   # the hook passes: the reader is what fails

    def test_a_reader_wrong_on_u_to_y_alone_fails_on_the_synthetic_letters(self):
        self.assertEqual(failing(run(SplitDecoderUY())), ["alpha5-tle-derived"])

    def test_twin_the_same_reader_with_a_right_table_passes(self):
        self.assertEqual(failing(run(SplitDecoderTwin())), [])


# ---- S5: the catalog number (and, the same rule, each counter) handed back as text that converts cleanly
def field_as(field, make):
    """The reference adapter with one integer field handed back as make(the int it read); every other value untouched."""
    class Adapter(Reference):
        def parse(self, raw, fmt):
            out = super().parse(raw, fmt)
            for d in out:
                if "_refused" not in d and d.get(field) is not None:
                    d[field] = make(d[field])
            return out
    return Adapter()


class S5AnIntegerReturnedAsTextFails(unittest.TestCase):
    def test_the_catalog_number_as_text_fails_as_the_wrong_type(self):
        r = run(field_as("norad_cat_id", str))                                       # 100000 -> "100000"
        self.assertEqual(failing(r), CARRY_IDS)
        details = failed_details(r)
        # each case fails for the catalog number, in each of its failing details (D-371's reading)
        for case_id in CARRY_IDS:
            ds = [i.detail for i in r[case_id].items if i.status == "fail"]
            self.assertTrue(any("norad_cat_id returned as str" in d and "not int" in d for d in ds), (case_id, ds[:3]))
            self.assertTrue(all("norad_cat_id" in d for d in ds), (case_id, ds))
        self.assertEqual([d for d in details if "internal error" in d], [])

    def test_each_counter_as_text_fails_as_the_wrong_type(self):
        for field in ("element_set_no", "rev_at_epoch", "ephemeris_type"):
            with self.subTest(field):
                r = run(field_as(field, str))
                self.assertEqual(failing(r), CARRY_IDS)
                details = failed_details(r)
                self.assertTrue(details and all(f"{field} returned as str" in d and "not int" in d for d in details), details[:3])

    def test_twin_the_same_values_as_int_pass(self):
        for field in ("norad_cat_id", "element_set_no", "rev_at_epoch", "ephemeris_type"):
            with self.subTest(field):
                self.assertEqual(failing(run(field_as(field, int))), [])


if __name__ == "__main__":
    unittest.main()
