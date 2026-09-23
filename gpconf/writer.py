"""
gpconf/writer.py -- checks for code that WRITES TLE lines.

The parser cases ask "does my parser survive the migration?"; the writer case asks the same of code
that produces TLEs: is the catalog number written as Alpha-5 above 99999, are the lines 69 characters
with a valid checksum, is a number the format cannot carry (above 339999, or negative) refused rather
than written as six digits or a blank field, and do the written lines read back to the record's values
at the TLE field's own resolution.

Standard library only. Used by the runner for the case kind 'writer' and by `python -m gpconf check-tle`,
which applies the same checks to a TLE file written by a tool that cannot be wrapped by an adapter.

Writer protocol (duck-typed, optional on any adapter):
    write_tle(record: dict) -> (line1, line2) | (line0, line1, line2) | text block
        record uses the parse() key names (norad_cat_id as int, epoch as ISO text or datetime, element
        values as decimal text, Decimal, int or float). Raise any exception to refuse a record; for a
        catalog number the TLE format cannot represent, refusing IS the correct output.

Precision rule: a TLE field has a fixed resolution (epoch 1e-8 day; mean motion 8 decimals; angles 4;
eccentricity 7 digits; BSTAR and the derivatives a 5-digit mantissa). A written field is correct when it
equals the input quantised at that resolution either by truncation or by rounding half up: CelesTrak
truncates the eccentricity and rounds the mantissas, Space-Track rounds both (DECISIONS D-070, D-071),
so both conventions are accepted and the one observed is reported. This is the format's resolution,
not a tolerance: the comparison is exact against one of the two renderings.
"""
import datetime as dt
import re
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP

from . import reference as ref
from . import tle as T

ALPHA5_CEILING = 339999
ELEMENT_FIELDS = ["epoch", "mean_motion", "eccentricity", "inclination", "ra_of_asc_node", "arg_of_pericenter", "mean_anomaly", "bstar"]
SECONDARY_FIELDS = ["mean_motion_dot", "mean_motion_ddot", "element_set_no", "rev_at_epoch", "classification_type", "object_id", "object_name"]
DECIMALS = {"mean_motion": 8, "inclination": 4, "ra_of_asc_node": 4, "arg_of_pericenter": 4, "mean_anomaly": 4, "mean_motion_dot": 8}
EXP_FIELDS = {"bstar", "mean_motion_ddot"}
PROVIDER_FIELDS = ["epoch_field", "ndot_field", "nddot_field", "bstar_field", "ecc_field", "element_set_field", "rev_field", "intl_designator_field"]


def representable(n):
    """True when the TLE catalog field can carry n (0..339999 -> five digits or Alpha-5)."""
    return 0 <= int(n) <= ALPHA5_CEILING


def strict_catalog_field(field):
    """Columns 3-7 as written -> int. Five digits, or one uppercase letter of the Space-Track table (I and O
    never) followed by four digits. Anything else (blank, lowercase, six digits, letter elsewhere) raises."""
    if len(field) != 5 or field != field.strip():
        raise ValueError(f"catalog field {field!r} is not five non-blank characters")
    if field.isdigit():
        return int(field)
    if field[0] in T.ALPHA5_LETTERS and field[1:].isdigit():
        return T.from_alpha5(field)
    raise ValueError(f"catalog field {field!r} is neither five digits nor Alpha-5")


def normalise_lines(out):
    """Adapter output -> (line0 or None, line1, line2). Accepts a sequence of 2 or 3 strings, or one text block."""
    if isinstance(out, (bytes, bytearray)):
        out = out.decode("utf-8")
    if isinstance(out, str):
        out = [l for l in out.splitlines() if l.strip()]
    lines = [str(l).rstrip("\r\n") for l in out]
    if len(lines) == 2:
        return None, lines[0], lines[1]
    if len(lines) == 3:
        return lines[0], lines[1], lines[2]
    raise ValueError(f"writer returned {len(lines)} line(s); expected 2 (line 1, line 2) or 3 (name, line 1, line 2)")


def check_lines(l1, l2):
    """Length and checksum of both lines -> list of problems (empty = valid)."""
    problems = []
    for name, l in (("line 1", l1), ("line 2", l2)):
        if len(l) != 69:
            problems.append(f"{name} is {len(l)} characters, not 69")
        elif l[68] != str(T.checksum(l)):
            problems.append(f"{name} checksum {l[68]!r}, computed {T.checksum(l)}")
    if l1[:2] != "1 " or l2[:2] != "2 ":
        problems.append("lines do not start with '1 ' and '2 '")
    return problems


def check_catalog_field(l1, l2, norad_cat_id):
    """-> (ok, detail). Columns 3-7 of both lines must equal the strict encoding of the id."""
    want = T.to_alpha5(norad_cat_id)  # callers test representable() first; raises otherwise
    f1, f2 = l1[2:7], l2[2:7]
    if f1 != f2:
        return False, f"line 1 field {f1!r} differs from line 2 field {f2!r} (expected {want!r})"
    if f1 != want:
        try:
            why = f"decodes to {strict_catalog_field(f1)}"
        except ValueError as e:
            why = str(e)
        return False, f"field {f1!r} written for {norad_cat_id} (expected {want!r}; {why})"
    return True, want


def _iso(v):
    if isinstance(v, dt.datetime):
        if v.tzinfo is not None:
            v = v.astimezone(dt.timezone.utc).replace(tzinfo=None)
        return v.strftime("%Y-%m-%dT%H:%M:%S.%f")
    return str(v).strip()


def quantised(field, value):
    """The input value at the field's resolution, both ways -> {'truncate': Decimal, 'round': Decimal}."""
    d = Decimal(repr(value) if isinstance(value, float) else str(value))
    text = format(d, "f")
    if field == "eccentricity":
        return {m: Decimal("0." + T.ecc_field(text, m)) for m in ("truncate", "round")}
    if field in EXP_FIELDS:
        return {m: Decimal(ref.tle_exp_to_plain(T.exp_field(text, m))) for m in ("truncate", "round")}
    q = Decimal(1).scaleb(-DECIMALS[field])
    return {"truncate": d.quantize(q, rounding=ROUND_DOWN), "round": d.quantize(q, rounding=ROUND_HALF_UP)}


def _classify(written, exact, q):
    """-> 'exact' | 'quantised' | 'truncate' | 'round' | None (mismatch)."""
    if written == exact:
        return "exact"
    if q["truncate"] == q["round"]:
        return "quantised" if written == q["truncate"] else None
    if written == q["truncate"]:
        return "truncate"
    if written == q["round"]:
        return "round"
    return None


def round_trip(l0, l1, l2, record):
    """Read the written lines back with the reference reader and compare the element fields with the record.
    -> (mismatches: list[str], conventions: {field: 'exact'|'quantised'|'truncate'|'round'})."""
    got = ref.parse_tle_lines(l0, l1, l2)
    mismatches, conventions = [], {}
    for f in ELEMENT_FIELDS:
        want = record.get(f)
        if want is None or want == "":
            continue
        if f == "epoch":
            iso = _iso(want)
            q = {"truncate": T.epoch_field(iso, ROUND_DOWN), "round": T.epoch_field(iso, ROUND_HALF_UP)}
            written, exact = got["tle"]["epoch_field"], (q["truncate"] if q["truncate"] == q["round"] else None)
        else:
            q = quantised(f, want)
            written = Decimal(str(got[f]))
            exact = Decimal(repr(want) if isinstance(want, float) else str(want))
        k = _classify(written, exact, q)
        if k is None:
            mismatches.append(f"{f}: written {written} for input {exact if exact is not None else want} (acceptable: {q['truncate']} or {q['round']})")
        else:
            conventions[f] = k
    return mismatches, conventions


def secondary_fields(l0, l1, l2, record):
    """How the writer treated the fields a fitting tool may legitimately regenerate. -> {field: status,
    'zero_ddot_sign': '+'|'-'|None}. Statuses: preserved | zeroed | dropped | cut-to-24 | changed."""
    got = ref.parse_tle_lines(l0, l1, l2)
    out = {}
    for f in ("mean_motion_dot", "mean_motion_ddot"):
        w = Decimal(str(record.get(f) or 0))
        g = Decimal(str(got[f] or 0))
        if g == w or (w != 0 and _classify(g, w, quantised(f, w)) is not None):
            out[f] = "preserved"
        else:
            out[f] = "zeroed" if g == 0 else "changed"
    for f in ("element_set_no", "rev_at_epoch"):
        w, g = int(record.get(f) or 0), int(got[f] or 0)
        out[f] = "preserved" if g == w else ("zeroed" if g == 0 else "changed")
    out["classification_type"] = "preserved" if got["classification_type"] == (record.get("classification_type") or "U") else "changed"
    w, g = record.get("object_id") or None, got.get("object_id")
    out["object_id"] = "preserved" if g == w else ("dropped" if g is None else "changed")
    name = (record.get("object_name") or "").strip()
    if l0 is None:
        out["object_name"] = "dropped" if name else "preserved"
    else:
        g = l0.strip()
        out["object_name"] = "preserved" if g == name else ("cut-to-24" if len(name) > 24 and g == name[:24].strip() else "changed")
    nddot = got["tle"]["nddot_field"]
    out["zero_ddot_sign"] = nddot[6] if nddot[1:6] == "00000" else None
    return out


def provider_field_matches(l1, l2, reference_fields):
    """Which written fields are byte-identical to the provider's (or the derived) rendering -> {field: bool}."""
    got = ref.parse_tle_lines(None, l1, l2)["tle"]
    return {k: got.get(k) == v for k, v in reference_fields.items() if k in PROVIDER_FIELDS}


# --------------------------------------------------------------------------- files written by a tool (check-tle)
WIDE_NUMBER = re.compile(r"^1 (\d{6,9})")


def extract_records(text):
    """TLE text -> [(line0 or None, line1, line2, line number of line 1)]. A '1 ' line followed by a '2 ' line is a
    record whatever their lengths (a 70-character line must be reported, not skipped); the preceding line is the
    name unless it is another element line, blank, or a '#' comment such as rffit's trailer. Trailing whitespace
    and line endings are removed; nothing else is changed."""
    lines = [l.rstrip() for l in text.splitlines()]
    out, i = [], 0
    while i < len(lines):
        if lines[i].startswith("1 ") and i + 1 < len(lines) and lines[i + 1].startswith("2 "):
            prev = lines[i - 1] if i > 0 else ""
            l0 = prev if prev.strip() and prev[:2] not in ("1 ", "2 ") and not prev.startswith("#") else None
            out.append((l0, lines[i], lines[i + 1], i + 1))
            i += 2
        else:
            i += 1
    return out


def check_record(l0, l1, l2, against=None):
    """One written record -> dict with status ('pass' | 'fail'), catalog_field, norad_cat_id (None when the field
    is invalid), problems (format failures, and round-trip mismatches when `against` is given), notes, and, when
    `against` supplies the source record, round_trip and secondary_fields. `against` maps id -> source record."""
    r = {"name": (l0 or "").strip() or None, "catalog_field": l1[2:7], "norad_cat_id": None, "problems": [], "notes": []}
    r["problems"] += check_lines(l1, l2)
    m = WIDE_NUMBER.match(l1)
    if m:
        n = int(m.group(1))
        r["problems"].append(f"{len(m.group(1))}-digit catalog number {n} written from column 3: "
                             + (f"the field must be the Alpha-5 form {T.to_alpha5(n)!r}" if representable(n)
                                else "the TLE format cannot carry it; the correct output is a refusal (use an OMM format)"))
    else:
        try:
            r["norad_cat_id"] = strict_catalog_field(l1[2:7])
            if l2[2:7] != l1[2:7]:
                r["problems"].append(f"line 2 catalog field {l2[2:7]!r} differs from line 1 {l1[2:7]!r}")
            elif r["norad_cat_id"] >= 100000:
                r["notes"].append(f"Alpha-5 field {l1[2:7]} decodes to {r['norad_cat_id']}")
        except ValueError as e:
            r["problems"].append(str(e))
    if len(l1) == 69 and len(l2) == 69 and r["norad_cat_id"] is not None and not r["problems"]:
        try:
            rec = ref.parse_tle_lines(l0, l1, l2)
        except Exception as e:
            r["problems"].append(f"reference reader raised {type(e).__name__}: {e}")
            rec = None
        if rec is not None:
            r["epoch"] = rec["epoch"]
            nddot = rec["tle"]["nddot_field"]
            if nddot[1:6] == "00000":
                r["notes"].append(f"zero second derivative written with exponent sign '{nddot[6]}' (CelesTrak writes +, Space-Track -)")
            if against is not None:
                src = against.get(r["norad_cat_id"])
                if src is None:
                    # a written id the source records do not contain is a failure, not a note (D-112): the record is
                    # about some other object, or about none. Two values name the likely cause on the rffit path.
                    why = ""
                    if r["norad_cat_id"] == 0:
                        why = " (likely cause: 00000 is what rffit writes when its -i lookup found no elements and the orbit stayed zero-initialised, e.g. an Alpha-5 field passed through satno2tle)"
                    elif r["norad_cat_id"] == 99999:
                        why = " (likely cause: 99999 is rffit's default catalog number)"
                    r["problems"].append(f"no source record with id {r['norad_cat_id']} in the --against file{why}; the round trip cannot be checked")
                else:
                    mism, conv = round_trip(l0, l1, l2, src)
                    r["round_trip"] = {"mismatches": mism, "conventions": conv}
                    r["problems"] += [f"round trip: {x}" for x in mism]
                    r["secondary_fields"] = secondary_fields(l0, l1, l2, src)
    r["status"] = "fail" if r["problems"] else "pass"
    return r


def check_file(text, against=None):
    """-> one check_record result per TLE record found in the text (with its line number); [] when none is found."""
    return [dict(check_record(l0, l1, l2, against), line_number=n) for l0, l1, l2, n in extract_records(text)]


def load_against(path):
    """Source records for --against, in any format the reference reader knows (csv, json, xml, kvn, tle, 2le)
    -> {norad_cat_id: record}."""
    _, recs, _ = ref.read_file(path)
    return {r["norad_cat_id"]: r for r in recs}
