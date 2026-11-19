# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
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
        exp = json.load(open(p, encoding="utf-8"))
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
        exp = json.load(open(p, encoding="utf-8"))
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


# D-462 (the owner's ruling of 2026-11-10): the exported decision log names neither the coding assistant nor its
# instructions file. The private log is append-only and never altered; only the exported copy changes, with a note.
# D-545 (the owner's ruling of 2026-11-14): the public tree never spells those names either, so the rewording table,
# its fallbacks, the names the export refuses to publish and the cases that prove each check are in the private names
# file, which stays in the private repository and which the export refuses. Without it (in the public tree) the
# rewording and the name check do not run; the export says so.
PRIVATE_NAMES_PATH = os.path.join(ROOT, "tools", "private-names.json")


def _private_names():
    if not os.path.exists(PRIVATE_NAMES_PATH):
        return None
    with open(PRIVATE_NAMES_PATH, encoding="utf-8") as f:
        return json.load(f)


PRIVATE_NAMES = _private_names()


def named_in(text):
    """-> the private names `text` holds, case-insensitive (D-545); [] when it holds none or the file is absent."""
    import re
    if not PRIVATE_NAMES:
        return []
    return [m.group(0) for w in PRIVATE_NAMES["names"] for m in re.finditer(w, text, re.I)]


DECISIONS_NOTE = ("*Public copy: the coding assistant's name and its instructions file, which stays in the maintainer's private "
                  "repository, are reworded here (D-462), and passages about unreported findings and private correspondence "
                  "are shortened (D-542); the private original is intact.*")

# D-542, D-612, D-613: what the public copy withholds from the decision log, the changelog and named files is listed in
# a private file, tools/private-passages.json, never exported (D-613: no hash of removed text goes public). Each passage
# is found from a neutral head to the first tail after it and replaced only if its SHA-256 is the recorded one; a
# passage missing or changed stops the export. Without the file (the public tree) every list is empty and the tree is
# taken as already shortened.
PRIVATE_PASSAGES_PATH = os.path.join(ROOT, "tools", "private-passages.json")


def _private_passages():
    if not os.path.exists(PRIVATE_PASSAGES_PATH):
        return {}
    with open(PRIVATE_PASSAGES_PATH, encoding="utf-8") as f:
        return json.load(f)


PASSAGES = _private_passages()
_PRIVATE = [tuple(x) for x in PASSAGES.get("passages", [])]
_STUBS = [tuple(x) for x in PASSAGES.get("stubs", [])]
_CHANGELOG = [tuple(x) for x in PASSAGES.get("changelog", [])]
_FILES = [tuple(x) for x in PASSAGES.get("files", [])]
EXEMPT_WINDOWS = set(PASSAGES.get("exempt_windows", []))
STUB_LINES = tuple(line for _, _, line in _STUBS)


def entry_start(text, entry):
    """Where an entry begins: "**D-n (" for a dated entry, "**D-n —" for the early undated ones (D-613: a lookup by the
    dated form alone skipped them silently). -1 if the text does not hold it."""
    found = [i for i in (text.find(f"**{entry} ("), text.find(f"**{entry} —")) if i >= 0]
    return min(found) if found else -1


class PrivatePassageError(ValueError):
    """A D-542 passage is missing or not the one recorded: the export stops rather than publish it."""


def scrub_private_passages(text):
    """-> (text, n): the D-542 passages shortened. An entry the text does not hold is skipped (a short test text);
    an entry already shortened is left alone; any other mismatch raises PrivatePassageError."""
    import hashlib
    n = 0
    for entry, head, tail, digest, new in _PRIVATE:
        start = entry_start(text, entry)
        if start < 0:
            continue
        end = text.find("\n**D-", start + 1)
        end = len(text) if end < 0 else end
        body = text[start:end]
        if body.count(head) != 1:
            if new in body:
                continue
            raise PrivatePassageError(f"{entry}: the passage's head is not found exactly once")
        i = body.find(head)
        j = body.find(tail, i + len(head))
        span = body[i:j + len(tail)] if j >= 0 else ""
        if j < 0 or hashlib.sha256(span.encode("utf-8")).hexdigest() != digest:
            if new in body:
                continue
            raise PrivatePassageError(f"{entry}: the passage is not the one D-542 records")
        text = text[:start] + body[:i] + new + body[j + len(tail):] + text[end:]
        n += 1
    return text, n






def scrub_stubbed_entries(text):
    """-> (text, n): each _STUBS entry replaced by its one line. An entry the text does not hold is skipped; an entry
    already stubbed is left alone; any other mismatch raises PrivatePassageError."""
    import hashlib
    n = 0
    for entry, digest, line in _STUBS:
        start = entry_start(text, entry)
        if start < 0:
            continue
        ends = [x for x in (text.find("\n**D-", start + 1), text.find("\n## ", start + 1)) if x > 0]
        end = min(ends) if ends else len(text)
        body = text[start:end]
        if body == line + "\n" or body == line:
            continue
        if hashlib.sha256(body.encode("utf-8")).hexdigest() != digest:
            raise PrivatePassageError(f"{entry}: the entry is not the one D-612 records")
        text = text[:start] + line + ("\n" if body.endswith("\n") else "") + text[end:]
        n += 1
    return text, n


def scrub_changelog_md(text):
    """-> (text, n): the exported CHANGELOG.md with the D-612 passages shortened. A release the text does not hold is
    skipped (a short test text); a passage already shortened is left alone; any other mismatch raises."""
    import hashlib
    n = 0
    for release, head, tail, digest, new in _CHANGELOG:
        start = text.find(f"## [{release}]")
        if start < 0:
            continue
        end = text.find("\n## [", start + 1)
        end = len(text) if end < 0 else end
        body = text[start:end]
        if body.count(head) != 1:
            if new in body:
                continue
            raise PrivatePassageError(f"CHANGELOG {release}: the passage's head is not found exactly once")
        i = body.find(head)
        j = body.find(tail, i + len(head))
        span = body[i:j + len(tail)] if j >= 0 else ""
        if j < 0 or hashlib.sha256(span.encode("utf-8")).hexdigest() != digest:
            if new in body:
                continue
            raise PrivatePassageError(f"CHANGELOG {release}: the passage is not the one D-612 records")
        text = text[:start] + body[:i] + new + body[j + len(tail):] + text[end:]
        n += 1
    return text, n


def scrub_file_passages(rel, text):
    """-> (text, n): the private file's passages for one exported file (D-613), each found from its head to the first
    tail after it and replaced only if its SHA-256 matches; a passage missing or changed raises PrivatePassageError."""
    import hashlib
    n = 0
    for path, head, tail, digest, new in _FILES:
        if path != rel:
            continue
        if text.count(head) != 1:
            if new and new in text:
                continue
            raise PrivatePassageError(f"{rel}: the passage's head is not found exactly once")
        i = text.find(head)
        j = text.find(tail, i + len(head))
        span = text[i:j + len(tail)] if j >= 0 else ""
        if j < 0 or hashlib.sha256(span.encode("utf-8")).hexdigest() != digest:
            raise PrivatePassageError(f"{rel}: the passage is not the recorded one")
        text = text[:i] + new + text[j + len(tail):]
        n += 1
    return text, n


def scrub_decisions_md(text):
    """-> (text, n): the exported DECISIONS.md with every mention of the coding assistant reworded (D-462) and the
    D-542 passages shortened, and a note under the title; n counts the replacements. The rewording table and its
    fallbacks are in the private names file (D-545); without it only the D-542 passages are shortened."""
    import re
    text, k = scrub_stubbed_entries(text)   # whole entries first (D-612), then the passages
    text, n = scrub_private_passages(text)
    n += k
    if PRIVATE_NAMES:
        for old, new in PRIVATE_NAMES["decisions_table"]:
            n += text.count(old)
            text = text.replace(old, new)
        for pattern, new in PRIVATE_NAMES["decisions_fallback"]:
            text, k = re.subn(pattern, new, text)
            n += k
    if n:
        title, _, rest = text.partition("\n")
        text = title + "\n\n" + DECISIONS_NOTE + "\n" + rest
    return text, n
