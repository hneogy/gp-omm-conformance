"""
tools/public_scrub.py -- what the public release withholds (DECISIONS D-049).

SupGP-derived snapshot values: the element values (epoch, mean motion, eccentricity, inclination,
node, argument of pericenter, mean anomaly, BSTAR, first and second derivative) and the raw TLE
field substrings of CelesTrak *supplemental* GP records. Catalog numbers, object names and ids,
record counts, hashes, URLs and aggregate statistics are metadata and stay.

Used by tools/export_public.py (to scrub expected.json on the way out), tools/make_failures.py
(to withhold value details in the catalogue) and tests/test_export.py (to prove nothing leaks).
"""
import glob
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUPGP_CASES = ("nine-digit-supgp-launch-nominals", "supgp-celestrak-classification-c")
VALUE_FIELDS = ("epoch", "mean_motion", "eccentricity", "inclination", "ra_of_asc_node", "arg_of_pericenter",
                "mean_anomaly", "bstar", "mean_motion_dot", "mean_motion_ddot")
TLE_VALUE_FIELDS = ("epoch_field", "ndot_field", "nddot_field", "bstar_field", "ecc_field")
# Strings distinctive enough to prove a leak: epochs (microsecond resolution), mean motions (8 decimals) and
# TLE epoch fields (1e-8 day); these are unique per record. Four-decimal angles, seven-digit eccentricities,
# five-digit drag terms and zero fields (' 00000+0') recur legitimately across unrelated objects (verified:
# identical eccentricities and BSTAR strings occur in GP and SupGP records) and are not evidence of a leak.
DISTINCTIVE_FIELDS = ("epoch", "mean_motion")
DISTINCTIVE_TLE_FIELDS = ("epoch_field",)
GENERIC = {"00000+0", "00000-0", "0", "0.0"}
WITHHELD = "SupGP-derived snapshot values withheld from the public release (DECISIONS D-049); structural checks apply to your own fetch"


def is_supgp_source(name):
    return os.path.basename(name or "").startswith("starlink-")


def scrub_expected(exp):
    """Return (scrubbed copy, changed)."""
    exp = json.loads(json.dumps(exp))
    changed = False
    if exp["case"] in SUPGP_CASES:
        n = len(exp.get("records", []))
        exp["records"] = []
        exp["records_withheld"] = f"{WITHHELD}; {n} record(s) removed"
        for s in exp.get("sets", {}).values():
            s.pop("metadata_by_format", None)
        changed = True
    if exp.get("kind") == "pairs":
        items = exp.get("case_specific", {}).get("pairs", [])
        keep = [it for it in items if not (is_supgp_source(it.get("tle_file")) or is_supgp_source(it.get("omm_file")))]
        if len(keep) != len(items):
            exp["case_specific"]["pairs"] = keep
            exp["pairs_withheld"] = f"{WITHHELD}; {len(items) - len(keep)} pair item(s) removed (aggregate summary retained)"
            changed = True
    return exp, changed


def supgp_value_strings(root=ROOT):
    """All SupGP-derived value strings present in this checkout's private expected.json files."""
    out = set()
    for case in SUPGP_CASES:
        p = os.path.join(root, "fixtures", case, "expected.json")
        if not os.path.exists(p):
            continue
        exp = json.load(open(p))
        for r in exp.get("records", []):
            for f in DISTINCTIVE_FIELDS:
                v = r.get("canonical", {}).get(f)
                if v is not None:
                    out.add(str(v))
            tle = r.get("by_format", {}).get("tle", {})
            for f in DISTINCTIVE_TLE_FIELDS:
                v = tle.get("fields", {}).get(f)
                if v:
                    out.add(str(v).strip())
            for k, v in tle.get("differs_from_omm", {}).items():
                if k in DISTINCTIVE_FIELDS:
                    out.add(str(v))
    for p in glob.glob(os.path.join(root, "fixtures", "*", "expected.json")):
        exp = json.load(open(p))
        if exp.get("kind") != "pairs":
            continue
        for it in exp.get("case_specific", {}).get("pairs", []):
            if is_supgp_source(it.get("tle_file")) or is_supgp_source(it.get("omm_file")):
                for vv in (it.get("epoch") or {}).values():
                    if isinstance(vv, str):
                        out.add(vv.strip())
    def distinctive(v):
        return len(v) >= 8 and v not in GENERIC and not set(v) <= set("0.+-") and v not in ("True", "False")
    return {v for v in out if distinctive(v)}


def scrub_audit_md(text):
    """Withhold appendix table rows of AUDIT.md that show SupGP-derived values (case in SUPGP_CASES or a
    starlink-* file). The private original is never altered; only the exported copy changes, and a note
    replaces the rows. Returns (text, rows_removed)."""
    out, removed = [], 0
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")] if line.startswith("|") else None
        if cells and len(cells) >= 3 and (cells[0] in SUPGP_CASES or is_supgp_source(cells[2])):
            removed += 1
            continue
        out.append(line)
    if removed:
        word = "one row" if removed == 1 else f"{removed} rows"
        notice = (f"**Public-copy notice.** {word[0].upper() + word[1:]} of the Appendix A table, a random-sample entry from the "
                  f"`nine-digit-supgp-launch-nominals` case, {'is' if removed == 1 else 'are'} withheld from this "
                  f"public copy because {'it shows' if removed == 1 else 'they show'} SupGP-derived element values "
                  f"(withheld per DECISIONS D-033, implemented by D-049). Nothing else in this document differs from "
                  f"the private original, which is intact.")
        # place the notice directly under the appendix heading and a pointer under the title
        placed = False
        for i, line in enumerate(out):
            if line.startswith("## Appendix A"):
                out.insert(i + 1, "")
                out.insert(i + 2, notice)
                placed = True
                break
        if not placed:
            out += ["", notice]
        for i, line in enumerate(out):
            if line.startswith("# "):
                out.insert(i + 1, "")
                out.insert(i + 2, f"_Public copy: {word} of the Appendix A table withheld; see the notice under Appendix A._")
                break
    return "\n".join(out) + "\n", removed
