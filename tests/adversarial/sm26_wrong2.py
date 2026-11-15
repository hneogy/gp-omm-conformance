# SPDX-License-Identifier: Apache-2.0
# Contributed by SM-26 in https://github.com/hneogy/gp-omm-conformance/issues/1 (comment 6583242093, 2026-11-02) and
# licensed by SM-26 under Apache-2.0, credited as SM-26 (D-380). SM-26's work, kept verbatim below this header.
"""Round two of the gpconf audit (hneogy/gp-omm-conformance#1), against gpconf 0.8.0.

Same idea as wrong.py: each class is the corpus's own reference Parser with one deliberate bug, and each finding has a
twin with a bug of the same kind that the corpus does reach, so the twin's fail shows the check exists and the pass
shows the data never asks.
"""
import datetime as dt
import re
from decimal import Decimal, ROUND_HALF_DOWN, ROUND_UP

from gpconf import tle as tlemod
from gpconf.adapters.reference import Parser as Ref
from gpconf.runner import Unsupported, norm_epoch


def write_scaled(record, field, factor):
    r = dict(record)
    if r.get(field) not in (None, ""):
        r[field] = str(Decimal(str(r[field])) * factor)
    return Ref().write_tle(r)


# ---------------------------------------------------------------- W1 writer doubles the first derivative (the ndot/2 mix-up)
class W1NdotDoubled(Ref):
    def write_tle(self, record):
        return write_scaled(record, "mean_motion_dot", 2)


class W1NdotDoubledTwin(Ref):  # the same factor on BSTAR, which the round trip grades: should fail
    def write_tle(self, record):
        return write_scaled(record, "bstar", 2)


# ---------------------------------------------------------------- E1 a reader whose day-of-year stops at a limit
def day_of_year(epoch):
    return dt.datetime.strptime(norm_epoch(epoch)[:10], "%Y-%m-%d").timetuple().tm_yday


def limited_days(limit):
    class DayLimit(Ref):
        def parse(self, raw, fmt):
            out = [{"_adapter": {"refusals": True}}]
            for r in super().parse(raw, fmt):
                if "_refused" not in r and r.get("epoch") and day_of_year(r["epoch"]) > limit:
                    n = r.get("norad_cat_id")
                    out.append({"_refused": f"ValueError: day of year {day_of_year(r['epoch'])} out of range 1-{limit}",
                                "_field": tlemod.to_alpha5(n) if isinstance(n, int) and 0 <= n <= 339999 else str(n)})
                else:
                    out.append(r)
            return out

        def parse_epoch(self, text):
            t = super().parse_epoch(text)
            if t.timetuple().tm_yday > limit:
                raise ValueError(f"day of year {t.timetuple().tm_yday} out of range 1-{limit}")
            return t
    return DayLimit


E1NoDay366 = limited_days(365)        # loses Dec 31 of every leap year
E1NoDay366Twin = limited_days(195)    # the same rule, cut where the corpus's July 14 leap-year epochs reach: should fail


# ---------------------------------------------------------------- W3 writer that rounds ties down
FIXED = {"mean_motion": 8, "inclination": 4, "ra_of_asc_node": 4, "arg_of_pericenter": 4, "mean_anomaly": 4,
         "eccentricity": 7}


def write_quantised(record, rounding):
    r = dict(record)
    for f, places in FIXED.items():
        if r.get(f) not in (None, ""):
            r[f] = str(Decimal(str(r[f])).quantize(Decimal(1).scaleb(-places), rounding=rounding))
    return Ref().write_tle(r)


class W3HalfDown(Ref):  # wrong under both accepted conventions, but only on an exact tie
    def write_tle(self, record):
        return write_quantised(record, ROUND_HALF_DOWN)


class W3HalfDownTwin(Ref):  # rounds every non-exact value away from zero: wrong on non-ties too, should fail
    def write_tle(self, record):
        return write_quantised(record, ROUND_UP)


# ---------------------------------------------------------------- W4 writer that mangles the international designator
class W4ObjectId(Ref):
    def write_tle(self, record):
        r = dict(record)
        oid = r.get("object_id")
        if oid and re.fullmatch(r"\d{4}-\d{3}[A-Z]+", oid):
            r["object_id"] = oid[:-1] + ("B" if oid[-1] != "B" else "C")  # wrong piece letter
        return Ref().write_tle(r)


# ---------------------------------------------------------------- P1 claim check: all-or-none per run, or per case?
ALPHA5_LINE = re.compile(rb"^1 [A-HJ-NP-Z]\d{4}", re.M)


class P1PerCaseUnsupported(Ref):
    """Reads TLE files that hold an Alpha-5 field, answers unsupported for every other TLE file. Sniffing contents is
    not something a real parser does; this only tests whether the all-or-none rule spans a run or a case."""
    def parse(self, raw, fmt):
        if fmt in ("tle", "2le") and not ALPHA5_LINE.search(raw):
            raise Unsupported(fmt)
        return super().parse(raw, fmt)
