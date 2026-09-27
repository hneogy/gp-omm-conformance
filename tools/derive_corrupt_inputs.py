#!/usr/bin/env python3
"""
tools/derive_corrupt_inputs.py -- the inputs of the corrupt-input case (D-171; v0.4.0 plan, section 5, inputs 1 to 5).

Corrupt provider output cannot be captured on demand, so each input is made: a real record frozen in this corpus with
one stated edit, placed between valid real records so that the records around it measure whether a parser picks up
again after it. Provenance synthetic-derived under the D-096 precedent; the owner approved the five inputs on
2026-09-27.

Every record is rendered by the corpus from values frozen in the public fixtures/<case>/expected.json files; no
provider file is read, so a public clone rebuilds the same bytes. TLE lines come from gpconf/tle.py's renderer with
CelesTrak's conventions (the settings of tools/derive_alpha5.py), checked against each record's frozen TLE field
substrings; for these five-digit records the unedited lines equal CelesTrak's own. The CSV and JSON files follow
CelesTrak's column order and line endings and write the frozen values as they are, in plain decimal notation.

Beside the inputs, three unedited files (D-175): the same records, laid out as the inputs lay them out, with no edit.
The runner compares every record a parser returns from an input with the same parser's reading of the matching
unedited file, so that the case measures what the edit changes, and leaves how exactly a parser reads these records to
the values check, which grades that on the same records in their own cases.

Output: derived/corrupt-input/<name>.<fmt> and <name>.provenance.json for each input and each unedited file.
"""
import csv
import datetime as dt
import hashlib
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from gpconf import reference as ref  # noqa: E402
from gpconf import tle as T  # noqa: E402

OUT = os.path.join(ROOT, "derived", "corrupt-input")
NOW = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
EOL = "\r\n"  # CelesTrak's TLE, CSV and JSON files end their lines with CRLF
RENDER = {"mantissa_mode": "round", "ecc_mode": "truncate"}  # the derived Alpha-5 files' settings: CelesTrak's rendering
CSV_COLUMNS = ref.CELESTRAK_CSV_JSON_KEYS
APPROVAL = ("owner approval 2026-09-27 of the v0.4.0 plan's inputs 1 to 5 (section 5) with decisions 2 to 4 of its "
            "section 10; synthetic-derived provenance under the D-096 precedent (PLAN.md section 2.1); DECISIONS D-171")
EDITED = "SYNTHETIC-DERIVED: real records frozen in this corpus, rendered by the corpus, with one stated edit; served by no provider"
UNEDITED = "DERIVED: real records frozen in this corpus, rendered by the corpus with no edit; served by no provider"
UNEDITED_BASIS = ("DECISIONS D-175 (owner instruction 2026-09-27): what a parser returns from each corrupt input is "
                  "compared with what the same parser returns from this file, the same records with no edit")

# The records: the corrupt input is always made from 69999's first record (stable tier); the valid neighbours are
# 25544's first record (stable) and 20453 from the decaying snapshot (live tier: its values are frozen in the case's
# expected.json as the snapshot of 2026-09-21). All three are five-digit records with a full international designator,
# so no neighbour trips a parser for a reason that has nothing to do with the corrupt input (an Alpha-5 field, a blank
# designator).
BEFORE = {"case": "epoch-year-19xx", "set": "iss-first", "norad_cat_id": 25544}
CORRUPT = {"case": "bstar-and-derivative-forms", "set": "gp-69999-first", "norad_cat_id": 69999}
AFTER = {"case": "bstar-and-derivative-forms", "set": "decaying", "norad_cat_id": 20453}


def frozen(spec):
    """The record as frozen in its case's expected.json, with where its values came from."""
    path = f"fixtures/{spec['case']}/expected.json"
    with open(os.path.join(ROOT, path)) as f:
        e = json.load(f)
    r = next(r for r in e["records"] if r.get("set") == spec["set"] and r["norad_cat_id"] == spec["norad_cat_id"])
    src = next(p for p in e["sources"] if os.path.basename(p) == r["canonical_source"])
    return r, {"norad_cat_id": r["norad_cat_id"], "values_from": path, "set": spec["set"], "tier": r["tier"],
               "source_file": src, "source_sha256": e["sources"][src]["sha256"]}


def tle(spec):
    """(line0, line1, line2) rendered from the frozen values and checked against the record's frozen TLE fields."""
    r, where = frozen(spec)
    lines = T.render(T.omm_fields_from_record(r["canonical"]), **RENDER)
    fields = ref.parse_tle_lines(*lines)["tle"]
    want = r["by_format"]["tle"]["fields"]
    differ = [k for k in want if k != "line_lengths" and fields.get(k) != want[k]]
    if differ:
        sys.exit(f"{spec}: the rendering differs from the frozen TLE fields {differ}; nothing written")
    return lines, where


def omm_row(spec):
    r, where = frozen(spec)
    c = r["canonical"]
    return {k: c[ref.TEXT_KEYS.get(k) or ref.INT_KEYS.get(k) or ref.DECIMAL_KEYS[k]] for k in CSV_COLUMNS}, where


def csv_text(rows):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator=EOL)
    w.writerow(CSV_COLUMNS)
    for row in rows:
        w.writerow(["" if row[k] is None else row[k] for k in CSV_COLUMNS])
    return buf.getvalue()


def json_object(row):
    """One record as CelesTrak writes it: its keys in column order, numbers as JSON numbers, written here from the
    frozen decimal text itself so that no value passes through a binary float."""
    parts = []
    for k in CSV_COLUMNS:
        v = row[k]
        if v is None:
            val = "null"
        elif k in ref.DECIMAL_KEYS or k in ref.INT_KEYS:
            val = str(v)
        else:
            val = json.dumps(v)
        parts.append(f"{json.dumps(k)}:{val}")
    return "{" + ",".join(parts) + "}"


def tle_text(sets):
    return "".join(EOL.join(s) + EOL for s in sets)


def write(name, text, meta, edited=True):
    os.makedirs(OUT, exist_ok=True)
    data = text.encode("utf-8")
    path = os.path.join(OUT, name)
    with open(path, "wb") as f:
        f.write(data)
    stem = name.rsplit(".", 1)[0]
    meta = {"file": f"derived/corrupt-input/{name}", "provenance": "synthetic-derived" if edited else "derived",
            "label": EDITED if edited else UNEDITED, **meta,
            **({"owner_approval": APPROVAL} if edited else {"basis": UNEDITED_BASIS}), "generator": "tools/derive_corrupt_inputs.py",
            "generated_at": NOW, "line_endings": "CRLF", "bytes": len(data), "output_sha256": hashlib.sha256(data).hexdigest()}
    with open(os.path.join(OUT, stem + ".provenance.json"), "w") as f:
        json.dump(meta, f, indent=2)
        f.write("\n")
    print(f"{meta['file']}: {len(data)} bytes, sha256 {meta['output_sha256'][:16]}...")


def main():
    before, w_before = tle(BEFORE)
    corrupt, w_corrupt = tle(CORRUPT)
    after, w_after = tle(AFTER)
    rendering = {"renderer": "gpconf/tle.py render", "settings": RENDER,
                 "checked_against": "each record's frozen TLE field substrings (by_format.tle.fields in its expected.json): equal",
                 "note": "for these five-digit records the renderer reproduces CelesTrak's own lines (tools/validate_render.py, 304 of 304 records)"}

    def records(corrupt_edit):
        return [{"position": 1, "role": "valid", **w_before},
                {"position": 2, "role": "corrupt", **w_corrupt, "edit": corrupt_edit},
                {"position": 3, "role": "valid", **w_after}]

    l0, l1, l2 = corrupt

    # Input 1: line 1's checksum digit replaced by another digit; every other character real.
    was = l1[68]
    now = str((int(was) + 5) % 10)
    edit = {"line": 1, "column": 69, "was": was, "now": now,
            "statement": f"line 1's checksum digit (column 69) changed from {was} to {now}; every other character is the real line"}
    write("c1-checksum-digit.tle", tle_text([before, (l0, l1[:68] + now, l2), after]),
          {"input": 1, "check": "corrupt-tle-checksum-digit", "description": "A set whose line 1 carries a wrong checksum digit, between two valid sets.",
           "rendering": rendering, "records": records(edit)})

    # Input 2: line 2 one character short, the character lost mid-line: the fourth digit of the eccentricity (column 30),
    # so that every column after it moves one to the left and a reader of fixed columns gets wrong values. A cut at the
    # end would take only the checksum digit and leave every value readable, which is not the garbage case, and
    # accepting a malformed line whose values survive is what input 1 already covers (owner decision, D-171).
    k = 29
    assert l2[26:33][k - 26].isdigit()
    edit = {"line": 2, "column": k + 1, "was": l2[k], "now": "",
            "statement": f"line 2's character at column {k + 1}, the fourth digit of the eccentricity ({l2[26:33]!r} becomes "
                         f"{(l2[:k] + l2[k + 1:])[26:32]!r}), removed: the line is 68 characters and every column after the cut has moved one to the left"}
    write("c2-line-2-short.tle", tle_text([before, (l0, l1, l2[:k] + l2[k + 1:]), after]),
          {"input": 2, "check": "corrupt-tle-line-short", "description": "A set whose line 2 is one character short, between two valid sets.",
           "rendering": rendering, "records": records(edit)})

    # Input 3: a letter in a numeric column: the first 0 among the epoch field's fractional digits becomes the letter O.
    # A letter counts 0 in the checksum, as the 0 it replaces did, so the line's checksum stays valid and the letter is
    # the only defect: a parser that relies on the checksum alone does not see it.
    col = next(i for i in range(24, 32) if l1[i] == "0")
    bad = l1[:col] + "O" + l1[col + 1:]
    assert T.checksum(bad) == int(bad[68]), "the checksum should stay valid"
    edit = {"line": 1, "column": col + 1, "was": "0", "now": "O", "epoch_field_was": l1[18:32], "epoch_field_now": bad[18:32],
            "statement": f"line 1 column {col + 1}, the first 0 among the epoch field's fractional digits, replaced by the letter O "
                         f"({l1[18:32]!r} becomes {bad[18:32]!r}); the checksum is still valid, since a letter counts 0 as the digit it replaced did"}
    write("c3-letter-in-epoch.tle", tle_text([before, (l0, bad, l2), after]),
          {"input": 3, "check": "corrupt-tle-letter-in-number", "description": "A set with a letter in a numeric column of line 1, between two valid sets.",
           "rendering": rendering, "records": records(edit)})

    # Input 4: a set missing its second line: line 1 followed directly by the next set's name line.
    edit = {"line": 2, "was": "present", "now": "removed",
            "statement": "line 2 removed: the set's name line and line 1 are followed directly by the next set's name line"}
    write("c4-line-2-missing.tle", tle_text([before, (l0, l1), after]),
          {"input": 4, "check": "corrupt-tle-missing-line-2", "description": "A set with no line 2, between two valid sets.",
           "rendering": rendering, "records": records(edit)})

    # Input 5: a file cut mid-record, in CSV (inside its last row) and in JSON (the closing bracket missing). The cut
    # record is 69999's, last in both files; the complete records are the two neighbours.
    rows = [omm_row(BEFORE), omm_row(AFTER), omm_row(CORRUPT)]
    full = csv_text([r for r, _ in rows])
    last = full[: -len(EOL)].rsplit(EOL, 1)[1]  # the last data row, without its line ending
    head = full[: len(full) - len(last) - len(EOL)]
    fields = last.split(",")
    assert next(csv.reader([last])) == fields, "a quoted field would make the cut position ambiguous"
    k = CSV_COLUMNS.index("MEAN_MOTION_DOT")
    value = fields[k]
    cut_row = ",".join(fields[:k]) + "," + value[:-2]
    edit = {"field": "MEAN_MOTION_DOT", "was": value, "now": value[:-2],
            "statement": f"the file ends inside its last row, two characters before the end of the MEAN_MOTION_DOT value "
                         f"({value!r} becomes {value[:-2]!r}); MEAN_MOTION_DDOT and the row's line ending are missing"}
    write("c5-cut-last-row.csv", head + cut_row,
          {"input": 5, "check": "corrupt-file-cut", "description": "A CSV file cut inside its last row: two complete records, then the cut one.",
           "rendering": {"layout": "CelesTrak's CSV column order and CRLF line endings; values as frozen, in plain decimal notation (CelesTrak writes some with a leading dot and an exponent, a difference of notation, not of value)"},
           "records": [{"position": 1, "role": "valid", **rows[0][1]}, {"position": 2, "role": "valid", **rows[1][1]},
                       {"position": 3, "role": "corrupt", **rows[2][1], "edit": edit}]})

    array = "[" + ",".join(json_object(r) for r, _ in rows) + "]" + EOL
    cut = array[: -len("]" + EOL)]
    edit = {"was": "]" + EOL.replace("\r", "\\r").replace("\n", "\\n"), "now": "",
            "statement": "the closing bracket of the array and the line ending after it removed: the text ends with the last record's closing brace"}
    write("c5-cut-closing-bracket.json", cut,
          {"input": 5, "check": "corrupt-file-cut", "description": "A JSON array with no closing bracket: three complete records and no end to the array.",
           "rendering": {"layout": "CelesTrak's JSON layout: one array on one line, keys in CSV column order, numbers written from the frozen decimal text"},
           "file_edit": edit,
           "records": [{"position": i + 1, "role": "valid", **w} for i, (_, w) in enumerate(rows)]})

    # The unedited files (D-175): each input's records as the input lays them out, with no edit. Inputs 1 to 4 share
    # one TLE file; input 5's CSV has its last row whole and its JSON array is closed. Each input is its unedited file
    # with its one edit made, which tests/test_corrupt_input.py checks byte for byte.
    write("unedited-sets.tle", tle_text([before, corrupt, after]),
          {"for_inputs": [1, 2, 3, 4], "description": "The three TLE sets of inputs 1 to 4 with no edit, in the inputs' order.",
           "rendering": rendering,
           "records": [{"position": 1, "role": "valid", **w_before}, {"position": 2, "role": "valid", "edited_in_inputs": [1, 2, 3, 4], **w_corrupt},
                       {"position": 3, "role": "valid", **w_after}]}, edited=False)
    write("unedited-rows.csv", full,
          {"for_inputs": [5], "description": "The CSV of input 5 with its last row whole: three complete records.",
           "rendering": {"layout": "CelesTrak's CSV column order and CRLF line endings; values as frozen, in plain decimal notation"},
           "records": [{"position": 1, "role": "valid", **rows[0][1]}, {"position": 2, "role": "valid", **rows[1][1]},
                       {"position": 3, "role": "valid", "edited_in_inputs": [5], **rows[2][1]}]}, edited=False)
    write("unedited-array.json", array,
          {"for_inputs": [5], "description": "The JSON array of input 5, closed: three complete records.",
           "rendering": {"layout": "CelesTrak's JSON layout: one array on one line, keys in CSV column order, numbers written from the frozen decimal text"},
           "records": [{"position": i + 1, "role": "valid", **w} for i, (_, w) in enumerate(rows)]}, edited=False)


if __name__ == "__main__":
    main()
