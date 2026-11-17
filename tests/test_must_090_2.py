# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""Tests that pin survivors of the 0.9.0 mutation run the owner ruled must be tested before the release (group 2 of the
"must" list): each passes on the code and fails under its mutant, named by number in each test's docstring.

They cover the propagation tier's counts (the installed python-sgp4 as a candidate, the steps compared, the steps both
propagated), the OMM renderings' agreement count and its copies, the provider's TLE epoch quantisation note, the KVN
variant items, the SATCAT data check, the nine-digit vector count, the writer case's counts and the corrupt-input
case's modes and per-input dodges (D-280). None needs Vallado's files, python-sgp4 or fetched data.

Run: python -m unittest tests.test_must_090_2"""
import json
import os
import shutil
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from gpconf import propagation as P  # noqa: E402
from gpconf import writer as W  # noqa: E402
from gpconf.adapters.reference import Parser as Reference  # noqa: E402
from gpconf.runner import KEYWORD_TO_FIELD, CaseResult, Runner, Unsupported  # noqa: E402
from gpconf.words import qty  # noqa: E402
from tests.adversarial.test_history_080 import SETS, csv_text, tle_text  # noqa: E402
from tests.adversarial.test_strict_files_080 import LIVE  # noqa: E402
from tests.test_propagation import REF, steps  # noqa: E402

CONSISTENCY = "tle-values-match-omm-within-tle-precision"
VARIANT_CHECKS = ("kvn-syntax-tolerance", "optional-tle-parameters-may-be-absent", "omm-version-3-accepted")
V05 = "v05-omm-3.0-header-optional-keywords-omitted.kvn"
V07 = "derived/kvn-variants/v07-xml-ndm-reserialised.xml"
CORRUPT = os.path.join(ROOT, "derived", "corrupt-input")


def expected(case):
    with open(os.path.join(ROOT, "fixtures", case, "expected.json"), encoding="utf-8") as f:
        return json.load(f)


def run_one(parser, case, root=ROOT, data=None):
    return Runner(parser, root=root, data=data, fetch_hints=False).run(case_ids=[case])[0]


# ---- the propagation tier

class PropagationCounts(unittest.TestCase):

    def test_an_installed_python_sgp4_is_a_candidate(self):
        """Kills 2948 (`or []` made `and []`: the installed python-sgp4 package's folder is never a candidate, so the
        documented way to get Vallado's files is never looked in)."""
        spec = types.SimpleNamespace(submodule_search_locations=["/x/sgp4"])
        with mock.patch("importlib.util.find_spec", return_value=spec):
            got = list(P._candidates(ROOT, None))
        self.assertIn(("/x/sgp4", "the installed python-sgp4 package"), got)
        self.assertEqual(got[0], ("/x/sgp4", "the installed python-sgp4 package"))

    def test_an_answer_of_the_wrong_length_compares_no_step(self):
        """Kills 2963 (grade_set's wrong-length answer counted 1 step compared instead of 0)."""
        for bad in (None, "x", steps(REF["rows"])[:2]):
            problems, st = P.grade_set(REF, bad)
            self.assertTrue(problems["values"])
            self.assertEqual(st, {"compared": 0, "max_r": 0.0, "max_v": 0.0})
        exact = [{k: v for k, v in s.items() if k != "error"} for s in steps(REF["rows"])]
        self.assertEqual(P.grade_set(REF, exact), ({"values": [], "codes": []}, {"compared": 3, "max_r": 0.0, "max_v": 0.0}))

    def test_the_twins_steps_are_counted_once_each(self):
        """Kills 2996 (a twins answer of the wrong length counted 1 step compared), 2997 (the count started at 1),
        3007 (each compared step counted twice) and 3021 (both_propagated counted each step twice). The corpus's own
        twins reference answered with itself, every step propagated (no python-sgp4 needed)."""
        sets = P.twins(ROOT)["sets"]
        self.assertTrue(sets)
        for st in sets:
            ref_steps = st["steps"]
            self.assertTrue(ref_steps)
            self.assertTrue(all(s["error"] == 0 for s in ref_steps), st["norad_cat_id"])
            a = [{"r": list(s["r"]), "v": list(s["v"])} for s in ref_steps]
            self.assertEqual(P.grade_steps(ref_steps, [])[1], {"compared": 0, "max_r": 0.0, "max_v": 0.0})
            self.assertEqual(P.grade_steps(ref_steps, a),
                             ({"values": [], "codes": []}, {"compared": len(ref_steps), "max_r": 0.0, "max_v": 0.0}))
            self.assertEqual(P.both_propagated(a, a), len(a))
            self.assertEqual(P.agree(a, a), (0.0, 0.0, []))


# ---- the OMM renderings' agreement (check_set_relations, called directly)

def omm_record(cat, esn, rev, epoch, mean_anomaly):
    return {"norad_cat_id": cat, "epoch": epoch, "mean_motion": "15.5", "eccentricity": "0.0001", "inclination": "51.6",
            "mean_anomaly": mean_anomaly, "element_set_no": esn, "rev_at_epoch": rev}


A = omm_record(25544, 1, 100, "2026-01-01T00:00:00.000000", "10.0")
B = omm_record(25544, 2, 101, "2026-01-02T00:00:00.000000", "20.0")


class OmmFormatsAgree(unittest.TestCase):

    def agree(self, csv_parsed, json_parsed, ids_held):
        refs = [{"norad_cat_id": i} for i in ids_held]
        res = CaseResult("scratch", "scratch")
        files = {"a.csv": ("ok", "csv", csv_parsed, refs), "a.json": ("ok", "json", json_parsed, refs)}
        Runner(Reference(), root=ROOT).check_set_relations(res, {"sources": {}}, "a set", files, {"omm-formats-agree"})
        (item,) = [i for i in res.items if i.check == "omm-formats-agree"]
        return item

    def test_an_id_no_input_holds_counts_once(self):
        """Kills 846 (an id no file's input holds counted twice in 'agree on N records'). Both files return the held id
        and the same made-up id 123456789: two records."""
        made_up = omm_record(123456789, 5, 5, "2026-01-03T00:00:00.000000", "30.0")
        item = self.agree([A, made_up], [dict(A), dict(made_up)], [25544])
        self.assertEqual((item.status, item.detail), ("pass", "2 OMM renderings agree on 2 records"))

    def test_an_id_held_twice_returned_in_another_order_agrees(self):
        """Kills 848 (an id held exactly twice sent to the first-copy-only path): the JSON file returns the two copies
        in the other order, and a correct parser passes (D-344)."""
        item = self.agree([A, B], [dict(B), dict(A)], [25544, 25544])
        self.assertEqual((item.status, item.detail), ("pass", "2 OMM renderings agree on 2 records"))

    def test_a_disagreement_on_an_id_held_once_fails(self):
        """Kills 852 (`len(d) > 1` made `> 2`: with two files a disagreement is never reported)."""
        item = self.agree([A], [dict(A, mean_anomaly="11.0")], [25544])
        self.assertEqual(item.status, "fail", item.detail)
        self.assertIn("id 25544 mean_anomaly", item.detail)


# ---- the provider's TLE epoch quantisation note (the pairs case on the ISS files written at test time)

class EpochQuantisationNote(unittest.TestCase):

    def setUp(self):
        self.data = tempfile.mkdtemp(prefix="gpconf-must-090-2-")

    def tearDown(self):
        shutil.rmtree(self.data, ignore_errors=True)

    def consistency(self, tle_sets, csv_sets):
        os.makedirs(os.path.join(self.data, LIVE), exist_ok=True)
        for name, text in (("iss.tle", tle_text(tle_sets)), ("iss.csv", csv_text(csv_sets))):
            with open(os.path.join(self.data, LIVE, name), "w", encoding="utf-8", newline="") as f:
                f.write(text)
        res = run_one(Reference(), "tle-vs-omm-precision-loss", data=self.data)
        return {i.check: i for i in res.items}[CONSISTENCY]

    def test_the_note_is_given_only_where_the_epochs_differ_within_the_allowance(self):
        """Kills 941 (exact epochs fed the quantisation stats, and tolerance ones no longer did) and 949 (`quant and
        not bad` made `or`: every passing item got the note, empty). The TLE epoch field holds this set's epoch
        exactly (98324.28472222 is 06:49:59.999808), so the first pair is exact; the second CSV's epoch is 100 us later,
        within the 432 us allowance."""
        item = self.consistency(SETS[:1], SETS[:1])
        self.assertEqual(item.status, "pass", item.detail)
        self.assertNotIn("quantisation", item.detail)
        item = self.consistency(SETS[:1], [dict(SETS[0], EPOCH="1998-11-20T06:49:59.999908")])
        self.assertEqual(item.status, "pass", item.detail)
        self.assertIn("provider TLE epoch quantisation observed", item.detail)
        self.assertIn("epoch n=1", item.detail)


# ---- the KVN variants (D-299)

class KvnVariantItems(unittest.TestCase):

    def test_the_omitted_keywords_note_is_on_its_own_item_alone(self):
        """Kills 977 (`exempt and c == ...` made `or`: every other variant's optional-parameters item says 'omitted
        keywords []', and v05's other two items carry the note) and 978 (`==` made `!=`: the note moves to the two
        other checks)."""
        exp = expected("kvn-syntax-variants")
        (rec,) = [r for r in exp["records"] if r.get("derived_file") == V05]
        note = f"variant parsed; omitted keywords {sorted(KEYWORD_TO_FIELD[k] for k in rec['keywords_absent'])}"
        r = run_one(Reference(), "kvn-syntax-variants")
        seen = {}
        for i in r.items:
            if i.check in VARIANT_CHECKS:
                seen[(os.path.basename(i.file), i.check)] = i
        kvn = [os.path.basename(p) for p in exp["sources"] if p.endswith(".kvn")]
        self.assertIn(V05, kvn)
        for b in kvn:
            for c in VARIANT_CHECKS:
                i = seen[(b, c)]
                self.assertEqual(i.status, "pass", (b, c, i.detail))
                want = note if (b == V05 and c == "optional-tle-parameters-may-be-absent") else "variant parsed"
                self.assertEqual(i.detail, want, (b, c))

    def test_a_file_of_another_format_in_the_case_is_no_variant(self):
        """Kills 973 (`kind == derived-kvn and fmt == kvn` made `or`: a non-KVN file of the case gets the three
        'variant parsed' items D-299 removed). A scratch root holding the case with the corpus's derived XML file,
        v07, listed among its sources again (its entry as the corrupt-input case records it): the XML file is read
        and graded, and no variant item names it."""
        d = tempfile.mkdtemp(prefix="gpconf-must-090-2-kvn-")
        try:
            with open(os.path.join(ROOT, "manifest.json"), encoding="utf-8") as f:
                m = json.load(f)
            m["cases"] = [c for c in m["cases"] if c["id"] == "kvn-syntax-variants"]
            with open(os.path.join(d, "manifest.json"), "w", encoding="utf-8") as f:
                json.dump(m, f)
            exp = expected("kvn-syntax-variants")
            exp["sources"][V07] = expected("corrupt-input")["sources"][V07]
            os.makedirs(os.path.join(d, "fixtures", "kvn-syntax-variants"))
            with open(os.path.join(d, "fixtures", "kvn-syntax-variants", "expected.json"), "w", encoding="utf-8") as f:
                json.dump(exp, f)
            shutil.copytree(os.path.join(ROOT, "derived", "kvn-variants"), os.path.join(d, "derived", "kvn-variants"))
            r = run_one(Reference(), "kvn-syntax-variants", root=d)
        finally:
            shutil.rmtree(d, ignore_errors=True)
        xml = os.path.basename(V07)
        self.assertEqual([(i.check, i.file, i.detail) for i in r.items if i.status == "fail" or i.check == "runner"], [])
        self.assertTrue(any(i.file and os.path.basename(i.file) == xml for i in r.items))   # the XML file was read
        self.assertEqual([i.check for i in r.items if i.check in VARIANT_CHECKS and os.path.basename(i.file or "") == xml], [])
        self.assertTrue(any(i.check in VARIANT_CHECKS and os.path.basename(i.file or "") == V05 for i in r.items))


# ---- the SATCAT data check

class SatcatDataCheck(unittest.TestCase):

    def test_a_live_legacy_file_with_an_id_at_70000_fails_the_data_check(self):
        """Kills 1013 (`==` made `!=`: snapshot and live swapped in res.modes and the detail) and 1015 (the id read from
        columns 15-18, its first digit dropped). Two fixed-width lines, ids 69999 and 70000 at columns 14-18."""
        data = tempfile.mkdtemp(prefix="gpconf-must-090-2-satcat-")
        try:
            folder = os.path.join(data, "fixtures", "satcat-70000-cutoff", "raw")
            os.makedirs(folder)
            with open(os.path.join(folder, "satcat.txt"), "w", encoding="utf-8", newline="") as f:
                f.write("1957-001A    69999 FIRST OBJECT\r\n2026-001A    70000 SECOND OBJECT\r\n")
            r = run_one(Reference(), "satcat-70000-cutoff", data=data)
        finally:
            shutil.rmtree(data, ignore_errors=True)
        (item,) = [i for i in r.items if i.check == "satcat-legacy-below-70000"]
        self.assertEqual(item.status, "fail", item.detail)
        self.assertIn("2 ids, max 70000, 1 at or above 70000 (data check, live)", item.detail)
        self.assertEqual(r.modes["fixtures/satcat-70000-cutoff/raw/satcat.txt"], "live")


# ---- the vectors case

class NineDigitVectorCount(unittest.TestCase):

    def test_the_nine_digit_count_is_the_vector_files(self):
        """Kills 1040 (each nine-digit valid form counted twice in catalog-number-is-integer's detail)."""
        exp = expected("alpha5-encoding-vectors")
        cid = next(v for k, v in exp["case_specific"].items() if k.endswith("norad-cat-id-text.json"))
        n = sum(1 for v in cid["valid"] if v["value"] >= 100_000_000)
        self.assertGreater(n, 0)
        r = run_one(Reference(), "alpha5-encoding-vectors")
        (item,) = [i for i in r.items if i.check == "catalog-number-is-integer"]
        self.assertEqual(item.status, "pass", item.detail)
        self.assertEqual(item.detail, f"{qty(len(cid['valid']), 'valid text form')} parsed as int ({n} nine-digit) and "
                                      f"{qty(len(cid['invalid_in_omm']), 'invalid form')} rejected")


# ---- the writer case

WRITER = "tle-writer-alpha5"


def summary(fails, ok_text, n_ok, n_all, unit="record"):
    """The writer case's detail, as run_writer words it."""
    if not fails:
        return ok_text
    return f"{n_ok} of {qty(n_all, unit)} correct; " + "; ".join(fails[:8]) + (f"; … and {len(fails) - 8} more" if len(fails) > 8 else "")


class WriterCounts(unittest.TestCase):

    def test_the_reference_writers_counts_are_the_records_it_wrote(self):
        """Kills 1067 (rt_checked counted twice), 1069 and 1070 (each rendering count started at 1, or counted 2),
        1072 and 1073 (each secondary-field outcome likewise), 1074 (side_checked counted twice), 1077 and 1078 (the
        zero second-derivative sign count likewise), 1079, 1080, 1081 and 1083 (the provider-rendering numerator or
        denominator started at 1, a match counted in the denominator, the denominator counted 2). The reference
        writer's output is recounted here with the writer module's own functions."""
        exp = expected(WRITER)
        p = Reference()
        conv, sec, signs, prov = {}, {}, {}, {}
        written = rt_checked = side_checked = 0
        side_changed = []
        for it in exp["records"]:
            if not it["representable_in_tle"]:
                continue
            rec = it["canonical"]
            l0, l1, l2 = W.normalise_lines(p.write_tle(dict(rec)))
            written += 1
            if len(l1) != 69 or len(l2) != 69:
                continue
            rt_checked += 1
            mism, c = W.round_trip(l0, l1, l2, rec)
            s = W.secondary_fields(l0, l1, l2, rec)
            for f, k in c.items():
                conv.setdefault(f, {})[k] = conv.setdefault(f, {}).get(k, 0) + 1
            for f in W.SECONDARY_FIELDS:
                sec.setdefault(f, {})[s[f]] = sec.setdefault(f, {}).get(s[f], 0) + 1
            side_checked += 1
            changed = [f for f in W.SECONDARY_FIELDS if s[f] == "changed"]
            if changed:
                side_changed.append(f"id {it['norad_cat_id']}: {', '.join(changed)}")
            if s["zero_ddot_sign"]:
                signs[s["zero_ddot_sign"]] = signs.get(s["zero_ddot_sign"], 0) + 1
            if it.get("reference_tle_fields"):
                for f, same in W.provider_field_matches(l1, l2, it["reference_tle_fields"]).items():
                    q = prov.setdefault(f, [0, 0])
                    q[0] += bool(same)
                    q[1] += 1
        self.assertGreater(rt_checked, 0)
        self.assertTrue(signs)   # some record has a zero second derivative
        self.assertTrue(any(a for a, _ in prov.values()))   # the reference renders some field as the provider does

        by = {i.check: i for i in run_one(Reference(), WRITER).items}
        conv_text = "; ".join(f"{f}: " + ", ".join(f"{k} {n}" for k, n in sorted(v.items())) for f, v in conv.items())
        self.assertEqual(by["tle-writer-round-trip"].status, "pass", by["tle-writer-round-trip"].detail)
        self.assertEqual(by["tle-writer-round-trip"].detail,
                         f"{qty(written, 'record')} read back at the TLE field resolution (rendering observed per field: {conv_text})")
        self.assertEqual(by["tle-writer-column-layout"].detail, f"{qty(rt_checked, 'record')} with every field in its fixed columns")
        sec_text = "; ".join(f"{f}: " + ", ".join(f"{k} {n}" for k, n in sorted(v.items())) for f, v in sec.items())
        sign_text = ", ".join(f"'{k}' {n}" for k, n in sorted(signs.items()))
        self.assertEqual(by["tle-writer-secondary-fields"].detail,
                         f"{sec_text}; zero second-derivative exponent sign: {sign_text} (CelesTrak writes +, Space-Track -)")
        self.assertEqual(by["tle-writer-secondary-not-changed"].detail,
                         summary([f"{c} written as another value, neither the record's nor zero or left out" for c in side_changed],
                                 f"{qty(side_checked, 'record')} with each side field kept, or zeroed or left out as documented",
                                 side_checked - len(side_changed), side_checked))
        self.assertEqual(by["tle-writer-matches-provider-rendering"].detail,
                         "byte-identical to the provider's or derived rendering: " + ", ".join(f"{f} {a}/{n}" for f, (a, n) in prov.items()))

    def test_a_writer_whose_output_is_never_lines_checks_no_side_field(self):
        """Kills 1043 (side_checked started at 1: a writer whose output never reaches the round trip passed
        tle-writer-secondary-not-changed instead of not-exercised)."""
        class NoLines(Reference):
            def write_tle(self, record):
                return "only one line"
        by = {i.check: i for i in run_one(NoLines(), WRITER).items}
        self.assertEqual(by["tle-writer-secondary-not-changed"].status, "not-exercised", by["tle-writer-secondary-not-changed"].detail)

    def test_a_refused_representable_id_counts_once(self):
        """Kills 1052 (a refused representable id counted twice in the catalog-field item's 'k of n'). The reference
        writer, refusing every record of the first representable id with a ValueError."""
        exp = expected(WRITER)
        real = [it for it in exp["records"] if it["representable_in_tle"]]
        target = real[0]["canonical"]["norad_cat_id"]
        m = sum(1 for it in real if it["canonical"].get("norad_cat_id") == target)

        class Refusing(Reference):
            def write_tle(self, record):
                if record.get("norad_cat_id") == target:
                    raise ValueError("refused on purpose")
                return super().write_tle(record)
        by = {i.check: i for i in run_one(Refusing(), WRITER).items}
        item = by["tle-writer-catalog-field"]
        self.assertEqual(item.status, "fail", item.detail)
        self.assertTrue(item.detail.startswith(f"{len(real) - m} of {qty(len(real), 'catalog field')} correct; "), item.detail[:120])


# ---- the corrupt-input case

def corrupt_bytes(name):
    with open(os.path.join(CORRUPT, name), "rb") as f:
        return f.read()


class CorruptInputModesAndDodges(unittest.TestCase):

    def test_every_shipped_file_is_read_in_snapshot_mode(self):
        """Kills 1119 (the unedited comparison files recorded 'live' on a clean run) and 1135 (the corrupt inputs
        themselves recorded 'live')."""
        r = run_one(Reference(), "corrupt-input")
        names = {os.path.basename(p) for p in r.modes}
        self.assertIn("c1-checksum-digit.tle", names)
        self.assertIn("unedited-sets.tle", names)
        self.assertEqual(set(r.modes.values()), {"snapshot"}, r.modes)

    def test_a_tle_input_declared_unsupported_while_others_are_read_fails_where_it_was_declared(self):
        """Kills 1122 and 1123 (the unedited file's dodge recorded two items past its skip, or the item before it) and
        1139 (a corrupt input's dodge recorded on the item before its skip): the D-280 failure lands on another item
        and the dodge stays a skip. A reference reader that declares TLE unsupported for unedited-first.tle and for
        c1-checksum-digit.tle alone, while it reads the case's other TLE files."""
        dodged = {corrupt_bytes("unedited-first.tle"), corrupt_bytes("c1-checksum-digit.tle")}

        class Dodging(Reference):
            def parse(self, raw, fmt):
                if bytes(raw) in dodged:
                    raise Unsupported("not this file")
                return super().parse(raw, fmt)
        r = run_one(Dodging(), "corrupt-input")
        for name in ("unedited-first.tle", "c1-checksum-digit.tle"):
            (item,) = [i for i in r.items if os.path.basename(i.file or "") == name and i.detail.startswith("parser reports tle unsupported")]
            self.assertEqual(item.status, "fail", (name, item.detail))
            self.assertIn("(D-280)", item.detail)
        for i in r.items:
            if "(D-280)" in i.detail:
                self.assertTrue(i.detail.startswith("parser reports"), (i.check, i.file, i.detail[:120]))


if __name__ == "__main__":
    unittest.main()
