#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""tools/make_failures.py -- render docs/FAILURES.md (the parser-breakage catalogue) from runner
JSON reports: tools/_out/report-naive.json, report-sgp4.json and report-reference.json."""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from public_scrub import SUPGP_CASES, is_supgp_source  # noqa: E402
from cases import CASES  # noqa: E402
sys.path.insert(0, ROOT)
from gpconf.words import qty  # noqa: E402
OUT = os.path.join(ROOT, "docs", "FAILURES.md")
KIND = {c["id"]: c["kind"] for c in CASES}

INTRO = """# Parser breakage catalogue

What actually breaks when a parser written for five-digit TLEs meets today's data. Every entry
below is a runner result (`python -m gpconf run`) against the corpus, not a hypothetical. Three
parsers were run:

- **reference** — the corpus's own readers (`tests/adapters/reference.py`); the control.
- **naive** — the parser most projects have (`tests/adapters/naive.py`): `int()` on five
  columns, one epoch format, classification assumed `U`, every column assumed present, KVN as
  strict `KEY = value`. Written deliberately with those shortcuts.
- **python-sgp4** — `tests/adapters/sgp4_adapter.py`, exposing python-sgp4 2.27 as-is (TLE via
  `twoline2rv`, CSV/XML/JSON via `sgp4.omm`; no KVN reader).

A failure here is a statement about the parser, not about the corpus: the reference parser
passes every case that exercises a parser; `satcat-70000-cutoff` is a data check the runner makes itself and
reports as not exercised for every parser, on a file the fetch brings only on request (D-231). Draft upstream reports for the python-sgp4 findings are in `docs/upstream/`.
The Alpha-5 letters I and O that python-sgp4's compiled `Satrec` writes, in the writer case below, are reported as
[brandon-rhodes/python-sgp4#173](https://github.com/brandon-rhodes/python-sgp4/issues/173) (filed 2026-10-10, D-307).

{basis}
python-sgp4 propagating an element set of ephemeris type 4 as SGP4, in `ephemeris-type-4-refused` below, is reported as
[brandon-rhodes/python-sgp4#178](https://github.com/brandon-rhodes/python-sgp4/issues/178) (filed 2026-11-08).
"""


def load(name):
    p = os.path.join(ROOT, "tools", "_out", f"report-{name}.json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


VALUE_CHECKS = {"values", "omm-formats-agree", "tle-values-match-omm-within-tle-precision", "mmdot-is-tle-field-value",
                "tle-writer-round-trip", "leading-dot-decimals", "bstar-implied-decimal-exponent", "negative-bstar-and-ndot"}


# the sentence the values item closes with where the input holds an id more than once (D-343), matched whole at the end
NOTICE = re.compile(r"; the input holds \d+ ids? more than once with records that differ \(e\.g\. id [^()]*, \d+ records\): "
                    r"each copy returned is compared with the input's record it matches \(D-343\)$")


def cut(detail, n=600):
    """A detail cut at n characters, its closing notice kept (2i, D-350; the hardening review's T5): where the input
    holds an id more than once the values item says so after its list, and a plain cut at 600 dropped the sentence that
    says which records the failure may be the input's, not the parser's. The notice is kept only where it closes the
    detail in its own words and takes less than half of n; any other detail is cut as before."""
    if len(detail) <= n:
        return detail
    m = NOTICE.search(detail)
    keep = m.group(0) if m else ""
    if not keep or len(keep) >= n // 2:
        return detail[:n] + " …"
    return detail[:n - len(keep)] + " …" + keep


# What python-sgp4 2.27 was seen to answer for c9 on other platforms (D-593): the page names the one its own run saw and
# these, recorded once, never assumed for the platform at hand
C9_SEEN = {"NaN": "ubuntu-24.04 (Linux x86_64) with Python 3.12.16", "0.0": "macOS arm64 with Python 3.14.6"}
C9 = "c9-letter-in-epoch-first.tle"


def platform_line(reps):
    """The platform the reports were measured on, read from the reports themselves (D-593): their own platform field
    and the python-sgp4 version the sgp4 preset found. Reports that disagree, or say nothing, are named as such."""
    seen = {n: (r or {}).get("platform") for n, r in reps.items() if r}
    plats = {(p or {}).get("system", "not recorded") + "; Python " + (p or {}).get("python", "not recorded") for p in seen.values()}
    found = ((reps.get("sgp4") or {}).get("preset") or {}).get("found") or "not recorded"
    if len(plats) == 1:
        return f"Platform, as the reports record it: {plats.pop()}; python-sgp4 {found}."
    return "Platform: the reports record different platforms: " + "; ".join(
        f"{n}: {(p or {}).get('system', 'not recorded')} / Python {(p or {}).get('python', 'not recorded')}" for n, p in seen.items()) + "."


def c9_answer(rep):
    """What python-sgp4 answered for c9's bstar in this run, read from its own item: "NaN", "0.0", or None."""
    for c in (rep or {}).get("results", []):
        for it in c.get("items", []):
            if C9 in (it.get("file") or "") and it.get("status") == "fail":
                d = it.get("detail") or ""
                if "bstar = nan" in d:
                    return "NaN"
                if "bstar = Decimal('0.0')" in d:
                    return "0.0"
    return None


def basis(reps, export):
    """The paragraph that says what the page was graded on, computed from the reports and the tree (D-593)."""
    ref = {c["case"]: c["status"] for c in (reps.get("reference") or {}).get("results", [])}
    captures_absent = ref.get("supgp-celestrak-classification-c") == "not-available"
    def n(rep, *keys):
        return sum((rep or {}).get("summary", {}).get(k, 0) for k in keys)
    # the case count from the reference's report, not a fixed number (D-604). Fixed text, not read from the reports:
    # "one run", the fetch and its date (the owner's ruled wording), C9_SEEN's other platform; the tree sentence
    # follows `export`, and the captures sentence classification-c's status in the reference report (D-605)
    cases = qty((reps.get("reference") or {}).get("summary", {}).get("cases", 0), "case")
    figures = (f"the reference passes {n(reps.get('reference'), 'pass', 'pass-tolerance')}, the naive adapter fails "
               f"{n(reps.get('naive'), 'fail')} and python-sgp4 fails {n(reps.get('sgp4'), 'fail')}")
    tree = ("the public export, the corpus as published, which leaves out the SupGP expected values (D-049)" if export
            else "the private tree, with the SupGP expected values")
    out = [f"All three columns come from one run, on the platform named below the intro, graded on {tree}, from the 0.9.0 "
           "re-measure's fresh fetch (2026-11-11)."]
    if captures_absent:
        out.append("The corpus's ten operator-sourced launch-window captures are excluded (D-002), as a new user's fetch "
                   "cannot obtain them either (D-229), so these figures are fetch-only, and `supgp-celestrak-classification-c`, "
                   "which reads only those captures, reports `not-available`, where with the captures it is a pass for the "
                   f"reference and a fail for naive. Of {cases}, {figures}. With the ten captures, 0.9.0's recorded "
                   "measurement (D-489, on the re-measure's fresh fetch with the ten captures copied in, not this run) was: the "
                   "reference passes 17 and the naive adapter fails 14.")
    else:
        out.append(f"The reference and naive columns read the corpus's ten launch-window captures as well (D-229). Of "
                   f"{cases}, {figures}.")
    here = c9_answer(reps.get("sgp4"))
    if here:
        others = "; ".join(f"{v} on {w}" for v, w in C9_SEEN.items() if v != here)
        out.append(f"python-sgp4's answer to one corrupt input differs by platform: for `{C9}` in `corrupt-input` it "
                   f"returned bstar {here} in this run" + (f", and was seen to return {others} (D-593)" if others else " (D-593)")
                   + "; the case fails either way.")
    return " ".join(out)


def render(reps, generated_at, platform=None, export=None):
    """The catalogue text from the three reports (any may be None). Failing details of value-carrying checks on
    SupGP-sourced files are withheld (D-049); structural details stay readable (D-118)."""
    ident = "; ".join(f"{n}: run {rep.get('generated_at', 'unknown time')} with gpconf {rep.get('gpconf')} on corpus {rep.get('corpus_version')} (parser {rep.get('parser')})"
                      for n, rep in reps.items() if rep)
    if export is None:
        export = os.path.exists(os.path.join(ROOT, "EXPORT-MANIFEST.txt"))
    import textwrap
    para = "\n".join(textwrap.wrap(basis(reps, export), 118, break_long_words=False, break_on_hyphens=False))
    md = [INTRO.replace("{basis}", para), f"Generated {generated_at} by `tools/make_failures.py` from the runner reports "
          f"`tools/_out/report-<adapter>.json` — {ident}.", ""] + ([platform, ""] if platform else []) + [
          "## Status by case", "", "| case | reference | naive | python-sgp4 |", "|---|---|---|---|"]
    cases = [r["case"] for r in reps["reference"]["results"]]
    by = {n: {r["case"]: r for r in rep["results"]} for n, rep in reps.items() if rep}
    for c in cases:
        row = [f"`{c}`"]
        for n in ("reference", "naive", "sgp4"):
            r = by.get(n, {}).get(c)
            row.append(f"{r['status']} ({r['counts']['fail']} failing)" if r else "not run")  # failing items; the word does not vary with the count (D-240)
        md.append("| " + " | ".join(row) + " |")
    md += ["", "## Gate: this month's launches", "",
           "One headline per parser, read across existing cases from the record counts behind their values items (D-142): "
           "words that name the behaviour, never a grade on the project. Snapshot facts and the letter caveat travel with each.", ""]
    for n, label in (("reference", "reference"), ("naive", "naive"), ("sgp4", "python-sgp4")):
        for g in (reps.get(n) or {}).get("gates", []):
            md.append(f"- **{label}**: {g['headline']}")
    naive = reps.get("naive")
    if naive:
        # The naive parser is the corpus's own control, wrong on purpose: one table, not item by item (the owner's
        # ruling, D-571, D-573). The detail is one command away, and the page no longer reads as a library failing.
        md += ["", "## Naive parser, the corpus's control: what failed", "",
               "The naive parser is the corpus's own, wrong on purpose, to show that each case catches what it is built to catch. "
               "Its item-by-item failures are in `python -m gpconf run --preset naive` (add `--case <case>` for one).", "",
               "| case | failing items | checks that failed |", "|---|---|---|"]
        for r in naive["results"]:
            fails = [i for i in r["items"] if i["status"] == "fail"]
            if fails:
                checks = ", ".join(f"`{c}`" for c in dict.fromkeys(i["check"] for i in fails))
                md.append(f"| `{r['case']}` | {len(fails)} | {checks} |")
    for n, label in (("sgp4", "python-sgp4 2.27 through sgp4.omm / twoline2rv"),):
        rep = reps.get(n)
        if not rep:
            continue
        md += ["", f"## {label}: what failed and why", ""]
        for r in rep["results"]:
            fails = [i for i in r["items"] if i["status"] == "fail"]
            if not fails:
                continue
            groups = {}  # identical details are collapsed into one bullet that says how many items it stands for (D-122)
            for i in fails:
                groups.setdefault((i["check"], i["detail"][:80]), []).append(i)
            collapsed = len(fails) - len(groups)
            md += [f"### `{r['case']}`", "", f"{qty(len(fails), 'failing item')}" + (f", shown as {qty(len(groups), 'bullet')}: {collapsed} carried a detail identical to one shown" if collapsed else "") + ".", ""]
            for (check, _), items in groups.items():
                i = items[0]
                detail = cut(i["detail"])
                if check in VALUE_CHECKS and (r["case"] in SUPGP_CASES or is_supgp_source(i["file"])):
                    detail = ("mismatch (details withheld: SupGP-derived values are not published, D-049; run the case on your own fetch, "
                              f"`python -m gpconf run --adapter <yours> --case {r['case']} --json out.json`, and the report shows them)")
                more = f" [{len(items)} items with this detail: " + ", ".join(os.path.basename(x["file"]) for x in items if x["file"]) + "]" if len(items) > 1 else ""
                md.append(f"- **{check}** ({os.path.basename(i['file']) if i['file'] else 'set'}): {detail}{more}")
            if KIND.get(r["case"]) == "writer":
                # so that a failure confined to the synthetic refusal inputs cannot be read as a failure on real records
                passed = [i for i in r["items"] if i["status"] == "pass"]
                if passed:
                    md.append("- passed: " + "; ".join(f"**{i['check']}** ({i['detail'][:220]}{' …' if len(i['detail']) > 220 else ''})" for i in passed))
            md.append("")
    md += ["## How to read this", "",
           "- `parse` failures mean the parser raised on real provider bytes, or returned a value the runner cannot read; the detail says which.",
           "- `values` failures list the first mismatching fields against the frozen expected values (snapshot) or the reference reader (live).",
           "- `not-exercised` means the data needed for that check was not present in the fetched snapshot (for example no nine-digit ids outside the days after a launch), or that the check involves no parser at all (the SATCAT data check, the same for every parser).",
           "- Each case entry opens with its failing-item count; items whose first 80 characters of detail are identical are collapsed into one bullet that names the files it stands for, so the count can exceed the bullets. A detail cut at 600 characters shows … where it was cut, and a closing sentence saying the input holds an id more than once is kept whole after it; the JSON report (`--json`) holds the full text.",
           "- For the writer case (`tle-writer-alpha5`) each adapter's entry also lists the checks it passed, with their record counts, so a failure confined to the three synthetic refusal inputs (340000, 799501621, -1: numbers the TLE field cannot carry, for which a refusal is the correct output) cannot be read as a failure on real records.",
           "- Re-run for your own parser: `python -m gpconf run --adapter your.module:Parser` (see README)."]
    return "\n".join(md) + "\n"


def main():
    import datetime as dt
    reps = {n: load(n) for n in ("reference", "naive", "sgp4")}
    open(OUT, "w", encoding="utf-8").write(render(reps, dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                                  platform_line(reps)))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
