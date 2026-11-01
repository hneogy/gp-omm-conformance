# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""An empty OMM value for an id the input holds more than once (D-352, split from D-351 on the owner's ruling), with
wrong-on-purpose adapters and twins, on the pairs case tle-vs-omm-precision-loss, where nothing but this item judges
the three fields (the records-returned item fails a parser that returns copies the input does not hold).

The parser's copy that returns BSTAR, the second derivative or the eccentricity empty must take an input copy of the id
that leaves it empty at its own epoch (within the item's own 432 us TLE/OMM epoch allowance), each input copy once,
however many TLE copies the parser's copy pairs with; where it takes one, the parser's TLE value is compared with the
values the input's TLE copies give at that TLE copy's epoch, or at the OMM copy's where the TLE copy has none. Neither
the parser's element set numbers nor an epoch it drops choose the copy it is judged by. Within one epoch, which input
copy an empty answer belongs to is not judged within the 432 us allowance of the parser copy's epoch (the owner's
ruling: the pairs-case escapes entry adds that check).

The files are built at test time from the ISS records epoch-year-19xx freezes (no provider's bytes, so the module runs
in the public export). Run: python -m unittest tests.adversarial.test_repeated_empty_080"""
import datetime as dt
from decimal import Decimal
import itertools
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from gpconf.adapters.reference import Parser as Reference  # noqa: E402
from gpconf.runner import Runner, _EmptyCopies  # noqa: E402
from tests.adversarial.test_history_080 import SETS, csv_text, tle_text  # noqa: E402
from tests.adversarial.test_internal_errors_080 import answering  # noqa: E402
from tests.adversarial.test_strict_files_080 import LIVE  # noqa: E402

CONSISTENCY = "tle-values-match-omm-within-tle-precision"
PAIRS = "tle-vs-omm-precision-loss"
B = "0.00012345"
GIVES = "but no copy of the id that leaves it empty is left within 432 us of that epoch (D-352)"


def both(how):
    """An adapter changing the parser's records of both files (TLE and OMM) as `how` says."""
    return answering(how, fmts=("csv", "tle"))


class EmptyValuesOfRepeatedIds(unittest.TestCase):

    def setUp(self):
        self.data = tempfile.mkdtemp(prefix="gpconf-repeated-empty-")

    def tearDown(self):
        shutil.rmtree(self.data, ignore_errors=True)

    def pairs(self, parser, tle_sets, csv_sets):
        for name, text in (("iss.tle", tle_text(tle_sets)), ("iss.csv", csv_text(csv_sets))):
            os.makedirs(os.path.join(self.data, LIVE), exist_ok=True)
            with open(os.path.join(self.data, LIVE, name), "w", encoding="utf-8", newline="") as f:
                f.write(text)
        res = Runner(parser, root=ROOT, data=self.data, fetch_hints=False).run(case_ids=[PAIRS])[0]
        items = {i.check: i for i in res.items}
        self.assertNotIn("runner", items, items.get("runner") and items["runner"].detail)
        return items[CONSISTENCY]

    def fails(self, item, words=GIVES):
        self.assertEqual(item.status, "fail", item.detail)
        self.assertIn(words, item.detail)

    def passes(self, item):
        self.assertEqual(item.status, "pass", item.detail)

    def test_a_dropped_value_fails_whatever_the_parser_says_of_the_copies(self):
        """The ISS twice, BSTAR empty in one copy and given in the other, the copies a day apart and at one epoch (a
        re-issued element set): a parser dropping BSTAR fails with its OMM numbers right, as 0, or dropped with the epoch;
        the reference passes, whichever copy is the empty one."""
        two = [SETS[0], dict(SETS[1], BSTAR=B)]
        tied = [SETS[0], dict(SETS[1], EPOCH=SETS[0]["EPOCH"], BSTAR=B)]
        for name, sets in (("apart", two), ("one epoch", tied)):
            csv = [dict(sets[0], BSTAR=""), sets[1]]
            for how, wrong in (("numbers kept", {}), ("numbers 0", dict(element_set_no=0, rev_at_epoch=0)),
                               ("epoch and numbers dropped", dict(epoch=None, element_set_no=None, rev_at_epoch=None))):
                with self.subTest(epochs=name, omm=how):
                    item = self.pairs(answering(lambda rs: [dict(r, bstar=None, **wrong) for r in rs]), sets, csv)
                    self.fails(item, "in a copy with no epoch, which can take no input copy that leaves it empty (D-352)" if "epoch" in wrong else GIVES)
            with self.subTest(epochs=name, twin="the reference"):
                self.passes(self.pairs(Reference(), sets, csv))
            with self.subTest(epochs=name, twin="the reference, the other copy empty"):
                self.passes(self.pairs(Reference(), [dict(sets[0], BSTAR=B), dict(sets[1], BSTAR="0")],
                                       [dict(sets[0], BSTAR=B), dict(sets[1], BSTAR="")]))

    def test_one_field_left_empty_does_not_excuse_another(self):
        """The fifth reading's mutant M12, for an id held twice: BSTAR empty in both copies, the eccentricity given; a
        parser dropping the eccentricity fails; its twin, the reference, passes."""
        sets = [dict(SETS[0], BSTAR="0"), dict(SETS[1], BSTAR="0")]
        csv = [dict(s, BSTAR="") for s in sets]
        self.fails(self.pairs(answering(lambda rs: [dict(r, eccentricity=None) for r in rs]), sets, csv))
        self.passes(self.pairs(Reference(), sets, csv))

    def test_the_tle_value_is_compared_with_the_tle_file_at_that_copys_epoch(self):
        """BSTAR empty in both OMM copies, the TLE copies giving 1E-4 and 2E-4: a parser whose TLE reader gives the first
        copy the second's BSTAR fails, with the second's numbers too or with its own; the reference passes, and passes
        where the TLE's 1E-8-day field rounds the epochs 292 us down (the fifth reading's mutant M13)."""
        tle = [dict(SETS[0], BSTAR="0.0001"), dict(SETS[1], BSTAR="0.0002")]
        csv = [dict(s, BSTAR="") for s in tle]

        def crossed(numbers):
            def how(rs):
                rs = [dict(r) for r in rs]
                a, b = sorted(rs, key=lambda r: r["epoch"])
                a.update(bstar=b["bstar"], **({"element_set_no": b["element_set_no"], "rev_at_epoch": b["rev_at_epoch"]} if numbers else {}))
                return rs
            return how
        for numbers in (True, False):
            with self.subTest(numbers_crossed=numbers):
                self.fails(self.pairs(answering(crossed(numbers), fmts=("tle",)), tle, csv),
                           "vs the TLE file's 0.0001 at that epoch (the OMM record leaves it empty)")
        self.passes(self.pairs(Reference(), tle, csv))
        late = [dict(SETS[0], EPOCH="1998-11-20T06:50:00.000100", BSTAR="0.0001"), dict(SETS[1], EPOCH="1998-11-21T06:50:00.000100", BSTAR="0.0002")]
        self.passes(self.pairs(Reference(), late, [dict(s, BSTAR="") for s in late]))

    def test_an_omm_copy_paired_with_several_tle_copies_takes_one_input_copy(self):
        """The fifth reading's finding 1: the TLE file holds the ISS twice, the CSV once with BSTAR empty; the reference
        passes; a parser dropping a BSTAR the CSV gives fails."""
        self.passes(self.pairs(Reference(), [SETS[0], SETS[0]], [dict(SETS[0], BSTAR="")]))
        self.fails(self.pairs(answering(lambda rs: [dict(r, bstar=None) for r in rs]), [dict(SETS[0], BSTAR=B)] * 2, [dict(SETS[0], BSTAR=B)]))

    def test_the_inputs_epochs_are_read_in_every_ccsds_form(self):
        """The fifth reading's finding 2: the CSV's epochs in day-of-year form, with nine fraction digits or with a Z; the
        reference passes, a parser dropping a given BSTAR fails."""
        two = [SETS[0], dict(SETS[1], BSTAR=B)]
        for name, form in (("day of year", lambda e: e[:4] + "-" + {"11-20": "324", "11-21": "325"}[e[5:10]] + e[10:]),
                           ("nine digits", lambda e: e + "000"), ("a Z", lambda e: e + "Z")):
            csv = [dict(two[0], BSTAR="", EPOCH=form(two[0]["EPOCH"])), dict(two[1], EPOCH=form(two[1]["EPOCH"]))]
            with self.subTest(form=name):
                self.passes(self.pairs(Reference(), two, csv))
                self.fails(self.pairs(answering(lambda rs: [dict(r, bstar=None) for r in rs]), two, csv))

    def test_a_parser_with_millisecond_epochs_is_judged_as_the_epoch_check_judges_it(self):
        """The fifth reading's finding 4: a parser whose OMM epochs are cut to milliseconds (as a JavaScript Date holds
        them), BSTAR empty in both input copies: it passes, as the item's 432 us epoch check passes it; dropping a value
        the input gives still fails."""
        ms = lambda rs: [dict(r, epoch=r["epoch"][:23] + "000") for r in rs]
        near = [dict(SETS[0], EPOCH="1998-11-20T06:50:00.000100", BSTAR="0"), dict(SETS[1], EPOCH="1998-11-21T06:50:00.000100", BSTAR="0")]
        self.passes(self.pairs(answering(ms), near, [dict(s, BSTAR="") for s in near]))   # 100 us off
        given = [near[0], dict(near[1], BSTAR=B)]
        self.fails(self.pairs(answering(lambda rs: [dict(r, bstar=None) for r in ms(rs)]), given, [dict(given[0], BSTAR=""), given[1]]))
        # its twin: 808 us off (SETS' epochs end .999808), which the epoch check fails as well
        far = [dict(SETS[0], BSTAR="0"), dict(SETS[1], BSTAR="0")]
        item = self.pairs(answering(ms), far, [dict(s, BSTAR="") for s in far])
        self.fails(item, "id 25544 epoch: tle 1998-11-20T06:49:59.999808 omm 1998-11-20T06:49:59.999000")

    def test_the_greedy_taking_never_fails_a_correct_parser(self):
        """The owner's ruling on the fifth reading's finding 8 (2026-10-23): copies are taken nearest first, in the order
        of the pairs, not by an optimal matching. A parser's copy can be left with no empty copy within the allowance only
        where other copies took the ones near it: that needs a chain of empty input copies each closer to the next than
        twice the parser's epoch error, the chain spanning more than about the allowance less that error (D-352's third
        reading: 12 copies 42 us apart, a parser 23 us early asking last to first, is refused once). Distinct element sets
        of one object lie minutes apart and a re-issue shares its epoch exactly, so no catalog holds such a chain. So:
        empty copies at one epoch and a few distinct ones within 432 us of each other, a correct parser off by up to 23 us
        either way, every order of its copies, every one takes an empty copy; and the dense chain, the stated limit,
        refused asked last to first and taken asked first to last (an optimal matching, later, takes it either way)."""
        base = dt.datetime(2026, 1, 1)
        stamp = lambda us: (base + dt.timedelta(microseconds=us)).strftime("%Y-%m-%dT%H:%M:%S.%f")
        for name, offsets in (("one epoch", [0, 0, 0, 0]), ("within 432 us", [0, 100, 250, 400]), ("both", [0, 0, 150, 150, 431])):
            for errors in ((0,) * len(offsets), tuple((23, -23)[k % 2] for k in range(len(offsets))), tuple((-23, 23)[k % 2] for k in range(len(offsets)))):
                for order in itertools.permutations(range(len(offsets))):
                    copies = _EmptyCopies([{"norad_cat_id": 1, "epoch": stamp(o), "bstar": None} for o in offsets])
                    asks = [{"epoch": stamp(o + e)} for o, e in zip(offsets, errors)]
                    with self.subTest(copies=name, errors=errors, order=order):
                        self.assertTrue(all(copies.take(1, "bstar", asks[k]) for k in order))
        chain = [42 * k for k in range(12)]
        def asked(order):
            copies = _EmptyCopies([{"norad_cat_id": 1, "epoch": stamp(o), "bstar": None} for o in chain])
            asks = [{"epoch": stamp(o - 23)} for o in chain]   # kept alive: take keys its answer by the copy's id()
            return [copies.take(1, "bstar", asks[k]) for k in order]
        self.assertEqual(asked(range(12)).count(False), 0)
        self.assertGreater(asked(range(11, -1, -1)).count(False), 0)   # the stated limit, as measured
        # end to end, the reference on three empty copies 150 us apart, its copies in the reverse of the file's order
        near = [dict(SETS[0], EPOCH=f"1998-11-20T06:50:00.{us:06d}", BSTAR="0", ELEMENT_SET_NO=str(n), REV_AT_EPOCH="0")
                for n, us in ((1, 0), (2, 150), (3, 300))]
        self.passes(self.pairs(answering(lambda rs: rs[::-1]), near, [dict(s, BSTAR="") for s in near]))

    def test_a_tle_copy_with_no_epoch_is_compared_at_its_omm_copys(self):
        """D-352's first reading, finding 1: BSTAR empty in both CSV copies, the TLE copies giving 1E-4 and 2E-4; a parser
        whose TLE reader drops the epoch and gives a BSTAR the file does not hold, or crosses the two, fails; with the
        epoch kept the same wrong value fails as before (its twin)."""
        tle = [dict(SETS[0], BSTAR="0.0001"), dict(SETS[1], BSTAR="0.0002")]
        csv = [dict(s, BSTAR="") for s in tle]
        noepoch = lambda bstar: answering(lambda rs: [dict(r, epoch=None, bstar=bstar(r)) for r in rs], fmts=("tle",))
        self.fails(self.pairs(noepoch(lambda r: "0.0009"), tle, csv), "the OMM record leaves it empty")
        cross = {"0.0001": "0.0002", "0.0002": "0.0001"}
        self.fails(self.pairs(noepoch(lambda r: cross[format(r["bstar"], "f") if not isinstance(r["bstar"], str) else r["bstar"]]), tle, csv),
                   "the OMM record leaves it empty")
        self.fails(self.pairs(answering(lambda rs: [dict(r, bstar="0.0009") for r in rs], fmts=("tle",)), tle, csv), "the OMM record leaves it empty")
        self.passes(self.pairs(Reference(), tle, csv))

    def test_what_the_mutants_of_the_first_reading_would_let_through(self):
        """D-352's first reading, findings 3 and 4 (the reviewer's scenarios K1 to K6): each must read so, or a mutant of
        the rule that brings back an escape or a false fail survives."""
        swap = [dict(SETS[0], BSTAR="0"), dict(SETS[1], BSTAR=B)]
        with self.subTest("K1: 0 written for one copy's empty value, another's dropped, a day apart (the 432 us window)"):
            self.fails(self.pairs(answering(lambda rs: [dict(r, bstar=Decimal(0)) if r["element_set_no"] == 0 else dict(r, bstar=None) for r in rs]),
                                  swap, [dict(swap[0], BSTAR=""), swap[1]]))
        ecc = [dict(SETS[0], ECCENTRICITY="0", BSTAR=B), dict(SETS[1], BSTAR=B)]
        with self.subTest("K2: the eccentricity empty in a copy whose BSTAR is dropped (the answer kept per field)"):
            self.fails(self.pairs(answering(lambda rs: [dict(r, bstar=None) if r["element_set_no"] == 0 else r for r in rs]), ecc,
                                  [dict(ecc[0], ECCENTRICITY=""), ecc[1]]))
            self.passes(self.pairs(Reference(), ecc, [dict(ecc[0], ECCENTRICITY=""), ecc[1]]))
        ddot = [dict(s, MEAN_MOTION_DDOT="0") for s in SETS[:2]]
        with self.subTest("K3: the second derivative empty in both copies, the reference (each field its own copies)"):
            self.passes(self.pairs(Reference(), ddot, [dict(s, MEAN_MOTION_DDOT="") for s in ddot]))
        two = [dict(SETS[0], BSTAR="0.0001"), dict(SETS[1], BSTAR="0.0002")]
        shift = lambda us: lambda rs: [dict(r, epoch=(dt.datetime.strptime(r["epoch"], "%Y-%m-%dT%H:%M:%S.%f") + dt.timedelta(microseconds=us))
                                            .strftime("%Y-%m-%dT%H:%M:%S.%f")) for r in rs]
        with self.subTest("K4: TLE epochs 10 us late, a Julian-date double (the nearest TLE epoch, either side)"):
            self.passes(self.pairs(answering(shift(10), fmts=("tle",)), two, [dict(s, BSTAR="") for s in two]))
        tied = [dict(SETS[0], BSTAR="0.0002"), dict(SETS[1], EPOCH=SETS[0]["EPOCH"], BSTAR="0.0001")]
        with self.subTest("K5: one epoch, TLE BSTARs 2E-4 and 1E-4, the reference (the value nearest, not the first)"):
            self.passes(self.pairs(Reference(), tied, [dict(s, BSTAR="") for s in tied]))
        swap_both = lambda rs: [dict(r, bstar=Decimal(0)) if r["element_set_no"] == 0 else dict(r, bstar=None) for r in rs]
        for apart in ("30 minutes", "1 ms", "600 us"):
            later = {"30 minutes": "1998-11-20T07:19:59.999808", "1 ms": "1998-11-20T06:50:00.000808", "600 us": "1998-11-20T06:50:00.000408"}[apart]
            near = [dict(SETS[0], BSTAR="0"), dict(SETS[1], EPOCH=later, BSTAR=B)]
            with self.subTest(f"K1 at {apart} apart (the second reading: the window pinned between 432 us and a day)"):
                self.fails(self.pairs(answering(swap_both), near, [dict(near[0], BSTAR=""), near[1]]))
        with self.subTest("K1 with the dropped copy's OMM epoch removed (the second reading: a copy with no epoch takes nothing)"):
            noep = lambda rs: [dict(r, bstar=Decimal(0)) if r["element_set_no"] == 0 else dict(r, bstar=None, epoch=None) for r in rs]
            self.fails(self.pairs(answering(noep), swap, [dict(swap[0], BSTAR=""), swap[1]]), "in a copy with no epoch")
        floats = [dict(SETS[0], BSTAR="0.000012345"), dict(SETS[1], EPOCH=SETS[0]["EPOCH"], BSTAR="0.00002")]
        with self.subTest("K5 with a float TLE reader (the second reading: the value nearest, either side, as a float holds it)"):
            item = self.pairs(answering(lambda rs: [dict(r, bstar=0.12345 * 10 ** -4 if str(r["bstar"]).startswith(("0.000012345", "1.2345")) else float(r["bstar"]))
                                                      for r in rs], fmts=("tle",)), floats, [dict(f, BSTAR="") for f in floats])
            self.assertEqual(item.status, "pass-tolerance", item.detail)   # the float's difference recorded (the third reading)
        below = [dict(SETS[0], BSTAR="0.000010805"), dict(SETS[1], EPOCH=SETS[0]["EPOCH"], BSTAR="0.00001")]   # a lower value beside it
        with self.subTest("K5 with a float TLE reader whose value reads just below the file's (0.10805 * 10**-4 = 1.0804999999999999e-05)"):
            item = self.pairs(answering(lambda rs: [dict(r, bstar=0.10805 * 10 ** -4 if str(r["bstar"]).startswith(("0.000010805", "1.0805")) else float(r["bstar"]))
                                                      for r in rs], fmts=("tle",)), below, [dict(f, BSTAR="") for f in below])
            self.assertEqual(item.status, "pass-tolerance", item.detail)
        whole = [dict(SETS[0], EPOCH="1998-11-20T06:50:00.000000", BSTAR="0"), dict(SETS[1], EPOCH="1998-11-21T06:50:00.000000", BSTAR="0")]
        with self.subTest("K6: OMM epochs exactly 432 us early, as the epoch check allows"):
            self.passes(self.pairs(answering(shift(-432)), whole, [dict(s, BSTAR="") for s in whole]))

    def test_an_id_the_omm_file_alone_holds_twice_is_judged_here(self):
        """D-352's third reading, finding 1: the CSV holding the ISS twice and the TLE file once (D-351's held-once path
        would raise KeyError on it): the reference passes, a parser dropping BSTAR fails."""
        tle, csv = [dict(SETS[0], BSTAR=B)], [dict(SETS[0], BSTAR=""), dict(SETS[0], BSTAR=B)]
        self.passes(self.pairs(Reference(), tle, csv))
        self.fails(self.pairs(answering(lambda rs: [dict(r, bstar=None) for r in rs]), tle, csv))

    def test_two_fields_empty_in_the_same_copies_are_each_compared_with_their_own(self):
        """D-352's third reading, finding 2: BSTAR and the second derivative, or the eccentricity and BSTAR, empty in both
        CSV copies, the TLE giving different values per field: the reference passes (each field's TLE values its own)."""
        two = [dict(SETS[0], BSTAR="0.0001", MEAN_MOTION_DDOT="0"), dict(SETS[1], BSTAR="0.0002", MEAN_MOTION_DDOT="0")]
        self.passes(self.pairs(Reference(), two, [dict(s, BSTAR="", MEAN_MOTION_DDOT="") for s in two]))
        ecc = [dict(SETS[0], BSTAR="0.0001"), dict(SETS[1], BSTAR="0.0002")]
        self.passes(self.pairs(Reference(), ecc, [dict(s, BSTAR="", ECCENTRICITY="") for s in ecc]))

    def test_a_tle_value_neither_copy_at_one_epoch_holds_fails(self):
        """D-352's third reading, finding 3: a re-issue at one epoch, BSTAR empty in both CSV copies, the TLE copies giving
        1E-4 and 2E-4; a TLE reader giving 3E-4 for both fails; its twin, the reference, passes."""
        tied = [dict(SETS[0], BSTAR="0.0001"), dict(SETS[1], EPOCH=SETS[0]["EPOCH"], BSTAR="0.0002")]
        csv = [dict(s, BSTAR="") for s in tied]
        self.fails(self.pairs(answering(lambda rs: [dict(r, bstar=Decimal("0.0003")) for r in rs], fmts=("tle",)), tied, csv),
                   "the OMM record leaves it empty")
        self.passes(self.pairs(Reference(), tied, csv))

    def test_an_empty_field_of_one_repeated_id_does_not_excuse_another(self):
        other = [dict(s, NORAD_CAT_ID="25545", OBJECT_ID="1998-067B", BSTAR=B) for s in SETS[:2]]
        sets = SETS[:2] + other
        csv = [dict(s, BSTAR="") for s in SETS[:2]] + other
        self.fails(self.pairs(answering(lambda rs: [dict(r, bstar=None) for r in rs]), sets, csv))
        self.passes(self.pairs(Reference(), [dict(s, BSTAR="0") for s in SETS[:2]] + other, csv))


if __name__ == "__main__":
    unittest.main()
