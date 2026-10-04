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
        parse_catalog_id(text: str) -> int        raise for invalid input
        any of the five: raise gpconf.runner.Unsupported for an operation the library does not have, and the
        item skips with the reason; an operation is unsupported for all of its vectors or none (D-205)
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
    """Raise from parse() for a format the parser does not implement, from write_tle() when it has no writer, or from
    a vector hook for an operation the library does not have (D-205)."""


class CorpusIncomplete(Exception):
    """A file that ships with the corpus (derived/, vectors/) is not on disk: the copy is broken, and no status
    the runner could report for the case would be true of the parser (D-148)."""


REPO_URL = "https://github.com/hneogy/gp-omm-conformance"


def is_provider_data(path):
    """A provider response under fixtures/<case>/raw/: never shipped with the corpus, always fetched (D-019)."""
    parts = path.replace("\\", "/").split("/")
    return len(parts) >= 4 and parts[0] == "fixtures" and parts[2] == "raw"


def launch_window_files(root):
    """Provider files that are the corpus's own captures of a launch window -> {path: which launch} (D-229).

    CelesTrak serves launch nominals and post-deployment files for the days after a launch, so no fetch requests
    these files and a user cannot obtain them: a case that needs one reports not-available for it, never
    not-fetched, which would send the user to a fetch that does not bring it. The list is read from the fetch list,
    which ships with the corpus; a bare copy without it has none."""
    try:
        with open(os.path.join(root, "tools", "fetchlist.json")) as f:
            entries = json.load(f)
    except (OSError, ValueError):
        return {}
    return {f"fixtures/{e['case']}/raw/{e['file']}": e["launch_window"] for e in entries if e.get("launch_window")}


def opt_in_files(root):
    """Provider files the fetch brings only on request -> {path: the flag that asks for it} (D-231): the legacy SATCAT
    file, most of the bytes of the whole fetch list, which one data check reads and no parser. Read from the fetch
    list; a bare copy without it has none."""
    try:
        with open(os.path.join(root, "tools", "fetchlist.json")) as f:
            entries = json.load(f)
    except (OSError, ValueError):
        return {}
    return {f"fixtures/{e['case']}/raw/{e['file']}": "--include-" + e["opt_in"] for e in entries if e.get("opt_in")}


def fetch_hint(root, *args, data=None, data_why=None):
    """The command that fetches provider data into the folder this run reads, naming a command that exists
    (D-148, D-150).

    A clone has tools/fetch.py; the path is given relative to the working directory when that is shorter and quoted
    when it needs to be. Without the script (an installed runner, or a bare copy of the corpus) the command is the
    package's own `python3 -m gpconf fetch`. A data folder chosen with --data is passed on; one chosen with the
    GPCONF_DATA environment variable is not, since the variable reaches the fetch too; a bare corpus copy given as
    --root is passed on, since the fetch would otherwise look elsewhere."""
    import shlex
    script = os.path.join(root, "tools", "fetch.py")
    flags = ""
    if data_why == "--root" and not os.path.exists(script):
        flags += f" --root {shlex.quote(root)}"
    if data_why == "--data" and data:
        flags += f" --data {shlex.quote(data)}"
    tail = flags + "".join(" " + a for a in args)
    if os.path.exists(script):
        try:
            rel = os.path.relpath(script)
        except ValueError:  # another drive on Windows
            rel = script
        path = script if rel.startswith("..") else rel
        return f"python3 {shlex.quote(path)}{tail}"
    return f"python3 -m gpconf fetch{tail}"


# --------------------------------------------------------------------------- normalisation
def norm_epoch(v):
    if v is None:
        return None
    if isinstance(v, dt.datetime):
        if v.tzinfo is not None:
            v = v.astimezone(dt.timezone.utc).replace(tzinfo=None)
        return v.strftime("%Y-%m-%dT%H:%M:%S.%f")
    return tlemod.iso_epoch(v)  # calendar or day-of-year form, fraction, Z, offset, leap second (D-118, D-119)


def as_integer(v):
    """-> (int or None, problem or None). A bool, a value int() cannot convert, or a float or Decimal with a
    fractional part is not an integer; the problem text carries the value and its type for the report (D-131)."""
    if isinstance(v, bool):
        return None, f"{v!r} (bool)"
    try:
        i = int(v)
    except (TypeError, ValueError):
        return None, f"{v!r} ({type(v).__name__})"
    if isinstance(v, (float, Decimal)) and v != i:
        return None, f"{v!r} ({type(v).__name__}, fractional)"
    return i, None


def norm_record(rec):
    """Parser output -> {field: comparable value}; also returns type notes. A field that should be an integer but is
    not stays None and is named in the record's _bad map, so the values item reports the value and its type
    instead of the runner raising (D-131)."""
    out, notes, bad = {}, {}, {}
    for k, v in rec.items():
        if k in INT_FIELDS:
            if v is None or v == "":
                out[k] = None
            else:
                notes[k] = type(v).__name__
                out[k], problem = as_integer(v)
                if problem:
                    bad[k] = problem
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
    return out, notes, bad


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


# --------------------------------------------------------------------------- the refusal channel (D-144)
REFUSAL_KEY, ADAPTER_KEY = "_refused", "_adapter"


def field_to_id(field):
    """The expected integer behind a catalog field as the input carried it: digits, or an Alpha-5 field; None otherwise."""
    if not isinstance(field, str):
        return None
    f = field.strip()
    if re.fullmatch(r"\d+", f):
        return int(f)
    if re.fullmatch(r"[A-Z]\d{4}", f):
        try:
            return tlemod.from_alpha5(f)
        except ValueError:
            return None
    return None


def split_refusals(recs):
    """An adapter's list -> (records, refusals, declared). A refusal is an entry carrying `_refused`; its reason must be a
    non-empty string, or the refusal is no better than a drop and is marked so (ok=False). `declared` is the adapter's
    capability declaration ({"_adapter": {"refusals": true}}), None when absent: without it, zero refusals means only that
    none were reported, not that none happened."""
    records, refusals, declared = [], [], None
    for r in recs:
        if isinstance(r, dict) and ADAPTER_KEY in r:
            decl = r.get(ADAPTER_KEY)
            declared = bool(decl.get("refusals")) if isinstance(decl, dict) else None
            continue
        if isinstance(r, dict) and REFUSAL_KEY in r:
            reason = r.get(REFUSAL_KEY)
            ok = isinstance(reason, str) and bool(reason.strip())
            field = r.get("_field")
            refusals.append({"reason": reason.strip() if ok else None, "ok": ok, "field": field if isinstance(field, str) else None,
                             "input": str(r.get("_input"))[:80] if r.get("_input") is not None else None, "id": field_to_id(field)})
            continue
        records.append(r)
    return records, refusals, declared


# --------------------------------------------------------------------------- report objects
class Item:
    def __init__(self, check, status, file=None, detail="", tolerance=None, counts=None):
        self.check, self.status, self.file, self.detail, self.tolerance = check, status, file, detail, tolerance
        self.counts = counts  # structured record counts behind a values item (D-142), so headlines never parse the sentence

    def as_dict(self):
        d = {"check": self.check, "status": self.status, "file": self.file, "detail": self.detail}
        if self.tolerance:
            d["tolerance_stats"] = self.tolerance.as_dict()
        if self.counts is not None:
            d["counts"] = self.counts
        return d


class CaseResult:
    def __init__(self, case_id, title):
        self.case_id, self.title, self.items, self.modes = case_id, title, [], {}
        self.drift = {}  # path -> {recorded_sha256, actual_sha256}: stable-tier sources whose bytes changed (D-115)
        self.refusals, self.declared = {}, {}  # path -> the adapter's refusal entries; path -> its capability declaration (D-144)
        self.reused = {}  # path -> the corpus version whose cache the file was copied from, not fetched (D-157)
        self.unexpected = {}  # path -> what the fetch recorded when the answer for that file was not one it expected (D-228)
        self.on_request = {}  # path -> the fetch's flag for a file it brings only on request, when a data check waits on it (D-232)

    def add(self, check, status, file=None, detail="", tolerance=None, counts=None):
        if tolerance and status == "pass":
            status = "pass-tolerance"
            detail = (detail + "; " if detail else "") + tolerance.text()
        self.items.append(Item(check, status, file, detail, tolerance, counts))

    @property
    def status(self):
        # not-fetched ranks above skip: a case with no provider data on disk says so, and never borrows skip, which
        # means the parser has no reader for the format (D-148). A case that ran on some of its files keeps the
        # result of those files; its missing ones are counted under not-fetched and named below the table.
        # not-available ranks below not-fetched (D-229): a case with anything still to fetch says that, since it is
        # what the user can act on; a case all of whose provider files are launch-window captures can never run
        # from a fetch and says not-available.
        st = {i.status for i in self.items}
        for s in ("fail", "pass-tolerance", "pass", "not-exercised", "not-fetched", "not-available"):
            if s in st:
                return s
        return "skip"

    def missing(self):
        """Provider files this case names that were not on disk and that a fetch can bring (D-148)."""
        return [i.file for i in self.items if i.status == "not-fetched"]

    def unavailable(self):
        """Provider files this case names that no fetch requests: launch-window captures (D-229)."""
        return [i.file for i in self.items if i.status == "not-available"]

    def counts(self):
        c = {"pass": 0, "pass-tolerance": 0, "fail": 0, "skip": 0, "not-exercised": 0, "not-fetched": 0, "not-available": 0, "info": 0}
        for i in self.items:
            c[i.status] = c.get(i.status, 0) + 1
        return c

    def as_dict(self):
        d = {"case": self.case_id, "title": self.title, "status": self.status, "counts": self.counts(),
             "modes": self.modes, "drift": self.drift, "items": [i.as_dict() for i in self.items]}
        if self.reused:
            d["reused"] = self.reused
        if self.unexpected:
            d["unexpected"] = self.unexpected
        if self.on_request:
            d["on_request"] = self.on_request
        return d


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


class _HookCalls:
    """One vector hook, counting the vectors it declares unsupported (a raise of Unsupported), so that an operation the
    library does not have skips its item, for all of its vectors or none (D-205)."""

    def __init__(self, name, hook):
        self.name, self.hook, self.calls, self.unsupported, self.reasons = name, hook, 0, 0, []

    def __call__(self, value):
        self.calls += 1
        try:
            return self.hook(value)
        except Unsupported as e:
            self.unsupported += 1
            reason = str(e).strip() or "no reason given"
            if reason not in self.reasons:
                self.reasons.append(reason)
            raise


def _vector_item(res, check, file, calls, bad, ok_detail):
    """The item for one hook: skip when the parser declared every vector unsupported, fail when it declared only some,
    since an operation is unsupported for all of its vectors or none, else pass or fail on the vectors (D-205)."""
    if calls.unsupported and calls.unsupported == calls.calls:
        res.add(check, "skip", file, f"parser reports {calls.name} unsupported: {'; '.join(calls.reasons)}")
    elif calls.unsupported:
        res.add(check, "fail", file, f"{calls.name} answered unsupported for {calls.unsupported} of {calls.calls} vectors "
                f"({'; '.join(calls.reasons)}) and answered the rest: an operation is unsupported for all of its vectors or none"
                + (f"; {'; '.join(bad[:8])}" if bad else ""))
    else:
        res.add(check, "fail" if bad else "pass", file, "; ".join(bad[:8]) if bad else ok_detail)


class Runner:
    def __init__(self, parser, root=None, verbose=False, data=None, data_why=None, fetch_hints=True):
        self.parser = parser
        # Two roots (D-150): the corpus root holds what ships (manifest, expected values, derived/, vectors/), the
        # data root the provider files this machine fetched. With no root given, both are resolved as the command
        # line resolves them (a clone, or the installed corpus and a per-user cache); with a root and no data, the
        # provider files are looked for under the root, the layout of a clone and of every test.
        if root is None:
            from . import locate
            loc = locate.resolve(None, data)
            root, data, data_why = loc["corpus"], loc["data"], loc["data_why"]
        self.root = root
        self.data = data or root
        self.data_why = data_why or ("--data" if data else "--root")
        # False for a run that is offline by design, the GitHub Action's: its data folder is empty and discarded with
        # the job, so a command that fetches into it would be wrong advice (D-158)
        self.fetch_hints = fetch_hints
        self.verbose = verbose
        self.manifest = json.load(open(os.path.join(self.root, "manifest.json")))
        self.launch_window = launch_window_files(self.root)
        self.opt_in = opt_in_files(self.root)

    def path(self, rel):
        """A source's path on disk: provider data under the data root, everything that ships under the corpus root."""
        return os.path.join(self.data if is_provider_data(rel) else self.root, rel)

    def hint(self, *args):
        return fetch_hint(self.root, *args, data=self.data, data_why=self.data_why)

    # ---- parsing helpers
    def parse(self, path, fmt):
        raw = open(path, "rb").read()
        fn = getattr(self.parser, "parse", None) or self.parser
        recs, self._refusals, self._declared = split_refusals(fn(raw, fmt))
        out = []
        for r in recs:
            n, notes, bad = norm_record(r)
            n["_notes"] = notes
            if bad:
                n["_bad"] = bad
            out.append(n)
        return out

    def launch_window_detail(self, path):
        return (f"not on disk: a launch-window capture ({self.launch_window[path]}). CelesTrak serves launch nominals for "
                "the days after a launch; the corpus captured this file then, and no fetch requests it")

    def unexpected_response(self, path):
        """What the fetch kept when its last answer for this provider file was not one it expected (D-228): the
        response sits beside the data as <file>.unexpected, never in its place -> {'http_status', 'at', 'why',
        'kept'}, or None when there is none."""
        full = self.path(path)
        if not os.path.exists(full + ".unexpected"):
            return None
        try:
            with open(full + ".unexpected.meta.json") as f:
                meta = json.load(f)
        except (OSError, ValueError):
            meta = {}
        status = meta.get("http_status")
        return {"http_status": status, "at": meta.get("retrieved_at"),
                "why": meta.get("unexpected") or (f"HTTP {status}" if status else "a response it did not expect"),
                "kept": os.path.basename(full) + ".unexpected"}

    def report_missing(self, res, path):
        """A source file that is not on disk. Provider data is reported as not-fetched with the command that fetches
        it; a file that ships with the corpus stops the run, since the copy itself is incomplete (D-148). When the
        fetch asked for the file and got a response it did not expect, the item says so and names no command: a
        plain fetch does not ask again (D-228)."""
        if not is_provider_data(path):
            raise CorpusIncomplete(f"{path} ships with the corpus and is not on disk under {self.root}: "
                                   f"this copy of the corpus is incomplete; re-clone {REPO_URL} or reinstall")
        if path in self.launch_window:
            res.add("source-present", "not-available", path, self.launch_window_detail(path))
            return
        unexp = self.unexpected_response(path)
        if unexp:
            res.unexpected[path] = unexp
            res.add("source-present", "not-fetched", path,
                    f"not on disk: the fetch got {unexp['why']} for it" + (f" at {unexp['at']}" if unexp["at"] else "")
                    + f" and kept that response as {unexp['kept']}, which is not provider data and is not read"
                    + ("; the fetch asks again only with --force, two hours or more after that answer" if self.fetch_hints else ""))
            return
        if path in self.opt_in:  # a plain fetch does not bring it, so the command names the flag that does (D-231)
            res.add("source-present", "not-fetched", path,
                    "not on disk: the fetch brings this file only on request, since no parser takes part in the check that reads it"
                    + (f"; fetch it with {self.hint(self.opt_in[path])}" if self.fetch_hints else ""))
            return
        res.add("source-present", "not-fetched", path, "not on disk: provider data is not shipped with the corpus"
                + (f"; fetch it with {self.hint()}" if self.fetch_hints else ""))

    def load_source(self, res, case, path, src):
        """Returns (state, fmt, mode, parsed, refrecs, reffacts). state: ok | missing | empty-404 | unreadable | parse-error | unsupported"""
        full = self.path(path)
        fmt = src.get("format")
        if not os.path.exists(full):
            self.report_missing(res, path)
            return "missing", fmt, None, None, None, None
        if is_provider_data(path) and os.path.exists(full + ".meta.json"):
            try:
                with open(full + ".meta.json") as f:
                    meta = json.load(f)
            except ValueError:
                meta = {}
            came = meta.get("reused_from")  # reused rather than fetched (D-157)
            if came:
                res.reused[path] = came.get("corpus_version")
            got = meta.get("http_status")
            if got not in (None, 200) and got != src.get("http_status", 200):
                # A fetch before v0.5.1 wrote a response it did not expect to the data path itself, "so it is never
                # re-requested". It is not the source, and reading it would charge the parser with an error page or
                # with the provider's no-data text where data is recorded (D-228).
                if path in self.launch_window:  # what a fetch before v0.5.1 met once the window had closed (D-229)
                    res.add("source-present", "not-available", path, self.launch_window_detail(path)
                            + f"; the file on disk holds an HTTP {got} response that an earlier fetch saved in its place, and is not read")
                    return "missing", fmt, None, None, None, None
                res.unexpected[path] = {"http_status": got, "at": meta.get("retrieved_at"), "why": f"HTTP {got}", "kept": os.path.basename(full)}
                res.add("source-present", "not-fetched", path,
                        f"holds an HTTP {got} response that an earlier fetch saved in the data's place"
                        + (f" at {meta['retrieved_at']}" if meta.get("retrieved_at") else "")
                        + ", where the corpus records HTTP " + str(src.get("http_status", 200))
                        + ": not provider data, and not read"
                        + ("; delete the file and its .meta.json, then fetch it again" if self.fetch_hints else ""))
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
                    + (f"Run {self.hint('--check-drift')}; if" if self.fetch_hints else "If")
                    + " CelesTrak changed this first-ever record, tell the corpus maintainer.")
        raw = open(full, "rb").read()
        text = raw.decode("utf-8", "replace")
        if src.get("http_status", 200) != 200 or text.strip() in ("No GP data found", "No SupGP data found"):
            if text.strip() in ("No GP data found", "No SupGP data found"):
                if "empty-answer-yields-no-records" in case.get("checks", []):
                    self.check_empty_answer(res, path, fmt, raw, text.strip(), src.get("http_status"))
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
        res.refusals[path], res.declared[path] = self._refusals, self._declared
        self.report_refusals(res, path, self._refusals)
        if refrecs and not parsed:
            # Fail closed (D-144): a file the reference reads records from, for which the parser returned none, is not a
            # file with nothing in it. Every per-file check would pass on zero records, so none of them runs; the item
            # names what happened to the records, refused with a reason or dropped.
            refs = self._refusals
            with_reason = [r for r in refs if r["ok"]]
            want = {r["norad_cat_id"] for r in refrecs}
            matched = {r["id"] for r in with_reason if r["id"] in want}
            top = sorted(((sum(1 for r in with_reason if r["reason"] == reason), reason) for reason in {r["reason"] for r in with_reason}), reverse=True)
            counts = {"expected": len(refrecs), "returned": 0, "loaded": 0, "misidentified": 0, "dropped": len(refrecs) - len(matched),
                      "extra": 0, "ids_not_returned": len(refrecs) - len(matched),
                      "non_integer_id": 0, "refused": len(with_reason), "refused_matched": len(matched),
                      "refused_without_reason": len(refs) - len(with_reason), "refusals_reported": self._declared,
                      "top_refusal_reason": top[0][1] if top else None}
            what = (f"{len(matched)} refused with a reason ({top[0][1][:120]})" if matched else "") + (", " if matched and counts["dropped"] else "") + \
                   (f"{counts['dropped']} dropped" + (" silently" if self._declared else " (refusals not reported by this adapter)") if counts["dropped"] else "")
            res.add("records-returned", "fail", path, f"parser returned 0 of {len(refrecs)} record(s): {what}", counts=counts)
            return "parse-error", fmt, mode, None, refrecs, reffacts
        return "ok", fmt, mode, parsed, refrecs, reffacts

    def report_refusals(self, res, path, refusals):
        """One item per file that carries refusals (D-144): the reasons with their counts; a refusal without a reason fails it."""
        if not refusals:
            return
        reasons = {}
        for r in refusals:
            if r["ok"]:
                reasons[r["reason"]] = reasons.get(r["reason"], 0) + 1
        no_reason = sum(1 for r in refusals if not r["ok"])
        text = f"{len(refusals) - no_reason} refused with a reason" + ("" if not reasons else ": " + "; ".join(
            f"{reason[:120]!r} x{n}" for reason, n in sorted(reasons.items(), key=lambda kv: -kv[1])[:5]))
        if no_reason:
            text += f"; {no_reason} refusal(s) without a reason, counted as dropped: a refusal that gives no reason is no better than a drop"
        res.add("refusals", "fail" if no_reason else "info", path, text)

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
            non_int = [p["_bad"]["norad_cat_id"] for p in by_id[None] if p.get("_bad", {}).get("norad_cat_id")]
            absent = len(by_id[None]) - len(non_int)
            if non_int:
                fails.append(f"{len(non_int)} record(s) whose norad_cat_id is not an integer, e.g. " + ", ".join(non_int[:3]))
            if absent:
                fails.append(f"{absent} record(s) without norad_cat_id")
        missing_ids = [i for i in oracle if i not in by_id]
        refusals = res.refusals.get(path, [])
        with_reason = [r for r in refusals if r["ok"]]
        refused_ids = {r["id"] for r in with_reason if r["id"] is not None and r["id"] in oracle and r["id"] not in by_id}
        if missing_ids and "norad_cat_id" not in exempt:
            if refused_ids:
                silent = [i for i in missing_ids if i not in refused_ids]
                eg = next((r for r in with_reason if r["id"] in refused_ids), None)
                fails.append(f"{len(missing_ids)} expected record(s) not returned: {len(refused_ids)} refused with a reason"
                             + (f" (e.g. {eg['field']!r}: {eg['reason'][:100]})" if eg else "") + f", {len(silent)} silently" + (f", e.g. {silent[:3]}" if silent else ""))
            else:
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
                if field in got.get("_bad", {}):
                    fails.append(f"id {cat}: {field} is not an integer: {got['_bad'][field]}")
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
        # Record counts by identity (D-142), one outcome per expected record (D-194, D-207): loaded = returned with the
        # expected integer id; misidentified = returned with an id that is absent, not an integer, or not one the oracle
        # expects; refused_matched = refused with a reason and credited to an expected record; dropped = the expected records
        # left, with no record returned at all and no refusal. A record returned under a wrong id is counted once, as
        # misidentified, and stands in for one of the expected records left; ids_not_returned keeps the count of expected
        # ids no record came back under (what dropped meant before 0.5.0); when more misidentified records come back than
        # there are expected records left, the surplus is counted as extra, never subtracted below zero.
        top = sorted(((sum(1 for r in with_reason if r["reason"] == reason), reason) for reason in {r["reason"] for r in with_reason}), reverse=True)
        misidentified = sum(len(v) for k, v in by_id.items() if k is None or k not in oracle)
        unaccounted = max(0, len(oracle) - compared - len(refused_ids))
        counts = {"expected": len(oracle), "returned": len(parsed), "loaded": compared, "misidentified": misidentified,
                  "dropped": max(0, unaccounted - misidentified), "extra": max(0, misidentified - unaccounted),
                  "ids_not_returned": unaccounted,
                  "non_integer_id": len([p for p in by_id.get(None, []) if p.get("_bad", {}).get("norad_cat_id")]),
                  "refused": len(with_reason), "refused_matched": len(refused_ids),
                  "refused_without_reason": len(refusals) - len(with_reason),
                  "refusals_reported": res.declared.get(path), "top_refusal_reason": top[0][1] if top else None}
        if fails:
            res.add(check, "fail", path, f"{compared} compared vs {label}; " + "; ".join(fails[:12]) + (" ..." if len(fails) > 12 else ""), counts=counts)
        else:
            res.add(check, "pass", path, f"{compared} record(s) match {label}", tolerance=tol, counts=counts)
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
            kws = leading_dot_keywords(open(self.path(path), "rb").read().decode("utf-8", "replace"), fmt)
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
        examples = [p["_bad"]["norad_cat_id"] for p in bad if p.get("_bad", {}).get("norad_cat_id")][:3]
        if "catalog-number-is-integer" in active:
            res.add("catalog-number-is-integer", "fail" if bad else "pass", path,
                    (f"{len(bad)} record(s) whose norad_cat_id is not an int" + (", e.g. " + ", ".join(examples) if examples else "")) if bad else f"{len(parsed)} record(s) with integer norad_cat_id")
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

    def check_empty_answer(self, res, path, fmt, raw, body, status):
        """The provider's empty answer is presented to the parser under test (D-143): an empty but valid result must
        come back as zero records and no error, or 'nothing to load' is indistinguishable from 'unreadable'."""
        what = f"the provider's empty answer (HTTP {status or 404}, body {body!r}, {len(raw)} bytes)"
        try:
            got = self.parser.parse(raw, fmt)
        except Unsupported:
            res.add("empty-answer-yields-no-records", "skip", path, f"parser reports {fmt} unsupported")
            return
        except Exception as e:
            res.add("empty-answer-yields-no-records", "fail", path,
                    f"parser raised {type(e).__name__}: {str(e)[:160]} on {what}; an empty but valid answer must yield no records, not an error")
            return
        records, refusals, _ = split_refusals(got) if isinstance(got, list) else (got, [], None)
        if refusals:
            reason = next((r["reason"] for r in refusals if r["ok"]), "no reason given")
            res.add("empty-answer-yields-no-records", "fail", path,
                    f"parser refused {what} ({reason[:120]}) instead of yielding zero records; an empty answer is not an unreadable one")
            return
        n = len(records) if isinstance(records, list) else None
        if n == 0:
            res.add("empty-answer-yields-no-records", "pass", path, f"{what} read as zero records, no error")
        else:
            res.add("empty-answer-yields-no-records", "fail", path,
                    f"parser returned {n if n is not None else 'a non-list'} record(s) from {what}; an empty answer must yield none")

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
        read_any = False  # a case none of whose files is on disk reports not-fetched, never "not exercised" (D-119, D-148)
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
            full = self.path(path)
            if not os.path.exists(full):
                if path in self.opt_in and src.get("format") == "satcat-legacy-fixed-width" and not self.unexpected_response(path):
                    # The legacy file comes only on request (D-231), and the check that reads it involves no parser.
                    # Without the file the case says what it says with it, not-exercised, and names the flag that
                    # runs the check: "needs fetched data" would tell every user to fetch the file that was made
                    # optional so that they would not (D-232, reversing the status D-231 chose).
                    res.on_request[path] = self.opt_in[path]
                    res.add("satcat-legacy-below-70000", "not-exercised", path,
                            "the data check was not made: the fetch brings the legacy SATCAT file only on request, and the parser "
                            "under test is not involved in the check"
                            + (f"; to run it, fetch the file with {self.hint(self.opt_in[path])}" if self.fetch_hints
                               else f"; the fetch brings the file with {self.opt_in[path]}"))
                    continue
                self.report_missing(res, path)
                continue
            mode = "snapshot" if sha256(full) == src.get("sha256") else "live"
            res.modes[path] = mode
            if src.get("format") == "satcat-legacy-fixed-width":
                ids = [int(l[13:18]) for l in open(full, encoding="utf-8", errors="replace").read().splitlines() if l[13:18].strip().isdigit()]
                above = sum(i >= 70000 for i in ids)
                what = f"{len(ids)} ids, max {max(ids)}, {above} at or above 70000 (data check, {mode})"
                if above:  # the corpus's premise about the legacy file no longer holds: loud, and about the data
                    res.add("satcat-legacy-below-70000", "fail", path, what + "; a data property of the legacy file, not a result of the parser under test")
                else:  # no adapter reads SATCAT: the check involves no parser, so it must never count as a parser pass (D-129)
                    res.add("satcat-legacy-below-70000", "not-exercised", path, what + "; the parser under test was not involved: no adapter reads SATCAT, so this is not a parser result")
            else:
                res.add("satcat-record", "info", path, f"{mode}; SATCAT records are not parsed by the GP parser under test")

    def run_vectors(self, case, exp, res):
        hooks = {h: _HookCalls(h, getattr(self.parser, h, None)) if getattr(self.parser, h, None) else None
                 for h in ("alpha5_decode", "alpha5_encode", "two_digit_year", "parse_epoch", "parse_catalog_id")}
        vec = exp["case_specific"]
        a5 = next((v for k, v in vec.items() if k.endswith("alpha5.json")), None)
        if a5:
            if hooks["alpha5_decode"]:
                bad = []
                for group in ("official_examples", "boundaries", "skip_boundaries", "below_100000"):
                    for v in a5[group]:
                        try:
                            got = hooks["alpha5_decode"](v["field"])
                        except Unsupported:
                            continue
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
                _vector_item(res, "alpha5-decode", "vectors/alpha5.json", hooks["alpha5_decode"], bad, "all decode vectors and all invalid inputs handled")
            else:
                res.add("alpha5-decode", "skip", "vectors/alpha5.json", "parser exposes no alpha5_decode hook")
            if hooks["alpha5_encode"]:
                bad = []
                for group in ("official_examples", "boundaries", "skip_boundaries", "below_100000"):
                    for v in a5[group]:
                        try:
                            got = hooks["alpha5_encode"](v["norad_cat_id"])
                        except Unsupported:
                            continue
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
                _vector_item(res, "alpha5-encode", "vectors/alpha5.json", hooks["alpha5_encode"], bad, "all encode vectors and all unrepresentable inputs handled")
            else:
                res.add("alpha5-encode", "skip", "vectors/alpha5.json", "parser exposes no alpha5_encode hook")
        yy = next((v for k, v in vec.items() if k.endswith("two-digit-epoch-year.json")), None)
        if yy:
            if hooks["two_digit_year"]:
                bad = []
                for v in yy["vectors"]:
                    try:
                        got = hooks["two_digit_year"](v["yy"])
                    except Unsupported:
                        continue
                    except Exception as e:  # a raising hook fails this vector, not the case (D-118)
                        bad.append(f"{v['yy']} -> raised {type(e).__name__}: {e}")
                        continue
                    if got != v["year"]:
                        bad.append(f"{v['yy']} -> {got}")
                _vector_item(res, "two-digit-year-pivot", "vectors/two-digit-epoch-year.json", hooks["two_digit_year"], bad, f"{len(yy['vectors'])} pivot vectors correct")
            else:
                res.add("two-digit-year-pivot", "skip", "vectors/two-digit-epoch-year.json", "parser exposes no two_digit_year hook")
        ep = next((v for k, v in vec.items() if k.endswith("ccsds-epoch-strings.json")), None)
        if ep and hooks["parse_epoch"]:
            bad = []
            for v in ep["valid"]:
                try:
                    got = hooks["parse_epoch"](v["text"])
                except Unsupported:
                    continue
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
            _vector_item(res, "ccsds-epoch-strings", "vectors/ccsds-epoch-strings.json", hooks["parse_epoch"], bad,
                         f"{len(ep['valid'])} valid epoch strings parsed to the instants they denote (within {EPOCH_TOLERANCE_US} us) and {len(ep['invalid'])} invalid strings rejected")
        elif ep:
            res.add("ccsds-epoch-strings", "skip", "vectors/ccsds-epoch-strings.json", "parser exposes no parse_epoch hook")
        cid = next((v for k, v in vec.items() if k.endswith("norad-cat-id-text.json")), None)
        if cid and hooks["parse_catalog_id"]:
            bad = []
            for v in cid["valid"]:
                try:
                    got = hooks["parse_catalog_id"](v["text"])
                except Unsupported:
                    continue
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
            _vector_item(res, "catalog-number-is-integer", "vectors/norad-cat-id-text.json", hooks["parse_catalog_id"], bad,
                         f"{len(cid['valid'])} valid text forms parsed as int ({nine} nine-digit) and {len(cid['invalid_in_omm'])} invalid forms rejected")
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

    @staticmethod
    def unedited_diffs(got, base):
        """The fields in which a record the parser returned from a corrupt input differs from the same parser's reading
        of that record in the unedited file (D-175), compared exactly: the same parser read the same record, so a
        difference is the edit's doing. How close either reading comes to the frozen values is the values check's
        question, asked in the records' own cases; asked here as well, it failed a parser that reads these records
        imprecisely in every file, whatever it did with the corrupt input."""
        def same(a, b):
            return a == b or (isinstance(a, Decimal) and isinstance(b, Decimal) and a.is_nan() and b.is_nan())
        diffs = []
        for field in CORE_FIELDS + OPTIONAL_FIELDS:
            a, b = got.get(field), base.get(field)
            bad_a, bad_b = got.get("_bad", {}).get(field), base.get("_bad", {}).get(field)
            if not same(a, b) or bad_a != bad_b:
                diffs.append(f"{field} = {bad_a or repr(a)}, from the unedited file {bad_b or repr(b)}")
        return diffs

    def read_unedited(self, res, path, src, fmt, readings):
        """The parser's reading of an unedited file (D-175), made once per run of the case: ({id: first record}, {id:
        count}, None), or (None, None, why) when the file cannot serve as the comparison, because the parser refused it
        as a whole or its bytes are not the ones the case was built on."""
        if path in readings:
            return readings[path]
        full = self.path(path)
        if not os.path.exists(full):
            self.report_missing(res, path)  # ships with the corpus: an incomplete copy stops the run (D-148)
        actual = sha256(full)
        res.modes[path] = "snapshot" if actual == src.get("sha256") else "live"
        if actual != src.get("sha256"):
            res.drift[path] = {"recorded_sha256": src.get("sha256"), "actual_sha256": actual}
            res.add("stable-source-drift", "fail", path, f"the unedited file's bytes differ from the ones the case was built on (recorded SHA-256 "
                    f"{str(src.get('sha256'))[:12]}…, actual {actual[:12]}…): the inputs it is the comparison for were not graded")
            readings[path] = (None, None, "its bytes are not the recorded ones")
            return readings[path]
        with open(full, "rb") as f:
            raw = f.read()
        try:
            out = (getattr(self.parser, "parse", None) or self.parser)(raw, fmt)
        except Exception as e:  # Unsupported too: the input of the same format was read, so this is a refusal of the file
            readings[path] = (None, None, f"the parser refused it as a whole ({type(e).__name__}: {str(e)[:160]})")
            return readings[path]
        if not isinstance(out, list):
            readings[path] = (None, None, f"the parser returned {type(out).__name__} for it, not a list of records")
            return readings[path]
        base, count = {}, {}
        for r in split_refusals(out)[0]:
            n, _, bad = norm_record(r)
            if bad:
                n["_bad"] = bad
            base.setdefault(n.get("norad_cat_id"), n)
            count[n.get("norad_cat_id")] = count.get(n.get("norad_cat_id"), 0) + 1
        readings[path] = (base, count, None)
        return readings[path]

    def run_corrupt_input(self, case, exp, res):
        """Corrupt-input case (D-171): each file that ships with the corpus hands the parser one corrupt input between
        valid records. The corrupt record must come back refused with a reason and the valid ones loaded; every record's
        outcome is counted in the vocabulary of D-142 and D-144 (loaded, misidentified, refused, dropped), a record built
        from garbage counting as misidentified. What the parser returns is compared, record by record and exactly, with
        what the same parser returns from the input's unedited file, the same records with no edit (D-175), so the items
        grade what the edit changes and nothing else; a record the parser does not return from the unedited file either
        is left out of the grading. A parser that raises on a file has refused it as a whole, which is fail-closed for a
        file cut mid-record, the complete records it gave up counted (owner decision 3), and for a TLE file gives up the
        valid sets around the corrupt one. A parser that validates no checksum returns input 1's set exactly as it
        returns it unedited: reported, not failed (owner decision 2)."""
        by_file = {}
        for r in exp["records"]:
            by_file.setdefault(r["file"], []).append(r)
        unedited = exp["case_specific"].get("unedited", {})
        readings = {}  # unedited file -> the parser's reading of it, made once
        for path, src in exp["sources"].items():
            if path in unedited:
                continue  # read when an input it is the comparison for is graded
            base_name = os.path.basename(path)
            spec = exp["case_specific"]["files"][base_name]
            check, fmt, cut = spec["check"], spec["format"], spec["check"] == "corrupt-file-cut"
            want = sorted(by_file.get(base_name, []), key=lambda r: r["position"])
            full = self.path(path)
            if not os.path.exists(full):
                self.report_missing(res, path)  # ships with the corpus: an incomplete copy stops the run (D-148)
                continue
            actual = sha256(full)
            res.modes[path] = "snapshot" if actual == src.get("sha256") else "live"
            if actual != src.get("sha256"):
                res.drift[path] = {"recorded_sha256": src.get("sha256"), "actual_sha256": actual}
                res.add("stable-source-drift", "fail", path, f"the file's bytes differ from the input the case was built on (recorded SHA-256 "
                        f"{str(src.get('sha256'))[:12]}…, actual {actual[:12]}…): its expectations describe other bytes and were not applied")
                continue
            whole = None
            with open(full, "rb") as f:
                raw = f.read()
            try:
                out = (getattr(self.parser, "parse", None) or self.parser)(raw, fmt)
            except Unsupported:
                res.add(check, "skip", path, f"parser reports {fmt} unsupported")
                continue
            except Exception as e:  # the parser refused the file as a whole, with the exception as its reason
                whole, out = f"{type(e).__name__}: {str(e)[:160]}", []
            if not isinstance(out, list):
                res.add(check, "fail", path, f"parser returned {type(out).__name__}, not a list of records")
                continue
            upath = spec["unedited"]
            uname = os.path.basename(upath)
            base, base_count, why = self.read_unedited(res, upath, exp["sources"][upath], fmt, readings)
            if why:
                for c in (check, "corrupt-input-neighbours-load"):
                    res.add(c, "not-exercised", path, f"no comparison: the unedited file {uname} cannot serve as one ({why}), so nothing here isolates what the edit changes")
                continue
            got, refusals, declared = split_refusals(out)
            res.refusals[path], res.declared[path] = refusals, declared
            self.report_refusals(res, path, refusals)
            parsed = []
            for r in got:
                n, notes, bad = norm_record(r)
                n["_notes"] = notes
                if bad:
                    n["_bad"] = bad
                parsed.append(n)
            by_id = {}
            for p in parsed:
                by_id.setdefault(p.get("norad_cat_id"), []).append(p)
            ids = {r["norad_cat_id"] for r in want}
            with_reason = [x for x in refusals if x["ok"]]
            outcome = {}  # id -> (outcome, what)
            for r in want:
                cat = r["norad_cat_id"]
                if whole:
                    outcome[cat] = ("refused" if r["role"] == "corrupt" else "given up", whole)
                elif by_id.get(cat):
                    diffs = self.unedited_diffs(by_id[cat][0], base[cat]) if cat in base else ["a record the parser does not return from the unedited file"]
                    outcome[cat] = ("garbage", "; ".join(diffs[:3])) if diffs else ("loaded", None)
                elif any(x["id"] == cat for x in with_reason):
                    outcome[cat] = ("refused", next(x["reason"] for x in with_reason if x["id"] == cat))
                elif any(x["id"] == cat for x in refusals):
                    outcome[cat] = ("refused without a reason", None)
                else:
                    outcome[cat] = ("dropped", None)
            corrupt = next((r for r in want if r["role"] == "corrupt"), None)
            unmatched = [x for x in with_reason if x["id"] not in ids]
            if corrupt and outcome[corrupt["norad_cat_id"]][0] == "dropped" and unmatched:
                # a refusal that names no record of the file stands for the corrupt record, which did not come back
                outcome[corrupt["norad_cat_id"]] = ("refused", unmatched[0]["reason"])
            # records the parser does not return from the unedited file either: what it does with them here is not the edit's doing
            unread = {cat for cat in ids if cat not in base and outcome[cat][0] != "garbage"}
            # records beyond the expected ones (an id the file does not hold, a second copy), unless the unedited reading has them too
            extra = [p for k, ps in by_id.items() for p in ps[max(base_count.get(k, 0), 1 if k in ids else 0):]]
            reasons = [x["reason"] for x in with_reason] or ([whole] if whole else [])
            counts = {"expected": len(want), "returned": len(parsed),
                      "loaded": sum(1 for o, _ in outcome.values() if o == "loaded"),
                      "misidentified": sum(1 for o, _ in outcome.values() if o == "garbage") + len(extra),
                      "dropped": sum(1 for o, _ in outcome.values() if o in ("dropped", "refused without a reason")),
                      "non_integer_id": len([p for p in by_id.get(None, []) if p.get("_bad", {}).get("norad_cat_id")]),
                      "refused": len(want) if whole else len(with_reason),
                      "refused_matched": sum(1 for o, _ in outcome.values() if o in ("refused", "given up")),
                      "refused_without_reason": len(refusals) - len(with_reason), "refusals_reported": declared,
                      "top_refusal_reason": max(set(reasons), key=reasons.count) if reasons else None}
            garbage_extra = f"; {len(extra)} record(s) the file does not hold, built from garbage" if extra else ""
            # the corrupt input itself
            if corrupt is None:  # the JSON array without its closing bracket: every record complete, the file cut
                if whole:
                    status, text = "pass", f"the parser refused the file as a whole ({whole}): fail-closed; {len(want)} complete record(s) given up with it"
                elif with_reason and not extra:
                    status, text = "pass", f"the cut reported with a reason: {with_reason[0]['reason'][:120]!r}"
                else:
                    status, text = "fail", (f"{counts['loaded']} of {len(want)} record(s) loaded and nothing said of the cut "
                                            f"({spec.get('file_edit', 'the file is cut')}): silent partial loading" + garbage_extra)
            elif corrupt["norad_cat_id"] in unread:
                status, text = "not-exercised", (f"the parser does not return {corrupt['norad_cat_id']} from the unedited file {uname} either, "
                                                 "so what it does with the edited record says nothing about the edit")
            else:
                o, what = outcome[corrupt["norad_cat_id"]]
                if o == "refused":
                    status, text = "pass", (f"the parser refused the file as a whole ({whole})" + (": fail-closed for a file cut mid-record" if cut else "")
                                            if whole else f"the corrupt record refused with a reason: {what[:160]!r}")
                elif o == "loaded":
                    status = "info" if corrupt["if_read_as_unedited"] == "report" else "fail"
                    text = f"{corrupt['read_as_unedited_means']} ({corrupt['edit']})"
                elif o == "garbage":
                    status, text = "fail", f"built a record from the corrupt input: {what}"
                elif o == "refused without a reason":
                    status, text = "fail", "the corrupt record refused without a reason: no better than a drop (D-144)"
                else:
                    status, text = "fail", ("the cut row dropped with nothing said: silent partial loading" if cut else "the corrupt record dropped " +
                                            ("silently" if declared else "(refusals not reported by this adapter)"))
                if extra:
                    status, text = "fail", text + garbage_extra
            res.add(check, status, path, text, counts=counts)
            # the valid records around it, graded where the parser returns them from the unedited file
            valid = [r for r in want if r["role"] == "valid"]
            graded = [r for r in valid if r["norad_cat_id"] not in unread]
            where = "complete record(s)" if cut else "valid set(s) around the corrupt one"
            left_out = [str(r["norad_cat_id"]) for r in valid if r["norad_cat_id"] in unread]
            note = f"; not graded: {', '.join(left_out)}, which the parser does not return from the unedited file either" if left_out else ""
            label = {"garbage": "changed by the corrupt input"}
            problems = [f"{r['norad_cat_id']} {label.get(outcome[r['norad_cat_id']][0], outcome[r['norad_cat_id']][0])}"
                        + (f" ({outcome[r['norad_cat_id']][1][:160]})" if outcome[r['norad_cat_id']][1] else "")
                        for r in graded if outcome[r["norad_cat_id"]][0] != "loaded"]
            if not graded:
                res.add("corrupt-input-neighbours-load", "not-exercised", path, f"the parser returns none of the {len(valid)} {where} from the unedited file "
                        f"{uname} either, so nothing here shows what the edit changed")
            elif whole and cut:
                res.add("corrupt-input-neighbours-load", "info", path, f"{len(graded)} {where} given up with the file: a whole-file refusal of a file cut mid-record is fail-closed (owner decision 3, D-171)" + note)
            elif whole:
                res.add("corrupt-input-neighbours-load", "fail", path, f"the parser refused the file as a whole ({whole}), so the {len(graded)} {where} were given up with it" + note)
            elif problems:
                res.add("corrupt-input-neighbours-load", "fail", path, f"{len(graded) - len(problems)} of {len(graded)} {where} loaded as the parser reads them from "
                        f"the unedited file {uname}; " + "; ".join(problems) + note)
            else:
                res.add("corrupt-input-neighbours-load", "pass", path, f"{len(graded)} {where} loaded, each exactly as the parser reads it from the unedited file {uname}" + note)

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
            elif kind == "corrupt-input":
                self.run_corrupt_input(case, exp, res)
        except CorpusIncomplete:
            raise  # a broken copy of the corpus is not a result about the parser (D-148)
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
    {fmt} in the command is replaced with the file's format, the only placeholder. Exit 3 = format unsupported; any
    other non-zero exit, or output that is not a JSON array = parse failure (docs/ADAPTERS.md, D-161).
    vectors_cmd (optional): {"op", "input"} on stdin, one of {"result": value}, {"error": reason} (a rejection) or,
    from 0.5.0, {"unsupported": reason} (the operation the library does not have: the item skips) on stdout; any
    non-zero exit is a rejection, 3 included, since the vectors protocol never gave it a meaning (D-205).
    write_cmd (optional): one JSON record on stdin, the TLE lines on stdout (2 or 3 lines); exit 0 =
    written, exit 3 = writing unsupported, any other non-zero exit = the record was refused.

    A command is a shell string, as `--cmd` gives it, or an argument list, as the Node presets build it (D-154): a list
    runs without a shell, in `cwd` with `env` when given, and only an element that is exactly "{fmt}" is substituted, so
    a harness's source passed as an argument is never altered."""

    def __init__(self, cmd, vectors_cmd=None, timeout=120, write_cmd=None, cwd=None, env=None):
        self.cmd, self.vectors_cmd, self.timeout, self.write_cmd = cmd, vectors_cmd, timeout, write_cmd
        self.cwd, self.env = cwd, env

    @staticmethod
    def _stderr(p):
        """A failing command's standard error as an item's detail carries it: the last 300 characters, without the
        line ending most programs end with, which would otherwise break the report's line (D-177)."""
        return p.stderr.decode("utf-8", "replace").strip()[-300:]

    def _run(self, cmd, data, fmt=None):
        if isinstance(cmd, (list, tuple)):
            argv = [fmt if (a == "{fmt}" and fmt is not None) else a for a in cmd]
            return subprocess.run(argv, input=data, capture_output=True, timeout=self.timeout, cwd=self.cwd, env=self.env)
        if fmt is not None:
            cmd = cmd.replace("{fmt}", fmt)
        return subprocess.run(cmd, shell=True, input=data, capture_output=True, timeout=self.timeout, cwd=self.cwd, env=self.env)

    def parse(self, raw, fmt):
        if not self.cmd:
            raise Unsupported(fmt)
        p = self._run(self.cmd, raw, fmt)
        if p.returncode == 3:
            raise Unsupported(fmt)
        if p.returncode != 0:
            raise RuntimeError(f"exit {p.returncode}: {self._stderr(p)}")
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
        p = self._run(self.write_cmd, json.dumps(record, default=str).encode())
        if p.returncode == 3:
            raise Unsupported("tle-writing")
        if p.returncode != 0:
            raise RuntimeError(f"exit {p.returncode}: {self._stderr(p)}")
        return p.stdout.decode("utf-8")

    def _vec(self, op, value):
        if not self.vectors_cmd:
            raise AttributeError(op)
        p = self._run(self.vectors_cmd, json.dumps({"op": op, "input": value}).encode())
        try:
            out = json.loads(p.stdout.decode("utf-8") or "{}")
        except ValueError as e:
            raise ValueError(f"the command's output is not JSON: {e}")
        if p.returncode != 0:  # any non-zero exit is a rejection, 3 included (D-205)
            raise ValueError(out.get("error", f"exit {p.returncode}"))
        if "unsupported" in out:  # an operation the library does not have: the item skips (D-205)
            reason = out["unsupported"]
            if not isinstance(reason, str) or not reason.strip():
                raise ValueError("the command's unsupported answer carries no reason")
            raise Unsupported(reason.strip())
        if "error" in out:
            raise ValueError(out["error"])
        if "result" not in out:  # a well-formed answer carries result, error or unsupported (D-118, D-205)
            raise ValueError("the command's answer carries neither 'result', 'error' nor 'unsupported'")
        return out["result"]

    def __getattr__(self, name):
        if name in ("alpha5_decode", "alpha5_encode", "two_digit_year", "parse_epoch", "parse_catalog_id") and self.vectors_cmd:
            def hook(value):
                r = self._vec(name, value if not isinstance(value, dt.datetime) else value.isoformat())
                return dt.datetime.fromisoformat(r) if name == "parse_epoch" else r
            return hook
        raise AttributeError(name)
