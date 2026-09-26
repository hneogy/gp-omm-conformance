#!/usr/bin/env python3
"""
tools/action_report.py -- what the GitHub Action (action.yml) runs (D-153, D-158). Standard library only.

The Action runs the corpus from its own checkout, the repository at the tag the workflow names, found in
GPCONF_ACTION_PATH: the runner and the corpus are both there, so nothing is installed and a corpus release changes
nothing in a maintainer's CI until the tag they name is moved. It runs one preset in the working directory, with the
interpreter GPCONF_PYTHON (the one the maintainer's library is installed in), and:

  * offline only: it never fetches, and it points the run at an empty data folder, so that only the cases that ship
    with the corpus run, whatever GPCONF_DATA the job sets; and it tells the runner not to name the fetch command,
    which would point at that folder, thrown away with the job;
  * report-only: failed cases do not fail the job (exit 0), so that a result never becomes a verdict in someone
    else's CI; the job summary carries the case table, the gate line, and the site's sentence that a count is a
    result against that version on that date;
  * a preset that cannot run (its library does not import, Node is missing) is a setup error, exit 2, and the
    summary says that nothing ran and that this says nothing about the library;
  * any other failure of the runner is passed on as it is, since it is not a result either.

Inputs, from the environment the Action sets: GPCONF_PRESET, GPCONF_MODULE (Node presets), GPCONF_PYTHON,
GPCONF_ACTION_PATH; GitHub's own GITHUB_STEP_SUMMARY, GITHUB_OUTPUT and RUNNER_TEMP.
"""
import json
import os
import subprocess
import sys
import tempfile

SITE_SENTENCE = "A count is a result against that version on that date, not a verdict on the project."
SITE_URL = "https://gpconf.neogy.dev/library/"


def append(path, text):
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(text)


def md(cell):
    return str(cell).replace("|", "\\|").replace("\n", " ")


def main():
    preset = os.environ.get("GPCONF_PRESET", "").strip()
    module = os.environ.get("GPCONF_MODULE", "").strip()
    python = os.environ.get("GPCONF_PYTHON", "").strip() or sys.executable
    corpus = os.environ.get("GPCONF_ACTION_PATH") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    summary, outputs = os.environ.get("GITHUB_STEP_SUMMARY"), os.environ.get("GITHUB_OUTPUT")
    temp = os.environ.get("RUNNER_TEMP") or tempfile.gettempdir()
    if not preset:
        print("gp-omm-conformance: the `preset` input is required", file=sys.stderr)
        return 2
    empty = tempfile.mkdtemp(prefix="gpconf-offline-", dir=temp)   # offline: no provider file can be found here
    report = os.path.join(temp, f"gpconf-report-{preset}.json")
    # --no-fetch-hint: the Action never fetches and its empty data folder goes with the job, so the runner's usual
    # advice to fetch into that folder would be wrong, in the log and in every missing item of the JSON report (D-158)
    argv = [python, "-m", "gpconf", "run", "--preset", preset, "--root", corpus, "--data", empty, "--no-fetch-hint", "--json", report]
    if module:
        argv += ["--module", module]
    env = dict(os.environ, PYTHONPATH=corpus + (os.pathsep + os.environ["PYTHONPATH"] if os.environ.get("PYTHONPATH") else ""))
    env.pop("GPCONF_DATA", None)
    p = subprocess.run(argv, capture_output=True, text=True, env=env)
    sys.stdout.write(p.stdout)
    sys.stderr.write(p.stderr)
    title = f"### GP/OMM conformance corpus: preset `{preset}`\n\n"

    if p.returncode == 2:  # a setup error (D-153): nothing ran, and nothing is said about the library
        message = (p.stderr.strip().splitlines() or ["the runner could not start"])[-1]
        append(summary, title + "**Setup error: nothing was run.** " + md(message.removeprefix("gpconf: ").removeprefix("setup: "))
               + "\n\nThis is a problem with the job's setup, not a result about the library.\n")
        append(outputs, "report=\nfailed=\n")
        return 2
    if p.returncode not in (0, 1) or not os.path.exists(report):
        append(summary, title + f"**The runner failed (exit {p.returncode}); nothing was reported.** This is not a result about the library.\n")
        return p.returncode or 1

    with open(report, encoding="utf-8") as f:
        data = json.load(f)
    results = data["results"]
    by = {}
    for r in results:
        by[r["status"]] = by.get(r["status"], 0) + 1
    exercised = sum(by.get(s, 0) for s in ("pass", "pass-tolerance", "fail"))
    lines = [title,
             f"Parser: {md(data['parser'])}. Corpus {data['corpus_version']}, runner gpconf {data['gpconf']}.\n\n",
             f"**{exercised} of {len(results)} cases exercised**, offline: {by.get('pass', 0)} pass, {by.get('pass-tolerance', 0)} pass "
             f"within tolerance, {by.get('fail', 0)} fail. {by.get('not-fetched', 0)} need provider data, which this Action does "
             f"not fetch; {by.get('skip', 0)} skip, where the parser has no reader for the format or no hook for the check; "
             f"{by.get('not-exercised', 0)} not exercised. Failed cases do not fail this job.\n\n",
             "| case | status | exact | tol | fail | skip | n/e | n/f |\n|---|---|---|---|---|---|---|---|\n"]
    for r in results:
        c = r["counts"]
        lines.append(f"| `{r['case']}` | {r['status']} | {c.get('pass', 0)} | {c.get('pass-tolerance', 0)} | {c.get('fail', 0)} | "
                     f"{c.get('skip', 0)} | {c.get('not-exercised', 0)} | {c.get('not-fetched', 0)} |\n")
    for g in data.get("gates", []):
        lines.append(f"\n**Gate, {md(g['name'])}:** {md(g['headline'])}\n")
    lines.append(f"\n{SITE_SENTENCE} See {SITE_URL} for what the corpus found across libraries, and the JSON report for every item.\n")
    append(summary, "".join(lines))
    append(outputs, f"report={report}\nfailed={by.get('fail', 0)}\nexercised={exercised}\n")
    return 0   # report-only (D-153): a failed case is a result, never a failed job


if __name__ == "__main__":
    sys.exit(main())
