#!/usr/bin/env python3
"""
gpconf/reference.py -- reference readers for GP data in TLE, CSV, JSON, XML and KVN.

Standard library only. Also imported by tools/gpref.py (shim).

Written from the format documents, not from any library (CelesTrak TLE column table,
CCSDS 502.0-B-3 sections 4 and 7, CCSDS 505.0-B-3 / SANA schemas). Used only to *produce*
expected values; python-sgp4 and Skyfield are used separately to cross-check them.

Numbers are carried as decimal text (Python Decimal), never as binary floats, and are
rendered in plain notation ('0.00015975118', not '.15975118E-3' or 1.5975118e-04).
"""
import csv
import datetime as dt
import io
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from decimal import Decimal, ROUND_HALF_EVEN

from .tle import from_alpha5, checksum

OMM_HEADER = ["CCSDS_OMM_VERS", "COMMENT", "CLASSIFICATION", "CREATION_DATE", "ORIGINATOR", "MESSAGE_ID"]
OMM_META = ["OBJECT_NAME", "OBJECT_ID", "CENTER_NAME", "REF_FRAME", "REF_FRAME_EPOCH", "TIME_SYSTEM", "MEAN_ELEMENT_THEORY"]
OMM_MEAN = ["EPOCH", "SEMI_MAJOR_AXIS", "MEAN_MOTION", "ECCENTRICITY", "INCLINATION", "RA_OF_ASC_NODE",
            "ARG_OF_PERICENTER", "MEAN_ANOMALY", "GM"]
OMM_SC = ["MASS", "SOLAR_RAD_AREA", "SOLAR_RAD_COEFF", "DRAG_AREA", "DRAG_COEFF"]
OMM_TLEP = ["EPHEMERIS_TYPE", "CLASSIFICATION_TYPE", "NORAD_CAT_ID", "ELEMENT_SET_NO", "REV_AT_EPOCH", "BSTAR",
            "BTERM", "MEAN_MOTION_DOT", "MEAN_MOTION_DDOT", "AGOM"]
OMM_KEYWORDS = set(OMM_HEADER + OMM_META + OMM_MEAN + OMM_SC + OMM_TLEP)
MANDATORY_META = ["OBJECT_NAME", "OBJECT_ID", "CENTER_NAME", "REF_FRAME", "TIME_SYSTEM", "MEAN_ELEMENT_THEORY"]
CELESTRAK_CSV_JSON_KEYS = ["OBJECT_NAME", "OBJECT_ID", "EPOCH", "MEAN_MOTION", "ECCENTRICITY", "INCLINATION",
                           "RA_OF_ASC_NODE", "ARG_OF_PERICENTER", "MEAN_ANOMALY", "EPHEMERIS_TYPE",
                           "CLASSIFICATION_TYPE", "NORAD_CAT_ID", "ELEMENT_SET_NO", "REV_AT_EPOCH", "BSTAR",
                           "MEAN_MOTION_DOT", "MEAN_MOTION_DDOT"]

DECIMAL_KEYS = {"MEAN_MOTION": "mean_motion", "ECCENTRICITY": "eccentricity", "INCLINATION": "inclination",
                "RA_OF_ASC_NODE": "ra_of_asc_node", "ARG_OF_PERICENTER": "arg_of_pericenter",
                "MEAN_ANOMALY": "mean_anomaly", "BSTAR": "bstar", "MEAN_MOTION_DOT": "mean_motion_dot",
                "MEAN_MOTION_DDOT": "mean_motion_ddot", "SEMI_MAJOR_AXIS": "semi_major_axis", "GM": "gm",
                "BTERM": "bterm", "AGOM": "agom"}
INT_KEYS = {"NORAD_CAT_ID": "norad_cat_id", "EPHEMERIS_TYPE": "ephemeris_type", "ELEMENT_SET_NO": "element_set_no",
            "REV_AT_EPOCH": "rev_at_epoch"}
TEXT_KEYS = {"OBJECT_NAME": "object_name", "OBJECT_ID": "object_id", "CENTER_NAME": "center_name",
             "REF_FRAME": "ref_frame", "TIME_SYSTEM": "time_system", "MEAN_ELEMENT_THEORY": "mean_element_theory",
             "CLASSIFICATION_TYPE": "classification_type", "EPOCH": "epoch", "REF_FRAME_EPOCH": "ref_frame_epoch",
             "CCSDS_OMM_VERS": "ccsds_omm_vers", "CREATION_DATE": "creation_date", "ORIGINATOR": "originator",
             "MESSAGE_ID": "message_id", "CLASSIFICATION": "classification"}


def plain(value):
    """Decimal text/number -> plain decimal string without exponent; None/'' -> None."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        d = value
    else:
        s = str(value).strip()
        if s == "":
            return None
        d = Decimal(s)
    s = format(d, "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".") or "0"
    if s in ("-0", ""):
        s = "0"
    return s


def line_endings(raw: bytes):
    crlf = raw.count(b"\r\n")
    return {"crlf": crlf, "lf": raw.count(b"\n") - crlf, "bom": raw.startswith(b"\xef\xbb\xbf")}


# --------------------------------------------------------------------------- canonical record
def canonical_from_fields(fields, presence, fmt):
    """fields: OMM keyword -> text (str) or Decimal/int for JSON; presence: keyword -> 'value'|'empty'|'null'|'absent'."""
    rec = {}
    for k, name in TEXT_KEYS.items():
        v = fields.get(k)
        rec[name] = (str(v) if v is not None and str(v) != "" else None) if presence.get(k) in ("value", "empty", "null") else None
    for k, name in INT_KEYS.items():
        v = fields.get(k)
        rec[name] = int(str(v)) if v not in (None, "") else None
    for k, name in DECIMAL_KEYS.items():
        v = fields.get(k)
        rec[name] = plain(v) if v not in (None, "") else None
    rec["extra"] = {k: (str(v) if v is not None else None) for k, v in fields.items() if k not in OMM_KEYWORDS}
    rec["presence"] = {k: presence[k] for k in sorted(presence)}
    rec["source_format"] = fmt
    return rec


# --------------------------------------------------------------------------- TLE
TLE_YEAR_PIVOT = 57  # two-digit years 57-99 -> 1957-1999, 00-56 -> 2000-2056 (CelesTrak, Satellite Times Jan 1998)


def two_digit_year(yy):
    yy = int(yy)
    return yy + 1900 if yy >= TLE_YEAR_PIVOT else yy + 2000


def tle_epoch_to_iso(field):
    """'26263.52959654' -> '2026-09-20T12:42:37.141056' (microsecond resolution, exact for 8-decimal days)."""
    yy, rest = field[:2], field[2:]
    day = Decimal(rest)
    doy = int(day)
    frac = day - doy
    us = (frac * Decimal(86_400_000_000)).quantize(Decimal(1), rounding=ROUND_HALF_EVEN)
    base = dt.datetime(two_digit_year(yy), 1, 1) + dt.timedelta(days=doy - 1, microseconds=int(us))
    return base.strftime("%Y-%m-%dT%H:%M:%S.%f")


def tle_exp_to_plain(field):
    f = field.strip()
    if not f:
        return None
    sign = "-" if f[0] == "-" else ""
    body = f.lstrip("+-")
    mant, exp = body[:-2], body[-2:]
    return plain(Decimal(f"{sign}0.{mant}E{exp}"))


def intl_designator_to_object_id(field):
    f = field.rstrip()
    if not f.strip():
        return None
    yy, launch, piece = f[0:2], f[2:5], f[5:8].strip()
    return f"{two_digit_year(yy)}-{launch}{piece}"


def parse_tle_lines(l0, l1, l2, strict=True):
    if strict and (len(l1) != 69 or len(l2) != 69):
        raise ValueError(f"line length {len(l1)}/{len(l2)} != 69")
    cat_field = l1[2:7]
    rec = {
        "norad_cat_id": from_alpha5(cat_field),
        "object_name": (l0.strip() or None) if l0 is not None else None,
        "object_id": intl_designator_to_object_id(l1[9:17]),
        "epoch": tle_epoch_to_iso(l1[18:32]),
        "mean_motion": plain(l2[52:63]),
        "eccentricity": plain(Decimal("0." + l2[26:33])),
        "inclination": plain(l2[8:16]), "ra_of_asc_node": plain(l2[17:25]),
        "arg_of_pericenter": plain(l2[34:42]), "mean_anomaly": plain(l2[43:51]),
        "bstar": tle_exp_to_plain(l1[53:61]),
        "mean_motion_dot": plain(l1[33:43]),
        "mean_motion_ddot": tle_exp_to_plain(l1[44:52]),
        "ephemeris_type": int(l1[62]) if l1[62].strip() else 0,
        "classification_type": l1[7],
        "element_set_no": int(l1[64:68]),
        "rev_at_epoch": int(l2[63:68]),
        "center_name": None, "ref_frame": None, "time_system": None, "mean_element_theory": None,
        "ccsds_omm_vers": None, "creation_date": None, "originator": None,
        "extra": {}, "source_format": "tle",
        "tle": {
            "line0": l0, "line1": l1, "line2": l2,
            "catalog_field": cat_field, "catalog_field_is_alpha5": cat_field[0].isalpha(),
            "intl_designator_field": l1[9:17], "epoch_field": l1[18:32], "two_digit_year": l1[18:20],
            "ndot_field": l1[33:43], "nddot_field": l1[44:52], "bstar_field": l1[53:61],
            "ephemeris_type_field": l1[62], "element_set_field": l1[64:68],
            "ecc_field": l2[26:33], "rev_field": l2[63:68],
            "checksum_written": [l1[68], l2[68]], "checksum_computed": [checksum(l1), checksum(l2)],
            "checksums_valid": l1[68] == str(checksum(l1)) and l2[68] == str(checksum(l2)),
            "line_lengths": [len(l0) if l0 is not None else None, len(l1), len(l2)],
        },
    }
    rec["presence"] = {"OBJECT_NAME": "value" if rec["object_name"] else "empty",
                       "OBJECT_ID": "value" if rec["object_id"] else "empty"}
    return rec


def read_tle_text(text):
    lines = text.splitlines()
    recs = []
    i = 0
    while i < len(lines):
        l = lines[i]
        if l.startswith("1 ") and i + 1 < len(lines) and lines[i + 1].startswith("2 "):
            l0 = lines[i - 1] if i > 0 and lines[i - 1][:2] not in ("1 ", "2 ") else None
            recs.append(parse_tle_lines(l0, l, lines[i + 1]))
            i += 2
        else:
            i += 1
    return recs


# --------------------------------------------------------------------------- CSV / JSON
def read_csv_text(text):
    rows = list(csv.DictReader(io.StringIO(text)))
    cols = list(rows[0].keys()) if rows else []
    recs = []
    for r in rows:
        presence = {k: ("value" if v != "" else "empty") for k, v in r.items()}
        for k in OMM_META + OMM_TLEP + OMM_MEAN + OMM_HEADER:
            presence.setdefault(k, "absent")
        recs.append(canonical_from_fields(r, presence, "csv"))
    facts = {"columns": cols, "omm_mandatory_metadata_absent": [k for k in MANDATORY_META if k not in cols],
             "non_omm_columns": [c for c in cols if c not in OMM_KEYWORDS]}
    return recs, facts


def read_json_text(text):
    data = json.loads(text, parse_float=Decimal)
    if not isinstance(data, list):
        raise ValueError("expected a JSON array of records")
    keys = []
    for r in data:
        for k in r:
            if k not in keys:
                keys.append(k)
    recs = []
    types = {}
    for r in data:
        presence = {}
        fields = {}
        for k in keys:
            if k not in r:
                presence[k] = "absent"
            elif r[k] is None:
                presence[k] = "null"
            elif r[k] == "":
                presence[k] = "empty"
            else:
                presence[k] = "value"
                fields[k] = r[k]
                types.setdefault(k, set()).add(type(r[k]).__name__)
        for k in OMM_META + OMM_TLEP + OMM_MEAN + OMM_HEADER:
            presence.setdefault(k, "absent")
        recs.append(canonical_from_fields(fields, presence, "json"))
    facts = {"keys": keys, "omm_mandatory_metadata_absent": [k for k in MANDATORY_META if k not in keys],
             "non_omm_keys": [k for k in keys if k not in OMM_KEYWORDS],
             "json_value_types": {k: sorted(v) for k, v in types.items()}}
    return recs, facts


# --------------------------------------------------------------------------- XML
def _strip_ns(tag):
    return tag.split("}", 1)[1] if "}" in tag else tag


def read_xml_text(text):
    root = ET.fromstring(text)
    rtag = _strip_ns(root.tag)
    omms = [root] if rtag == "omm" else [e for e in root if _strip_ns(e.tag) == "omm"]
    recs = []
    units_seen = {}
    for o in omms:
        fields, presence = {}, {}
        fields["CCSDS_OMM_VERS"] = o.get("version")
        presence["CCSDS_OMM_VERS"] = "value" if o.get("version") else "absent"
        blocks = []
        h = o.find("header")
        if h is not None:
            blocks.append(h)
        seg = o.find("body/segment")
        if seg is not None:
            m = seg.find("metadata")
            if m is not None:
                blocks.append(m)
            d = seg.find("data")
            if d is not None:
                for b in d:
                    blocks.append(b)
        for b in blocks:
            for e in b:
                k = _strip_ns(e.tag)
                if k == "COMMENT":
                    fields.setdefault("_comments", []).append(e.text or "")
                    continue
                t = e.text if e.text is not None else ""
                fields[k] = t
                presence[k] = "value" if t.strip() != "" else "empty"
                if "units" in e.attrib:
                    units_seen[k] = e.attrib["units"]
        for k in OMM_META + OMM_TLEP + OMM_MEAN + OMM_HEADER:
            presence.setdefault(k, "absent")
        comments = fields.pop("_comments", None)
        rec = canonical_from_fields(fields, presence, "xml")
        rec["xml"] = {"omm_id_attribute": o.get("id"), "version_attribute": o.get("version"),
                      "comments": comments, "units_attributes": dict(units_seen)}
        recs.append(rec)
    facts = {"root_element": rtag, "root_attributes": {_strip_ns(k): v for k, v in root.attrib.items()},
             "omm_count": len(omms), "version_attributes": sorted({o.get("version") for o in omms}),
             "units_attributes_seen": units_seen}
    return recs, facts


# --------------------------------------------------------------------------- KVN
KVN_LINE = re.compile(r"^\s*([A-Z][A-Z0-9_]*)\s*=\s*(.*?)\s*$")


def read_kvn_text(text):
    msgs = []
    cur = None
    max_len = 0
    for raw in text.splitlines():
        max_len = max(max_len, len(raw))
        line = raw.rstrip()
        if not line.strip():
            continue
        if line.startswith("COMMENT"):
            if cur is not None:
                cur["_comments"].append(line[len("COMMENT"):].lstrip(" ", ) if len(line) > 7 else "")
            continue
        m = KVN_LINE.match(line)
        if not m:
            if cur is not None:
                cur["_unparsed"].append(raw)
            continue
        k, v = m.group(1), m.group(2)
        if k == "CCSDS_OMM_VERS":
            cur = {"_fields": {}, "_order": [], "_units": {}, "_comments": [], "_unparsed": []}
            msgs.append(cur)
        if cur is None:
            continue
        um = re.match(r"^(.*?)\s*\[([^\]]+)\]$", v)
        if um:
            v = um.group(1)
            cur["_units"][k] = um.group(2)
        cur["_fields"][k] = v
        cur["_order"].append(k)
    recs = []
    for m in msgs:
        presence = {k: ("value" if v != "" else "empty") for k, v in m["_fields"].items()}
        for k in OMM_META + OMM_TLEP + OMM_MEAN + OMM_HEADER:
            presence.setdefault(k, "absent")
        rec = canonical_from_fields(m["_fields"], presence, "kvn")
        rec["kvn"] = {"keyword_order": m["_order"], "units": m["_units"], "comments": m["_comments"],
                      "unparsed_lines": m["_unparsed"]}
        recs.append(rec)
    facts = {"message_count": len(msgs), "max_line_length": max_len,
             "keyword_order_first_message": msgs[0]["_order"] if msgs else []}
    return recs, facts


# --------------------------------------------------------------------------- dispatch
def read_file(path):
    raw = open(path, "rb").read()
    text = raw.decode("utf-8")
    ext = path.rsplit(".", 1)[-1].lower()
    if ext in ("tle", "2le"):
        recs, facts = read_tle_text(text), {}
        fmt = "tle" if ext == "tle" else "2le"
    elif ext == "csv":
        recs, facts = read_csv_text(text)
        fmt = "csv"
    elif ext == "json":
        recs, facts = read_json_text(text)
        fmt = "json"
    elif ext == "xml":
        recs, facts = read_xml_text(text)
        fmt = "xml"
    elif ext == "kvn":
        recs, facts = read_kvn_text(text)
        fmt = "kvn"
    else:
        raise ValueError(f"unknown format for {path}")
    facts.update({"format": fmt, "record_count": len(recs), "line_endings": line_endings(raw), "bytes": len(raw)})
    return fmt, recs, facts


if __name__ == "__main__":
    for p in sys.argv[1:]:
        fmt, recs, facts = read_file(p)
        print(p, fmt, facts)
        for r in recs[:2]:
            print(json.dumps(r, indent=1, default=str)[:1500])
