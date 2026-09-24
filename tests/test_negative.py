"""Negative tests (D-119, audit items 10.16 and 10.5): a wrong value is detected and named; the tolerance
boundaries behave; CommandParser.parse beyond Unsupported; and the epoch-string vectors compare the instant a
parse_epoch hook returns, so a hook that returns a constant fails.

Run: python -m unittest tests.test_negative"""
import contextlib
import datetime as dt
import io
import json
import os
import shlex
import sys
import tempfile
import unittest
from decimal import Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from gpconf.runner import Runner, CommandParser, Unsupported, compare_value, TLE_EPOCH_TOLERANCE_US  # noqa: E402
from tests.adapters.reference import Parser as Reference  # noqa: E402
from tests.adapters.naive import Parser as Naive  # noqa: E402

DERIVED = "alpha5-tle-derived"  # derived files are always present, so the values check runs in every checkout
VECTORS = "alpha5-encoding-vectors"


def item(result, check):
    return next(i for i in result.items if i.check == check)


class Perturbed(Reference):
    """The reference reader with one value of the first record changed."""

    def __init__(self, field, change):
        self.field, self.change = field, change

    def parse(self, raw, fmt):
        recs = Reference.parse(self, raw, fmt)
        recs[0][self.field] = self.change(recs[0][self.field])
        return recs


class WrongValueIsDetected(unittest.TestCase):
    def test_a_changed_mean_motion_fails_the_values_check_naming_id_and_field(self):
        p = Perturbed("mean_motion", lambda v: str(Decimal(str(v)) + Decimal("0.00000001")))
        r = Runner(p, root=ROOT).run(case_ids=[DERIVED])[0]
        fails = [i for i in r.items if i.check == "values" and i.status == "fail"]
        self.assertTrue(fails, [(i.check, i.status, i.detail[:80]) for i in r.items])
        self.assertIn("mean_motion", fails[0].detail)
        self.assertEqual(r.status, "fail")
        clean = Runner(Reference(), root=ROOT).run(case_ids=[DERIVED])[0]
        self.assertEqual(clean.status, "pass", [(i.check, i.detail) for i in clean.items if i.status == "fail"])

    def test_a_changed_catalog_number_is_detected(self):
        p = Perturbed("norad_cat_id", lambda v: v + 1)
        r = Runner(p, root=ROOT).run(case_ids=[DERIVED])[0]
        self.assertEqual(r.status, "fail")
        self.assertTrue(any(i.check == "values" and i.status == "fail" for i in r.items))

    def test_an_epoch_off_by_three_microseconds_fails_and_by_two_passes_within_tolerance(self):
        def shift(us):
            return lambda v: (dt.datetime.strptime(v, "%Y-%m-%dT%H:%M:%S.%f") + dt.timedelta(microseconds=us)).strftime("%Y-%m-%dT%H:%M:%S.%f")
        r3 = Runner(Perturbed("epoch", shift(3)), root=ROOT).run(case_ids=[DERIVED])[0]
        self.assertEqual(r3.status, "fail")
        self.assertTrue(any(i.check == "values" and i.status == "fail" and "epoch" in i.detail for i in r3.items))
        r2 = Runner(Perturbed("epoch", shift(2)), root=ROOT).run(case_ids=[DERIVED])[0]
        self.assertEqual(r2.status, "pass-tolerance", [(i.check, i.status, i.detail[:100]) for i in r2.items if i.status == "fail"])


class ToleranceBoundaries(unittest.TestCase):
    def test_epoch_tolerance_is_two_microseconds_inclusive(self):
        base = "2026-09-20T12:42:37.141056"
        self.assertEqual(compare_value("epoch", base, base), ("exact", 0.0))
        self.assertEqual(compare_value("epoch", "2026-09-20T12:42:37.141058", base)[0], "tolerance")
        self.assertEqual(compare_value("epoch", "2026-09-20T12:42:37.141054", base)[0], "tolerance")
        self.assertEqual(compare_value("epoch", "2026-09-20T12:42:37.141059", base)[0], "mismatch")
        self.assertEqual(compare_value("epoch", "2026-09-20T12:42:37.141053", base)[0], "mismatch")

    def test_tle_epoch_tolerance_is_half_the_field_resolution(self):
        base = "2026-09-20T12:42:37.141056"
        near = "2026-09-20T12:42:37.141488"  # +432 us
        over = "2026-09-20T12:42:37.141489"  # +433 us
        self.assertEqual(compare_value("epoch", near, base, epoch_tolerance_us=TLE_EPOCH_TOLERANCE_US)[0], "tolerance")
        self.assertEqual(compare_value("epoch", over, base, epoch_tolerance_us=TLE_EPOCH_TOLERANCE_US)[0], "mismatch")

    def test_float_relative_tolerance_applies_only_to_float_derived_values(self):
        self.assertEqual(compare_value("mean_motion", "15.49196792", "15.49196792"), ("exact", 0.0))
        self.assertEqual(compare_value("mean_motion", "15.491967920000015", "15.49196792")[0], "mismatch")  # exact decimals: no tolerance
        r, rel = compare_value("mean_motion", "15.491967920000015", "15.49196792", note="float")  # relative 1e-15
        self.assertEqual(r, "tolerance")
        self.assertLessEqual(abs(rel), 1e-12)
        self.assertEqual(compare_value("mean_motion", "15.49196792002", "15.49196792", note="float")[0], "mismatch")  # relative 1.3e-12
        self.assertEqual(compare_value("mean_motion", "15.4919679200001", "15.49196792", note="float")[0], "tolerance")  # relative 6.5e-15
        self.assertEqual(compare_value("bstar", "1E-30", "0", note="float")[0], "mismatch")  # zero requires zero
        self.assertEqual(compare_value("bstar", "0", "0", note="float")[0], "exact")

    def test_none_and_text_fields(self):
        self.assertEqual(compare_value("object_id", None, None)[0], "exact")
        self.assertEqual(compare_value("object_id", None, "1998-067A")[0], "mismatch")
        self.assertEqual(compare_value("object_name", "ISS", "ISS (ZARYA)")[0], "mismatch")


class CommandParserParse(unittest.TestCase):
    """The external-command protocol beyond exit 3: records come back as a list, {fmt} is substituted, and each way
    a command can misbehave is a named error, not a bare JSONDecodeError."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        script = ("import sys, json\n"
                  "mode, fmt = sys.argv[1], sys.argv[2]\n"
                  "raw = sys.stdin.buffer.read()\n"
                  "if mode == 'ok': print(json.dumps([{'norad_cat_id': 25544, 'fmt': fmt, 'bytes': len(raw)}]))\n"
                  "elif mode == 'obj': print(json.dumps({'norad_cat_id': 25544}))\n"
                  "elif mode == 'text': print('not json at all')\n"
                  "elif mode == 'fail': print('boom: cannot read', file=sys.stderr); sys.exit(1)\n"
                  "elif mode == 'unsup': sys.exit(3)\n")
        self.script = os.path.join(self.tmp.name, "p.py")
        with open(self.script, "w") as f:
            f.write(script)

    def tearDown(self):
        self.tmp.cleanup()

    def cmd(self, mode):
        return f"{shlex.quote(sys.executable)} {shlex.quote(self.script)} {mode} {{fmt}}"

    def test_records_come_back_with_fmt_substituted(self):
        recs = CommandParser(self.cmd("ok")).parse(b"1 25544U", "csv")
        self.assertEqual(recs, [{"norad_cat_id": 25544, "fmt": "csv", "bytes": 8}])

    def test_exit_3_is_unsupported(self):
        with self.assertRaises(Unsupported):
            CommandParser(self.cmd("unsup")).parse(b"", "kvn")

    def test_non_zero_exit_names_the_exit_code_and_stderr(self):
        with self.assertRaises(RuntimeError) as cm:
            CommandParser(self.cmd("fail")).parse(b"", "csv")
        self.assertIn("exit 1", str(cm.exception))
        self.assertIn("boom", str(cm.exception))

    def test_a_json_object_instead_of_an_array_is_named(self):
        with self.assertRaises(RuntimeError) as cm:
            CommandParser(self.cmd("obj")).parse(b"", "csv")
        self.assertIn("array", str(cm.exception))

    def test_output_that_is_not_json_is_named(self):
        with self.assertRaises(RuntimeError) as cm:
            CommandParser(self.cmd("text")).parse(b"", "csv")
        self.assertIn("not JSON", str(cm.exception))

    def test_the_runner_reports_a_failing_command_as_a_parse_failure(self):
        r = Runner(CommandParser(self.cmd("fail")), root=ROOT).run(case_ids=[DERIVED])[0]
        fails = [i for i in r.items if i.check == "parse" and i.status == "fail"]
        self.assertTrue(fails)
        self.assertIn("exit 1", fails[0].detail)
        self.assertNotIn("internal error", " ".join(i.detail for i in r.items))


class EpochVectorValues(unittest.TestCase):
    """10.5: ccsds-epoch-strings used to pass any hook that returned without raising."""

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(ROOT, "vectors", "ccsds-epoch-strings.json")) as f:
            cls.vec = json.load(f)

    def run_hook(self, parse_epoch):
        class P(Reference):
            pass
        P.parse_epoch = staticmethod(parse_epoch)
        r = Runner(P(), root=ROOT).run(case_ids=[VECTORS])[0]
        return item(r, "ccsds-epoch-strings")

    def test_every_valid_vector_carries_the_instant_it_denotes(self):
        for v in self.vec["valid"]:
            self.assertIn("iso", v, v["text"])
            dt.datetime.strptime(v["iso"], "%Y-%m-%dT%H:%M:%S.%f")  # canonical microsecond form
        self.assertEqual(next(v for v in self.vec["valid"] if v["text"].startswith("2020-064"))["iso"], "2020-03-04T10:34:41.426400")
        self.assertEqual(next(v for v in self.vec["valid"] if v["text"].startswith("2002-204"))["iso"], "2002-07-23T15:56:23.000000")

    def test_the_reference_hook_passes_with_the_instants_compared(self):
        it = item(Runner(Reference(), root=ROOT).run(case_ids=[VECTORS])[0], "ccsds-epoch-strings")
        self.assertEqual(it.status, "pass", it.detail)
        self.assertIn("instant", it.detail)

    def test_a_constant_returning_hook_fails(self):
        ref = Reference()

        def constant(text):
            ref.parse_epoch(text)  # keeps the invalid strings rejected, so only the values are at stake
            return dt.datetime(2000, 1, 1)
        it = self.run_hook(constant)
        self.assertEqual(it.status, "fail")
        self.assertIn("2020-064T10:34:41.4264", it.detail)
        self.assertIn("2000-01-01", it.detail)

    def test_the_leap_second_accepts_the_second_before_and_the_rollover_only(self):
        ref = Reference()

        def rollover(text):
            t = ref.parse_epoch(text)
            return t + dt.timedelta(seconds=1) if text.endswith(":60") else t
        self.assertEqual(self.run_hook(rollover).status, "pass")

        def wrong(text):
            t = ref.parse_epoch(text)
            return t - dt.timedelta(seconds=59) if text.endswith(":60") else t
        it = self.run_hook(wrong)
        self.assertEqual(it.status, "fail")
        self.assertIn("23:59:60", it.detail)

    def test_an_aware_datetime_is_compared_as_utc(self):
        ref = Reference()

        def aware(text):
            return (ref.parse_epoch(text) + dt.timedelta(hours=2)).replace(tzinfo=dt.timezone(dt.timedelta(hours=2)))  # same instant, +02:00 wall clock
        self.assertEqual(self.run_hook(aware).status, "pass")

    def test_the_naive_hook_still_fails_on_the_forms_it_rejects(self):
        it = item(Runner(Naive(), root=ROOT).run(case_ids=[VECTORS])[0], "ccsds-epoch-strings")
        self.assertEqual(it.status, "fail")
        self.assertIn("rejected", it.detail)


if __name__ == "__main__":
    unittest.main()


class NonIntegerCatalogIdTests(unittest.TestCase):
    """An adapter that returns a catalog id the runner cannot take as an integer (Alpha-5 text kept as a string, a
    fractional float, a bool) gets a failed values item naming the value and its type, not a parse item saying the
    runner raised (D-131). Several libraries keep the field as a string."""

    def test_norm_record_reports_instead_of_raising(self):
        from gpconf.runner import norm_record, as_integer
        self.assertEqual(as_integer(25544), (25544, None))
        self.assertEqual(as_integer("25544"), (25544, None))          # a digit string converts; the type note records it
        self.assertEqual(as_integer(25544.0), (25544, None))
        self.assertEqual(as_integer("A0000"), (None, "'A0000' (str)"))
        self.assertEqual(as_integer(25544.5), (None, "25544.5 (float, fractional)"))
        self.assertEqual(as_integer(True), (None, "True (bool)"))
        out, notes, bad = norm_record({"norad_cat_id": "A0000", "rev_at_epoch": 12.5, "mean_motion": "15.5"})
        self.assertIsNone(out["norad_cat_id"])
        self.assertEqual(bad, {"norad_cat_id": "'A0000' (str)", "rev_at_epoch": "12.5 (float, fractional)"})
        self.assertEqual(notes["norad_cat_id"], "str")

    def test_values_item_names_the_value_and_type(self):
        ref = Reference()

        class KeepsTheField:
            """the reference reader, except that the TLE catalog field travels as the raw five characters"""
            def parse(self, raw, fmt):
                recs = ref.parse(raw, fmt)
                if fmt in ("tle", "2le"):
                    lines = [l for l in raw.decode("utf-8").splitlines() if l.startswith("1 ")]
                    for r, l in zip(recs, lines):
                        r["norad_cat_id"] = l[2:7]
                return recs

        results = Runner(KeepsTheField(), root=ROOT).run(case_ids=["alpha5-tle-derived"])
        r = next(x for x in results if x.case_id == "alpha5-tle-derived")
        self.assertEqual(r.status, "fail")
        self.assertEqual([i for i in r.items if i.check == "parse"], [], "the runner must not raise on a string id")
        values = [i for i in r.items if i.check == "values" and i.file.endswith("alpha5-A-100000-saramago-first.tle")]
        self.assertEqual(len(values), 1)
        self.assertEqual(values[0].status, "fail")
        self.assertIn("1 record(s) whose norad_cat_id is not an integer, e.g. 'A0000' (str)", values[0].detail)
        self.assertNotIn("without norad_cat_id", values[0].detail)
