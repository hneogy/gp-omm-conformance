#!/usr/bin/env python3
"""
tools/inventory.py -- describe every raw fixture file and write docs/INVENTORY.md.

Read-only and offline. It never touches the network. It exists so that a reviewer can
see, per file: where it came from, when, how big, its hash, how many records it holds,
the catalog-number range, and the format quirks that the fixtures will later have to
encode as expected values (empty mandatory fields, precision differences between the
TLE and OMM renderings of the same record, line endings, and so on).
"""
import collections
import csv
import datetime as dt
import glob
import io
import json
import os
import re
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "fixtures")
OUT = os.path.join(ROOT, "docs", "INVENTORY.md")

OMM_KEYS = ["OBJECT_NAME", "OBJECT_ID", "EPOCH", "MEAN_MOTION", "ECCENTRICITY", "INCLINATION",
            "RA_OF_ASC_NODE", "ARG_OF_PERICENTER", "MEAN_ANOMALY", "EPHEMERIS_TYPE",
            "CLASSIFICATION_TYPE", "NORAD_CAT_ID", "ELEMENT_SET_NO", "REV_AT_EPOCH", "BSTAR",
            "MEAN_MOTION_DOT", "MEAN_MOTION_DDOT"]


# ----------------------------------------------------------------------------- helpers
def from_alpha5(s):
    s = s.strip()
    if not s or not s[0].isalpha():
        return int(s)
    c, rest = s[0].upper(), s[1:]
    n = ord(c) - ord("A") + 10
    n -= c > "I"
    n -= c > "O"
    return n * 10000 + int(rest)


def to_alpha5_letter(n):
    if n < 100000 or n > 339999:
        return None
    i = n // 10000 - 10 + ord("A")
    if i >= ord("I"):
        i += 1
    if i >= ord("O"):
        i += 1
    return chr(i)


def tle_checksum(line):
    return sum(int(c) if c.isdigit() else (c == "-") for c in line[:68]) % 10


def tle_exp_field(f):
    """'15975-3' -> Decimal-ish string '0.15975e-3'; returns (float, text)."""
    f = f.strip()
    if not f:
        return None, ""
    sign = "-" if f[0] == "-" else ""
    body = f.lstrip("+-")
    mant, exp = body[:-2], body[-2:]
    txt = f"{sign}0.{mant}e{exp}"
    return float(txt), txt


def bucket(i):
    if i >= 100_000_000:
        return "9-digit"
    if i >= 100_000:
        return "6-digit"
    if i >= 70_000:
        return "70000-99999"
    return "<70000"


def id_stats(ids):
    if not ids:
        return "no records"
    b = collections.Counter(bucket(i) for i in ids)
    parts = ", ".join(f"{k}: {v}" for k, v in sorted(b.items()))
    return f"{len(ids)} ids, min {min(ids)}, max {max(ids)} ({parts})"


def line_endings(raw):
    crlf = raw.count(b"\r\n")
    lf = raw.count(b"\n") - crlf
    bom = raw.startswith(b"\xef\xbb\xbf")
    return f"CRLF={crlf}, bare LF={lf}{', UTF-8 BOM' if bom else ''}"


# ----------------------------------------------------------------------------- per-format readers
def read_tle(text):
    lines = text.splitlines()
    recs = []
    for i, l in enumerate(lines):
        if l.startswith("1 ") and i + 1 < len(lines) and lines[i + 1].startswith("2 "):
            name = lines[i - 1] if i > 0 and not lines[i - 1][:2] in ("1 ", "2 ") else None
            recs.append({"name": name, "l1": l, "l2": lines[i + 1]})
    return recs


def summarize_tle(text):
    recs = read_tle(text)
    ids, notes = [], []
    letters = collections.Counter()
    years = collections.Counter()
    classif = collections.Counter()
    ephtype = collections.Counter()
    bad_ck = bad_len = ndot_neg = nddot_nonzero = bstar_zero_plus = bstar_zero_minus = bstar_pos_exp = bstar_neg = 0
    bstar_vals = []
    name_lens = collections.Counter()
    for r in recs:
        l1, l2 = r["l1"], r["l2"]
        f = l1[2:7]
        if f[0].isalpha():
            letters[f[0]] += 1
        ids.append(from_alpha5(f))
        if len(l1) != 69 or len(l2) != 69:
            bad_len += 1
        if not (l1[68].isdigit() and l2[68].isdigit()) or tle_checksum(l1) != int(l1[68]) or tle_checksum(l2) != int(l2[68]):
            bad_ck += 1
        years[l1[18:20]] += 1
        classif[l1[7]] += 1
        ephtype[l1[62]] += 1
        if l1[33:43].strip().startswith("-"):
            ndot_neg += 1
        v, _ = tle_exp_field(l1[44:52])
        if v:
            nddot_nonzero += 1
        bf = l1[53:61]
        bv, _ = tle_exp_field(bf)
        bstar_vals.append((bv, bf, f))
        if bv == 0:
            if bf.strip().endswith("+0"):
                bstar_zero_plus += 1
            else:
                bstar_zero_minus += 1
        elif bv < 0:
            bstar_neg += 1
        if bv and bf.strip()[-2] == "+" and bf.strip()[-1] != "0":
            bstar_pos_exp += 1
        if r["name"] is not None:
            name_lens[len(r["name"])] += 1
    out = [f"records: {len(recs)}; {id_stats(ids)}"]
    out.append(f"line-1 col 3-7 letters (Alpha-5): {dict(letters) or 'none'}")
    out.append(f"two-digit epoch years: {dict(sorted(years.items()))}")
    out.append(f"classification: {dict(classif)}; ephemeris type: {dict(ephtype)}")
    out.append(f"checksum failures: {bad_ck}; lines not 69 chars: {bad_len}; name-line lengths: {dict(name_lens) or 'n/a'}")
    out.append(f"ndot negative: {ndot_neg}; nddot non-zero: {nddot_nonzero}")
    out.append(f"BSTAR: negative {bstar_neg}; zero written '00000+0': {bstar_zero_plus}; zero written '00000-0': {bstar_zero_minus}; positive exponent (>=1.0): {bstar_pos_exp}")
    if bstar_vals:
        lo = min(bstar_vals, key=lambda t: t[0])
        hi = max(bstar_vals, key=lambda t: t[0])
        out.append(f"BSTAR extremes: min {lo[0]:.6g} (raw '{lo[1]}', id {lo[2]}); max {hi[0]:.6g} (raw '{hi[1]}', id {hi[2]})")
    return out, {from_alpha5(r["l1"][2:7]): r for r in recs}


def summarize_csv(text):
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        return ["no rows"], {}
    cols = list(rows[0].keys())
    ids = [int(r["NORAD_CAT_ID"]) for r in rows]
    out = [f"records: {len(rows)}; {id_stats(ids)}"]
    extra = [c for c in cols if c not in OMM_KEYS]
    missing = [c for c in OMM_KEYS if c not in cols]
    out.append(f"columns: {len(cols)}; non-OMM extra columns: {extra or 'none'}; OMM keys absent: {missing or 'none'}")
    for k in ("OBJECT_NAME", "OBJECT_ID"):
        if k in cols:
            out.append(f"{k} empty cells: {sum(1 for r in rows if r[k] == '')}")
    out.append(f"EPOCH string lengths: {dict(collections.Counter(len(r['EPOCH']) for r in rows))}; example {rows[0]['EPOCH']!r}")
    out.append(f"MEAN_MOTION_DDOT non-zero: {sum(1 for r in rows if float(r['MEAN_MOTION_DDOT'] or 0) != 0)}")
    out.append(f"values starting with '.' (no leading zero), ECCENTRICITY: {sum(1 for r in rows if r['ECCENTRICITY'].startswith('.'))}, BSTAR: {sum(1 for r in rows if r['BSTAR'].lstrip('-').startswith('.'))}")
    out.append(f"CLASSIFICATION_TYPE: {dict(collections.Counter(r['CLASSIFICATION_TYPE'] for r in rows))}; ELEMENT_SET_NO values (top 3): {collections.Counter(r['ELEMENT_SET_NO'] for r in rows).most_common(3)}")
    if "DATA_SOURCE" in cols:
        out.append(f"DATA_SOURCE: {dict(collections.Counter(r['DATA_SOURCE'] for r in rows))}")
    return out, {int(r["NORAD_CAT_ID"]): r for r in rows}


def summarize_json(text):
    data = json.loads(text)
    if not isinstance(data, list):
        return [f"top-level JSON type: {type(data).__name__}"], {}
    if not data:
        return ["empty list"], {}
    keys = collections.Counter(k for r in data for k in r)
    ids = [int(r["NORAD_CAT_ID"]) for r in data]
    out = [f"records: {len(data)}; {id_stats(ids)}"]
    n = len(data)
    partial = {k: v for k, v in keys.items() if v != n}
    out.append(f"keys present in every record: {sorted(k for k, v in keys.items() if v == n)}")
    out.append(f"keys present in only some records (key omitted elsewhere): {partial or 'none'}")
    for k in ("OBJECT_NAME", "OBJECT_ID"):
        vals = [r.get(k, "<absent>") for r in data]
        out.append(f"{k}: absent {vals.count('<absent>')}, null {vals.count(None)}, empty string {vals.count('')}")
    types = {k: sorted({type(r[k]).__name__ for r in data if k in r}) for k in ("NORAD_CAT_ID", "EPOCH", "MEAN_MOTION", "BSTAR", "ELEMENT_SET_NO", "EPHEMERIS_TYPE")}
    out.append(f"JSON value types: {types}")
    return out, {int(r["NORAD_CAT_ID"]): r for r in data}


def summarize_xml(text):
    root = ET.fromstring(text)
    out = [f"root element: <{root.tag}>; attributes: {dict(root.attrib)}"]
    omms = root.findall(".//omm") if root.tag != "omm" else [root]
    versions = collections.Counter(o.get("version") for o in omms)
    out.append(f"<omm> elements: {len(omms)}; version attributes: {dict(versions)}; id attributes: {dict(collections.Counter(o.get('id') for o in omms))}")
    ids = []
    empty_name = empty_id = 0
    creation = collections.Counter()
    originator = collections.Counter()
    met = collections.Counter()
    units_attrs = 0
    for o in omms:
        h = o.find("header")
        creation[(h.findtext("CREATION_DATE") or "") if h is not None else "<no header>"] += 1
        originator[(h.findtext("ORIGINATOR") or "") if h is not None else "<no header>"] += 1
        m = o.find("body/segment/metadata")
        if m is not None:
            if not (m.findtext("OBJECT_NAME") or ""):
                empty_name += 1
            if not (m.findtext("OBJECT_ID") or ""):
                empty_id += 1
            met[m.findtext("MEAN_ELEMENT_THEORY")] += 1
        t = o.find("body/segment/data/tleParameters")
        if t is not None and t.findtext("NORAD_CAT_ID"):
            ids.append(int(t.findtext("NORAD_CAT_ID")))
        units_attrs += sum(1 for e in o.iter() if "units" in e.attrib)
    out.append(id_stats(ids))
    out.append(f"header CREATION_DATE values: {dict(creation)}; ORIGINATOR values: {dict(originator)}")
    out.append(f"metadata OBJECT_NAME empty: {empty_name}; OBJECT_ID empty: {empty_id}; MEAN_ELEMENT_THEORY: {dict(met)}")
    out.append(f"elements carrying a 'units' attribute: {units_attrs}")
    return out, {}


def summarize_kvn(text):
    lines = text.splitlines()
    msgs = []
    cur = None
    maxlen = 0
    units = 0
    for l in lines:
        maxlen = max(maxlen, len(l))
        if "[" in l and "]" in l and "=" in l:
            units += 1
        if l.startswith("CCSDS_OMM_VERS"):
            cur = collections.OrderedDict()
            msgs.append(cur)
        if cur is not None and "=" in l:
            k, v = l.split("=", 1)
            cur[k.strip()] = v.strip()
    versions = collections.Counter(m.get("CCSDS_OMM_VERS") for m in msgs)
    ids = [int(m["NORAD_CAT_ID"]) for m in msgs if m.get("NORAD_CAT_ID")]
    out = [f"messages: {len(msgs)}; {id_stats(ids)}; CCSDS_OMM_VERS: {dict(versions)}"]
    blanks = collections.Counter(k for m in msgs for k, v in m.items() if v == "")
    out.append(f"keywords with blank values (count of messages): {dict(blanks) or 'none'}")
    out.append(f"MEAN_ELEMENT_THEORY: {dict(collections.Counter(m.get('MEAN_ELEMENT_THEORY') for m in msgs))}")
    out.append(f"longest line: {maxlen} chars (CCSDS limit 254); lines with [units]: {units}")
    if msgs:
        out.append(f"keyword order (first message): {list(msgs[0].keys())}")
    return out, {}


def summarize_satcat_txt(raw):
    text = raw.decode("utf-8", "replace")
    ids, bad = [], 0
    for l in text.splitlines():
        s = l[13:18].strip()
        if s.isdigit():
            ids.append(int(s))
        else:
            bad += 1
    return [f"lines: {len(text.splitlines())}; numeric id field (cols 14-18): {len(ids)}; min {min(ids)}; max {max(ids)}; ids >= 70000: {sum(i >= 70000 for i in ids)}; non-numeric id lines: {bad}",
            f"contiguous 1..max with no gaps: {sorted(ids) == list(range(1, max(ids) + 1))}"], {}


def summarize_satcat_records(text, fmt):
    if fmt == "json":
        data = json.loads(text)
        return [f"records: {len(data)}; fields: {list(data[0].keys()) if data else []}", f"record: {json.dumps(data[0]) if data else ''}"], {}
    rows = list(csv.DictReader(io.StringIO(text)))
    return [f"records: {len(rows)}; columns: {list(rows[0].keys()) if rows else []}"], {}


# ----------------------------------------------------------------------------- cross-format comparison
def tle_epoch_iso(l1):
    yy = int(l1[18:20])
    year = yy + 2000 if yy < 57 else yy + 1900
    day = float(l1[20:32])
    t = dt.datetime(year, 1, 1) + dt.timedelta(days=day - 1)
    return t.strftime("%Y-%m-%dT%H:%M:%S.%f")


def compare_tle_csv(tle_map, csv_map):
    common = sorted(set(tle_map) & set(csv_map))
    if not common:
        return ["no common ids"]
    only_csv = sorted(set(csv_map) - set(tle_map))
    only_tle = sorted(set(tle_map) - set(csv_map))
    out = [f"common ids: {len(common)}; only in CSV: {len(only_csv)} ({id_stats(only_csv) if only_csv else '-'}); only in TLE: {len(only_tle)}"]
    ecc_trunc = ecc_round = ecc_other = 0
    bstar_eq = bstar_more = 0
    ndot_eq = 0
    epoch_eq = 0
    epoch_diffs = []
    mm_eq = 0
    examples = []
    for i in common:
        l1, l2 = tle_map[i]["l1"], tle_map[i]["l2"]
        r = csv_map[i]
        # eccentricity: CSV decimal string vs TLE 7-digit implied-decimal field
        e_csv = r["ECCENTRICITY"]
        digits = (e_csv.split(".")[1] if "." in e_csv else "").ljust(7, "0")
        tle_e = l2[26:33]
        if tle_e == digits[:7]:
            if len(e_csv.split(".")[1]) > 7:
                ecc_trunc += 1
            else:
                ecc_round += 1  # indistinguishable when <= 7 digits
        elif tle_e == f"{round(float(e_csv), 7):.7f}".split(".")[1]:
            ecc_round += 1
        else:
            ecc_other += 1
            if len(examples) < 3:
                examples.append(f"id {i}: CSV ECC {e_csv} vs TLE {tle_e}")
        # bstar digits
        b_csv = r["BSTAR"]
        m = re.match(r"^(-?)\.?(\d+)E?([+-]?\d+)?$", b_csv.replace("0.", ".", 1) if b_csv.startswith("0.") or b_csv.startswith("-0.") else b_csv)
        bv_tle, _ = tle_exp_field(l1[53:61])
        try:
            if abs(float(b_csv) - bv_tle) <= 1e-12:
                bstar_eq += 1
            else:
                bstar_more += 1
        except ValueError:
            pass
        # ndot
        try:
            if abs(float(r["MEAN_MOTION_DOT"]) - float(l1[33:43])) <= 1e-12:
                ndot_eq += 1
        except ValueError:
            pass
        if tle_epoch_iso(l1) == r["EPOCH"]:
            epoch_eq += 1
        else:
            a = dt.datetime.strptime(tle_epoch_iso(l1), "%Y-%m-%dT%H:%M:%S.%f")
            b = dt.datetime.strptime(r["EPOCH"], "%Y-%m-%dT%H:%M:%S.%f")
            epoch_diffs.append((abs((a - b).total_seconds()) * 1e6, i, r["EPOCH"], l1[18:32]))
        if l2[52:63].strip() == r["MEAN_MOTION"]:
            mm_eq += 1
    n = len(common)
    out.append(f"EPOCH: TLE(yy+ddd.dddddddd, pivot 57) converted to ISO equals CSV EPOCH string in {epoch_eq}/{n}"
               + (f"; mismatches: max {max(d[0] for d in epoch_diffs):.0f} us, e.g. id {epoch_diffs[0][1]} CSV {epoch_diffs[0][2]} vs TLE '{epoch_diffs[0][3]}' (TLE day resolution is 1e-8 d = 864 us)" if epoch_diffs else ""))
    out.append(f"MEAN_MOTION: TLE field text equals CSV text in {mm_eq}/{n}")
    out.append(f"MEAN_MOTION_DOT: TLE field value equals CSV value (i.e. OMM carries the TLE 'ndot/2' field as printed) in {ndot_eq}/{n}")
    out.append(f"ECCENTRICITY: CSV has >7 decimals and TLE equals the first 7 (truncation) in {ecc_trunc}; equal/rounded in {ecc_round}; other {ecc_other} {examples}")
    out.append(f"BSTAR: numerically equal in {bstar_eq}/{n}; CSV carries more digits than the TLE's 5-digit mantissa in {bstar_more}/{n}")
    return out


# ----------------------------------------------------------------------------- main
def main():
    cases = sorted(d for d in os.listdir(FIX) if os.path.isdir(os.path.join(FIX, d, "raw")))
    md = ["# Fixture inventory (raw files)", "",
          f"Generated {dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')} by `tools/inventory.py` from `fixtures/*/raw/`. ",
          "Read-only description of what was fetched; nothing here is an expected value yet.", ""]
    total_bytes = 0
    total_files = 0
    alpha5_letters_real = collections.Counter()
    for case in cases:
        md += [f"## {case}", ""]
        rawdir = os.path.join(FIX, case, "raw")
        files = sorted(f for f in os.listdir(rawdir) if not f.endswith(".meta.json"))
        maps = {}  # (stem, kind) -> id map, so comparisons pair files of the same name
        for f in files:
            p = os.path.join(rawdir, f)
            meta_p = p + ".meta.json"
            meta = json.load(open(meta_p)) if os.path.exists(meta_p) else {}
            raw = open(p, "rb").read()
            total_bytes += len(raw)
            total_files += 1
            md += [f"### `{f}`", "",
                   f"- source: <{meta.get('url', '?')}>",
                   f"- retrieved: {meta.get('retrieved_at', '?')} UTC; HTTP {meta.get('http_status', '?')}; {len(raw)} bytes; sha256 `{meta.get('sha256', '?')}`",
                   f"- provenance: {meta.get('provenance', '?')}" + (f"; note: {meta['note']}" if meta.get("note") else ""),
                   f"- line endings: {line_endings(raw)}"]
            text = raw.decode("utf-8", "replace")
            ext = f.rsplit(".", 1)[-1].lower()
            try:
                if meta.get("http_status", 200) != 200:
                    lines, m = [f"response body: {text.strip()!r}"], {}
                elif f == "satcat.txt":
                    lines, m = summarize_satcat_txt(raw)
                elif ".satcat." in f or f.startswith("satcat-"):
                    lines, m = summarize_satcat_records(text, ext)
                elif ext in ("tle", "2le"):
                    lines, m = summarize_tle(text)
                    if ext == "tle":
                        maps[(f[:-4], "tle")] = m
                elif ext == "csv":
                    lines, m = summarize_csv(text)
                    maps[(f[:-4], "csv")] = m
                elif ext == "json":
                    lines, m = summarize_json(text)
                elif ext == "xml":
                    lines, m = summarize_xml(text)
                elif ext == "kvn":
                    lines, m = summarize_kvn(text)
                else:
                    lines, m = ["(no summarizer)"], {}
            except Exception as e:  # keep going; report the failure in the inventory
                lines, m = [f"SUMMARIZER ERROR: {type(e).__name__}: {e}"], {}
            for i in m:
                if isinstance(i, int) and to_alpha5_letter(i):
                    alpha5_letters_real[to_alpha5_letter(i)] += 1
            md += [f"- {l}" for l in lines] + [""]
        for (stem, kind), tmap in sorted(maps.items()):
            if kind == "tle" and tmap and maps.get((stem, "csv")):
                md += [f"### TLE vs CSV, same ids (`{stem}.tle` vs `{stem}.csv`)", ""] + \
                      [f"- {l}" for l in compare_tle_csv(tmap, maps[(stem, "csv")])] + [""]
    md += ["## Totals", "", f"- files: {total_files}; bytes: {total_bytes:,}",
           f"- real catalog ids inside the Alpha-5 range (100000-339999) seen in TLE/CSV maps, by Alpha-5 first letter: {dict(sorted(alpha5_letters_real.items())) or 'none'}", ""]
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        f.write("\n".join(md))
    print(f"wrote {OUT}: {total_files} files, {total_bytes:,} bytes")


if __name__ == "__main__":
    main()
