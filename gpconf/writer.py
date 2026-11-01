# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""
gpconf/writer.py -- checks for code that WRITES TLE lines.

The parser cases ask "does my parser survive the migration?"; the writer case asks the same of code
that produces TLEs: is the catalog number written as Alpha-5 above 99999, are the lines 69 characters
with a valid checksum, is a number the format cannot carry (above 339999, or negative) refused rather
than written as six digits or a blank field, and do the written lines read back to the record's values
at the TLE field's own resolution.

Standard library only. Used by the runner for the case kind 'writer' and by `python -m gpconf check-tle`,
which applies the same checks to a TLE file written by a tool that cannot be wrapped by an adapter. The checks:
length and checksum (check_lines), the catalog field (check_catalog_field), every field in its fixed columns
(check_layout), the round trip through the reference reader (round_trip) and the secondary fields (information).

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
from .words import qty

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
    raise ValueError(f"writer returned {qty(len(lines), 'line')}; expected 2 (line 1, line 2) or 3 (name, line 1, line 2)")


def check_lines(l1, l2):
    """Length and checksum of both lines -> list of problems (empty = valid)."""
    problems = []
    for name, l in (("line 1", l1), ("line 2", l2)):
        if len(l) != 69:
            problems.append(f"{name} is {qty(len(l), 'character')}, not 69")
        elif not l.isascii():
            # a TLE line is ASCII (D-325): a digit of another script read as the digit it stands for in the layout and the
            # round trip, so a writer that put one in an element field and recomputed its checksum passed the case
            bad = next((i, c) for i, c in enumerate(l) if not c.isascii())
            problems.append(f"{name} column {bad[0] + 1} holds {bad[1]!r}, which is not ASCII")
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
        return T.epoch_text(v)
    return T.iso_epoch(v)  # a source record may carry the day-of-year form (legal; the KVN case declares it) (D-119)


# The fixed columns of a TLE (CelesTrak's format description; 1-based columns in the names, 0-based slices here).
# Length and checksum say nothing about alignment: a left-justified value with a recomputed checksum passes both.
_NUM8 = r" {0,2}\d{1,3}\.\d{4}"
LAYOUT = {
    1: [(0, 2, "line number and separator", r"1 "), (7, 8, "classification", r"[A-Z]"), (8, 9, "separator", r" "),
        (9, 17, "international designator", r"[A-Z0-9 ]{8}"), (17, 18, "separator", r" "),
        (18, 32, "epoch YYDDD.DDDDDDDD", r"\d{5}\.\d{8}"), (32, 33, "separator", r" "),
        (33, 43, "first derivative", r"[ +-]\.\d{8}"), (43, 44, "separator", r" "),
        (44, 52, "second derivative", r"[ +-]\d{5}[+-]\d"), (52, 53, "separator", r" "),
        (53, 61, "BSTAR", r"[ +-]\d{5}[+-]\d"), (61, 62, "separator", r" "),
        (62, 63, "ephemeris type", r"\d"), (63, 64, "separator", r" "),
        (64, 68, "element set number, right-justified", r" *\d+")],
    2: [(0, 2, "line number and separator", r"2 "), (7, 8, "separator", r" "),
        (8, 16, "inclination, right-justified nnn.nnnn", _NUM8), (16, 17, "separator", r" "),
        (17, 25, "RA of ascending node, right-justified nnn.nnnn", _NUM8), (25, 26, "separator", r" "),
        (26, 33, "eccentricity, seven digits", r"\d{7}"), (33, 34, "separator", r" "),
        (34, 42, "argument of pericenter, right-justified nnn.nnnn", _NUM8), (42, 43, "separator", r" "),
        (43, 51, "mean anomaly, right-justified nnn.nnnn", _NUM8), (51, 52, "separator", r" "),
        (52, 63, "mean motion, right-justified nn.nnnnnnnn", r" ?\d{1,2}\.\d{8}"),
        (63, 68, "revolution number, right-justified", r" *\d+")],
}


def check_layout(l1, l2):
    """Every field in its fixed columns -> list of problems (empty = standard layout). Call on 69-character lines;
    columns 3-7 and the checksum are checked elsewhere (D-119)."""
    problems = []
    for n, line in ((1, l1), (2, l2)):
        for a, b, name, pat in LAYOUT[n]:
            sub = line[a:b]
            if not re.fullmatch(pat, sub, re.ASCII):   # \d is an ASCII digit here, as everywhere a line is read (D-325)
                problems.append(f"line {n} columns {a + 1}-{b} ({name}): {sub!r}")
    return problems


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
    got = ref.parse_tle_lines(l0, l1, l2, written=True)
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
    got = ref.parse_tle_lines(l0, l1, l2, written=True)
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
    got = ref.parse_tle_lines(None, l1, l2, written=True)["tle"]
    return {k: got.get(k) == v for k, v in reference_fields.items() if k in PROVIDER_FIELDS}


# --------------------------------------------------------------------------- files written by a tool (check-tle)
WIDE_NUMBER = re.compile(r"^1 (\d{6,9})")


def _kind(line):
    """'1' | '2' | None for an element line, with any indentation ignored (reported separately)."""
    s = line.lstrip()
    return s[0] if s[:2] in ("1 ", "2 ") else None


def scan_lines(text):
    """TLE text -> (records, strays). records: [(line0 or None, line1, line2, line number of line 1, pre-problems,
    pre-notes)];
    strays: [(line number, line, problem)] for element lines that pair with nothing. A '1 ' line followed by a '2 '
    line is a record whatever their lengths (a 70-character line must be reported, not skipped); the preceding line
    is the name unless it is another element line, blank, or a '#' comment such as rffit's trailer. An indented
    element pair is checked with the indentation removed and the indentation reported; a byte-order mark is reported
    on the first record. Trailing whitespace and line endings are removed; nothing else is changed (D-119: none of
    these used to be reported). Trailing whitespace on an element line is reported as a note, which lines and which
    columns, never as a failure: a card image's blanks past column 69 are no fault of the values (D-338, the owner's
    ruling), but no TLE line carries them."""
    bom = text.startswith("\ufeff")
    raw = (text[1:] if bom else text).splitlines()
    lines = [l.rstrip() for l in raw]
    records, strays, i = [], [], 0
    bom_note = "the file starts with a UTF-8 byte-order mark (BOM, three bytes before the first line); TLE readers expect none"
    while i < len(lines):
        k = _kind(lines[i])
        if k == "1" and i + 1 < len(lines) and _kind(lines[i + 1]) == "2":
            pre = []
            if bom:
                pre.append(bom_note)
                bom = False
            notes = []
            for n, set_line, l in ((i + 1, 1, lines[i]), (i + 2, 2, lines[i + 1])):
                ind = len(l) - len(l.lstrip())
                if ind:
                    pre.append(f"line {n} is indented by {qty(ind, 'space or tab', 'spaces or tabs')}; a TLE line starts at column 1")
                tail = raw[n - 1][len(l):]
                if tail:   # an element line only: CelesTrak pads its names to 24 columns, so a name's blanks say nothing
                    what = qty(len(tail), "trailing blank") if not tail.strip(" ") else qty(len(tail), "trailing whitespace character")
                    cols = f"column {len(l) + 1}" if len(tail) == 1 else f"columns {len(l) + 1} to {len(raw[n - 1])}"
                    card = not tail.strip(" ") and len(l.lstrip()) == 69 and len(raw[n - 1]) <= 80
                    notes.append(f"file line {n} (the set's line {set_line}) carries {what} ({cols}), taken off before the checks; "
                                 "no TLE line carries any" + (" (an 80-column card image's padding, perhaps)" if card else ""))
            prev = lines[i - 1] if i > 0 else ""
            l0 = prev if prev.strip() and _kind(prev) is None and not prev.startswith("#") else None
            records.append((l0, lines[i].lstrip(), lines[i + 1].lstrip(), i + 1, pre, notes))
            i += 2
        elif k == "1":
            strays.append((i + 1, lines[i], "a line 1 with no line 2 following it; the record cannot be checked"))
            i += 1
        elif k == "2":
            strays.append((i + 1, lines[i], "a line 2 with no line 1 before it; the record cannot be checked"))
            i += 1
        else:
            i += 1
    if bom:
        strays.append((1, lines[0] if lines else "", bom_note))
    return records, strays


def extract_records(text):
    """TLE text -> [(line0 or None, line1, line2, line number of line 1)] (the records scan_lines finds)."""
    return [(l0, l1, l2, n) for l0, l1, l2, n, _, _ in scan_lines(text)[0]]


def check_record(l0, l1, l2, against=None):
    """One written record -> dict with status ('pass' | 'fail' | 'not compared', the last where the source holds the
    record's id more than once, D-370), catalog_field, norad_cat_id (None when the field
    is invalid), problems (format failures, and round-trip mismatches when `against` is given), notes, and, when
    `against` supplies the source record, round_trip and secondary_fields. `against` maps id -> source record."""
    r = {"name": (l0 or "").strip() or None, "catalog_field": l1[2:7], "norad_cat_id": None, "problems": [], "notes": []}
    r["problems"] += check_lines(l1, l2)
    m = WIDE_NUMBER.match(l1)
    if m:
        n = int(m.group(1))
        r["written_id"] = n   # written, in a form the format does not allow: the record fails, the id is not lost (D-369)
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
    if len(l1) == 69 and len(l2) == 69:
        r["problems"] += check_layout(l1, l2)  # a shifted field with a recomputed checksum has the right length and checksum (D-119)
    if len(l1) == 69 and len(l2) == 69 and r["norad_cat_id"] is not None and not r["problems"]:
        try:
            rec = ref.parse_tle_lines(l0, l1, l2, written=True)
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
                elif getattr(against, "held", {}).get(r["norad_cat_id"], 1) > 1:
                    # a source that holds an id more than once (a history) cannot yet say which of its records this
                    # copy was written from: not compared rather than failed against the wrong one (the owner's
                    # ruling on D-369's reading; per-epoch pairing comes in 0.8.1)
                    r["notes"].append(f"not compared: source holds {against.held[r['norad_cat_id']]} copies (per-epoch pairing comes in 0.8.1)")
                    r["not_compared"] = True
                else:
                    try:
                        mism, conv = round_trip(l0, l1, l2, src)
                        r["round_trip"] = {"mismatches": mism, "conventions": conv}
                        r["problems"] += [f"round trip: {x}" for x in mism]
                        r["secondary_fields"] = secondary_fields(l0, l1, l2, src)
                    except Exception as e:  # a source value the corpus cannot read is a problem on the record, not a crash (D-119)
                        r["problems"].append(f"round trip could not be checked: {type(e).__name__}: {e}")
    # a record whose round trip was not made is neither a pass nor a fail: its status says so (D-370; the second
    # blind review's F1: it read [pass], and the run exited 0, for wrong values written under such an id)
    r["status"] = "fail" if r["problems"] else ("not compared" if r.get("not_compared") else "pass")
    return r


def check_file(text, against=None):
    """-> one result per TLE record found in the text (with its line number) plus one failing entry per element
    line that pairs with nothing ('unpaired': True); [] when the text holds no element line at all."""
    records, strays = scan_lines(text)
    out = []
    for l0, l1, l2, n, pre, notes in records:
        r = dict(check_record(l0, l1, l2, against), line_number=n)
        r["notes"] = notes + r["notes"]   # information, never a failure: the exit code is as before (D-338)
        if pre:
            r["problems"] = pre + r["problems"]
            r["status"] = "fail"
        out.append(r)
    for n, line, problem in strays:
        out.append({"name": None, "catalog_field": line.lstrip()[2:7], "norad_cat_id": None, "problems": [problem], "notes": [],
                    "status": "fail", "line_number": n, "unpaired": True})
    return sorted(out, key=lambda r: r["line_number"])


class Against(dict):
    """{norad_cat_id: record} for the round trip, and `held`, how many of the source's records carry each id, so that a
    source record no file wrote, or an id written more often than the source holds it, is seen (D-369)."""

    held: dict
    without_id: int


def load_against(path):
    """Source records for --against, in any format the reference reader knows (csv, json, xml, kvn, tle, 2le)
    -> Against, {norad_cat_id: record} with each id's count of source records in `held`, and in `without_id` the
    source records that carry no catalog number, which no written record can be held to. For an id the source holds
    more than once no round trip is made: the record is noted "not compared" (D-369; per-epoch pairing comes in 0.8.1)."""
    _, recs, _ = ref.read_file(path)
    out = Against((r["norad_cat_id"], r) for r in recs if r["norad_cat_id"] is not None)
    out.held, out.without_id = {}, 0
    for r in recs:
        if r["norad_cat_id"] is None:
            out.without_id += 1
        else:
            out.held[r["norad_cat_id"]] = out.held.get(r["norad_cat_id"], 0) + 1
    return out


def source_coverage(results, against):
    """The written records of every file checked, against the source records (D-369; the red team's finding 1 on the
    0.8.0 candidate): `not_written`, (id, written, held) where the files wrote an id the format can carry fewer times
    than the source holds it, none at all included, a failure; `written_more`, (id, written, held) where they wrote it
    more often, a failure; and `refusal_correct`, ids no file wrote that the TLE format cannot carry, for which a
    refusal was the correct output, information; and `not_compared`, (id, held) for an id the source holds more than
    once and a file wrote, whose round trip is not made (information; per-epoch pairing comes in 0.8.1). A record written in a form the format does not allow (a six-digit
    number from column 3) fails on its own and counts as written (`written_id`). The secondary fields stay information
    (D-095)."""
    written = {}
    for r in results:
        k = r.get("norad_cat_id") if r.get("norad_cat_id") is not None else r.get("written_id")
        if not r.get("unpaired") and k is not None:
            written[k] = written.get(k, 0) + 1
    held = getattr(against, "held", None) or {k: 1 for k in against if k is not None}
    return {"not_compared": [(k, h) for k, h in sorted(held.items()) if h > 1 and k in written],
            "not_written": [(k, written.get(k, 0), h) for k, h in sorted(held.items()) if representable(k) and written.get(k, 0) < h],
            "refusal_correct": [k for k in sorted(held) if not representable(k) and k not in written],
            "written_more": [(k, n, held[k]) for k, n in sorted(written.items()) if k in held and n > held[k]]}
