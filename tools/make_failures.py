#!/usr/bin/env python3
"""tools/make_failures.py -- render docs/FAILURES.md (the parser-breakage catalogue) from runner
JSON reports: tools/_out/report-naive.json, report-sgp4.json and report-reference.json."""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from public_scrub import SUPGP_CASES, is_supgp_source  # noqa: E402
OUT = os.path.join(ROOT, "docs", "FAILURES.md")

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
passes every case. Draft upstream reports for the python-sgp4 findings are in `docs/upstream/`.
"""


def load(name):
    p = os.path.join(ROOT, "tools", "_out", f"report-{name}.json")
    return json.load(open(p)) if os.path.exists(p) else None


def main():
    reps = {n: load(n) for n in ("reference", "naive", "sgp4")}
    import datetime as dt
    ident = "; ".join(f"{n}: run {rep.get('generated_at', 'unknown time')} with gpconf {rep.get('gpconf')} on corpus {rep.get('corpus_version')} (parser {rep.get('parser')})"
                      for n, rep in reps.items() if rep)
    md = [INTRO, f"Generated {dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')} by `tools/make_failures.py` from the runner reports "
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
            md += [f"### `{r['case']}`", ""]
            seen = set()
            for i in fails:
                key = (i["check"], i["detail"][:80])
                if key in seen:
                    continue
                seen.add(key)
                detail = i["detail"][:600]
                if i["check"] == "values" and (r["case"] in SUPGP_CASES or is_supgp_source(i["file"])):
                    detail = "value mismatch (details withheld: SupGP-derived values are not published, D-049)"
                md.append(f"- **{i['check']}** ({os.path.basename(i['file']) if i['file'] else 'set'}): {detail}")
            md.append("")
    md += ["## How to read this", "",
           "- `parse` failures mean the parser raised on real provider bytes; the detail carries the exception.",
           "- `values` failures list the first mismatching fields against the frozen expected values (snapshot) or the reference reader (live).",
           "- `not-exercised` means the data needed for that check was not present in the fetched snapshot (for example no nine-digit ids outside the days after a launch).",
           "- Re-run for your own parser: `python -m gpconf run --adapter your.module:Parser` (see README)."]
    open(OUT, "w").write("\n".join(md) + "\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
