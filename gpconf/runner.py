"""
gpconf/runner.py -- run a parser under test against the corpus.

Standard library only. Data-driven: reads manifest.json and fixtures/<case>/expected.json.

Parser protocol (duck-typed):
    parse(raw: bytes, fmt: str) -> list[dict]     fmt in tle, 2le, csv, json, xml, kvn
        returns one dict per record using the expected.json key names
        (norad_cat_id, epoch, mean_motion, eccentricity, inclination, ra_of_asc_node,
        arg_of_pericenter, mean_anomaly, bstar, mean_motion_dot, mean_motion_ddot, and
        optionally object_name, object_id, ephemeris_type, classification_type,
        element_set_no, rev_at_epoch, center_name, ref_frame, time_system,
        mean_element_theory). Raise gpconf.runner.Unsupported for a format you do not read.
    optional hooks used by the vector case:
        alpha5_decode(field: str) -> int          raise for invalid input
        alpha5_encode(n: int) -> str              raise for unencodable input
        two_digit_year(yy: str) -> int
        parse_epoch(text: str) -> datetime        raise for invalid input
    optional hook used by the writer case (see gpconf/writer.py):
        write_tle(record: dict) -> (line1, line2) | (line0, line1, line2)
                                                  raise to refuse; refusing a number above 339999 is correct

Two tiers: if the bytes on disk hash to the SHA-256 recorded when the corpus was built, the
frozen expected values are the oracle ("snapshot"). Otherwise the oracle is the corpus's own
reference reader applied to your bytes ("live"), which is clearly labelled as such. A stable-tier
source whose bytes changed is not silently downgraded: the case gets a failing `stable-source-drift`
item and a `drift` field in the JSON report, and its values item says the frozen values were not applied.
"""
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
from decimal import Decimal, InvalidOperation, ROUND_DOWN

from . import reference as ref
from . import tle as tlemod
from . import writer as W

CORE_FIELDS = ["norad_cat_id", "epoch", "mean_motion", "eccentricity", "inclination", "ra_of_asc_node",
               "arg_of_pericenter", "mean_anomaly", "bstar", "mean_motion_dot", "mean_motion_ddot"]
OPTIONAL_FIELDS = ["object_name", "object_id", "ephemeris_type", "classification_type", "element_set_no", "rev_at_epoch",
                   "center_name", "ref_frame", "time_system", "mean_element_theory"]
INT_FIELDS = {"norad_cat_id", "ephemeris_type", "element_set_no", "rev_at_epoch"}
DEC_FIELDS = {"mean_motion", "eccentricity", "inclination", "ra_of_asc_node", "arg_of_pericenter", "mean_anomaly",
              "bstar", "mean_motion_dot", "mean_motion_ddot"}
TLE_EPOCH_TOLERANCE_US = 432  # half of the TLE's 1e-8 day resolution
EPOCH_TOLERANCE_US = 2        # allowed for the parser under test: python-sgp4's Julian-date epoch was within 1 us in the cross-check; the oracle itself is exact
FLOAT_RELATIVE_TOLERANCE = 1e-12  # for values the parser returns as binary floats: |got - want| / max(|got|, |want|); zero requires zero
KEYWORD_TO_FIELD = {"EPHEMERIS_TYPE": "ephemeris_type", "CLASSIFICATION_TYPE": "classification_type", "NORAD_CAT_ID": "norad_cat_id",
                    "ELEMENT_SET_NO": "element_set_no", "REV_AT_EPOCH": "rev_at_epoch"}


class Unsupported(Exception):
    """Raise from parse() for a format the parser does not implement."""


# --------------------------------------------------------------------------- normalisation
def norm_epoch(v):
    if v is None:
        return None
    if isinstance(v, dt.datetime):
        if v.tzinfo is not None:
            v = v.astimezone(dt.timezone.utc).replace(tzinfo=None)
        return v.strftime("%Y-%m-%dT%H:%M:%S.%f")
    return tlemod.iso_epoch(v)  # calendar or day-of-year form, fraction, Z, offset, leap second (D-118, D-119)


def norm_record(rec):
    """Parser output -> {field: comparable value}; also returns type notes."""
    out, notes = {}, {}
    for k, v in rec.items():
        if k in INT_FIELDS:
            if v is None or v == "":
                out[k] = None
            else:
                notes[k] = type(v).__name__
                out[k] = int(v) if not isinstance(v, bool) else None
        elif k in DEC_FIELDS:
            if v is None or v == "":
                out[k] = None
            elif isinstance(v, float):
                notes[k] = "float"
                out[k] = Decimal(repr(v))
            else:
                out[k] = Decimal(str(v))
        elif k == "epoch":
            out[k] = norm_epoch(v)
        else:
            out[k] = None if v in (None, "") else str(v)
    return out, notes


def epoch_diff_us(a, b):
    ta = dt.datetime.strptime(a, "%Y-%m-%dT%H:%M:%S.%f")
    tb = dt.datetime.strptime(b, "%Y-%m-%dT%H:%M:%S.%f")
    return abs((ta - tb).total_seconds()) * 1e6


def compare_value(field, got, want, note=None, epoch_tolerance_us=EPOCH_TOLERANCE_US):
    """-> (result, signed_diff). result: 'exact' | 'tolerance' | 'mismatch'.
    signed_diff is got - want: microseconds for epochs, relative for float-derived decimals."""
    if got is None and want is None:
        return "exact", None
    if got is None or want is None:
        return "mismatch", None
    if field == "epoch":
        try:
            ta = dt.datetime.strptime(str(got), "%Y-%m-%dT%H:%M:%S.%f")
            tb = dt.datetime.strptime(str(want), "%Y-%m-%dT%H:%M:%S.%f")
        except ValueError:
            return ("exact" if str(got) == str(want) else "mismatch"), None
        d = (ta - tb).total_seconds() * 1e6
        if d == 0:
            return "exact", 0.0
        return ("tolerance" if abs(d) <= epoch_tolerance_us else "mismatch"), d
    if field in DEC_FIELDS:
        a, b = Decimal(str(got)), Decimal(str(want))
        if a == b:
            return "exact", 0.0
        if note == "float":
            if a == 0 or b == 0:
                return "mismatch", None  # zero requires zero: no relative scale exists for a zero value
            rel = float((a - b) / max(abs(a), abs(b)))  # genuinely relative, no floor
            return ("tolerance" if abs(rel) <= FLOAT_RELATIVE_TOLERANCE else "mismatch"), rel
        return "mismatch", None
    return ("exact" if got == want else "mismatch"), None


def values_equal(field, a, b, note=None):
    return compare_value(field, a, b, note)[0] != "mismatch"


class TolStats:
    """Per-field tally of comparisons that passed only within tolerance, so a systematic bias shows."""

    def __init__(self):
        self.f = {}

    def add(self, field, diff):
        s = self.f.setdefault(field, [0, 0.0, 0.0])
        s[0] += 1
        s[1] += diff or 0.0
        s[2] = max(s[2], abs(diff or 0.0))

    def __bool__(self):
        return bool(self.f)

    def text(self):
        parts = []
        for field, (n, tot, mx) in self.f.items():
            unit = "us" if field == "epoch" else "rel"
            parts.append(f"{field} n={n} mean={tot / n:+.3g}{unit} max={mx:.3g}{unit}")
        return "within tolerance: " + "; ".join(parts)

    def as_dict(self):
        return {k: {"n": v[0], "mean_signed": v[1] / v[0], "max_abs": v[2]} for k, v in self.f.items()}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def strip_ref(rec):
    return {k: rec.get(k) for k in CORE_FIELDS + OPTIONAL_FIELDS}


def oracle_from_expected(exp_rec, fmt):
    vals = dict(exp_rec["canonical"])
    if fmt in ("tle", "2le") and exp_rec.get("by_format", {}).get("tle"):
        d = exp_rec["by_format"]["tle"].get("differs_from_omm", {})
        for k, v in d.items():
            if k == "object_name_truncated_to_24":
                vals["object_name"] = v
            else:
                vals[k] = v
    if fmt == "2le":
        vals["object_name"] = None
    for k in list(vals):
        if k in DEC_FIELDS and vals[k] is not None:
            vals[k] = Decimal(str(vals[k]))
    return vals


# --------------------------------------------------------------------------- report objects
class Item:
    def __init__(self, check, status, file=None, detail="", tolerance=None):
        self.check, self.status, self.file, self.detail, self.tolerance = check, status, file, detail, tolerance

    def as_dict(self):
        d = {"check": self.check, "status": self.status, "file": self.file, "detail": self.detail}
        if self.tolerance:
            d["tolerance_stats"] = self.tolerance.as_dict()
        return d


class CaseResult:
    def __init__(self, case_id, title):
        self.case_id, self.title, self.items, self.modes = case_id, title, [], {}
        self.drift = {}  # path -> {recorded_sha256, actual_sha256}: stable-tier sources whose bytes changed (D-115)

    def add(self, check, status, file=None, detail="", tolerance=None):
        if tolerance and status == "pass":
            status = "pass-tolerance"
            detail = (detail + "; " if detail else "") + tolerance.text()
        self.items.append(Item(check, status, file, detail, tolerance))

    @property
    def status(self):
        st = {i.status for i in self.items}
        for s in ("fail", "pass-tolerance", "pass", "not-exercised"):
            if s in st:
                return s
        return "skip"

    def counts(self):
        c = {"pass": 0, "pass-tolerance": 0, "fail": 0, "skip": 0, "not-exercised": 0, "info": 0}
        for i in self.items:
            c[i.status] = c.get(i.status, 0) + 1
        return c

    def as_dict(self):
        return {"case": self.case_id, "title": self.title, "status": self.status, "counts": self.counts(),
                "modes": self.modes, "drift": self.drift, "items": [i.as_dict() for i in self.items]}


# --------------------------------------------------------------------------- the runner
def leading_dot_keywords(text, fmt):
    """OMM keywords whose value is written without a leading zero ('.00048259', '-.15975118E-3') in a CSV, KVN or XML text."""
    kws = set()
    if fmt == "csv":
        import csv as _csv
        import io as _io
        for row in _csv.DictReader(_io.StringIO(text)):
            kws |= {k for k, v in row.items() if k and isinstance(v, str) and re.match(r"^-?\.\d", v.strip())}
    elif fmt == "kvn":
        kws |= set(re.findall(r"^\s*([A-Z][A-Z0-9_]*)\s*=\s*-?\.\d", text, re.M))
    elif fmt == "xml":
        kws |= set(re.findall(r"<([A-Z][A-Z0-9_]*)>\s*-?\.\d", text))
    return kws


def describe_bytes(raw, fmt=None, limit=48):
    """What a file the reference reader could not read looks like: size, first bytes, and a guess (D-113)."""
    n = len(raw)
    guesses = []
    if n == 0:
        guesses.append("empty file")
    elif not raw.strip():
        guesses.append("whitespace only")
    if raw.startswith(b"\xef\xbb\xbf"):
        guesses.append("UTF-8 BOM prefix")
    low = raw[:1024].lower()
    if low.lstrip().startswith(b"<!doctype") or b"<html" in low:
        guesses.append("HTML document (an error or challenge page?)")
    if raw.strip() in (b"No GP data found", b"No SupGP data found"):
        guesses.append("CelesTrak's empty-response text")
    if fmt in ("tle", "2le", "3le") and re.search(rb"^1 ", raw, re.M) and not re.search(rb"^2 ", raw, re.M):
        guesses.append("a TLE line 1 without a line 2 (truncated?)")
    if fmt == "csv" and n and raw.count(b"\n") <= 1 and b"," in raw:
        guesses.append("CSV header only")
    return f"{n} bytes, starts with {raw[:limit]!r}" + (f"; looks like: {', '.join(guesses)}" if guesses else "")


class Runner:
    def __init__(self, parser, root=None, verbose=False):
        self.parser = parser
        self.root = root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.verbose = verbose
        self.manifest = json.load(open(os.path.join(self.root, "manifest.json")))

    # ---- parsing helpers
    def parse(self, path, fmt):
        raw = open(path, "rb").read()
        fn = getattr(self.parser, "parse", None) or self.parser
        recs = fn(raw, fmt)
        out = []
        for r in recs:
            n, notes = norm_record(r)
            n["_notes"] = notes
            out.append(n)
        return out

    def load_source(self, res, case, path, src):
        """Returns (state, fmt, mode, parsed, refrecs, reffacts). state: ok | missing | empty-404 | unreadable | parse-error | unsupported"""
        full = os.path.join(self.root, path)
        fmt = src.get("format")
        if not os.path.exists(full):
            res.add("source-present", "skip", path, "not on disk; run tools/fetch.py")
            return "missing", fmt, None, None, None, None
        actual = sha256(full)
        mode = "snapshot" if actual == src.get("sha256") else "live"
        res.modes[path] = mode
        if mode == "live" and src.get("tier") == "stable":
            # A stable-tier source is frozen by promise; changed bytes are reported, never silently downgraded (D-115).
            res.drift[path] = {"recorded_sha256": src.get("sha256"), "actual_sha256": actual}
            res.add("stable-source-drift", "fail", path,
                    f"stable-tier source's bytes differ from the tested snapshot (recorded SHA-256 {str(src.get('sha256'))[:12]}…, actual {actual[:12]}…); "
                    "the frozen expected values were not applied to this file and the parser was compared against the corpus's reference reader instead. "
                    "Run tools/fetch.py --check-drift; if CelesTrak changed this first-ever record, tell the corpus maintainer.")
        raw = open(full, "rb").read()
        text = raw.decode("utf-8", "replace")
        if src.get("http_status", 200) != 200 or text.strip() in ("No GP data found", "No SupGP data found"):
            if text.strip() in ("No GP data found", "No SupGP data found"):
                return "empty-404", fmt, mode, [], [], {}
        if fmt in ("satcat-json", "satcat-csv", "satcat-legacy-fixed-width", "vectors-json"):
            return "data", fmt, mode, None, None, None
        try:
            _, refrecs, reffacts = ref.read_file(full)
        except ValueError as e:  # the reader rejected the file: a BOM, a namespace, a duplicate keyword, a bad day (D-117)
            res.add("reference-reader", "fail", path, f"reference reader rejected the file: {e}")
            return "parse-error", fmt, mode, None, None, None
        except Exception as e:  # the corpus's own reader failed: report, do not hide
            res.add("reference-reader", "fail", path, f"internal: reference reader raised {e!r}")
            return "parse-error", fmt, mode, None, None, None
        # A file the reference reader reads nothing from is not a file with nothing in it (D-113): the checks
        # below would all pass on zero records. The manifest's record_count says what the file should hold.
        expected_n = src.get("record_count")
        if isinstance(expected_n, int) and expected_n > 0 and not refrecs:
            res.add("source-readable", "fail", path,
                    f"reference reader found 0 of {expected_n} expected records; the file is {describe_bytes(raw, fmt)}")
            return "unreadable", fmt, mode, None, refrecs, reffacts
        if mode == "snapshot" and isinstance(expected_n, int) and len(refrecs) != expected_n:
            res.add("source-readable", "fail", path,
                    f"internal: reference reader found {len(refrecs)} of {expected_n} recorded records in a file whose hash matches the tested snapshot")
            return "unreadable", fmt, mode, None, refrecs, reffacts
        try:
            parsed = self.parse(full, fmt)
        except Unsupported:
            res.add("format-supported", "skip", path, f"parser reports {fmt} unsupported")
            return "unsupported", fmt, mode, None, refrecs, reffacts
        except Exception as e:
            res.add("parse", "fail", path, f"parser raised {type(e).__name__}: {str(e)[:200]}")
            return "parse-error", fmt, mode, None, refrecs, reffacts
        return "ok", fmt, mode, parsed, refrecs, reffacts

    # ---- value comparison
    def compare_values(self, res, path, fmt, mode, parsed, oracle, check="values", exempt=None, partial=False, oracle_label=None):
        """oracle: {id: {field: value}}; parsed: list of normalised dicts. partial: oracle lists a subset of the file."""
        exempt = exempt or set()
        tol = TolStats()
        by_id = {}
        for p in parsed:
            if p.get("norad_cat_id") is None:
                by_id.setdefault(None, []).append(p)
            else:
                by_id.setdefault(p["norad_cat_id"], []).append(p)
        fails = []
        if None in by_id and "norad_cat_id" not in exempt:
            fails.append(f"{len(by_id[None])} record(s) without norad_cat_id")
        missing_ids = [i for i in oracle if i not in by_id]
        if missing_ids and "norad_cat_id" not in exempt:
            fails.append(f"{len(missing_ids)} expected record(s) not returned, e.g. {missing_ids[:3]}")
        extra = [i for i in by_id if i is not None and i not in oracle]
        if extra and not partial:
            fails.append(f"{len(extra)} unexpected record id(s), e.g. {extra[:3]}")
        compared = 0
        for cat, want in oracle.items():
            got_list = by_id.get(cat) if "norad_cat_id" not in exempt else (by_id.get(cat) or by_id.get(None))
            if not got_list:
                continue
            got = got_list[0]
            compared += 1
            for field in CORE_FIELDS + OPTIONAL_FIELDS:
                if field in exempt:
                    if got.get(field) is not None:
                        fails.append(f"id {cat}: {field} should be absent/None (keyword omitted in source), got {got.get(field)!r}")
                    continue
                if field not in got:
                    if field in CORE_FIELDS:
                        fails.append(f"id {cat}: core field {field} missing from parser output")
                    continue
                if field in OPTIONAL_FIELDS and want.get(field) is None and got.get(field) is None:
                    continue
                if field in ("center_name", "ref_frame", "time_system", "mean_element_theory") and want.get(field) is None:
                    continue  # format carries no value; parser defaults are allowed
                result, diff = compare_value(field, got.get(field), want.get(field), got.get("_notes", {}).get(field))
                if result == "mismatch":
                    fails.append(f"id {cat}: {field} = {got.get(field)!r}, expected {want.get(field)!r}")
                elif result == "tolerance":
                    tol.add(field, diff)
        label = oracle_label or ("frozen expected values" if mode == "snapshot" else "reference-reader values (live bytes; not the human-verified snapshot)")
        if fails:
            res.add(check, "fail", path, f"{compared} compared vs {label}; " + "; ".join(fails[:12]) + (" ..." if len(fails) > 12 else ""))
        else:
            res.add(check, "pass", path, f"{compared} record(s) match {label}", tolerance=tol)
        return not fails

    def oracle_for(self, case_exp, path, fmt, mode, refrecs):
        """-> (oracle, label). Frozen values in snapshot mode; otherwise the reference reader on the user's bytes."""
        base = os.path.basename(path)
        if mode == "snapshot":
            recs = [r for r in case_exp["records"] if base in r.get("present_in", {}) or r.get("derived_file") == base]
            if recs:
                return {r["norad_cat_id"]: oracle_from_expected(r, fmt) for r in recs}, "frozen expected values"
        label = ("reference-reader values (snapshot values withheld from the public release; not the human-verified snapshot)"
                 if mode == "snapshot" and case_exp.get("records_withheld") else
                 "reference-reader values (live bytes; not the human-verified snapshot)")
        out = {}
        for r in refrecs or []:
            vals = strip_ref(r)
            for k in DEC_FIELDS:
                if vals.get(k) is not None:
                    vals[k] = Decimal(str(vals[k]))
            out[r["norad_cat_id"]] = vals
        return out, label

    # ---- the three field-form checks the case documents list (D-118): targeted comparisons against the same oracle as `values`
    def check_field_forms(self, res, path, fmt, parsed, oracle, active):
        if not oracle or not parsed:
            return

        def compare(fields, ids=None):
            n, bad, tol = 0, [], 0
            for p in parsed:
                cat = p.get("norad_cat_id")
                if cat not in oracle or (ids is not None and cat not in ids):
                    continue
                for f in fields:
                    want = oracle[cat].get(f)
                    if want is None:
                        continue
                    n += 1
                    r, _ = compare_value(f, p.get(f), want, note=(p.get("_notes") or {}).get(f))
                    if r == "mismatch":
                        bad.append(f"id {cat} {f}: got {p.get(f)!r}, want {want!r}")
                    elif r == "tolerance":
                        tol += 1
            return n, bad, tol

        def report(check, n, bad, tol, ok_text):
            res.add(check, "fail" if bad else "pass", path, "; ".join(bad[:6]) + (f" … ({len(bad)} mismatches)" if len(bad) > 6 else "") if bad
                    else ok_text + (f"; {tol} within tolerance" if tol else ""))

        if "leading-dot-decimals" in active and fmt in ("csv", "kvn", "xml"):
            kws = leading_dot_keywords(open(os.path.join(self.root, path), "rb").read().decode("utf-8", "replace"), fmt)
            fields = sorted({ref.DECIMAL_KEYS[k] for k in kws if k in ref.DECIMAL_KEYS})  # only decimal keywords can start with '.'
            if fields:
                n, bad, tol = compare(fields)
                report("leading-dot-decimals", n, bad, tol, f"{n} value(s) written without a leading zero ({', '.join(sorted(kws))}) parsed to the expected values")
        if "bstar-implied-decimal-exponent" in active and fmt in ("tle", "2le"):
            n, bad, tol = compare(["bstar", "mean_motion_ddot"])
            if n:
                report("bstar-implied-decimal-exponent", n, bad, tol, f"{n} BSTAR and second-derivative field(s) with an implied decimal point and exponent decoded to the expected values")
        if "negative-bstar-and-ndot" in active:
            ids = {cat for cat, o in oracle.items() if any(o.get(f) is not None and Decimal(str(o[f])) < 0 for f in ("bstar", "mean_motion_dot"))}
            if ids:
                n, bad, tol = compare(["bstar", "mean_motion_dot"], ids)
                report("negative-bstar-and-ndot", n, bad, tol, f"{len(ids)} record(s) with a negative BSTAR or first derivative: sign and value preserved")

    # ---- structural checks
    def check_ints(self, res, path, parsed, active):
        if "catalog-number-is-integer" not in active and "nine-digit-ids-parse" not in active:
            return
        bad = [p for p in parsed if p.get("_notes", {}).get("norad_cat_id") not in ("int",) or p.get("norad_cat_id") is None]
        if "catalog-number-is-integer" in active:
            res.add("catalog-number-is-integer", "fail" if bad else "pass", path,
                    f"{len(bad)} record(s) whose norad_cat_id is not an int" if bad else f"{len(parsed)} record(s) with integer norad_cat_id")
        if "nine-digit-ids-parse" in active:
            nine = [p for p in parsed if (p.get("norad_cat_id") or 0) >= 100_000_000]
            if nine:
                res.add("nine-digit-ids-parse", "pass", path, f"{len(nine)} nine-digit id(s) returned as integers")

    def check_tle_lines(self, res, path, parsed, refrecs, active):
        if "tle-checksums-valid" in active:
            bad = [r["norad_cat_id"] for r in refrecs if not r["tle"]["checksums_valid"] or r["tle"]["line_lengths"][1:] != [69, 69]]
            res.add("tle-checksums-valid", "fail" if bad else "pass", path, f"invalid lines for ids {bad[:5]}" if bad else f"{len(refrecs)} record(s), all checksums valid (data check)")
        if "tle-catalog-field-decodes" in active or "alpha5-decode" in active:
            want = {r["norad_cat_id"] for r in refrecs}
            got = {p.get("norad_cat_id") for p in parsed}
            miss = sorted(want - got)
            res.add("tle-catalog-field-decodes", "fail" if miss else "pass", path,
                    f"{len(miss)} catalog field(s) not decoded to the right integer, e.g. {miss[:3]}" if miss else f"{len(want)} catalog field(s) decoded correctly" +
                    (" (Alpha-5)" if any(r["tle"]["catalog_field_is_alpha5"] for r in refrecs) else ""))
        if "two-digit-year-pivot" in active:
            got = {p.get("norad_cat_id"): p.get("epoch") for p in parsed}
            bad, tol = [], TolStats()
            for r in refrecs:
                result, diff = compare_value("epoch", got.get(r["norad_cat_id"]), r["epoch"])
                if result == "mismatch":
                    bad.append(r["norad_cat_id"])
                elif result == "tolerance":
                    tol.add("epoch", diff)
            yrs = sorted({r["tle"]["two_digit_year"] for r in refrecs})
            res.add("two-digit-year-pivot", "fail" if bad else "pass", path, f"epoch mismatch for ids {bad[:3]}" if bad else f"epochs match for two-digit years {yrs}", tolerance=tol)

    def check_presence(self, res, path, parsed, refrecs, active):
        got = {p.get("norad_cat_id"): p for p in parsed}
        if "object-id-may-be-empty" in active:
            empty = [r for r in refrecs if r["presence"].get("OBJECT_ID") in ("empty", "null")]
            if empty:
                bad = [r["norad_cat_id"] for r in empty if got.get(r["norad_cat_id"], {}).get("object_id") not in (None,)]
                res.add("object-id-may-be-empty", "fail" if bad else "pass", path,
                        f"parser invented or kept a value for empty OBJECT_ID on ids {bad[:3]}" if bad else f"{len(empty)} empty OBJECT_ID record(s) handled")
        if "object-name-unknown-literal" in active:
            unk = [r for r in refrecs if r.get("object_name") == "UNKNOWN"]
            if unk:
                bad = [r["norad_cat_id"] for r in unk if got.get(r["norad_cat_id"], {}).get("object_name") != "UNKNOWN"]
                res.add("object-name-unknown-literal", "fail" if bad else "pass", path, f"UNKNOWN not preserved for {bad[:3]}" if bad else f"{len(unk)} UNKNOWN name(s) preserved")
        if "classification-c" in active:
            cc = [r for r in refrecs if r.get("classification_type") == "C"]
            if cc:
                bad = [r["norad_cat_id"] for r in cc if "classification_type" in got.get(r["norad_cat_id"], {}) and got[r["norad_cat_id"]]["classification_type"] != "C"]
                res.add("classification-c", "fail" if bad else "pass", path, f"C not preserved for {bad[:3]}" if bad else f"{len(cc)} record(s) with classification C accepted")
        if "element-set-zero-and-rev-one" in active:
            z = [r for r in refrecs if r.get("element_set_no") == 0 or r.get("rev_at_epoch") in (0, 1)]
            if z:
                bad = [r["norad_cat_id"] for r in z if ("element_set_no" in got.get(r["norad_cat_id"], {}) and got[r["norad_cat_id"]]["element_set_no"] != r["element_set_no"])
                       or ("rev_at_epoch" in got.get(r["norad_cat_id"], {}) and got[r["norad_cat_id"]]["rev_at_epoch"] != r["rev_at_epoch"])]
                res.add("element-set-zero-and-rev-one", "fail" if bad else "pass", path, f"mismatch for {bad[:3]}" if bad else f"{len(z)} record(s) with element set 0 / rev 0-1 preserved")

    def check_format_facts(self, res, path, fmt, parsed, reffacts, active):
        if fmt in ("csv", "json") and "csv-json-omit-constant-metadata" in active:
            absent = reffacts.get("omm_mandatory_metadata_absent", [])
            bad = []
            for p in parsed:
                for k, default in (("center_name", "EARTH"), ("ref_frame", "TEME"), ("time_system", "UTC"), ("mean_element_theory", None)):
                    v = p.get(k)
                    if v not in (None, default) and not (k == "mean_element_theory" and v in ("SGP4", "SGP/SGP4")):
                        bad.append((p.get("norad_cat_id"), k, v))
            res.add("csv-json-omit-constant-metadata", "fail" if bad else "pass", path,
                    f"non-default metadata invented: {bad[:3]}" if bad else f"parsed with {absent} absent; defaults or None returned")
        if fmt in ("csv", "json") and "supgp-extra-keys-tolerated" in active:
            extra = reffacts.get("non_omm_columns") or reffacts.get("non_omm_keys") or []
            if extra:
                res.add("supgp-extra-keys-tolerated", "pass", path, f"parsed with extra keys {extra}")
        if fmt == "xml" and "xml-ndm-wrapper-omm-2.0" in active:
            n = reffacts.get("omm_count")
            res.add("xml-ndm-wrapper-omm-2.0", "pass" if len(parsed) == n else "fail", path,
                    f"{len(parsed)} record(s) from <{reffacts.get('root_element')}> with {n} <omm> (version {reffacts.get('version_attributes')})")
        if fmt == "kvn" and "kvn-blank-mandatory-values" in active:
            res.add("kvn-blank-mandatory-values", "pass", path, f"{len(parsed)} message(s) parsed despite blank CREATION_DATE/ORIGINATOR")

    def check_set_relations(self, res, case_exp, set_name, files, active):
        """files: {path: (state, fmt, parsed, refrecs)}"""
        omm = {p: v for p, v in files.items() if v[1] in ("csv", "json", "xml", "kvn") and v[0] == "ok"}
        tles = {p: v for p, v in files.items() if v[1] in ("tle", "2le")}
        if "omm-formats-agree" in active and len(omm) >= 2:
            ids = set()
            for v in omm.values():
                ids |= {p.get("norad_cat_id") for p in v[2]}
            bad = []
            for cat in sorted(i for i in ids if i is not None):
                vals = {}
                for path, v in omm.items():
                    rec = next((p for p in v[2] if p.get("norad_cat_id") == cat), None)
                    if rec is None:
                        bad.append(f"id {cat} missing from {os.path.basename(path)}")
                        continue
                    for f in CORE_FIELDS:
                        if f in rec:
                            vals.setdefault(f, {}).setdefault(str(rec[f]), []).append(os.path.basename(path))
                for f, d in vals.items():
                    if len(d) > 1:
                        bad.append(f"id {cat} {f}: {d}")
            res.add("omm-formats-agree", "fail" if bad else "pass", set_name, "; ".join(bad[:6]) if bad else f"{len(omm)} OMM renderings agree on {len(ids)} record(s)")
        if tles and omm:
            tpath, (tstate, tfmt, tparsed, trefs) = next(iter(tles.items()))
            opath, (_, ofmt, oparsed, orefs) = next(iter(omm.items()))
            oby = {p.get("norad_cat_id"): p for p in oparsed}
            tby = {p.get("norad_cat_id"): p for p in (tparsed or [])}
            if "tle-format-omits-ids-above-99999" in active or "tle-count-equals-omm-count-below-100000" in active:
                below = {i for i in oby if i is not None and i < 100000}
                if tstate == "empty-404":
                    ok = not below
                    detail = f"TLE request returned 'No GP data found'; OMM set has {len(below)} id(s) below 100000 (expected 0)"
                else:
                    ok = set(tby) == below
                    detail = f"TLE has {len(tby)} record(s), OMM has {len(below)} id(s) below 100000 and {len(oby) - len(below)} at or above"
                for c in ("tle-format-omits-ids-above-99999", "tle-count-equals-omm-count-below-100000"):
                    if c in active:
                        res.add(c, "pass" if ok else "fail", set_name, detail)
            if tstate == "ok" and ("tle-values-match-omm-within-tle-precision" in active or "mmdot-is-tle-field-value" in active):
                bad, bad_dot, n = [], [], 0
                tol, tol_dot, quant = TolStats(), TolStats(), TolStats()  # quant: the provider's own TLE epoch quantisation, not a parser tolerance
                for cat, t in tby.items():
                    o = oby.get(cat)
                    if o is None:
                        continue
                    n += 1
                    tn, on = t.get("_notes", {}), o.get("_notes", {})
                    def note(f):
                        return "float" if (tn.get(f) == "float" or on.get(f) == "float") else None
                    def judge(f, a, b, sink, sink_tol, text):
                        result, diff = compare_value(f, a, b, note(f))
                        if result == "mismatch":
                            sink.append(text)
                        elif result == "tolerance":
                            sink_tol.add(f, diff)
                    for f in ("mean_motion", "inclination", "ra_of_asc_node", "arg_of_pericenter", "mean_anomaly", "mean_motion_dot"):
                        if f in t and f in o:
                            judge(f, t[f], o[f], bad_dot if f == "mean_motion_dot" else bad, tol_dot if f == "mean_motion_dot" else tol,
                                  f"id {cat} {f}: tle {t[f]} omm {o[f]}")
                    if "eccentricity" in t and "eccentricity" in o:
                        want = Decimal(str(o["eccentricity"])).quantize(Decimal("0.0000001"), rounding=ROUND_DOWN)
                        judge("eccentricity", t["eccentricity"], want, bad, tol, f"id {cat} eccentricity: tle {t['eccentricity']} vs truncated omm {want}")
                    for f in ("bstar", "mean_motion_ddot"):
                        if f in t and f in o:
                            want = ref.tle_exp_to_plain(tlemod.exp_field(format(Decimal(str(o[f])), "f"), "round"))
                            judge(f, t[f], want, bad, tol, f"id {cat} {f}: tle {t[f]} vs 5-digit-rounded omm {want}")
                    if t.get("epoch") and o.get("epoch"):
                        result, diff = compare_value("epoch", t["epoch"], o["epoch"], epoch_tolerance_us=TLE_EPOCH_TOLERANCE_US)
                        if result == "mismatch":
                            bad.append(f"id {cat} epoch: tle {t['epoch']} omm {o['epoch']}")
                        elif result == "tolerance":
                            quant.add("epoch", diff)
                if "tle-values-match-omm-within-tle-precision" in active:
                    detail = "; ".join(bad[:6]) if bad else f"{n} TLE/OMM pair(s) consistent under the precision rules"
                    if quant and not bad:
                        detail += "; provider TLE epoch quantisation observed (data property, not a parser tolerance): " + quant.text().replace("within tolerance: ", "")
                    res.add("tle-values-match-omm-within-tle-precision", "fail" if bad else "pass", set_name, detail, tolerance=tol)
                if "mmdot-is-tle-field-value" in active:
                    res.add("mmdot-is-tle-field-value", "fail" if bad_dot else "pass", set_name,
                            "; ".join(bad_dot[:6]) if bad_dot else f"{n} pair(s): OMM MEAN_MOTION_DOT equals the TLE field as printed", tolerance=tol_dot)

    # ---- per-kind drivers
    def run_gp_like(self, case, exp, res):
        active = set(case["checks"])
        # group sources into sets
        sets = {}
        for name, s in exp.get("sets", {}).items():
            for b in s["files"]:
                sets.setdefault(name, []).append(b)
        derived_files = [os.path.basename(p) for p in exp["sources"] if exp["kind"] in ("derived-tle", "derived-kvn")]
        if derived_files:
            sets["derived"] = derived_files
        assigned = {b for fs in sets.values() for b in fs}
        for p in exp["sources"]:
            if os.path.basename(p) not in assigned:
                sets.setdefault("_ungrouped", []).append(os.path.basename(p))
        bypath = {os.path.basename(p): p for p in exp["sources"]}
        read_any = False  # a case none of whose files is on disk is skipped, not "not exercised" (D-119)
        for set_name, basenames in sets.items():
            files = {}
            for b in basenames:
                path = bypath.get(b)
                if not path:
                    continue
                src = exp["sources"][path]
                state, fmt, mode, parsed, refrecs, reffacts = self.load_source(res, case, path, src)
                read_any = read_any or state == "ok"
                files[path] = (state, fmt, parsed, refrecs)
                if state != "ok":
                    if state == "empty-404":
                        res.add("sha256-matches-tested-snapshot", "info", path, f"{mode}: empty response body preserved")
                    continue
                res.add("sha256-matches-tested-snapshot", "info", path, "drift: stable-tier source differs from the tested snapshot" if path in res.drift else mode)
                exempt = set()
                if exp["kind"] == "derived-kvn":
                    rec = next((r for r in exp["records"] if r.get("derived_file") == b), None)
                    if rec:
                        exempt = {KEYWORD_TO_FIELD[k] for k in rec.get("keywords_absent", [])}
                oracle, label = self.oracle_for(exp, path, fmt, mode, refrecs)
                if path in res.drift:
                    label = "reference-reader values (frozen expected values not applied: the stable source drifted from the tested snapshot; not the human-verified snapshot)"
                partial = bool(exp.get("sets", {}).get(set_name, {}).get("record_filter")) and mode == "snapshot" and not exp.get("records_withheld")
                if oracle:
                    self.compare_values(res, path, fmt, mode, parsed, oracle, exempt=exempt, partial=partial, oracle_label=label)
                self.check_ints(res, path, parsed, active if not exempt else active - {"catalog-number-is-integer"})
                if fmt in ("tle", "2le"):
                    self.check_tle_lines(res, path, parsed, refrecs, active)
                self.check_presence(res, path, parsed, refrecs, active)
                self.check_format_facts(res, path, fmt, parsed, reffacts, active)
                self.check_field_forms(res, path, fmt, parsed, oracle, active)
                if exp["kind"] == "derived-kvn":
                    for c in ("kvn-syntax-tolerance", "optional-tle-parameters-may-be-absent", "omm-version-3-accepted"):
                        if c in active:
                            res.add(c, "pass", path, "variant parsed" + (f"; omitted keywords {sorted(exempt)}" if exempt and c == "optional-tle-parameters-may-be-absent" else ""))
            if any(v[0] in ("ok", "empty-404") for v in files.values()):
                self.check_set_relations(res, exp, set_name, files, active)
        if not read_any:
            return  # nothing was parsed: "not exercised" would claim the data lacked the feature, when there was no data
        if "nine-digit-ids-parse" in active and not any(i.check == "nine-digit-ids-parse" for i in res.items):
            res.add("nine-digit-ids-parse", "not-exercised", None, "no nine-digit ids in the fetched data (launch nominals exist only ~5-8 days after a launch)")
        for c, what in (("leading-dot-decimals", "no value written without a leading zero in the fetched OMM files"),
                        ("bstar-implied-decimal-exponent", "no TLE file with an oracle in this run"),
                        ("negative-bstar-and-ndot", "no negative BSTAR or first derivative in the fetched data")):
            if c in active and not any(i.check == c for i in res.items):
                res.add(c, "not-exercised", None, what)

    def run_pairs(self, case, exp, res):
        active = set(case["checks"])
        pairs = exp["case_specific"]["pairs"]
        stems = {}
        bypath = {os.path.basename(p): p for p in exp["sources"]}
        for it in pairs:
            if "tle_file" in it:
                stems.setdefault((it["tle_file"], it["omm_file"]), None)
        if not stems:  # fall back to pairing sources by stem
            for b in bypath:
                if b.endswith(".tle") and b[:-4] + ".csv" in bypath:
                    stems.setdefault((b, b[:-4] + ".csv"), None)
        for tb, ob in stems:
            files = {}
            for b in (tb, ob):
                path = bypath[b]
                state, fmt, mode, parsed, refrecs, reffacts = self.load_source(res, case, path, exp["sources"][path])
                files[path] = (state, fmt, parsed, refrecs)
            if all(v[0] == "ok" for v in files.values()):
                self.check_set_relations(res, exp, f"{tb} vs {ob}", files, active)

    def run_facts(self, case, exp, res):
        active = set(case["checks"])
        for path, src in exp["sources"].items():
            state, fmt, mode, parsed, refrecs, reffacts = self.load_source(res, case, path, src)
            if state == "ok":
                self.check_format_facts(res, path, fmt, parsed, reffacts, active)

    def run_xml(self, case, exp, res):
        active = set(case["checks"])
        for path, src in exp["sources"].items():
            state, fmt, mode, parsed, refrecs, reffacts = self.load_source(res, case, path, src)
            if state == "ok":
                self.check_format_facts(res, path, fmt, parsed, reffacts, active | {"xml-ndm-wrapper-omm-2.0"})
                v = exp["case_specific"].get(path, {}).get("validation")
                if isinstance(v, dict):
                    res.add("schema-validation-recorded", "info", path, "; ".join(f"{k}: {'valid' if r['valid'] else 'invalid'}" for k, r in v.items()))

    def run_satcat(self, case, exp, res):
        for path, src in exp["sources"].items():
            full = os.path.join(self.root, path)
            if not os.path.exists(full):
                res.add("source-present", "skip", path, "not on disk; run tools/fetch.py")
                continue
            mode = "snapshot" if sha256(full) == src.get("sha256") else "live"
            res.modes[path] = mode
            if src.get("format") == "satcat-legacy-fixed-width":
                ids = [int(l[13:18]) for l in open(full, encoding="utf-8", errors="replace").read().splitlines() if l[13:18].strip().isdigit()]
                above = sum(i >= 70000 for i in ids)
                res.add("satcat-legacy-below-70000", "fail" if above else "pass", path, f"{len(ids)} ids, max {max(ids)}, {above} at or above 70000 (data check, {mode})")
            else:
                res.add("satcat-record", "info", path, f"{mode}; SATCAT records are not parsed by the GP parser under test")

    def run_vectors(self, case, exp, res):
        hooks = {h: getattr(self.parser, h, None) for h in ("alpha5_decode", "alpha5_encode", "two_digit_year", "parse_epoch", "parse_catalog_id")}
        vec = exp["case_specific"]
        a5 = next((v for k, v in vec.items() if k.endswith("alpha5.json")), None)
        if a5:
            if hooks["alpha5_decode"]:
                bad = []
                for group in ("official_examples", "boundaries", "skip_boundaries", "below_100000"):
                    for v in a5[group]:
                        try:
                            got = hooks["alpha5_decode"](v["field"])
                        except Exception as e:
                            got = f"raised {type(e).__name__}"
                        if got != v["norad_cat_id"]:
                            bad.append(f"{v['field']} -> {got} (expected {v['norad_cat_id']})")
                for v in a5["decode_invalid"]:
                    try:
                        got = hooks["alpha5_decode"](v["field"])
                        bad.append(f"{v['field']} accepted as {got} (should be rejected: {v['reason']})")
                    except Exception:
                        pass
                res.add("alpha5-decode", "fail" if bad else "pass", "vectors/alpha5.json", "; ".join(bad[:8]) if bad else "all decode vectors and all invalid inputs handled")
            else:
                res.add("alpha5-decode", "skip", "vectors/alpha5.json", "parser exposes no alpha5_decode hook")
            if hooks["alpha5_encode"]:
                bad = []
                for group in ("official_examples", "boundaries", "skip_boundaries", "below_100000"):
                    for v in a5[group]:
                        try:
                            got = hooks["alpha5_encode"](v["norad_cat_id"])
                        except Exception as e:
                            got = f"raised {type(e).__name__}"
                        if got != v["field"]:
                            bad.append(f"{v['norad_cat_id']} -> {got!r} (expected {v['field']!r})")
                for v in a5["encode_unrepresentable"]:
                    try:
                        got = hooks["alpha5_encode"](v["norad_cat_id"])
                        bad.append(f"{v['norad_cat_id']} encoded as {got!r} (should be rejected: {v['reason']})")
                    except Exception:
                        pass
                res.add("alpha5-encode", "fail" if bad else "pass", "vectors/alpha5.json", "; ".join(bad[:8]) if bad else "all encode vectors and all unrepresentable inputs handled")
            else:
                res.add("alpha5-encode", "skip", "vectors/alpha5.json", "parser exposes no alpha5_encode hook")
        yy = next((v for k, v in vec.items() if k.endswith("two-digit-epoch-year.json")), None)
        if yy:
            if hooks["two_digit_year"]:
                bad = []
                for v in yy["vectors"]:
                    try:
                        got = hooks["two_digit_year"](v["yy"])
                    except Exception as e:  # a raising hook fails this vector, not the case (D-118)
                        bad.append(f"{v['yy']} -> raised {type(e).__name__}: {e}")
                        continue
                    if got != v["year"]:
                        bad.append(f"{v['yy']} -> {got}")
                res.add("two-digit-year-pivot", "fail" if bad else "pass", "vectors/two-digit-epoch-year.json", "; ".join(bad) if bad else f"{len(yy['vectors'])} pivot vectors correct")
            else:
                res.add("two-digit-year-pivot", "skip", "vectors/two-digit-epoch-year.json", "parser exposes no two_digit_year hook")
        ep = next((v for k, v in vec.items() if k.endswith("ccsds-epoch-strings.json")), None)
        if ep and hooks["parse_epoch"]:
            bad = []
            for v in ep["valid"]:
                try:
                    got = hooks["parse_epoch"](v["text"])
                except Exception as e:
                    bad.append(f"valid {v['text']!r} rejected ({type(e).__name__})")
                    continue
                accepted = ([v["iso"]] + list(v.get("iso_alternatives", []))) if v.get("iso") else []
                if not accepted:
                    continue
                try:  # the value is compared, not only that the hook returned (D-119): a constant-returning hook fails
                    got_iso = norm_epoch(got)
                except Exception as e:
                    bad.append(f"valid {v['text']!r} -> {got!r} is not an epoch ({type(e).__name__})")
                    continue
                if all(compare_value("epoch", got_iso, a)[0] == "mismatch" for a in accepted):
                    bad.append(f"valid {v['text']!r} -> {got_iso}, expected {' or '.join(accepted)}")
            for v in ep["invalid"]:
                try:
                    hooks["parse_epoch"](v["text"])
                    bad.append(f"invalid {v['text']!r} accepted")
                except Exception:
                    pass
            res.add("ccsds-epoch-strings", "fail" if bad else "pass", "vectors/ccsds-epoch-strings.json", "; ".join(bad[:8]) if bad else
                    f"{len(ep['valid'])} valid epoch strings parsed to the instants they denote (within {EPOCH_TOLERANCE_US} us) and {len(ep['invalid'])} invalid strings rejected")
        elif ep:
            res.add("ccsds-epoch-strings", "skip", "vectors/ccsds-epoch-strings.json", "parser exposes no parse_epoch hook")
        cid = next((v for k, v in vec.items() if k.endswith("norad-cat-id-text.json")), None)
        if cid and hooks["parse_catalog_id"]:
            bad = []
            for v in cid["valid"]:
                try:
                    got = hooks["parse_catalog_id"](v["text"])
                except Exception as e:
                    got = f"raised {type(e).__name__}"
                if got != v["value"] or type(got) is not int:
                    bad.append(f"{v['text']!r} -> {got!r} (expected int {v['value']})")
            for v in cid["invalid_in_omm"]:
                try:
                    got = hooks["parse_catalog_id"](v["text"])
                    bad.append(f"{v['text']!r} accepted as {got!r} (should be rejected: {v['reason']})")
                except Exception:
                    pass
            nine = sum(1 for v in cid["valid"] if v["value"] >= 100_000_000)
            res.add("catalog-number-is-integer", "fail" if bad else "pass", "vectors/norad-cat-id-text.json",
                    "; ".join(bad[:8]) if bad else f"{len(cid['valid'])} valid text forms parsed as int ({nine} nine-digit) and {len(cid['invalid_in_omm'])} invalid forms rejected")
        elif cid:
            res.add("catalog-number-is-integer", "skip", "vectors/norad-cat-id-text.json", "parser exposes no parse_catalog_id hook")

    def run_writer(self, case, exp, res):
        """Writer case: every record in expected.json is an input to write_tle; inputs the TLE format cannot
        represent must be refused (that is the correct output); the rest must produce valid, decodable,
        round-tripping lines. Inputs are inline, so the case runs without any fetched file."""
        hook = getattr(self.parser, "write_tle", None)
        if hook is None:
            res.add("tle-writer-catalog-field", "skip", None, "parser exposes no write_tle hook")
            return
        lines_bad, cat_bad, rt_bad, emitted_bad, refused_ok, layout_bad = [], [], [], [], [], []
        conv, sec, signs, prov = {}, {}, {}, {}
        written, refused_real, rt_checked = 0, 0, 0
        for it in exp["records"]:
            cat, rec, ok_id = it["norad_cat_id"], it["canonical"], it["representable_in_tle"]
            try:
                out = hook(dict(rec))
            except Unsupported:
                res.add("tle-writer-catalog-field", "skip", None, "parser reports TLE writing unsupported")
                return
            except Exception as e:
                if ok_id:
                    refused_real += 1
                    cat_bad.append(f"id {cat} refused although the TLE field can carry it: {type(e).__name__}: {str(e)[:120]}")
                else:
                    refused_ok.append(cat)
                continue
            try:
                l0, l1, l2 = W.normalise_lines(out)
            except Exception as e:
                (lines_bad if ok_id else emitted_bad).append(f"id {cat}: {e}")
                continue
            if not ok_id:
                emitted_bad.append(f"id {cat}: lines written instead of a refusal (line 1 columns 3-7 {l1[2:7]!r}, {len(l1)} characters)")
                continue
            written += 1
            problems = W.check_lines(l1, l2)
            if problems:
                lines_bad.append(f"id {cat}: " + "; ".join(problems))
            ok, detail = W.check_catalog_field(l1, l2, cat)
            if not ok:
                cat_bad.append(f"id {cat}: {detail}")
            if len(l1) != 69 or len(l2) != 69:
                continue  # the reader needs well-formed lines; the length failure is already recorded
            layout = W.check_layout(l1, l2)  # right length and checksum say nothing about where the fields sit (D-119)
            if layout:
                layout_bad.append(f"id {cat}: " + "; ".join(layout[:3]) + (f" … ({len(layout)} fields)" if len(layout) > 3 else ""))
            rt_checked += 1
            try:
                mism, c = W.round_trip(l0, l1, l2, rec)
                s = W.secondary_fields(l0, l1, l2, rec)
            except Exception as e:
                rt_bad.append(f"id {cat}: reference reader raised {type(e).__name__}: {str(e)[:120]}")
                continue
            if mism:
                rt_bad.append(f"id {cat}: " + "; ".join(mism))
            for f, k in c.items():
                conv.setdefault(f, {})[k] = conv.setdefault(f, {}).get(k, 0) + 1
            for f in W.SECONDARY_FIELDS:
                sec.setdefault(f, {})[s[f]] = sec.setdefault(f, {}).get(s[f], 0) + 1
            if s["zero_ddot_sign"]:
                signs[s["zero_ddot_sign"]] = signs.get(s["zero_ddot_sign"], 0) + 1
            if it.get("reference_tle_fields"):
                for f, same in W.provider_field_matches(l1, l2, it["reference_tle_fields"]).items():
                    p = prov.setdefault(f, [0, 0])
                    p[0] += bool(same)
                    p[1] += 1

        def summary(fails, ok_text, n_ok, n_all, unit="record(s)"):
            # a failing detail opens with what passed, so a failure confined to a few inputs cannot read as a general one
            if not fails:
                return ok_text
            return f"{n_ok} of {n_all} {unit} correct; " + "; ".join(fails[:8]) + (" ..." if len(fails) > 8 else "")

        n_real = written + refused_real
        res.add("tle-checksums-valid", "fail" if lines_bad else "pass", None,
                summary(lines_bad, f"{written} record(s) written as two 69-character lines with valid checksums", written - len(lines_bad), written))
        res.add("tle-writer-catalog-field", "fail" if cat_bad else "pass", None,
                summary(cat_bad, f"{written} catalog field(s) written correctly (five digits below 100000, Alpha-5 from 100000)",
                        n_real - len(cat_bad), n_real, "catalog field(s)"))
        res.add("tle-writer-column-layout", "fail" if layout_bad else "pass", None,
                summary(layout_bad, f"{rt_checked} record(s) with every field in its fixed columns", rt_checked - len(layout_bad), rt_checked))
        conv_text = "; ".join(f"{f}: " + ", ".join(f"{k} {n}" for k, n in sorted(v.items())) for f, v in conv.items())
        res.add("tle-writer-round-trip", "fail" if rt_bad else "pass", None,
                summary(rt_bad, f"{written} record(s) read back at the TLE field resolution (rendering observed per field: {conv_text})",
                        rt_checked - len(rt_bad), rt_checked))
        unrep = [it["norad_cat_id"] for it in exp["records"] if not it["representable_in_tle"]]
        if unrep:
            head = f"{len(refused_ok)} of {len(unrep)} number(s) the TLE catalog field cannot represent (synthetic inputs, D-096) correctly refused"
            if emitted_bad:
                detail = head + (f" ({', '.join(map(str, refused_ok))})" if refused_ok else "") + "; written instead of refused: " + "; ".join(emitted_bad[:8])
            else:
                detail = head + f" ({', '.join(map(str, refused_ok))}); a refusal is the right output here, and such numbers belong in the OMM formats"
            res.add("tle-writer-refuses-unencodable", "fail" if emitted_bad else "pass", None, detail)
        if sec:
            sec_text = "; ".join(f"{f}: " + ", ".join(f"{k} {n}" for k, n in sorted(v.items())) for f, v in sec.items())
            sign_text = ", ".join(f"'{k}' {n}" for k, n in sorted(signs.items())) or "no zero second derivative written"
            res.add("tle-writer-secondary-fields", "info", None, f"{sec_text}; zero second-derivative exponent sign: {sign_text} (CelesTrak writes +, Space-Track -)")
        if prov:
            res.add("tle-writer-matches-provider-rendering", "info", None,
                    "byte-identical to the provider's or derived rendering: " + ", ".join(f"{f} {a}/{n}" for f, (a, n) in prov.items()))

    def run_case(self, case):
        exp = json.load(open(os.path.join(self.root, "fixtures", case["id"], "expected.json")))
        res = CaseResult(case["id"], case["title"])
        kind = exp["kind"]
        try:
            if kind in ("gp", "derived-tle", "derived-kvn"):
                self.run_gp_like(case, exp, res)
            elif kind == "pairs":
                self.run_pairs(case, exp, res)
            elif kind == "facts":
                self.run_facts(case, exp, res)
            elif kind == "xml":
                self.run_xml(case, exp, res)
            elif kind == "satcat":
                self.run_satcat(case, exp, res)
            elif kind == "vectors":
                self.run_vectors(case, exp, res)
            elif kind == "writer":
                self.run_writer(case, exp, res)
        except Exception as e:
            res.add("runner", "fail", None, f"internal error in runner: {type(e).__name__}: {e}")
        return res

    def run(self, case_ids=None, tags=None):
        results = []
        for case in self.manifest["cases"]:
            if case_ids and case["id"] not in case_ids:
                continue
            if tags and not (set(tags) & set(case["tests"])):
                continue
            results.append(self.run_case(case))
        return results


# --------------------------------------------------------------------------- external command adapter
class CommandParser:
    """Runs an external program per file: raw bytes on stdin, JSON array of records on stdout.
    The command may contain {fmt} and {path}. Non-zero exit or invalid JSON = parse failure.
    write_cmd (optional): one JSON record on stdin, the TLE lines on stdout (2 or 3 lines); exit 0 =
    written, exit 3 = writing unsupported, any other non-zero exit = the record was refused."""

    def __init__(self, cmd, vectors_cmd=None, timeout=120, write_cmd=None):
        self.cmd, self.vectors_cmd, self.timeout, self.write_cmd = cmd, vectors_cmd, timeout, write_cmd

    def parse(self, raw, fmt):
        if not self.cmd:
            raise Unsupported(fmt)
        cmd = self.cmd.replace("{fmt}", fmt)
        p = subprocess.run(cmd, shell=True, input=raw, capture_output=True, timeout=self.timeout)
        if p.returncode == 3:
            raise Unsupported(fmt)
        if p.returncode != 0:
            raise RuntimeError(f"exit {p.returncode}: {p.stderr.decode('utf-8', 'replace')[-300:]}")
        try:
            data = json.loads(p.stdout.decode("utf-8"))
        except ValueError as e:
            raise RuntimeError(f"stdout is not JSON ({e}): {p.stdout.decode('utf-8', 'replace')[:120]!r}")
        if not isinstance(data, list):
            raise RuntimeError("stdout must be a JSON array of records")
        return data

    def write_tle(self, record):
        if not self.write_cmd:
            raise Unsupported("tle-writing")
        p = subprocess.run(self.write_cmd, shell=True, input=json.dumps(record, default=str).encode(), capture_output=True, timeout=self.timeout)
        if p.returncode == 3:
            raise Unsupported("tle-writing")
        if p.returncode != 0:
            raise RuntimeError(f"exit {p.returncode}: {p.stderr.decode('utf-8', 'replace')[-300:]}")
        return p.stdout.decode("utf-8")

    def _vec(self, op, value):
        if not self.vectors_cmd:
            raise AttributeError(op)
        p = subprocess.run(self.vectors_cmd, shell=True, input=json.dumps({"op": op, "input": value}).encode(), capture_output=True, timeout=self.timeout)
        try:
            out = json.loads(p.stdout.decode("utf-8") or "{}")
        except ValueError as e:
            raise ValueError(f"the command's output is not JSON: {e}")
        if p.returncode != 0 or "error" in out:
            raise ValueError(out.get("error", f"exit {p.returncode}"))
        if "result" not in out:  # a well-formed answer carries result or error (D-118)
            raise ValueError("the command's answer carries neither 'result' nor 'error'")
        return out["result"]

    def __getattr__(self, name):
        if name in ("alpha5_decode", "alpha5_encode", "two_digit_year", "parse_epoch", "parse_catalog_id") and self.vectors_cmd:
            def hook(value):
                r = self._vec(name, value if not isinstance(value, dt.datetime) else value.isoformat())
                return dt.datetime.fromisoformat(r) if name == "parse_epoch" else r
            return hook
        raise AttributeError(name)
