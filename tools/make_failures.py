#!/usr/bin/env python3
"""tools/make_failures.py -- render docs/FAILURES.md (the parser-breakage catalogue) from runner
JSON reports: tools/_out/report-naive.json, report-sgp4.json and report-reference.json."""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from public_scrub import SUPGP_CASES, is_supgp_source  # noqa: E402
from cases import CASES  # noqa: E402
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
reports as not exercised for every parser. Draft upstream reports for the python-sgp4 findings are in `docs/upstream/`.
"""


def load(name):
    p = os.path.join(ROOT, "tools", "_out", f"report-{name}.json")
    return json.load(open(p)) if os.path.exists(p) else None


VALUE_CHECKS = {"values", "omm-formats-agree", "tle-values-match-omm-within-tle-precision", "mmdot-is-tle-field-value",
                "tle-writer-round-trip", "leading-dot-decimals", "bstar-implied-decimal-exponent", "negative-bstar-and-ndot"}


def render(reps, generated_at):
    """The catalogue text from the three reports (any may be None). Failing details of value-carrying checks on
    SupGP-sourced files are withheld (D-049); structural details stay readable (D-118)."""
    ident = "; ".join(f"{n}: run {rep.get('generated_at', 'unknown time')} with gpconf {rep.get('gpconf')} on corpus {rep.get('corpus_version')} (parser {rep.get('parser')})"
                      for n, rep in reps.items() if rep)
    md = [INTRO, f"Generated {generated_at} by `tools/make_failures.py` from the runner reports "
          f"`tools/_out/report-<adapter>.json` — {ident}.", "",
          "## Status by case", "", "| case | reference | naive | python-sgp4 |", "|---|---|---|---|"]
    cases = [r["case"] for r in reps["reference"]["results"]]
    by = {n: {r["case"]: r for r in rep["results"]} for n, rep in reps.items() if rep}
    for c in cases:
        row = [f"`{c}`"]
        for n in ("reference", "naive", "sgp4"):
            r = by.get(n, {}).get(c)
            row.append(f"{r['status']} ({r['counts']['fail']} fail)" if r else "not run")
        md.append("| " + " | ".join(row) + " |")
    for n, label in (("naive", "Naive parser"), ("sgp4", "python-sgp4 2.27 through sgp4.omm / twoline2rv")):
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
            md += [f"### `{r['case']}`", "", f"{len(fails)} failing item(s)" + (f", shown as {len(groups)} bullet(s): {collapsed} carried a detail identical to one shown" if collapsed else "") + ".", ""]
            for (check, _), items in groups.items():
                i = items[0]
                detail = i["detail"][:600] + (" …" if len(i["detail"]) > 600 else "")
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
           "- `parse` failures mean the parser raised on real provider bytes; the detail carries the exception.",
           "- `values` failures list the first mismatching fields against the frozen expected values (snapshot) or the reference reader (live).",
           "- `not-exercised` means the data needed for that check was not present in the fetched snapshot (for example no nine-digit ids outside the days after a launch), or that the check involves no parser at all (the SATCAT data check, the same for every parser).",
           "- Each case entry opens with its failing-item count; items whose first 80 characters of detail are identical are collapsed into one bullet that names the files it stands for, so the count can exceed the bullets. A detail ending in … was cut at 600 characters; the JSON report (`--json`) holds the full text.",
           "- For the writer case (`tle-writer-alpha5`) each adapter's entry also lists the checks it passed, with their record counts, so a failure confined to the three synthetic refusal inputs (340000, 799501621, -1: numbers the TLE field cannot carry, for which a refusal is the correct output) cannot be read as a failure on real records.",
           "- Re-run for your own parser: `python -m gpconf run --adapter your.module:Parser` (see README)."]
    return "\n".join(md) + "\n"


def main():
    import datetime as dt
    reps = {n: load(n) for n in ("reference", "naive", "sgp4")}
    open(OUT, "w").write(render(reps, dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
