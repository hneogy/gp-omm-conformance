# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""python -m gpconf: run a parser against the corpus and print a report; fetch: fetch the provider data the corpus
does not ship; list: the cases; check-tle: check a TLE file a tool wrote."""
import argparse
import importlib
import json
import os
import sys

from . import __version__
from . import locate
from .runner import Runner, CommandParser, CorpusIncomplete, annotation_totals, status_totals
from .words import pick, printable, qty


def load_adapter(spec):
    mod, _, attr = spec.partition(":")
    sys.path.insert(0, os.getcwd())
    m = importlib.import_module(mod)
    obj = getattr(m, attr or "Parser")
    return obj() if isinstance(obj, type) else obj


def count_line(results):
    """The line under the table: how many cases ended in each status. Every count agrees in number with what follows
    it, so one case passes, fails, skips or needs fetched data where two pass, fail, skip or need it (D-239)."""
    by = status_totals(results)  # the numbers the JSON report carries as `summary` (D-240)
    p, tol, failed, skip, need = (by[s] for s in ("pass", "pass-tolerance", "fail", "skip", "not-fetched"))
    return (f"{qty(by['cases'], 'case')}: {p} {pick(p, 'passes', 'pass')} (exact), {tol} {pick(tol, 'passes', 'pass')} within tolerance, "
            f"{failed} {pick(failed, 'fails', 'fail')}, {skip} {pick(skip, 'skips', 'skip')}, {need} {pick(need, 'needs', 'need')} fetched data, "
            f"{by['not-available']} not available, {by['not-exercised']} not exercised")


def graded_line(results):
    """Under the count line when cases were not graded for lack of data (D-312): how many were, said plainly, so that
    a green run on five cases is not read as a conformance result. None when every case had its data."""
    by, n = status_totals(results), annotation_totals(results)["cases_graded"]
    if not by["not-fetched"]:
        return None
    # offline: no provider file was read at all. They live under fixtures/<case>/raw/ and none ships; a case records
    # every source it loaded in `modes`, whatever its items went on to say (a data check's are info), so a folder
    # holding only the SATCAT files is not "offline"
    ran_on_data = any("/raw/" in str(p).replace("\\", "/") for r in results for p in r.modes)
    if not ran_on_data:
        return f"{n} of {qty(by['cases'], 'case')} graded offline; not a full conformance result."
    return f"{n} of {qty(by['cases'], 'case')} graded; {by['not-fetched']} {pick(by['not-fetched'], 'needs', 'need')} fetched data: not a full conformance result."


def inside_line(results):
    """Under the count line (D-312): what the statuses above do not say. None when there is nothing to say."""
    a = annotation_totals(results)
    parts = []
    if a["items_skipped"]:
        parts.append(f"{qty(a['items_skipped'], 'item')} skipped because the parser answered unsupported or has no hook for the check")
    if a["field_gaps"]:
        parts.append(f"{qty(a['field_gaps'], 'field gap')} (a file in which a field with expected values was never returned)")
    return ("Inside cases that did not skip: " + "; ".join(parts) + ". These are not failures, and they were not graded.") if parts else None


def print_missing(results, unfetched, runner):
    """Below the count line: what was not fetched and what cannot be, so that neither a case with no data nor a case
    that ran on part of its data reads as a result it has not earned (D-148, D-228, D-229, D-231)."""
    # a case that read a file from disk ran on part of its files; one that read none, its status made other than
    # not-fetched by a check that needs no file, ran on none of them: the SATCAT case read "ran without 6 of its provider
    # files, so its result covers only the files on disk" with no file on disk (2i, W6, D-350)
    partial = [r for r in results if r.status != "not-fetched" and r.missing() and r.modes]
    bare = [r for r in results if r.status != "not-fetched" and r.missing() and not r.modes]
    never = [r for r in results if r.status == "not-available"]
    lacking = [r for r in results if r.status != "not-available" and r.unavailable()]
    if never or lacking:  # D-229: files no fetch requests are not "to be fetched", and the published counts used them
        if never:
            k = len(never)
            print(f"{qty(k, 'case')} cannot run from a fetch and {pick(k, 'reports', 'report')} not-available: {', '.join(r.case_id for r in never)}. "
                  f"Every provider file {pick(k, 'it needs', 'they need')} is a launch-window capture: CelesTrak serves launch nominals for the days after "
                  "a launch, the corpus captured them then, and no fetch requests them.")
        if lacking:
            k = len(lacking)
            print(f"{qty(k, 'other case')} {pick(k, 'names', 'name')} {qty(sum(len(r.unavailable()) for r in lacking), 'launch-window file')} (column n/a) "
                  f"and {pick(k, 'is judged on its', 'are judged on their')} other files: {', '.join(r.case_id for r in lacking)}.")
        print("  The counts the corpus publishes were measured with those files. A run without them cannot reproduce the "
              "failures that rest on them, so it can show fewer failing cases than a published count.")
    on_request = [r for r in results if r.on_request]
    if on_request:  # D-232: a data check that was not made by default says so, and says what runs it; it asks for nothing
        flags = sorted({flag for r in on_request for flag in r.on_request.values()})
        print(f"{', '.join(r.case_id for r in on_request)} is a data check on the legacy SATCAT file, 9.4 MB, which the fetch brings "
              "only on request. It was not made, and no parser takes part in it: nothing about the parser under test depends on it. "
              + (f"{' '.join(flags)} runs it: {runner.hint(*flags)}." if runner.fetch_hints else f"The fetch's {' '.join(flags)} runs it."))
    if not unfetched and not partial and not bare:
        return
    # a not-fetched case that read some of its files (a SATCAT capture on disk, its GP files not) has not "none of its
    # provider files on disk" (D-350's reading, finding 7; D-355)
    nothing = [r for r in unfetched if not r.modes]
    some = [r for r in unfetched if r.modes]
    if nothing:
        k = len(nothing)
        print(f"{qty(k, 'case')} {pick(k, 'has none of its', 'have none of their')} provider files on disk and {pick(k, 'reports', 'report')} not-fetched; "
              "skip is reserved for a parser with no reader for a format or no hook for a check.")
    if some:
        k = len(some)
        print(f"{qty(k, 'case')} {pick(k, 'reports', 'report')} not-fetched with {qty(sum(len(r.modes) for r in some), 'provider file')} on disk and "
              f"{sum(len(r.missing()) for r in some)} not (column n/f): the files {pick(k, 'it grades', 'they grade')} are among those not on disk: "
              f"{', '.join(r.case_id for r in some)}.")
    if bare:   # what the files it read and the files missing establish, and no more (D-350's reading)
        files = [f for r in bare for f in r.missing()]
        k = len(bare)
        print(f"{qty(k, 'case')} read none of {pick(k, 'its', 'their')} provider files ({len(files)} not on disk, column n/f): "
              f"{', '.join(r.case_id for r in bare)}.")
    if partial:
        files = [f for r in partial for f in r.missing()]
        k = len(partial)
        print(f"{qty(k, 'case')} ran without {len(files)} of {pick(k, 'its', 'their')} provider files, so {pick(k, 'its', 'each')} result covers only the files on disk "
              f"(column n/f): {', '.join(r.case_id for r in partial)}.")
    if any("recapture" in os.path.basename(f) for r in partial + bare for f in r.missing()):
        # corrected by D-150: a normal fetch never requests a re-capture, so a later run does not bring it (the files of both
        # lines above, D-350's reading)
        print("  A re-capture file is the same endpoint requested a second time when the corpus was built; the fetch requests it "
              "only with --include-recaptures, once its original is at least two hours old, so a normal fetch leaves these cases without it.")
    unexpected = {p: v for r in results for p, v in r.unexpected.items()}
    if unexpected:  # D-228: the fetch asked and got something else; that response is kept out of the data and is not read
        whys = ", ".join(sorted({str(v["why"]) for v in unexpected.values()}))
        k = len(unexpected)
        placed = sum(1 for v in unexpected.values() if v.get("in_place"))   # saved in the data's place by a fetch before v0.5.1 (D-351's reading)
        kept = ("kept beside the data, not in its place, and is not read" if not placed else
                "saved in the data's place by an earlier fetch, and is not read" if placed == k else
                f"kept beside the data or, for {placed}, saved in its place by an earlier fetch, and is not read")
        print(f"{qty(k, 'provider file')} {pick(k, 'is', 'are')} missing because the fetch got a response it did not expect for {pick(k, 'it', 'them')} ({whys}); "
              f"{pick(k, 'the', 'each')} response is {kept}."
              + (" The fetch asks for such a file again only with --force, two hours or more after that answer." if runner.fetch_hints else ""))
    # the fetch command only where a plain fetch would bring something: not for a re-capture, which it never requests
    # (D-150), a file whose last answer was unexpected, which it does not ask for again (D-228), or one it brings only
    # on request (D-231)
    if runner.fetch_hints and any("recapture" not in os.path.basename(f) and f not in unexpected and f not in runner.opt_in
                                  for r in results for f in r.missing()):
        print(f"Provider data is not shipped with the corpus; fetch it with {runner.hint()}.")


def check_tle(args):
    """check-tle FILE... [--against RECORDS] [--json OUT]: the writer checks applied to files a tool wrote."""
    from . import writer as W
    if not args.files:
        print("check-tle needs at least one TLE file", file=sys.stderr)
        return 2
    try:
        against = W.load_against(args.against) if args.against else None
    except (OSError, ValueError) as e:
        # a source file the reference reader rejects is no reference for a round trip (D-336); a traceback said so before
        print(f"gpconf check-tle: the --against file {args.against} cannot be read: {e}", file=sys.stderr)
        return 2
    print(f"gpconf {__version__} | check-tle | {qty(len(args.files), 'file')}" + (f" | round trip against {printable(args.against)}" if args.against else ""))
    report, n_pass, n_fail, n_nc = [], 0, 0, 0
    for path in args.files:
        try:
            with open(path, "rb") as f:
                text = f.read().decode("utf-8", "replace")
        except OSError as e:
            print(f"gpconf check-tle: {path}: {e.strerror or e}", file=sys.stderr)
            return 2
        results = W.check_file(text, against)
        print(f"\n{printable(path)}: {qty(len(results), 'record')}" + ("" if results else " (no element line found)"))
        for r in results:
            ident = printable(repr(r["catalog_field"])) + (f" -> {r['norad_cat_id']}" if r["norad_cat_id"] is not None else "")
            head = "unpaired element line" if r.get("unpaired") else printable(r["name"] or "(no name line)")
            print(f"  [{r['status']}] line {r['line_number']}: {head} | catalog field {ident}")
            for p in r["problems"]:
                print(f"         {printable(p)}")
            for n in r["notes"]:
                print(f"         note: {printable(n)}")
            if r.get("round_trip"):
                print("         round trip against the source record: " + ", ".join(f"{k} {v}" for k, v in r["round_trip"]["conventions"].items()))
            if r.get("secondary_fields"):
                print("         secondary fields (information): " + ", ".join(f"{k} {v}" for k, v in r["secondary_fields"].items() if k != "zero_ddot_sign"))
            n_pass += r["status"] == "pass"
            n_fail += r["status"] == "fail"
            n_nc += r["status"] == "not compared"
        report.append({"file": path, "records": results})
    cov, short = None, ""
    if against is not None:
        # every source record written, and none more often than the source holds it (D-369): a file that lost or
        # repeated records passed before, with exit 0, its records each passing on its own
        cov = W.source_coverage([r for f in report for r in f["records"]], against)
        print(f"\nagainst the source: {qty(sum(against.held.values()), 'record')}")
        if against.without_id:
            print(f"  note: {qty(against.without_id, 'source record')} without a catalog number, which no written record can be held to")
        if cov["not_written"]:
            lost = sum(h - w for _, w, h in cov["not_written"])
            print(f"  [fail] {qty(lost, 'source record')} no file wrote: "
                  + ids_shown([str(k) if (w, h) == (0, 1) else f"{k} ({w} of {h} written)" for k, w, h in cov["not_written"]]))
        if cov["written_more"]:
            print(f"  [fail] {qty(len(cov['written_more']), 'id')} written more often than the source holds: "
                  + "; ".join(f"{k} written {n}, held {h}" for k, n, h in cov["written_more"][:20])
                  + (f"; and {len(cov['written_more']) - 20} more" if len(cov["written_more"]) > 20 else ""))
        if cov["not_compared"]:
            print(f"  note: {qty(len(cov['not_compared']), 'id')} not compared: the source holds more than one copy of "
                  + pick(len(cov["not_compared"]), "it", "each") + " (per-epoch pairing comes in 0.8.1): "
                  + ids_shown([f"{k} ({h} copies)" for k, h in cov["not_compared"]]))
        if cov["refusal_correct"]:
            print(f"  note: {qty(len(cov['refusal_correct']), 'id')} the TLE format cannot carry, written by no file, as a refusal "
                  f"should be: ids {ids_shown(cov['refusal_correct'])}")
        if not (cov["not_written"] or cov["written_more"]):
            print("  [pass] every source record written, none more often than the source holds it")
        bad = len(cov["not_written"]) + len(cov["written_more"])
        short = f"; against the source, {bad} {pick(bad, 'failure', 'failures')}" if bad else ""
    print(f"\n{qty(n_pass + n_fail + n_nc, 'record')}: {n_pass} {pick(n_pass, 'passes', 'pass')}, {n_fail} {pick(n_fail, 'fails', 'fail')}"
          + (f", {n_nc} not compared" if n_nc else "") + ("" if n_pass + n_fail + n_nc else "; nothing to check") + short)
    if args.json:
        import datetime as _dt
        failed_write = write_json(args.json, {"gpconf": __version__, "command": "check-tle", "against": args.against, "source": cov,
                                              "generated_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "files": report})
        if failed_write:
            print(f"gpconf: --json {printable(args.json)}: the report was not written ({failed_write})", file=sys.stderr)
            return 2
    if n_fail or not (n_pass + n_fail + n_nc) or short:
        return 1
    # nothing failed, but not everything was compared: neither 0, which says every record passed, nor 1 (D-370)
    return 3 if n_nc else 0


def json_target_problem(path):
    """Why `--json PATH` cannot be written, or None: checked before anything runs, so that a run does not print its
    report and then end in a traceback with exit status 1, which reads as a failure (D-370; the second blind review's
    F9). The write itself is still guarded."""
    if not path:
        return None
    full = os.path.abspath(path)
    folder = os.path.dirname(full)
    if os.path.isdir(full):
        return "is a folder"
    if not os.path.isdir(folder):
        return f"its folder {folder} does not exist"
    if os.path.exists(full) and not os.access(full, os.W_OK):
        return "cannot be written"
    if not os.path.exists(full) and not os.access(folder, os.W_OK):   # a new file needs its folder writable (D-370's reading)
        return "cannot be written"
    return None


def write_json(path, data):
    """The report as JSON at path -> None, or the error text when it cannot be written (D-370)."""
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1, default=str)
    except OSError as e:
        return f"{type(e).__name__}: {e.strerror or e}"
    return None


def ids_shown(ids, most=20):
    """A list of ids, or of texts naming them, as text: the first `most` of them and how many more."""
    return ", ".join(str(k) for k in ids[:most]) + (f", and {len(ids) - most} more" if len(ids) > most else "")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv[:1] == ["fetch"]:  # its own options (tools/fetch.py's), parsed by gpconf/fetch.py (D-150)
        from .fetch import run as fetch_run
        return fetch_run(argv[1:], prog="gpconf fetch")
    ap = argparse.ArgumentParser(prog="gpconf", description="gpconf, the GP/OMM conformance corpus. Free test kit: does your satellite software handle catalog numbers above 99,999? "
                                                         "Built from real CelesTrak data.",
                                 epilog="gpconf fetch --help: the fetch subcommand's own options")
    ap.add_argument("command", choices=["run", "list", "presets", "check-tle", "fetch"])
    ap.add_argument("files", nargs="*", help="check-tle: one or more TLE files written by the tool under test")
    ap.add_argument("--against", help="check-tle: the source records the lines were written from (CSV/JSON/XML/KVN/TLE); enables the round-trip check")
    ap.add_argument("--preset", help="a shipped adapter by name: reference, naive, sgp4, pyephem, satellite.js, tle.js or tle.js-api (gpconf presets lists them)")
    ap.add_argument("--module", help="Node presets: the library's entry file, for a checkout the working directory cannot import by name")
    ap.add_argument("--adapter", help="python import path module:attr of a parser object or class")
    ap.add_argument("--cmd", help="external command; raw bytes on stdin, JSON array on stdout; {fmt} substituted; exit 3 = unsupported format")
    ap.add_argument("--vectors-cmd", help="external command for vector hooks (JSON {op,input} on stdin -> {result}|{error})")
    ap.add_argument("--write-cmd", help="external TLE writer for the writer case: one JSON record on stdin, 2-3 TLE lines on stdout; exit 3 = unsupported, other non-zero = refused; an end by a signal or a timeout is a crash, never a refusal")
    ap.add_argument("--root", help="corpus root (default: the clone this package sits in, else the corpus installed with it)")
    ap.add_argument("--data", help=f"folder holding the fetched provider files (default: ${locate.DATA_ENV}, else the clone, else a per-user cache folder)")
    ap.add_argument("--no-fetch-hint", action="store_true", help="do not name the command that fetches provider data, for a run that is "
                    "offline by design, such as the GitHub Action's, whose data folder is empty and discarded with the job")
    ap.add_argument("--case", action="append", help="case id (repeatable)")
    ap.add_argument("--tag", action="append", help="test tag (repeatable)")
    ap.add_argument("--json", help="write the full report to this file")
    ap.add_argument("--verbose", "-v", action="store_true", help="print every item, not only failures and within-tolerance passes")
    args = ap.parse_args(argv)

    why = json_target_problem(getattr(args, "json", None))
    if why and args.command in ("run", "check-tle"):
        print(f"gpconf: --json {printable(args.json)}: {why}; nothing was run", file=sys.stderr)
        return 2
    if args.command == "check-tle":  # needs no corpus: it checks the user's own file
        return check_tle(args)
    if args.command == "presets":
        from .presets import listing
        print("\n".join(listing()))
        return 0
    try:
        loc = locate.resolve(args.root, args.data)
    except locate.CorpusNotFound as e:
        print(f"gpconf: {e}", file=sys.stderr)
        return 2
    root = loc["corpus"]
    manifest = json.load(open(os.path.join(root, "manifest.json"), encoding="utf-8"))
    if args.command == "list":
        for c in manifest["cases"]:
            print(f"{c['id']:40s} {c['kind']:12s} {', '.join(c['tests'])}")
        return 0
    chosen = [f for f in ("preset", "adapter", "cmd") if getattr(args, f)] + (["write-cmd"] if args.write_cmd and not args.cmd else [])
    if not chosen:
        ap.error("run needs --preset, --adapter, --cmd or --write-cmd")
    if args.preset and len(chosen) > 1:
        ap.error("--preset names the parser; it cannot be combined with --adapter, --cmd or --write-cmd")
    if args.module and not args.preset:
        ap.error("--module applies to the Node presets")
    preset = None
    if args.preset:
        from .presets import load as load_preset, PresetUnavailable
        try:
            parser, preset = load_preset(args.preset, module=args.module)
        except PresetUnavailable as e:
            print(f"gpconf: {e}", file=sys.stderr)
            return 2
    elif args.cmd or args.write_cmd:
        parser = CommandParser(args.cmd, args.vectors_cmd, write_cmd=args.write_cmd)
    else:
        try:
            parser = load_adapter(args.adapter)
        except SystemExit as e:   # an adapter that exits while it is imported or built ran nothing (D-293)
            print(f"gpconf: setup: the adapter {args.adapter} exited while loading (SystemExit({e.code!r})); nothing was run", file=sys.stderr)
            return 2
    parser_name = preset["label"] if preset else (args.cmd or args.write_cmd or args.adapter)
    runner = Runner(parser, root=root, verbose=args.verbose, data=loc["data"], data_why=loc["data_why"], fetch_hints=not args.no_fetch_hint)
    if args.case:   # a name that matches nothing is an error, not a silent no-op (D-269: a typo in CI went green forever)
        ids = [c["id"] for c in manifest["cases"]]
        unknown = [x for x in args.case if x not in ids]
        if unknown:
            print(f"gpconf: no case {', '.join(repr(x) for x in unknown)}; the cases are: {', '.join(ids)}", file=sys.stderr)
            return 2
    try:
        results = runner.run(case_ids=args.case, tags=args.tag)
    except CorpusIncomplete as e:
        print(f"gpconf: {e}", file=sys.stderr)
        return 2
    print(f"gpconf {__version__} | corpus {manifest['corpus_version']} | parser: {parser_name}")
    if runner.data != root:  # a clone's output is unchanged; elsewhere the reader is told where the provider files were looked for
        print(f"provider data: {runner.data} ({runner.data_why})")
    print()
    w = max([15] + [len(r.status_text()) for r in results])   # the status, with what it leaves out (D-312)
    print(f"{'case':40s} {'status':{w}s} exact  tol fail skip n/e n/f n/a")
    for r in results:
        c = r.counts()
        print(f"{r.case_id:40s} {r.status_text():{w}s} {c['pass']:5d} {c['pass-tolerance']:4d} {c['fail']:4d} {c['skip']:4d} {c['not-exercised']:3d} {c['not-fetched']:3d} {c['not-available']:3d}")
    print()
    from .gates import compute_gates
    gates = compute_gates(results, root, runner.data)
    for g in gates:
        print(f"gate {g['name']}: {g['headline']}")
    print()
    for r in results:
        shown = [i for i in r.items if args.verbose or i.status in ("fail", "pass-tolerance")]
        if shown:
            print(f"== {r.case_id}")
            for i in shown:
                print(f"  [{i.status}] {i.check} ({i.file or '-'}): {printable(i.detail)}")
    drifted = [(r.case_id, p) for r in results for p in r.drift]
    if drifted:
        print("\nSTABLE SOURCE DRIFT: " + ", ".join(f"{c}: {p}" for c, p in drifted)
              + "\n  These stable-tier files differ from the tested snapshot; the frozen expected values were not applied to them and the parser was compared against the reference reader instead."
              + (" Run " + runner.hint("--check-drift") + "." if runner.fetch_hints else ""))
    modes = {m for r in results for m in r.modes.values()}
    if "live" in modes:
        print("\nnote: some sources hash differently from the tested snapshot; for those, values were compared against the corpus's own reference reader, not the human-verified snapshot.")
    if args.json:
        import datetime as _dt
        failed_write = write_json(args.json, {"gpconf": __version__, "corpus_version": manifest["corpus_version"], "parser": parser_name,
                       **({"preset": {k: preset.get(k) for k in ("name", "library", "found", "tested_with", "runtime") if k != "runtime" or preset.get(k)}} if preset else {}),
                       "generated_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                       "summary": status_totals(results),  # case totals as numbers: what a script reads (D-240)
                       "inside_cases": annotation_totals(results),  # item skips, field gaps, cases graded (D-312)
                       "results": [r.as_dict() for r in results], "gates": gates})
        if failed_write:
            print(f"gpconf: --json {printable(args.json)}: the report was not written ({failed_write})", file=sys.stderr)
            return 2
    failed = sum(1 for r in results if r.status == "fail")
    tol = sum(1 for r in results if r.status == "pass-tolerance")
    unfetched = [r for r in results if r.status == "not-fetched"]
    print("\n" + count_line(results))
    for line in (graded_line(results), inside_line(results)):
        if line:
            print(line)
    print_missing(results, unfetched, runner)
    reused = {p: v for r in results for p, v in r.reused.items()}
    if reused:  # D-157: the report says which provider files were copied from an earlier version's cache, not fetched
        print(f"{qty(len(reused), 'provider file')} {pick(len(reused), 'was', 'were')} reused from corpus {', '.join(sorted(set(map(str, reused.values()))))}'s cache "
              "rather than fetched: stable tier, bytes matching this version's recorded SHA-256.")
    recorded = {p: v for r in results for p, v in r.recorded.items()}
    if recorded:  # D-247: the report says which files hold the corpus's record of the provider's empty answer, not a fetched one
        print(f"{qty(len(recorded), 'provider file')} {pick(len(recorded), 'holds', 'hold')} the corpus's record of CelesTrak's empty answer "
              "(HTTP 404, 'No GP data found', to a TLE request above 99999): written by the fetch from recorded/, not requested.")
    if tol:
        print("'pass within tolerance' items list per-field count, mean signed difference and maximum, so a systematic bias is visible (see README, Tolerances).")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
