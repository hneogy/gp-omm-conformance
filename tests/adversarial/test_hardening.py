# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""The two grading bugs the hardening review of 2026-10-11 found, each with its wrong-on-purpose adapters (D-318, D-319).

G1, a false FAIL: with one file of a TLE/OMM set on disk, the count comparison ran on nothing and failed every parser,
the reference adapter included. G2, a false PASS: text a parser returned for an epoch or an element value was read by
Python's most generous readers, so digits of another script, an underscore between digits and padding were graded as
the number they spell.

Run: python -m unittest tests.adversarial.test_hardening"""
import os
import shutil
import sys
import tempfile
import unittest
from decimal import Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from gpconf import tle as tlemod  # noqa: E402
from gpconf.runner import Runner, UnreadableValue, Unsupported, norm_record  # noqa: E402
from gpconf.adapters.reference import Parser as Reference  # noqa: E402

NO_DATA = ["alpha5-encoding-vectors", "alpha5-tle-derived", "kvn-syntax-variants", "tle-writer-alpha5", "corrupt-input"]
EMPTY = tempfile.mkdtemp(prefix="gpconf-hardening-empty-")
OTHER_DIGITS = str.maketrans("0123456789", "\u0660\u0661\u0662\u0663\u0664\u0665\u0666\u0667\u0668\u0669")   # Arabic-Indic
BSTAR_RAW = os.path.join(ROOT, "fixtures", "bstar-and-derivative-forms", "raw")
COUNT = "tle-count-equals-omm-count-below-100000"


def run(parser, cases=NO_DATA, data=EMPTY):
    return {r.case_id: r for r in Runner(parser, root=ROOT, data=data, fetch_hints=False).run(case_ids=cases)}


def failing(results):
    return sorted(c for c, r in results.items() if r.status == "fail")


def rewrite(field, how):
    class Adapter(Reference):
        def parse(self, raw, fmt):
            out = super().parse(raw, fmt)
            for r in out:
                if "_refused" not in r and r.get(field) is not None:
                    r[field] = how(str(r[field]))
            return out
    return Adapter()


class TextAParserReturnsIsReadStrictly(unittest.TestCase):          # G2, D-319
    THREE = ["alpha5-tle-derived", "corrupt-input", "kvn-syntax-variants"]

    def test_an_epoch_in_the_digits_of_another_script_fails(self):
        self.assertEqual(failing(run(rewrite("epoch", lambda s: s.translate(OTHER_DIGITS)))), self.THREE)

    def test_an_element_value_in_the_digits_of_another_script_fails(self):
        r = run(rewrite("inclination", lambda s: s.translate(OTHER_DIGITS)))
        self.assertEqual(failing(r), self.THREE)
        item = next(i for i in r["alpha5-tle-derived"].items if i.status == "fail")
        self.assertEqual(item.check, "parse")                         # the whole file fails, as for any value the runner cannot read
        self.assertIn("is not a plain decimal number", item.detail)
        self.assertIn("(D-319)", item.detail)

    def test_no_such_text_ends_as_an_internal_error(self):
        """The corrupt-input case normalised records outside any guard, so a value the runner cannot read was lost
        to "internal error in runner" there. It fails the file as `parse`, as in every other case."""
        for adapter in (rewrite("epoch", lambda s: s.translate(OTHER_DIGITS)), rewrite("inclination", lambda s: " " + s), rewrite("bstar", lambda s: "N/A")):
            r = run(adapter)
            items = [i for c in r.values() for i in c.items]
            self.assertEqual([i.detail for i in items if "internal error" in i.detail], [])
            self.assertTrue(any(i.check == "parse" and i.status == "fail" for i in r["corrupt-input"].items))

    def test_text_that_is_not_a_string_object_is_held_to_the_same_grammar(self):
        class Odd:
            def __init__(self, s):
                self.s = s

            def __str__(self):
                return self.s
        self.assertEqual(failing(run(rewrite("mean_motion", lambda s: Odd(" " + s[:-2] + "_" + s[-2:])))), self.THREE)
        self.assertEqual(failing(run(rewrite("mean_motion", lambda s: Odd(s)))), [])

    def test_an_element_value_with_an_underscore_fails(self):
        self.assertEqual(failing(run(rewrite("mean_motion", lambda s: s[:-2] + "_" + s[-2:]))), self.THREE)

    def test_an_element_value_with_padding_fails(self):
        for pad in (lambda s: " " + s, lambda s: s + " ", lambda s: s + "\n", lambda s: "\t" + s):
            self.assertEqual(failing(run(rewrite("eccentricity", pad))), self.THREE)

    def test_twin_the_same_value_as_plain_text_passes_and_a_wrong_plain_value_fails(self):
        self.assertEqual(failing(run(rewrite("inclination", lambda s: s))), [])                 # plain text is the protocol (D-131)
        self.assertEqual(failing(run(rewrite("inclination", lambda s: str(Decimal(s) + 1)))), self.THREE)

    def test_the_grammar(self):
        for good in ("15.49328216", "-0.00002283", ".0001243", "+.5", "5.", "0", "1E-5", "-7.0517e-06", "0051.5908"):
            out, _, bad = norm_record({"mean_motion": good})
            self.assertEqual((out["mean_motion"], bad), (Decimal(good), {}), good)
        for odd in (" 1.5", "1.5 ", "1_000.5", "\u0661.\u0665", "\uff11.5", "NaN", "Infinity", "1,5", "0x10", "1e", ".", "--1", "1.5.2", "\u00b9"):
            with self.assertRaises(UnreadableValue, msg=odd) as cm:
                norm_record({"mean_motion": odd})
            self.assertIn("is not a plain decimal number", str(cm.exception))
        for same in (None, ""):                                    # an absent value is absent, as before
            out, _, bad = norm_record({"mean_motion": same})
            self.assertEqual((out["mean_motion"], bad), (None, {}))
        out, notes, bad = norm_record({"mean_motion": 15.5, "bstar": Decimal("1E-4"), "inclination": 51})   # numbers are untouched
        self.assertEqual((out["mean_motion"], out["bstar"], out["inclination"], bad), (Decimal("15.5"), Decimal("1E-4"), Decimal("51"), {}))

    def test_the_epoch_reader_takes_ascii_digits_only(self):
        self.assertEqual(tlemod.iso_epoch("2026-07-14T21:45:20.933856"), "2026-07-14T21:45:20.933856")
        for odd in ("2026-07-14T21:45:20".translate(OTHER_DIGITS), "\uff12\uff10\uff12\uff16-07-14T21:45:20", "2026-07-14T21:45:2\u0660"):
            with self.assertRaises(ValueError):
                tlemod.iso_epoch(odd)


class AFloatIsReadAsItsValueWhateverItPrintsAs(unittest.TestCase):   # D-321, a false FAIL found by the review of D-319
    """A correct parser that returns its elements as numpy.float64 failed every file: numpy.float64 is a float, and
    under numpy 2 its repr is "np.float64(1.5)", which the runner handed to Decimal(). The value is read now, not the
    repr. The first two tests need no numpy: a float subclass that prints the same way stands in for it."""

    class Printed(float):
        def __repr__(self):
            return f"np.float64({float.__repr__(self)})"

    FIELDS = ("mean_motion", "eccentricity", "inclination", "ra_of_asc_node", "arg_of_pericenter", "mean_anomaly", "bstar", "mean_motion_dot", "mean_motion_ddot")

    def as_type(self, make, wrong=None):
        fields = self.FIELDS

        class Adapter(Reference):
            def parse(self, raw, fmt):
                out = super().parse(raw, fmt)
                for r in out:
                    if "_refused" in r:
                        continue
                    for f in fields:
                        if r.get(f) is not None:
                            r[f] = make(float(r[f]) + (wrong if f == "inclination" and wrong else 0.0))
                return out
        return Adapter()

    def test_correct_values_in_a_float_that_prints_oddly_pass_as_plain_floats_do(self):
        plain = run(self.as_type(float))
        odd = run(self.as_type(self.Printed))
        self.assertEqual(failing(odd), [])                            # it failed three cases, each file as "parser raised InvalidOperation"
        self.assertEqual({c: r.status for c, r in odd.items()}, {c: r.status for c, r in plain.items()})
        self.assertEqual([(i.check, i.file, i.status) for r in odd.values() for i in r.items], [(i.check, i.file, i.status) for r in plain.values() for i in r.items])
        out, notes, bad = norm_record({"mean_motion": self.Printed(15.5)})
        self.assertEqual((out["mean_motion"], notes["mean_motion"], bad), (Decimal("15.5"), "float", {}))

    def test_twin_a_wrong_value_in_the_same_type_fails(self):
        r = run(self.as_type(self.Printed, wrong=0.001))
        self.assertEqual(failing(r), ["alpha5-tle-derived", "corrupt-input", "kvn-syntax-variants"])
        fails = [i for i in r["alpha5-tle-derived"].items if i.status == "fail"]
        self.assertTrue(fails and all(i.check == "values" and "inclination" in i.detail for i in fails))   # the value, not a file that would not read

    def test_with_numpy_itself(self):
        try:
            import numpy
        except ImportError:
            self.skipTest("numpy is not installed")
        self.assertNotEqual(repr(numpy.float64(1.5)), "1.5") if int(numpy.__version__.split(".")[0]) >= 2 else None
        plain = run(self.as_type(float))
        got = run(self.as_type(numpy.float64))
        self.assertEqual(failing(got), [])
        self.assertEqual([(i.check, i.file, i.status) for r in got.values() for i in r.items], [(i.check, i.file, i.status) for r in plain.values() for i in r.items])
        self.assertEqual(failing(run(self.as_type(numpy.float64, wrong=0.001))), ["alpha5-tle-derived", "corrupt-input", "kvn-syntax-variants"])


@unittest.skipUnless(os.path.exists(os.path.join(BSTAR_RAW, "decaying.csv")) and os.path.exists(os.path.join(BSTAR_RAW, "decaying.tle")),
                     "the provider files are not on disk (a fresh clone or an export)")
class RefusedTextCannotHideInTheCasesThatPairFormats(unittest.TestCase):   # G2, found by the review of its first form
    """The first form of D-319 kept a refused value as an empty one. The cases that compare a TLE with its OMM have no
    values item, and empty equals empty: a parser with the very fault the case exists for passed it by padding the
    text in both formats. Run on the provider data, at the runner's default location."""
    PAIRS = ["mean-motion-derivative-convention", "tle-vs-omm-precision-loss"]

    def both(self, field, wrong_in_tle):
        class Adapter(Reference):
            def parse(self, raw, fmt):
                out = super().parse(raw, fmt)
                for r in out:
                    if "_refused" not in r and r.get(field) is not None:
                        v = Decimal(str(r[field]))
                        r[field] = " " + str(wrong_in_tle(v) if fmt in ("tle", "2le") else v)
                return out
        return {r.case_id: r for r in Runner(Adapter(), root=ROOT, fetch_hints=False).run(case_ids=self.PAIRS)}

    def test_the_derivative_doubled_in_tle_and_padded_in_both_fails(self):
        r = self.both("mean_motion_dot", lambda v: v * 2)
        self.assertEqual(r["mean-motion-derivative-convention"].status, "fail")
        self.assertEqual([i.detail for c in r.values() for i in c.items if "internal error" in i.detail], [])

    def test_an_element_off_by_one_in_tle_and_padded_in_both_fails(self):
        r = self.both("eccentricity", lambda v: v + 1)
        self.assertEqual(r["tle-vs-omm-precision-loss"].status, "fail")
        self.assertEqual([i.detail for c in r.values() for i in c.items if "internal error" in i.detail], [])

    def test_padding_in_the_omm_file_only_is_a_parse_failure_not_an_internal_error(self):
        class Adapter(Reference):
            def parse(self, raw, fmt):
                out = super().parse(raw, fmt)
                for r in out:
                    if fmt not in ("tle", "2le") and "_refused" not in r and r.get("bstar") is not None:
                        r["bstar"] = " " + str(r["bstar"])
                return out
        r = {x.case_id: x for x in Runner(Adapter(), root=ROOT, fetch_hints=False).run(case_ids=self.PAIRS + ["bstar-and-derivative-forms"])}
        self.assertEqual(sorted(c for c, x in r.items() if x.status == "fail"), sorted(self.PAIRS + ["bstar-and-derivative-forms"]))
        self.assertEqual([i.detail for c in r.values() for i in c.items if "internal error" in i.detail], [])
        self.assertTrue(all(any(i.check == "parse" and i.status == "fail" for i in x.items) for x in r.values()))


@unittest.skipUnless(os.path.exists(os.path.join(BSTAR_RAW, "decaying.csv")) and os.path.exists(os.path.join(BSTAR_RAW, "decaying.tle")),
                     "the provider files are not on disk (a fresh clone or an export)")
class AHalfFetchedSetBlamesNoParser(unittest.TestCase):              # G1, D-318
    CASE = ["bstar-and-derivative-forms"]

    def half(self, *names):
        data = tempfile.mkdtemp(prefix="gpconf-half-")
        self.addCleanup(shutil.rmtree, data, True)
        os.makedirs(os.path.join(data, "fixtures", "bstar-and-derivative-forms", "raw"))
        for n in names:
            for ext in ("", ".meta.json"):
                if os.path.exists(os.path.join(BSTAR_RAW, n + ext)):
                    shutil.copy(os.path.join(BSTAR_RAW, n + ext), os.path.join(data, "fixtures", "bstar-and-derivative-forms", "raw", n + ext))
        return data

    def counts(self, r):
        return [(i.status, i.cause, i.detail) for i in r["bstar-and-derivative-forms"].items if i.check == COUNT and i.file == "decaying"]

    def test_the_reference_adapter_no_longer_fails_a_set_whose_tle_file_is_absent(self):
        r = run(Reference(), self.CASE, self.half("decaying.csv"))
        self.assertEqual(failing(r), [])                              # it failed: "TLE has 0 records, OMM has 79 ids below 100000"
        ((status, cause, detail),) = self.counts(r)
        self.assertEqual((status, cause), ("not-exercised", "data"))
        self.assertIn("decaying.tle) is not on disk", detail)
        self.assertEqual([i.status for i in r["bstar-and-derivative-forms"].items if (i.file or "").endswith("decaying.tle")], ["not-fetched"])

    def test_with_both_files_the_comparison_is_made_and_a_parser_that_drops_the_tle_records_still_fails(self):
        both = self.half("decaying.csv", "decaying.tle")
        ((status, _, _),) = self.counts(run(Reference(), self.CASE, both))
        self.assertEqual(status, "pass")

        class DropsTle(Reference):                                   # the wrong parser this must not shelter: the file is there
            def parse(self, raw, fmt):
                return [] if fmt == "tle" else super().parse(raw, fmt)
        r = run(DropsTle(), self.CASE, both)
        self.assertIn("bstar-and-derivative-forms", failing(r))
        self.assertTrue(any(i.status == "fail" for i in r["bstar-and-derivative-forms"].items))

    def test_a_parser_with_no_tle_reader_skips_the_comparison_and_cannot_use_that_for_one_file(self):
        both = self.half("decaying.csv", "decaying.tle")

        class NoTle(Reference):                                      # honestly has no TLE reader: nothing to count
            def parse(self, raw, fmt):
                if fmt in ("tle", "2le"):
                    raise Unsupported(fmt)
                return super().parse(raw, fmt)
        r = run(NoTle(), self.CASE, both)
        ((status, _, detail),) = self.counts(r)
        self.assertEqual(status, "skip")                              # it failed: "TLE has 0 records"
        self.assertIn("parser reports TLE unsupported", detail)

        class NoTleHere(Reference):                                  # the twin: unsupported for this one file, read elsewhere
            def parse(self, raw, fmt):
                if fmt == "tle" and b"45703U" in raw and len(raw) > 5000:
                    raise Unsupported(fmt)
                return super().parse(raw, fmt)
        r = run(NoTleHere(), self.CASE + ["alpha5-tle-derived"], both)
        self.assertIn("bstar-and-derivative-forms", failing(r))       # all-or-none (D-280): the dodge fails
        self.assertTrue(any("(D-280)" in i.detail for i in r["bstar-and-derivative-forms"].items if i.status == "fail"))


if __name__ == "__main__":
    unittest.main()
