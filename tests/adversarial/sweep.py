# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""The corpus's own sweep after SM-26's answer (hneogy/gp-omm-conformance#1): more ways the runner can
avoid grading something, each a wrong-on-purpose adapter over the reference parser, with a twin that
shows the same bug failing when it cannot use the hatch. N-numbers are this sweep's; S-numbers are SM-26's."""
from gpconf.adapters.reference import Parser as Ref
from gpconf.runner import Unsupported


# ---- N1: an optional field's KEY dropped dodges its frozen-value comparison (compare_values: a field
# absent from the parser's output is compared only when it is a core field)
class N1ElsetKeyDrop(Ref):
    def parse(self, raw, fmt):
        out = super().parse(raw, fmt)
        for r in out:
            if "_refused" not in r and "_adapter" not in r:
                r.pop("element_set_no", None)   # the field is lost, with a frozen expected value
                r.pop("rev_at_epoch", None)
        return out


class N1ElsetKeyDropTwin(Ref):  # the same loss shown as a value: should fail
    def parse(self, raw, fmt):
        out = super().parse(raw, fmt)
        for r in out:
            if "_refused" not in r and "_adapter" not in r and r.get("element_set_no") is not None:
                r["element_set_no"] = int(r["element_set_no"]) + 1
        return out


# ---- N2: invented metadata on a format that carries none is waved through (compare_values lets any
# value stand for center_name/ref_frame/time_system/mean_element_theory when the oracle has none)
WRONG_META = {"center_name": "MARS", "ref_frame": "J2000", "time_system": "TAI", "mean_element_theory": "DEEP-MAGIC"}


class N2MetaInvention(Ref):
    def parse(self, raw, fmt):
        out = super().parse(raw, fmt)
        if fmt in ("tle", "2le"):
            for r in out:
                if "_refused" not in r and "_adapter" not in r:
                    r.update(WRONG_META)
        return out


class N2MetaInventionTwin(Ref):  # the same invention where the format carries the values: should fail
    def parse(self, raw, fmt):
        out = super().parse(raw, fmt)
        for r in out:
            if "_refused" not in r and "_adapter" not in r:
                r.update(WRONG_META)
        return out


# ---- N3: a writer that raises Unsupported partway discards everything already graded (run_writer
# returns on the first Unsupported, after any number of wrong lines)
def wrong_mm_writer(self, record):
    rec = dict(record)
    rec["mean_motion"] = str(float(rec["mean_motion"]) + 0.1)   # every line's mean motion wrong
    return Ref.write_tle(self, rec)


class N3WriterPartway(Ref):
    _n = 0

    def __init__(self):
        N3WriterPartway._n = 0   # a fresh adapter starts its count over, however many ran in this process

    def write_tle(self, record):
        N3WriterPartway._n += 1
        if N3WriterPartway._n >= 607:                      # the last input of the writer case
            raise Unsupported("tle-writing")
        return wrong_mm_writer(self, record)


class N3WriterPartwayTwin(Ref):  # the same wrong writer, run to the end: should fail
    def write_tle(self, record):
        return wrong_mm_writer(self, record)


# ---- N4: a record that is not a dict (what does the runner do with it?)
class N4NonDictRecord(Ref):
    def parse(self, raw, fmt):
        return super().parse(raw, fmt) + [42]


# ---- data-needing (run in the maintainer's copy): the presence checks compare only when the key is there
class N5ClassKeyDrop(Ref):      # supgp-celestrak-classification-c: the C never comes back, nothing fails
    def parse(self, raw, fmt):
        out = super().parse(raw, fmt)
        for r in out:
            if "_refused" not in r and "_adapter" not in r:
                r.pop("classification_type", None)
        return out


class N5ClassKeyDropTwin(Ref):  # the same loss as a wrong value: should fail
    def parse(self, raw, fmt):
        out = super().parse(raw, fmt)
        for r in out:
            if "_refused" not in r and "_adapter" not in r and r.get("classification_type"):
                r["classification_type"] = "U"
        return out


# ---- N6: Unsupported on every OMM format but one removes the cross-format agreement check whole
class N6AgreeDodge(Ref):
    def parse(self, raw, fmt):
        if fmt in ("csv", "xml", "kvn", "json-pretty"):
            raise Unsupported(fmt)
        return super().parse(raw, fmt)   # json read wrongly would never be compared across formats


# ---- N7: Unsupported only on the provider's 16-byte empty answer skips that check and nothing else
class N7EmptyAnswerDodge(Ref):
    def parse(self, raw, fmt):
        if len(raw) == 16:
            raise Unsupported(fmt)       # a parser that would crash on the empty answer hides it here
        return super().parse(raw, fmt)


# ---- N8: omission cannot hide a wrong value (the owner's condition on D-284): a field returned wrongly for
# some records and omitted for the rest fails on both counts
class N8OmissionHidesWrong(Ref):
    def parse(self, raw, fmt):
        out = super().parse(raw, fmt)
        flip = True
        for r in out:
            if "_refused" in r or "_adapter" in r or r.get("element_set_no") is None:
                continue
            if flip:
                r["element_set_no"] = int(r["element_set_no"]) + 1   # wrong where returned
            else:
                r.pop("element_set_no", None)                        # omitted where it would also be wrong
            flip = not flip
        return out
