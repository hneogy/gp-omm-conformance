#!/usr/bin/env python3
"""
tools/derive_kvn_variants.py -- CCSDS-legal OMM renderings that CelesTrak does not emit.

Base record: the first ISS GP record (1998) from fixtures/epoch-year-19xx/raw/iss-first.csv,
a stable source. Every variant carries exactly the same orbital values; only the syntax and
optional/header content change. Each output has a .provenance.json describing the transform
with a pointer to the CCSDS 502.0-B-3 / 505.0-B-3 clause that allows it.

Header values: CelesTrak leaves CREATION_DATE and ORIGINATOR blank. Where a variant fills
them, the values describe THIS derived message (its generation time and this project as the
originator); they are not claims about CelesTrak or 18 SDS.
"""
import csv
import datetime as dt
import hashlib
import io
import json
import os
import sys
from decimal import Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = "fixtures/epoch-year-19xx/raw/iss-first.csv"
OUT = os.path.join(ROOT, "derived", "kvn-variants")
NOW = dt.datetime.now(dt.timezone.utc)
ORIGINATOR = "GP-OMM-CONFORMANCE-CORPUS"


def plain(s):
    d = Decimal(s)
    t = format(d, "f")
    return (t.rstrip("0").rstrip(".") if "." in t else t) or "0"


def doy_epoch(iso):
    t = dt.datetime.strptime(iso, "%Y-%m-%dT%H:%M:%S.%f")
    return f"{t.year:04d}-{t.timetuple().tm_yday:03d}T{t.strftime('%H:%M:%S.%f')}"


def kvn(pairs, eol="\r\n", pad=True):
    w = max(len(k) for k, _ in pairs if k not in ("", "COMMENT")) if pad else 0
    out = []
    for k, v in pairs:
        if k == "":
            out.append("")
        elif k == "COMMENT":
            out.append(f"COMMENT {v}")
        else:
            out.append(f"{k.ljust(w)} = {v}" if pad else f"{k}={v}")
    return eol.join(out) + eol


def base_pairs(r):
    return [
        ("CCSDS_OMM_VERS", "2.0"), ("CREATION_DATE", ""), ("ORIGINATOR", ""), ("", ""),
        ("OBJECT_NAME", r["OBJECT_NAME"]), ("OBJECT_ID", r["OBJECT_ID"]), ("CENTER_NAME", "EARTH"),
        ("REF_FRAME", "TEME"), ("TIME_SYSTEM", "UTC"), ("MEAN_ELEMENT_THEORY", "SGP/SGP4"), ("", ""),
        ("EPOCH", r["EPOCH"]), ("MEAN_MOTION", r["MEAN_MOTION"]), ("ECCENTRICITY", r["ECCENTRICITY"]),
        ("INCLINATION", r["INCLINATION"]), ("RA_OF_ASC_NODE", r["RA_OF_ASC_NODE"]),
        ("ARG_OF_PERICENTER", r["ARG_OF_PERICENTER"]), ("MEAN_ANOMALY", r["MEAN_ANOMALY"]), ("", ""),
        ("EPHEMERIS_TYPE", r["EPHEMERIS_TYPE"]), ("CLASSIFICATION_TYPE", r["CLASSIFICATION_TYPE"]),
        ("NORAD_CAT_ID", r["NORAD_CAT_ID"]), ("ELEMENT_SET_NO", r["ELEMENT_SET_NO"]),
        ("REV_AT_EPOCH", r["REV_AT_EPOCH"]), ("BSTAR", r["BSTAR"]), ("MEAN_MOTION_DOT", r["MEAN_MOTION_DOT"]),
        ("MEAN_MOTION_DDOT", r["MEAN_MOTION_DDOT"]),
    ]


def variants(r):
    P = base_pairs(r)
    d = dict(P)
    creation = NOW.strftime("%Y-%m-%dT%H:%M:%S")
    v = []
    # v01: CelesTrak-shaped baseline re-serialised (control): identical semantics, CRLF
    v.append(("v01-baseline-reserialised", kvn(P), "Control: CelesTrak's own KVN shape re-serialised from the CSV record.", ["7.4"]))
    # v02: day-of-year epoch + Z terminator
    p2 = [(k, doy_epoch(v_) + "Z" if k == "EPOCH" else v_) for k, v_ in P]
    v.append(("v02-day-of-year-epoch-Z", kvn(p2), "EPOCH in YYYY-DDDThh:mm:ss.d Z form.", ["7.5.10"]))
    # v03: units in brackets, leading-zero decimals, MEAN_ELEMENT_THEORY = SGP4
    units = {"MEAN_MOTION": "rev/day", "INCLINATION": "deg", "RA_OF_ASC_NODE": "deg", "ARG_OF_PERICENTER": "deg",
             "MEAN_ANOMALY": "deg", "BSTAR": "1/ER", "MEAN_MOTION_DOT": "rev/day**2", "MEAN_MOTION_DDOT": "rev/day**3"}
    p3 = []
    for k, v_ in P:
        if k in units or k == "ECCENTRICITY":
            v_ = plain(v_)
        if k in units:
            v_ = f"{v_} [{units[k]}]"
        if k == "MEAN_ELEMENT_THEORY":
            v_ = "SGP4"
        p3.append((k, v_))
    v.append(("v03-units-brackets-leading-zeros", kvn(p3), "Bracketed units after values (Table 4-3 units), decimals written with a leading zero, MEAN_ELEMENT_THEORY = SGP4.", ["7.7.1", "7.5.6", "Table 4-2"]))
    # v04: comments, blank lines, irregular whitespace, LF endings, no alignment padding
    p4 = [("CCSDS_OMM_VERS", "2.0"), ("COMMENT", "Derived conformance fixture; see provenance file"),
          ("COMMENT", "  leading spaces in comment values are significant"), ("CREATION_DATE", ""), ("ORIGINATOR", ""), ("", ""), ("", "")]
    p4 += [("COMMENT", "metadata block")] + [(k, v_) for k, v_ in P[4:10]] + [("COMMENT", "mean elements block")] + P[10:]
    text4 = kvn(p4, eol="\n", pad=False).replace("EPOCH=", "EPOCH   =   ").replace("MEAN_MOTION=", "  MEAN_MOTION =\t")
    v.append(("v04-comments-blank-lines-whitespace-LF", text4, "COMMENT lines at the allowed positions, blank lines, irregular whitespace around '=', a TAB, LF line endings.", ["7.3.5", "7.3.7", "7.4.5", "7.4.6", "7.8.5", "7.8.8"]))
    # v05: OMM 3.0 header filled, optional TLE parameters omitted, CLASSIFICATION present
    p5 = [("CCSDS_OMM_VERS", "3.0"), ("CLASSIFICATION", "UNCLASSIFIED DERIVED TEST DATA"), ("CREATION_DATE", creation),
          ("ORIGINATOR", ORIGINATOR), ("MESSAGE_ID", "GPOMM-KVN-V05"), ("", "")]
    p5 += [(k, "SGP4" if k == "MEAN_ELEMENT_THEORY" else v_) for k, v_ in P[4:10]] + P[10:18]
    p5 += [("BSTAR", d["BSTAR"]), ("MEAN_MOTION_DOT", d["MEAN_MOTION_DOT"]), ("MEAN_MOTION_DDOT", d["MEAN_MOTION_DDOT"])]
    v.append(("v05-omm-3.0-header-optional-keywords-omitted", kvn(p5), "CCSDS_OMM_VERS 3.0; header CLASSIFICATION, CREATION_DATE, ORIGINATOR, MESSAGE_ID filled (describing this derived message); EPHEMERIS_TYPE, CLASSIFICATION_TYPE, NORAD_CAT_ID, ELEMENT_SET_NO and REV_AT_EPOCH omitted, which Table 4-3 permits (all Optional).", ["Table 4-1", "Table 4-3", "7.9.1"]))
    # v06: plus-signed integers and exponent notation with lowercase e
    p6 = []
    for k, v_ in P:
        if k in ("NORAD_CAT_ID", "REV_AT_EPOCH", "ELEMENT_SET_NO", "EPHEMERIS_TYPE"):
            v_ = "+" + v_
        if k == "BSTAR":
            v_ = "0"
        if k == "MEAN_MOTION_DDOT":
            v_ = f"{Decimal(v_):.5e}".replace("E", "e")
        p6.append((k, v_))
    v.append(("v06-signed-integers-lowercase-exponent", kvn(p6), "Integers with explicit '+' sign; MEAN_MOTION_DDOT in floating-point notation with lowercase 'e'.", ["7.5.4", "7.5.7"]))
    return v


def main():
    os.makedirs(OUT, exist_ok=True)
    src = os.path.join(ROOT, SRC)
    meta = json.load(open(src + ".meta.json"))
    r = list(csv.DictReader(io.StringIO(open(src, encoding="utf-8").read())))[0]
    for stem, text, desc, clauses in variants(r):
        out = os.path.join(OUT, stem + ".kvn")
        with open(out, "w", newline="") as f:
            f.write(text)
        prov = {"file": os.path.relpath(out, ROOT), "provenance": "derived",
                "label": "DERIVED: CCSDS-legal KVN re-serialisation of a CelesTrak record; not served by CelesTrak",
                "description": desc, "ccsds_502_0_b3_clauses": clauses,
                "source_file": SRC, "source_sha256": meta["sha256"], "source_url": meta["url"],
                "source_retrieved_at": meta["retrieved_at"], "source_norad_cat_id": int(r["NORAD_CAT_ID"]),
                "generator": "tools/derive_kvn_variants.py",
                "generated_at": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "orbital_values_identical_to_source": True,
                "header_values_note": "Any CREATION_DATE/ORIGINATOR/MESSAGE_ID/CLASSIFICATION values describe this derived message, not the provider.",
                "output_sha256": hashlib.sha256(text.encode()).hexdigest()}
        json.dump(prov, open(out[:-4] + ".provenance.json", "w"), indent=2)
        print(f"{stem}.kvn ({len(text)} bytes)")


if __name__ == "__main__":
    main()
