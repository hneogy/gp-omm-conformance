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

# D-542 (the owner's ruling of 2026-11-14): passages in entries since 0.8.0 that spell out unreported findings (against
# D-134) or private correspondence are shortened in the exported copy. This file is exported, so it never holds the
# passages themselves: each is found inside its own entry from a neutral head to the first tail after it, and replaced
# only if its SHA-256 is the one below. A passage missing or changed stops the export.
_PRIVATE = [
    # (entry, head, tail, SHA-256 of the passage from head through tail, the replacement)
    ("D-388", "confirms written bundling permission ", "Dr. Kelso.",
     "50eba8e74d6547c17f081c08c4db24b51265f99462da1be9069b21281d53ee17",
     "confirms written bundling permission, which is asked for separately."),
    ("D-388", "confirms Dr. Kelso's ", "written permission",
     "0e25669efd814d0ee90dc6412724b63cab58b00e389afd6ee812b88e07fee254",
     "confirms written bundling permission, asked for separately"),
    ("D-474", "§2 0.9.0 ships without Vallado's files, ", "later",
     "a0a8e1aa2b554157cb52c81368f4a8bc8ad6d1ed503e15c1403ae7a35fec21e6",
     "§2 0.9.0 ships without Vallado's files, the bundling permission is asked for separately"),
    ("D-497", "- Still failing in both modes: ", "on 8 Nov.",
     "cee1be692792e4b1e17e5f517e403737aa2d26b652287ecb01d2704a20302898",
     "- Still failing in both modes: two unreported minor observations (8 Nov), recorded privately (the Batch G "
     "convention, D-134)."),
    ("D-498", "The six still failing are the ", "observations.",
     "356b3f9791783f59983fc739c0680f8752bbe7b5ff10a7d5347b9279f58921a3",
     "The six still failing are the two unreported observations (D-134)."),
    ("D-499", "and keep the ", "for after 0.9.0.",
     "5827e2e2ab93b7a222ef69a23b5b2738d5f81c04a9e50bd5588a90dce2982c0b",
     "and keep two unreported findings in the ledger, for after 0.9.0."),
    ("D-499", "It lists satkit's ", "again on 0.24.3.",
     "586d1531386b025ff2869e29fb88995974b058e29f4ba0369157868badb88571",
     "It lists two satkit observations, seen on 0.24.2 (8 Nov) and again on 0.24.3; their specifics stay private "
     "until reported (D-134)."),
    ("D-502", "the owner's permission request ", "covers both",
     "cd3f919ce813b7a8d32902e54c2cac50f53bdc53f2a80226e0c71dcd2030003c",
     "the owner's permission request covers both"),
    ("D-502", "D-388 keeps ", "the owner's to send.",
     "9ff1b865846f3714d499e0992bf6b43e4f37b23a5e6b9f5aae63169cbc94f59e",
     "D-388 keeps `SGP4-VER.TLE` and `tcppver.out` private until the owner confirms written bundling permission. The "
     "request for that permission covers both files; its text stays private. No file or other entry changes."),
    ("D-541", "  - D-502 describes ", "says;",
     "eb5687e656367b401df6c666090ef9425c950fe80b7619490c68fa5f46f26e53",
     "  - D-502 describes private correspondence;"),
    # The owner's rulings of 2026-11-15 and 2026-11-16: CelesTrak's reply of 9 Oct 2026 is not reproduced, nor the
    # letter's quoted text or its summary.
    ("D-340", '; the public text says "', 'with no name and no quote',
     "f76aa570cf1a322117c8e9732e9f7ab4a079ef9d4b5c3bd176eb76b1e917a9f8",
     '; the public text cites its source, with no name and no quote'),
    ("D-340", ' not catalogued objects (', 'October 2026); text only.**',
     "a17b22afefab35068b3cd200b402f54301351fc4b69420bb24ec38a2757d338d",
     " not catalogued objects (measured in the corpus's captures, D-274); text only.**"),
    ("D-340", " D-274's reading of the first point, recorded as the owner's reading until it", 'now stands for the 70000-99999 block as scoped',
     "a6f4e363f81a5f220cbde7039ff6cdaa9e866024d35283501047c87ff364906e",
     " The corpus's own measurement (D-274: across its seventeen TLE capture files, no catalog number above 69999 outside 80000-89999 but the supplemental product's placeholders) now stands for the 70000-99999 block as scoped"),
    ("D-238", ' What it says: ', 'going to that tracker first.',
     "3fe668cf2c8a2669ff893e08d3919d5710b7a6b623dd68f684ad3604bed3ec7a",
     ' What it says is kept in the private record.'),
    ("D-238", "; the usage policy's date as the letter gives it", 'requests nothing from celestrak.org]',
     "ddf31e69326ad3f62af811fd84d2dcd1f0016075c24c6af83f788cdce0926aa1",
     ''),
    ("D-274", "; the reply is recorded here word for word", "on 2026-10-09.**",
     "370b8203869d39ee624c4a0b0072fd886bcba0b69b471cc1b8ecc90fac357c7b",
     ".**"),
    ("D-274", " The reply, exactly as received:", "\n\n**The owner's reading of the first point",
     "38185d560e13fb97f610553fe2a3f99612adfe5f516e0d59cacc56b0c9e0da32",
     " Reply received 9 Oct 2026; not reproduced here.\n\n**The owner's reading of the first point"),
    ("D-274", "it answers the letter's sentence ", "80000-89999. **Checked",
     "0e74ce2876a1ad832022cc94fc7f36f99180aba593bdd762d5a8b3be7b180732",
     "it concerns the letter's statement on TLE formats and catalog numbers above 99999. **Checked"),
    ("D-261", ", under the subject ", "CelesTrak data\", ",
     "b2238d92b34a036fb4414a3dd1c37c5afd82b52adf22d923d7c4f04d593f3217",
     ", "),
    ("D-261", " It promises: ", "word for word.\"",
     "db958948475e14c689b5e1e96edc218c3780c461b0e565c84ff5dbe1b48fce40",
     ""),
    ("D-246", "so the tracker's paragraph changes. And ", 'is the wrong unit',
     "733564df239b0e3d459a8b4004bba1ec44d25b79b598068626cce27be0ec1a96",
     "so the tracker's paragraph changes. And the draft's count, in lines, is the wrong unit"),
    ("D-248", ', which says ', '". Counted',
     "fee6eddf2e3f067a534594322c0c7b6a566dbee54911aac9cce0d83cafa9411c",
     ', which counted the sets as lines. Counted'),
]


class PrivatePassageError(ValueError):
    """A D-542 passage is missing or not the one recorded: the export stops rather than publish it."""


def scrub_private_passages(text):
    """-> (text, n): the D-542 passages shortened. An entry the text does not hold is skipped (a short test text);
    an entry already shortened is left alone; any other mismatch raises PrivatePassageError."""
    import hashlib
    n = 0
    for entry, head, tail, digest, new in _PRIVATE:
        start = text.find(f"**{entry} (")
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


def scrub_decisions_md(text):
    """-> (text, n): the exported DECISIONS.md with every mention of the coding assistant reworded (D-462) and the
    D-542 passages shortened, and a note under the title; n counts the replacements. The rewording table and its
    fallbacks are in the private names file (D-545); without it only the D-542 passages are shortened."""
    import re
    text, n = scrub_private_passages(text)
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
