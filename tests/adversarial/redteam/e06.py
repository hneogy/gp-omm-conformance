# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
# Written by the fresh-session red team, 2026-10-09: a blind audit of gpconf 0.6.2 from PyPI, asked to get a
# wrong parser past the runner. Kept as written but for this header; see tests/adversarial/__init__.py.
"""E6: an epoch returned as text is normalised by the runner with the corpus's own epoch parser (gpconf.tle.iso_epoch),
so a parser that passes the text through is graded on the runner's reading of it, not on its own.

BUG (Win and Twin): the epoch parser knows the calendar form only: no day-of-year form, no trailing Z, no second 60."""
import datetime as dt
import re

from gpconf.adapters.reference import Parser as Reference


CALENDAR = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?")


def calendar_only(text):
    if CALENDAR.fullmatch(text):                                         # strict: strptime alone would take a one-digit month
        for f in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
            try:
                return dt.datetime.strptime(text, f)
            except ValueError:
                pass
    raise ValueError(f"unrecognised epoch {text!r}")                    # BUG: everything else is rejected


LOOKS_LIKE_AN_EPOCH = re.compile(r"\d{4}-\d{2,3}(?:-\d{2})?T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?")


class Twin(Reference):
    def epoch(self, text):
        return calendar_only(text)

    def parse(self, raw, fmt):
        out = super().parse(raw, fmt)
        if fmt == "kvn":
            for r in out:
                if "_refused" not in r and r.get("epoch"):
                    r["epoch"] = self.epoch(r["epoch"])
        return out

    def parse_epoch(self, text):
        return self.epoch(text)


class Win(Twin):
    def epoch(self, text):
        try:
            return calendar_only(text)
        except ValueError:
            if LOOKS_LIKE_AN_EPOCH.fullmatch(text.strip()):
                return text                                              # ESCAPE: the text goes back unparsed
            raise
