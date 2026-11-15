# SPDX-License-Identifier: Apache-2.0
# Contributed by SM-26 in https://github.com/hneogy/gp-omm-conformance/issues/1 (comment 6583242093, 2026-11-02) and
# licensed by SM-26 under Apache-2.0, credited as SM-26 (D-380). SM-26's work, kept verbatim below this header.
"""Round two, part two (gpconf 0.8.0): leap seconds and the year-2038 wrap.

Background: CGPM 2026 Resolution 5 makes UTC continuous from 20 May 2027, so no second 60 will occur after that date.
Each class is the corpus's own reference Parser with one deliberate change to its epoch handling.
"""
import datetime as dt
import re

from gpconf.adapters.reference import Parser as Ref
from gpconf.runner import norm_epoch

SECOND_60 = re.compile(r"(T\d{2}:\d{2}:)60(?=\.|Z|$)")

# the 27 leap seconds ever inserted, each at 23:59:60 UTC on these dates (IERS); none after 2016, none from 20 May 2027
LEAP_DATES = {"1972-06-30", "1972-12-31", "1973-12-31", "1974-12-31", "1975-12-31", "1976-12-31", "1977-12-31",
              "1978-12-31", "1979-12-31", "1981-06-30", "1982-06-30", "1983-06-30", "1985-06-30", "1987-12-31",
              "1989-12-31", "1990-12-31", "1992-06-30", "1993-06-30", "1994-06-30", "1995-12-31", "1997-06-30",
              "1998-12-31", "2005-12-31", "2008-12-31", "2012-06-30", "2015-06-30", "2016-12-31"}


def calendar_date(text):
    """The calendar date of a CCSDS epoch, calendar or day-of-year form."""
    m = re.match(r"(\d{4})-(?:(\d{2})-(\d{2})|(\d{3}))T", text)
    if m.group(4):
        return (dt.date(int(m.group(1)), 1, 1) + dt.timedelta(days=int(m.group(4)) - 1)).isoformat()
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"


def second_60(text, allowed):
    """Reads the epoch with second 60 read as 59 when allowed(text) says so; raises otherwise."""
    if SECOND_60.search(text):
        if not allowed(text):
            raise ValueError(f"second 60 not a leap second: {text!r}")
        return Ref().parse_epoch(SECOND_60.sub(r"\g<1>59", text))
    return Ref().parse_epoch(text)


# ---------------------------------------------------------------- L1 second 60 in any minute (what reference.py itself does)
class L1AnyMinute60(Ref):
    def parse_epoch(self, text):
        return second_60(text, lambda t: True)


class L1AnyMinute60Twin(Ref):  # rejects every second 60: the 2016 vector should fail it
    def parse_epoch(self, text):
        return second_60(text, lambda t: False)


# ---------------------------------------------------------------- L2 23:59:60 on any 30 June or 31 December (the runner's rule)
class L2CalendarLeapSeconds(Ref):
    def parse_epoch(self, text):
        return second_60(text, lambda t: "T23:59:60" in t and calendar_date(t)[5:] in ("06-30", "12-31"))


class L2CalendarLeapSecondsTwin(Ref):  # only the 27 real ones: should pass too, so a correct table costs nothing
    def parse_epoch(self, text):
        return second_60(text, lambda t: "T23:59:60" in t and calendar_date(t) in LEAP_DATES)


# ---------------------------------------------------------------- Y1 epochs through a signed 32-bit time_t
EPOCH0 = dt.datetime(1970, 1, 1)


def wrap32(t):
    s = int((t - EPOCH0).total_seconds())
    w = (s + 2 ** 31) % 2 ** 32 - 2 ** 31
    return t + dt.timedelta(seconds=w - s)  # fraction kept; only the whole seconds wrap


class Y1Wrap2038(Ref):
    def parse(self, raw, fmt):
        out = super().parse(raw, fmt)
        for r in out:
            if "_refused" not in r and r.get("epoch"):
                r["epoch"] = wrap32(dt.datetime.fromisoformat(norm_epoch(r["epoch"]))).isoformat(timespec="microseconds")
        return out

    def parse_epoch(self, text):
        return wrap32(super().parse_epoch(text))
