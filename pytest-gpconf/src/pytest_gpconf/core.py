# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""The plugin's logic, with no pytest in it, so gpconf's own unittest suite tests it (D-434).

One gpconf run per test session, through gpconf's command line and its --json report (the results schema 1.0), never
through gpconf's internals: the plugin reads what any script reads. Each case then gives one verdict: "pass" (pass or
pass within tolerance), "fail" with the failing items, or "skip" with the reason (a case that skipped, needs fetched
data, or was not exercised or available). gpconf's own judgement is not changed: the plugin only maps it."""
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field

PASS, FAIL, SKIP = "pass", "fail", "skip"


@dataclass
class CaseResult:
    case: str
    outcome: str          # pass, fail or skip
    status: str           # gpconf's own status
    message: str = ""
    failing: list = field(default_factory=list)


def verdict(case_dict):
    """A --json report's case entry -> CaseResult."""
    status = case_dict["status"]
    if status in ("pass", "pass-tolerance"):
        return CaseResult(case_dict["case"], PASS, status)
    if status == "fail":
        bad = [i for i in case_dict["items"] if i["status"] == "fail"]
        lines = [f"[{i['check']}] {i.get('file') or ''}: {i['detail']}" for i in bad]
        return CaseResult(case_dict["case"], FAIL, status, "\n".join(lines[:20]) + (f"\n... {len(lines) - 20} more" if len(lines) > 20 else ""), bad)
    reasons = {"skip": "the parser answered unsupported for every input of this case",
               "not-fetched": "this case reads provider files: run `gpconf fetch` once",
               "not-available": "a provider file this case needs is not available",
               "not-exercised": "the data on disk does not exercise this case"}
    why = next((i["detail"] for i in case_dict["items"] if i["status"] == status and i.get("detail")), "")
    return CaseResult(case_dict["case"], SKIP, status, reasons.get(status, status) + (f" ({why[:200]})" if why else ""))


class GpconfRun:
    """The adapter options as gpconf takes them, one run for all chosen cases, results by case id."""

    def __init__(self, preset=None, adapter=None, cmd=None, vectors_cmd=None, write_cmd=None, root=None, cases=(),
                 python=None, extra=()):
        if sum(x is not None for x in (preset, adapter, cmd)) != 1:
            raise ValueError("give exactly one of --gpconf-preset, --gpconf-adapter and --gpconf-cmd")
        self.argv = ["--preset", preset] if preset else ["--adapter", adapter] if adapter else ["--cmd", cmd]
        for flag, v in (("--vectors-cmd", vectors_cmd), ("--write-cmd", write_cmd), ("--root", root)):
            if v:
                self.argv += [flag, v]
        for c in cases:
            self.argv += ["--case", c]
        self.argv += list(extra)
        self.python = python or sys.executable
        self._results = None
        self.output = ""

    def results(self):
        if self._results is None:
            with tempfile.TemporaryDirectory() as d:
                out = os.path.join(d, "report.json")
                p = subprocess.run([self.python, "-m", "gpconf", "run", "--json", out] + self.argv,
                                   capture_output=True, text=True)
                self.output = p.stdout + p.stderr
                if not os.path.exists(out):
                    raise RuntimeError(f"gpconf wrote no report (exit {p.returncode}):\n{self.output[-2000:]}")
                with open(out, encoding="utf-8") as f:
                    report = json.load(f)
            self._results = {c["case"]: verdict(c) for c in report["results"]}
        return self._results
