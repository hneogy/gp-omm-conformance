#!/usr/bin/env python3
"""
tools/make_expected.py -- build fixtures/<case>/expected.json for every case in tools/cases.py.

Offline. Reads raw files with the reference readers (tools/gpref.py), merges the renderings of
each object, checks that all OMM renderings agree, records where the TLE rendering differs and
by how much, and writes the result with source hashes and per-case coverage statements.
Any disagreement between OMM renderings is printed and recorded; none is silently resolved.
"""
import csv
import datetime as dt
import hashlib
import io
import json
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gpref  # noqa: E402
import tlerender as R  # noqa: E402
from cases import CASES, CHECKS, AMBIGUITIES  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOW = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
CANON_KEYS = ["norad_cat_id", "object_name", "object_id", "epoch", "mean_motion", "eccentricity", "inclination",
              "ra_of_asc_node", "arg_of_pericenter", "mean_anomaly", "bstar", "mean_motion_dot", "mean_motion_ddot",
              "ephemeris_type", "classification_type", "element_set_no", "rev_at_epoch"]
META_KEYS = ["center_name", "ref_frame", "time_system", "mean_element_theory", "ccsds_omm_vers", "creation_date", "originator"]
OMM_ORDER = ["csv", "json", "kvn", "xml", "tle", "2le"]
PROBLEMS = []


def meta_for(path):
    mp = os.path.join(ROOT, path + ".meta.json")
    if os.path.exists(mp):
        return json.load(open(mp))
    pp = os.path.join(ROOT, path.rsplit(".", 1)[0] + ".provenance.json")
    if os.path.exists(pp):
        p = json.load(open(pp))
        return {"url": None, "retrieved_at": p.get("generated_at"), "http_status": None, "sha256": p.get("output_sha256"),
                "provenance": "derived", "provenance_file": os.path.relpath(pp, ROOT)}
    return {}


def sha_bytes(path):
    b = open(os.path.join(ROOT, path), "rb").read()
    return hashlib.sha256(b).hexdigest(), len(b)


def source_entry(path, tier, fmt=None, facts=None, record_count=None):
    m = meta_for(path)
    sha, n = sha_bytes(path)
    if m.get("sha256") and m["sha256"] != sha:
        PROBLEMS.append(f"{path}: on-disk sha256 differs from metadata")
    e = {"tier": tier, "format": fmt, "url": m.get("url"), "retrieved_at": m.get("retrieved_at"),
         "http_status": m.get("http_status", 200), "bytes": n, "sha256": sha,
         "provenance": m.get("provenance", "live"), "record_count": record_count}
    if m.get("provenance_file"):
        e["provenance_file"] = m["provenance_file"]
    if m.get("recapture_of"):
        e["recapture_of"] = m["recapture_of"]
    if m.get("superseded_for_citation_by"):
        e["superseded_for_citation_by"] = m["superseded_for_citation_by"]
    if facts:
        e["facts"] = facts
    return e


def strip_record(rec):
    return {k: rec.get(k) for k in CANON_KEYS}


def tle_diff(canon, trec):
    diff = {}
    for k in ("eccentricity", "bstar", "mean_motion_ddot", "mean_motion_dot", "epoch", "mean_motion",
              "inclination", "ra_of_asc_node", "arg_of_pericenter", "mean_anomaly", "object_name", "object_id"):
        a, b = canon.get(k), trec.get(k)
        if a is None or b is None:
            continue
        if k == "object_name":
            if a != b:
                if len(a) > 24 and a[:24].rstrip() == (b or "").rstrip():
                    diff["object_name_truncated_to_24"] = b
                else:
                    diff[k] = b
            continue
        if k in ("epoch", "object_id"):
            if a != b:
                diff[k] = b
            continue
        if Decimal(a) != Decimal(b):
            diff[k] = b
    return diff


def build_gp_set(name, spec, out_sources, out_records, out_notes, out_sets=None):
    tier = spec["tier"]
    by_id = {}
    set_records = []
    for path in spec["files"]:
        full = os.path.join(ROOT, path)
        m = meta_for(path)
        if m.get("http_status", 200) != 200:
            body = open(full, "rb").read().decode("utf-8", "replace")
            out_sources[path] = source_entry(path, tier, fmt=path.rsplit(".", 1)[-1], facts={"response_body": body}, record_count=0)
            continue
        fmt, recs, facts = gpref.read_file(full)
        out_sources[path] = source_entry(path, tier, fmt=fmt, facts=facts, record_count=len(recs))
        for r in recs:
            by_id.setdefault(r["norad_cat_id"], {})[path] = r
    flt = spec.get("record_filter")
    for cat in sorted(by_id):
        if flt == "nine-digit" and cat < 100_000_000:
            continue
        per = by_id[cat]
        ordered = sorted(per.items(), key=lambda kv: OMM_ORDER.index(kv[1]["source_format"]) if kv[1]["source_format"] in OMM_ORDER else 99)
        canon_path, canon_rec = ordered[0]
        canon = strip_record(canon_rec)
        omm = {p: r for p, r in per.items() if r["source_format"] in ("csv", "json", "kvn", "xml")}
        disagreements = []
        for k in CANON_KEYS:
            vals = {}
            for p, r in omm.items():
                v = r.get(k)
                if v is None and r["presence"].get(k.upper(), "absent") == "absent":
                    continue
                key = str(Decimal(v)) if (k in gpref.DECIMAL_KEYS.values() and v is not None) else str(v)
                vals.setdefault(key, []).append(os.path.basename(p))
            if len(vals) > 1:
                disagreements.append({"field": k, "values": vals})
        if disagreements:
            PROBLEMS.append(f"set {name} id {cat}: OMM renderings disagree: {disagreements}")
        metadata_by_format = {}
        for p, r in omm.items():
            metadata_by_format[os.path.basename(p)] = {k: r.get(k) for k in META_KEYS}
        present = {}
        for p, r in per.items():
            pi = {"format": r["source_format"], "presence": {k: r["presence"].get(k) for k in ("OBJECT_NAME", "OBJECT_ID")}}
            if r.get("extra"):
                pi["extra"] = r["extra"]
            present[os.path.basename(p)] = pi
        entry = {"norad_cat_id": cat, "set": name, "tier": tier, "canonical": canon,
                 "canonical_source": os.path.basename(canon_path), "present_in": present,
                 "metadata_by_format": metadata_by_format, "omm_formats_agree": not disagreements}
        if disagreements:
            entry["disagreements"] = disagreements
        tles = [r for r in per.values() if r["source_format"] in ("tle", "2le")]
        if tles and omm:
            t = tles[0]
            d = tle_diff(canon, t)
            entry["by_format"] = {"tle": {"differs_from_omm": d, "fields": {k: v for k, v in t["tle"].items() if k not in ("line0", "line1", "line2")}}}
            if "epoch" in d:
                a = dt.datetime.strptime(canon["epoch"], "%Y-%m-%dT%H:%M:%S.%f")
                b = dt.datetime.strptime(d["epoch"], "%Y-%m-%dT%H:%M:%S.%f")
                entry["by_format"]["tle"]["epoch_difference_us"] = abs((a - b).total_seconds()) * 1e6
        elif tles:
            entry["by_format"] = {"tle": {"fields": {k: v for k, v in tles[0]["tle"].items() if k not in ("line0", "line1", "line2")}}}
        out_records.append(entry)
        set_records.append(entry)
    # metadata_by_format is constant across a set in every observed file; hoist it to set level when so
    if set_records:
        first = json.dumps(set_records[0]["metadata_by_format"], sort_keys=True)
        uniform = all(json.dumps(e["metadata_by_format"], sort_keys=True) == first for e in set_records)
        if uniform:
            for e in set_records:
                del e["metadata_by_format"]
        if out_sets is not None:
            out_sets[name] = {"tier": tier, "files": [os.path.basename(p) for p in spec["files"]], "record_count": len(set_records),
                              "record_filter": flt,
                              "metadata_by_format": set_records[0]["metadata_by_format"] if not uniform else json.loads(first),
                              "metadata_uniform_across_records": uniform}
    if flt == "nine-digit":
        out_notes.append(f"set {name}: only records with NORAD_CAT_ID >= 100000000 are listed ({sum(1 for c in by_id if c >= 100_000_000)} of {len(by_id)}).")


def build_satcat_set(spec, out_sources, out_records):
    for path in spec["files"]:
        full = os.path.join(ROOT, path)
        text = open(full, encoding="utf-8").read()
        if path.endswith(".json"):
            data = json.loads(text, parse_float=Decimal)
            recs = [{k: (str(v) if isinstance(v, Decimal) else v) for k, v in r.items()} for r in data]
            fmt = "satcat-json"
        else:
            recs = list(csv.DictReader(io.StringIO(text)))
            fmt = "satcat-csv"
        out_sources[path] = source_entry(path, spec["tier"], fmt=fmt, record_count=len(recs))
        for r in recs:
            out_records.append({"norad_cat_id": int(r["NORAD_CAT_ID"]), "source": os.path.basename(path), "record": r})


LEGACY_COLS = {"intl_designator": (1, 11), "norad_cat_id": (14, 18), "multiple_name_flag": (20, 20), "payload_flag": (21, 21),
               "ops_status_code": (22, 22), "name": (24, 47), "owner": (50, 54), "launch_date": (57, 66), "launch_site": (69, 73),
               "decay_date": (76, 85), "period_min": (88, 94), "inclination_deg": (97, 101), "apogee_km": (104, 109),
               "perigee_km": (112, 117), "rcs_m2": (120, 127), "orbital_status_code": (130, 132)}


def parse_legacy(line):
    return {k: line[a - 1:b].strip() for k, (a, b) in LEGACY_COLS.items()}


def build_satcat_legacy(spec, out_sources, case_specific):
    path = spec["files"][0]
    raw = open(os.path.join(ROOT, path), "rb").read()
    lines = raw.decode("utf-8", "replace").splitlines()
    ids = [int(l[13:18]) for l in lines if l[13:18].strip().isdigit()]
    facts = {"line_count": len(lines), "numeric_id_lines": len(ids), "min_id": min(ids), "max_id": max(ids),
             "ids_at_or_above_70000": sum(i >= 70000 for i in ids), "contiguous_1_to_max": sorted(ids) == list(range(1, max(ids) + 1)),
             "line_endings": gpref.line_endings(raw), "column_layout_source": "https://celestrak.org/satcat/satcat-format.php (Legacy Text Data Format)"}
    out_sources[path] = source_entry(path, spec["tier"], fmt="satcat-legacy-fixed-width", facts=facts, record_count=len(ids))
    picked = {}
    for l in lines:
        s = l[13:18].strip()
        if s.isdigit() and int(s) in (25544, 69999):
            picked[int(s)] = parse_legacy(l)
    case_specific["legacy_parsed_records"] = picked
    case_specific["legacy_has_100000"] = any(l[13:18].strip() == "100000" for l in lines)
    case_specific["legacy_facts"] = facts


def pairs_analysis(pairs):
    out = []
    for tpath, cpath in pairs:
        _, trecs, _ = gpref.read_file(os.path.join(ROOT, tpath))
        _, crecs, _ = gpref.read_file(os.path.join(ROOT, cpath))
        cm = {r["norad_cat_id"]: r for r in crecs}
        for t in trecs:
            c = cm.get(t["norad_cat_id"])
            if not c:
                continue
            csv_fields = {k: None for k in ()}
            # raw OMM texts for the fields of interest, from the CSV row (re-read as text)
            out.append((tpath, cpath, t, c))
    return out


def omm_texts(cpath):
    rows = list(csv.DictReader(io.StringIO(open(os.path.join(ROOT, cpath), encoding="utf-8").read())))
    return {int(r["NORAD_CAT_ID"]): r for r in rows}


def build_precision_loss(pairs):
    items, summary = [], {"pairs": 0, "names_longer_than_24": 0, "tle_line0_equals_first_24_chars": 0, "ecc_omm_more_than_7_digits": 0, "ecc_tle_equals_truncation": 0, "ecc_tle_equals_rounding": 0,
                          "bstar_numerically_equal": 0, "bstar_tle_equals_round_half_up_5": 0, "bstar_tle_equals_truncate_5": 0,
                          "ddot_numerically_equal": 0, "ddot_tle_equals_round_half_up_5": 0, "epoch_exact": 0, "epoch_max_diff_us": 0.0}
    for tpath, cpath in pairs:
        _, trecs, _ = gpref.read_file(os.path.join(ROOT, tpath))
        texts = omm_texts(cpath)
        for t in trecs:
            row = texts.get(t["norad_cat_id"])
            if not row:
                continue
            summary["pairs"] += 1
            e_txt = row["ECCENTRICITY"]
            digits = e_txt.split(".")[1] if "." in e_txt else ""
            ecc_more = len(digits) > 7
            trunc = R.ecc_field(e_txt, "truncate") == t["tle"]["ecc_field"]
            rnd = R.ecc_field(e_txt, "round") == t["tle"]["ecc_field"]
            b_round = R.exp_field(row["BSTAR"], "round") == t["tle"]["bstar_field"]
            b_trunc = R.exp_field(row["BSTAR"], "truncate") == t["tle"]["bstar_field"]
            b_eq = Decimal(row["BSTAR"] or "0") == Decimal(t["bstar"])
            d_round = R.exp_field(row["MEAN_MOTION_DDOT"], "round") == t["tle"]["nddot_field"]
            d_eq = Decimal(row["MEAN_MOTION_DDOT"] or "0") == Decimal(t["mean_motion_ddot"])
            a = dt.datetime.strptime(row["EPOCH"], "%Y-%m-%dT%H:%M:%S.%f")
            b = dt.datetime.strptime(t["epoch"], "%Y-%m-%dT%H:%M:%S.%f")
            ediff = abs((a - b).total_seconds()) * 1e6
            nm = row["OBJECT_NAME"]
            if len(nm) > 24:
                summary["names_longer_than_24"] += 1
                summary["tle_line0_equals_first_24_chars"] += (t["tle"]["line0"] == nm[:24])
            summary["ecc_omm_more_than_7_digits"] += ecc_more
            summary["ecc_tle_equals_truncation"] += trunc
            summary["ecc_tle_equals_rounding"] += rnd
            summary["bstar_numerically_equal"] += b_eq
            summary["bstar_tle_equals_round_half_up_5"] += b_round
            summary["bstar_tle_equals_truncate_5"] += b_trunc
            summary["ddot_numerically_equal"] += d_eq
            summary["ddot_tle_equals_round_half_up_5"] += d_round
            summary["epoch_exact"] += (ediff == 0)
            summary["epoch_max_diff_us"] = max(summary["epoch_max_diff_us"], ediff)
            items.append({"norad_cat_id": t["norad_cat_id"], "tle_file": os.path.basename(tpath), "omm_file": os.path.basename(cpath),
                          "eccentricity": {"omm_text": e_txt, "tle_field": t["tle"]["ecc_field"], "omm_decimals": len(digits), "tle_equals_truncation": trunc, "tle_equals_rounding": rnd},
                          "bstar": {"omm_text": row["BSTAR"], "tle_field": t["tle"]["bstar_field"], "numerically_equal": b_eq, "tle_equals_round_half_up_5": b_round, "tle_equals_truncate_5": b_trunc},
                          "mean_motion_ddot": {"omm_text": row["MEAN_MOTION_DDOT"], "tle_field": t["tle"]["nddot_field"], "numerically_equal": d_eq, "tle_equals_round_half_up_5": d_round},
                          "epoch": {"omm": row["EPOCH"], "tle_field": t["tle"]["epoch_field"], "tle_as_iso": t["epoch"], "difference_us": ediff}})
    return items, summary


def build_mmdot(pairs):
    items, n, eq_dot, eq_ddot = [], 0, 0, 0
    for tpath, cpath in pairs:
        _, trecs, _ = gpref.read_file(os.path.join(ROOT, tpath))
        texts = omm_texts(cpath)
        for t in trecs:
            row = texts.get(t["norad_cat_id"])
            if not row:
                continue
            n += 1
            a = Decimal(row["MEAN_MOTION_DOT"]) == Decimal(t["mean_motion_dot"])
            b = Decimal(row["MEAN_MOTION_DDOT"] or "0") == Decimal(t["mean_motion_ddot"])
            eq_dot += a
            eq_ddot += b
            items.append({"norad_cat_id": t["norad_cat_id"], "tle_file": os.path.basename(tpath), "omm_file": os.path.basename(cpath),
                          "omm_mean_motion_dot": row["MEAN_MOTION_DOT"], "tle_ndot_field": t["tle"]["ndot_field"], "equal": a,
                          "omm_mean_motion_ddot": row["MEAN_MOTION_DDOT"], "tle_nddot_field": t["tle"]["nddot_field"], "ddot_equal": b})
    return items, {"pairs": n, "mean_motion_dot_equal_to_tle_field": eq_dot, "mean_motion_ddot_equal_to_tle_field": eq_ddot,
                   "interpretation": "OMM carries the TLE field values as printed (ndot/2 and nddot/6 in the SGP4 Taylor-series sense); multiply by 2 and 6 for the true derivatives (CCSDS 4.2.4.7 NOTE 2)."}


def build_derived_tle(case, out_sources, out_records):
    spec = case["sets"]["derived"]
    for path in spec["files"]:
        prov = json.load(open(os.path.join(ROOT, path.rsplit(".", 1)[0] + ".provenance.json")))
        _, trecs, facts = gpref.read_file(os.path.join(ROOT, path))
        texts = omm_texts(prov["source_file"])
        src_recs = {r["norad_cat_id"]: r for r in gpref.read_file(os.path.join(ROOT, prov["source_file"]))[1]}
        out_sources[path] = source_entry(path, "stable", fmt="tle", facts=facts, record_count=len(trecs))
        for t in trecs:
            s = src_recs[t["norad_cat_id"]]
            canon = strip_record(s)
            d = tle_diff(canon, t)
            unexpected = {k: v for k, v in d.items() if k not in ("eccentricity", "bstar", "mean_motion_ddot", "object_name_truncated_to_24")}
            if unexpected:
                PROBLEMS.append(f"derived {path} id {t['norad_cat_id']}: unexpected difference from source {unexpected}")
            out_records.append({"norad_cat_id": t["norad_cat_id"], "set": "derived", "tier": "stable", "derived_file": os.path.basename(path),
                                "source_file": prov["source_file"], "canonical": canon, "canonical_source": os.path.basename(prov["source_file"]),
                                "by_format": {"tle": {"differs_from_omm": d, "fields": {k: v for k, v in t["tle"].items() if k not in ("line0", "line1", "line2")}}},
                                "alpha5": {"field": t["tle"]["catalog_field"], "letter": t["tle"]["catalog_field"][0], "decodes_to": t["norad_cat_id"],
                                           "expected_field": R.to_alpha5(t["norad_cat_id"])}})


def build_derived_kvn(case, out_sources, out_records):
    base = gpref.read_file(os.path.join(ROOT, case["base"]))[1][0]
    canon = strip_record(base)
    for path in case["sets"]["variants"]["files"]:
        prov = json.load(open(os.path.join(ROOT, path.rsplit(".", 1)[0] + ".provenance.json")))
        _, recs, facts = gpref.read_file(os.path.join(ROOT, path))
        out_sources[path] = source_entry(path, "stable", fmt="kvn", facts=facts, record_count=len(recs))
        r = recs[0]
        diffs = {}
        for k in CANON_KEYS:
            if r.get(k) is None and r["presence"].get(k.upper()) == "absent":
                continue
            a, b = canon.get(k), r.get(k)
            if k in gpref.DECIMAL_KEYS.values():
                if a is not None and b is not None and Decimal(a) != Decimal(b):
                    diffs[k] = b
            elif k == "epoch":
                # allow day-of-year / Z forms: compare instants
                def inst(s):
                    s = s.rstrip("Z")
                    if len(s.split("T")[0]) == 8:
                        return dt.datetime.strptime(s, "%Y-%jT%H:%M:%S.%f")
                    return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%S.%f")
                if inst(a) != inst(b):
                    diffs[k] = b
            elif a != b:
                diffs[k] = b
        if diffs:
            PROBLEMS.append(f"derived kvn {path}: value differences from base {diffs}")
        out_records.append({"norad_cat_id": canon["norad_cat_id"], "set": "variants", "tier": "stable", "derived_file": os.path.basename(path),
                            "transform": prov["description"], "ccsds_clauses": prov["ccsds_502_0_b3_clauses"],
                            "canonical": canon, "values_identical_to_base": not diffs, "differences": diffs,
                            "as_written": {"epoch": r["epoch"], "ccsds_omm_vers": r["ccsds_omm_vers"], "creation_date": r["creation_date"], "originator": r["originator"],
                                           "mean_element_theory": r["mean_element_theory"], "message_id": r.get("message_id"), "classification": r.get("classification")},
                            "keywords_absent": [k for k in ("EPHEMERIS_TYPE", "CLASSIFICATION_TYPE", "NORAD_CAT_ID", "ELEMENT_SET_NO", "REV_AT_EPOCH") if r["presence"].get(k) == "absent"],
                            "kvn": r.get("kvn")})


REFERENCE_TLE_FIELD_KEYS = ["catalog_field", "epoch_field", "ndot_field", "nddot_field", "bstar_field", "ecc_field",
                            "element_set_field", "rev_field", "intl_designator_field"]


def originating_tier(path, from_case):
    """The tier the case that owns a file recorded for it (D-114). The writer case's inputs are frozen records, so
    the records are stable, but a source file keeps its own tier: the two rolling group files are live."""
    for cid in (from_case, path.split("/")[1] if path.startswith("fixtures/") else None):
        if not cid:
            continue
        f = os.path.join(ROOT, "fixtures", cid, "expected.json")
        if os.path.exists(f):
            tier = json.load(open(f)).get("sources", {}).get(path, {}).get("tier")
            if tier:
                return tier
    PROBLEMS.append(f"{path}: no originating case records a tier for it; labelled live")
    return "live"


def build_writer(case, out_sources, out_records, out_notes, case_specific):
    """Writer-case inputs: canonical records copied from the frozen expected.json of stable-tier sets of other
    cases (no fetch, no raw bytes), plus the owner-approved synthetic-derived refusal inputs (D-096)."""
    seen, letters, five_digit, files = set(), {}, [], {}
    for spec in case["inputs_from"]:
        e = json.load(open(os.path.join(ROOT, "fixtures", spec["case"], "expected.json")))
        for r in e["records"]:
            if spec.get("set") and r.get("set") != spec["set"]:
                continue
            if r.get("tier") != "stable":
                PROBLEMS.append(f"writer input {spec['case']} id {r['norad_cat_id']}: not a stable-tier record; only frozen records may be inputs")
                continue
            cat = r["norad_cat_id"]
            if cat in seen:
                continue
            seen.add(cat)
            if r.get("derived_file"):
                from_file = next(p for p in e["sources"] if os.path.basename(p) == r["derived_file"])
                src_file, rendering = r["source_file"], "celestrak-style-derived-line"
            else:
                from_file = next(p for p in e["sources"] if os.path.basename(p) == r["canonical_source"])
                src_file, rendering = from_file, "celestrak-tle"
            files.setdefault(from_file, spec["case"])
            files.setdefault(src_file, spec["case"])
            entry = {"norad_cat_id": cat, "role": "input", "provenance": "derived", "tier": "stable",
                     "derived_from": f"fixtures/{spec['case']}/expected.json: frozen canonical values of a stable-tier source (v0.1.0)",
                     "from_case": spec["case"], "from_file": from_file, "source_file": src_file,
                     "source_sha256": meta_for(src_file).get("sha256"), "canonical": r["canonical"],
                     "representable_in_tle": True, "expected_catalog_field": R.to_alpha5(cat), "reference_rendering": rendering}
            fields = (r.get("by_format") or {}).get("tle", {}).get("fields")
            if fields:
                entry["reference_tle_fields"] = {k: v for k, v in fields.items() if k in REFERENCE_TLE_FIELD_KEYS}
            out_records.append(entry)
            if cat >= 100000:
                letters[entry["expected_catalog_field"][0]] = letters.get(entry["expected_catalog_field"][0], 0) + 1
            else:
                five_digit.append(cat)
    n_frozen = len(out_records)
    u = case["unrepresentable"]
    e = json.load(open(os.path.join(ROOT, "fixtures", u["from_case"], "expected.json")))
    base = next(r for r in e["records"] if r.get("set") == u["set"])
    base_file = next(p for p in e["sources"] if os.path.basename(p) == base["canonical_source"])
    files.setdefault(base_file, u["from_case"])
    vec = json.load(open(os.path.join(ROOT, u["vectors"])))
    for v in vec["encode_unrepresentable"]:
        n = v["norad_cat_id"]
        rec = dict(base["canonical"])
        rec["norad_cat_id"] = n
        out_records.append({"norad_cat_id": n, "role": "input", "provenance": "synthetic-derived", "tier": "stable",
                            "from_case": u["from_case"], "from_file": base_file, "source_file": base_file,
                            "source_sha256": e["sources"][base_file]["sha256"],
                            "synthetic_change": {"field": "NORAD_CAT_ID", "from": base["norad_cat_id"], "to": n,
                                                 "vector_source": f"{u['vectors']} encode_unrepresentable", "reason": v["reason"]},
                            "canonical": rec, "representable_in_tle": False, "expected_catalog_field": None, "expected_behaviour": "refuse",
                            "note": "The TLE catalog field cannot represent this number, so a refusal (an error, no lines) is the correct output; the OMM formats carry it. "
                                    "Real elements with a vector id: no catalogued object carries this number. Owner approval 2026-09-22 (DECISIONS D-096)."})
    n_vectors = 0
    for sv in case.get("synthetic_field_vectors", []):  # field forms no fetched record supplies, rendered by the corpus (D-125)
        e2 = json.load(open(os.path.join(ROOT, "fixtures", sv["from_case"], "expected.json")))
        b2 = next(r for r in e2["records"] if r.get("set") == sv["set"])
        b2_file = next(p for p in e2["sources"] if os.path.basename(p) == b2["canonical_source"])
        files.setdefault(b2_file, sv["from_case"])
        rec = dict(b2["canonical"])
        rec["norad_cat_id"] = sv["norad_cat_id"]
        rec[sv["field"]] = sv["value"]
        l0, l1, l2 = R.render(R.omm_fields_from_record(rec), mantissa_mode="round", ecc_mode="truncate")
        fields = {k: v for k, v in gpref.parse_tle_lines(l0, l1, l2)["tle"].items() if k in REFERENCE_TLE_FIELD_KEYS}
        if fields[sv["field"] + "_field"] != sv["expected_tle_field"]:
            PROBLEMS.append(f"synthetic field vector {sv['norad_cat_id']}: rendered {fields[sv['field'] + '_field']!r}, expected {sv['expected_tle_field']!r}")
        out_records.append({"norad_cat_id": sv["norad_cat_id"], "role": "input", "provenance": "synthetic-derived", "tier": "stable",
                            "from_case": sv["from_case"], "from_file": b2_file, "source_file": b2_file, "source_sha256": e2["sources"][b2_file]["sha256"],
                            "synthetic_changes": [{"field": "NORAD_CAT_ID", "from": b2["norad_cat_id"], "to": sv["norad_cat_id"], "vector_source": sv["id_vector_source"]},
                                                  {"field": sv["field"].upper(), "from": b2["canonical"][sv["field"]], "to": sv["value"], "vector_source": sv["value_vector_source"], "reason": sv["reason"]}],
                            "canonical": rec, "representable_in_tle": True, "expected_catalog_field": R.to_alpha5(sv["norad_cat_id"]), "expected_behaviour": "write",
                            "expected_tle_field": {sv["field"] + "_field": sv["expected_tle_field"]},
                            "reference_rendering": "corpus-rendered", "reference_tle_fields": fields, "note": sv["note"]})
        n_vectors += 1
    for path in sorted(files):
        fmt, recs, _ = gpref.read_file(os.path.join(ROOT, path))
        out_sources[path] = source_entry(path, originating_tier(path, files[path]), fmt=fmt, record_count=len(recs))
    case_specific.update({
        "inputs": {"frozen_records": n_frozen, "synthetic_derived": len(vec["encode_unrepresentable"]), "synthetic_field_vectors": n_vectors, "alpha5_letters": letters, "five_digit_ids": five_digit},
        "writer_protocol": "write_tle(record) -> (line1, line2) or (line0, line1, line2); raise to refuse. External: --write-cmd, one JSON record on stdin, the lines on stdout, exit 3 = unsupported, other non-zero = refused.",
        "precision_rule": "A written element field equals the input quantised at the TLE field's resolution (epoch 1e-8 day; mean motion 8 decimals; angles 4; eccentricity 7 digits; BSTAR 5-digit mantissa) by truncation or by rounding half up; the convention observed is reported per field. Refusing a catalog number above 339999 or below 0 is the correct output.",
    })
    out_notes.append(f"{n_frozen} frozen input records ({sum(letters.values())} Alpha-5, {len(five_digit)} five-digit), {len(vec['encode_unrepresentable'])} synthetic-derived refusal inputs and {n_vectors} synthetic-derived field vector(s) rendered by the corpus.")


def main():
    wanted = set(sys.argv[1:])  # optional case ids: rebuild only those files, leaving the others' frozen values untouched
    xmlval = {}
    xp = os.path.join(ROOT, "tools", "_out", "xml-validation.json")
    if os.path.exists(xp):
        xmlval = json.load(open(xp))
    mm_pairs = next(c for c in CASES if c["id"] == "mean-motion-derivative-convention")["pairs"]
    for case in CASES:
        if wanted and case["id"] not in wanted:
            continue
        out = {"case": case["id"], "title": case["title"], "schema_version": "1.0", "generated_at": NOW, "generator": "tools/make_expected.py",
               "kind": case["kind"], "sources": {}, "records": [], "checks": [{"id": c, "description": CHECKS[c]} for c in case["checks"]],
               "tests": case["tests"], "coverage": case["coverage"],
               "ambiguities": [{"id": a, "text": AMBIGUITIES[a]} for a in case["ambiguities"]], "notes": [], "sets": {}, "case_specific": {}}
        kind = case["kind"]
        if kind == "gp":
            for name, spec in case["sets"].items():
                if spec.get("kind") == "satcat":
                    build_satcat_set(spec, out["sources"], out["case_specific"].setdefault("satcat_records", []))
                else:
                    build_gp_set(name, spec, out["sources"], out["records"], out["notes"], out["sets"])
        elif kind == "satcat":
            for name, spec in case["sets"].items():
                if spec.get("kind") == "satcat-legacy":
                    build_satcat_legacy(spec, out["sources"], out["case_specific"])
                else:
                    build_satcat_set(spec, out["sources"], out["case_specific"].setdefault("satcat_records", []))
        elif kind == "facts":
            for name, spec in case["sets"].items():
                for path in spec["files"]:
                    fmt, recs, facts = gpref.read_file(os.path.join(ROOT, path))
                    out["sources"][path] = source_entry(path, "mixed", fmt=fmt, facts=facts, record_count=len(recs))
        elif kind == "pairs":
            pairs = case["pairs"] or mm_pairs
            for tpath, cpath in pairs:
                for p in (tpath, cpath):
                    if p not in out["sources"]:
                        fmt, recs, facts = gpref.read_file(os.path.join(ROOT, p))
                        out["sources"][p] = source_entry(p, "mixed", fmt=fmt, record_count=len(recs))
            if case["id"] == "tle-vs-omm-precision-loss":
                items, summary = build_precision_loss(pairs)
            else:
                items, summary = build_mmdot(pairs)
            out["case_specific"] = {"summary": summary, "pairs": items}
        elif kind == "xml":
            for path in case["files"]:
                fmt, recs, facts = gpref.read_file(os.path.join(ROOT, path))
                out["sources"][path] = source_entry(path, "mixed", fmt=fmt, facts=facts, record_count=len(recs))
                out["case_specific"][path] = {"validation": xmlval.get(path, "not run"),
                                              "header_empty_elements": sorted({k for r in recs for k in ("creation_date", "originator") if r.get(k) is None})}
        elif kind == "vectors":
            for path in case["files"]:
                sha, n = sha_bytes(path)
                out["sources"][path] = {"tier": "stable", "format": "vectors-json", "bytes": n, "sha256": sha, "provenance": "specification"}
                out["case_specific"][path] = json.load(open(os.path.join(ROOT, path)))
        elif kind == "derived-tle":
            build_derived_tle(case, out["sources"], out["records"])
        elif kind == "derived-kvn":
            build_derived_kvn(case, out["sources"], out["records"])
        elif kind == "writer":
            build_writer(case, out["sources"], out["records"], out["notes"], out["case_specific"])
        d = os.path.join(ROOT, "fixtures", case["id"])
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "expected.json"), "w") as f:
            json.dump(out, f, indent=1, default=str)
            f.write("\n")
        print(f"{case['id']}: {len(out['sources'])} sources, {len(out['records'])} records, "
              f"{sum(1 for r in out['records'] if not r.get('omm_formats_agree', True))} disagreements")
    if PROBLEMS:
        print("\nPROBLEMS (must be resolved or recorded, never ignored):")
        for p in PROBLEMS:
            print("  -", p)
        sys.exit(1)


if __name__ == "__main__":
    main()
