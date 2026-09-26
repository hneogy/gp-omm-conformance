"""python -m gpconf: run a parser against the corpus and print a report; check-tle: check a TLE file a tool wrote."""
import argparse
import importlib
import json
import os
import sys

from . import __version__
from .runner import Runner, CommandParser, CorpusIncomplete, fetch_hint


def load_adapter(spec):
    mod, _, attr = spec.partition(":")
    sys.path.insert(0, os.getcwd())
    m = importlib.import_module(mod)
    obj = getattr(m, attr or "Parser")
    return obj() if isinstance(obj, type) else obj


def print_missing(results, unfetched, root):
    """Below the count line: what was not fetched, so that neither a case with no data nor a case that ran on part
    of its data reads as a result it has not earned (D-148)."""
    partial = [r for r in results if r.status != "not-fetched" and r.missing()]
    if not unfetched and not partial:
        return
    if unfetched:
        print(f"{len(unfetched)} case(s) have none of their provider files on disk and report not-fetched; "
              "skip is reserved for a parser with no reader for a format or no hook for a check.")
    if partial:
        files = [f for r in partial for f in r.missing()]
        print(f"{len(partial)} case(s) ran without {len(files)} of their provider files, so each result covers only the files on disk "
              f"(column n/f): {', '.join(r.case_id for r in partial)}.")
        if any("recapture" in os.path.basename(f) for f in files):
            print("  A re-capture file is fetched on a later run, once its original is at least two hours old.")
    print(f"Provider data is not shipped with the corpus; fetch it with {fetch_hint(root)}.")


def check_tle(args):
    """check-tle FILE... [--against RECORDS] [--json OUT]: the writer checks applied to files a tool wrote."""
    from . import writer as W
    if not args.files:
        print("check-tle needs at least one TLE file", file=sys.stderr)
        return 2
    against = W.load_against(args.against) if args.against else None
    print(f"gpconf {__version__} | check-tle | {len(args.files)} file(s)" + (f" | round trip against {args.against}" if args.against else ""))
    report, n_pass, n_fail = [], 0, 0
    for path in args.files:
        with open(path, "rb") as f:
            text = f.read().decode("utf-8", "replace")
        results = W.check_file(text, against)
        print(f"\n{path}: {len(results)} record(s)" + ("" if results else " (no element line found)"))
        for r in results:
            ident = repr(r["catalog_field"]) + (f" -> {r['norad_cat_id']}" if r["norad_cat_id"] is not None else "")
            head = "unpaired element line" if r.get("unpaired") else (r["name"] or "(no name line)")
            print(f"  [{r['status']}] line {r['line_number']}: {head} | catalog field {ident}")
            for p in r["problems"]:
                print(f"         {p}")
            for n in r["notes"]:
                print(f"         note: {n}")
            if r.get("round_trip"):
                print("         round trip against the source record: " + ", ".join(f"{k} {v}" for k, v in r["round_trip"]["conventions"].items()))
            if r.get("secondary_fields"):
                print("         secondary fields (information): " + ", ".join(f"{k} {v}" for k, v in r["secondary_fields"].items() if k != "zero_ddot_sign"))
            n_pass += r["status"] == "pass"
            n_fail += r["status"] == "fail"
        report.append({"file": path, "records": results})
    print(f"\n{n_pass + n_fail} record(s): {n_pass} pass, {n_fail} fail"
          + ("" if n_pass + n_fail else "; nothing to check"))
    if args.json:
        import datetime as _dt
        with open(args.json, "w") as f:
            json.dump({"gpconf": __version__, "command": "check-tle", "against": args.against,
                       "generated_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "files": report}, f, indent=1, default=str)
    return 1 if n_fail or not (n_pass + n_fail) else 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="gpconf", description="GP/OMM conformance corpus runner")
    ap.add_argument("command", choices=["run", "list", "check-tle"])
    ap.add_argument("files", nargs="*", help="check-tle: TLE file(s) written by the tool under test")
    ap.add_argument("--against", help="check-tle: the source records the lines were written from (CSV/JSON/XML/KVN/TLE); enables the round-trip check")
    ap.add_argument("--adapter", help="python import path module:attr of a parser object or class")
    ap.add_argument("--cmd", help="external command; raw bytes on stdin, JSON array on stdout; {fmt} substituted; exit 3 = unsupported format")
    ap.add_argument("--vectors-cmd", help="external command for vector hooks (JSON {op,input} on stdin -> {result}|{error})")
    ap.add_argument("--write-cmd", help="external TLE writer for the writer case: one JSON record on stdin, 2-3 TLE lines on stdout; exit 3 = unsupported, other non-zero = refused")
    ap.add_argument("--root", help="corpus root (default: the directory containing manifest.json next to this package)")
    ap.add_argument("--case", action="append", help="case id (repeatable)")
    ap.add_argument("--tag", action="append", help="test tag (repeatable)")
    ap.add_argument("--json", help="write the full report to this file")
    ap.add_argument("--verbose", "-v", action="store_true", help="print every item, not only failures and within-tolerance passes")
    args = ap.parse_args(argv)

    root = args.root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    manifest = json.load(open(os.path.join(root, "manifest.json")))
    if args.command == "list":
        for c in manifest["cases"]:
            print(f"{c['id']:40s} {c['kind']:12s} {', '.join(c['tests'])}")
        return 0
    if args.command == "check-tle":
        return check_tle(args)
    if not args.adapter and not args.cmd and not args.write_cmd:
        ap.error("run needs --adapter, --cmd or --write-cmd")
    parser = CommandParser(args.cmd, args.vectors_cmd, write_cmd=args.write_cmd) if (args.cmd or args.write_cmd) else load_adapter(args.adapter)
    runner = Runner(parser, root=root, verbose=args.verbose)
    try:
        results = runner.run(case_ids=args.case, tags=args.tag)
    except CorpusIncomplete as e:
        print(f"gpconf: {e}", file=sys.stderr)
        return 2
    print(f"gpconf {__version__} | corpus {manifest['corpus_version']} | parser: {args.cmd or args.write_cmd or args.adapter}")
    print()
    print(f"{'case':40s} {'status':15s} exact  tol fail skip n/e n/f")
    for r in results:
        c = r.counts()
        print(f"{r.case_id:40s} {r.status:15s} {c['pass']:5d} {c['pass-tolerance']:4d} {c['fail']:4d} {c['skip']:4d} {c['not-exercised']:3d} {c['not-fetched']:3d}")
    print()
    from .gates import compute_gates
    gates = compute_gates(results, root)
    for g in gates:
        print(f"gate {g['name']}: {g['headline']}")
    print()
    for r in results:
        shown = [i for i in r.items if args.verbose or i.status in ("fail", "pass-tolerance")]
        if shown:
            print(f"== {r.case_id}")
            for i in shown:
                print(f"  [{i.status}] {i.check} ({i.file or '-'}): {i.detail}")
    drifted = [(r.case_id, p) for r in results for p in r.drift]
    if drifted:
        print("\nSTABLE SOURCE DRIFT: " + ", ".join(f"{c}: {p}" for c, p in drifted)
              + "\n  These stable-tier files differ from the tested snapshot; the frozen expected values were not applied to them and the parser was compared against the reference reader instead. Run "
              + fetch_hint(root, "--check-drift") + ".")
    modes = {m for r in results for m in r.modes.values()}
    if "live" in modes:
        print("\nnote: some sources hash differently from the tested snapshot; for those, values were compared against the corpus's own reference reader, not the human-verified snapshot.")
    if args.json:
        import datetime as _dt
        with open(args.json, "w") as f:
            json.dump({"gpconf": __version__, "corpus_version": manifest["corpus_version"], "parser": args.cmd or args.write_cmd or args.adapter,
                       "generated_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                       "results": [r.as_dict() for r in results], "gates": gates}, f, indent=1, default=str)
    failed = sum(1 for r in results if r.status == "fail")
    tol = sum(1 for r in results if r.status == "pass-tolerance")
    unfetched = [r for r in results if r.status == "not-fetched"]
    print(f"\n{len(results)} case(s): {sum(1 for r in results if r.status == 'pass')} pass (exact), {tol} pass within tolerance, {failed} fail, "
          f"{sum(1 for r in results if r.status == 'skip')} skip, {len(unfetched)} need fetched data, {sum(1 for r in results if r.status == 'not-exercised')} not exercised")
    print_missing(results, unfetched, root)
    if tol:
        print("'pass within tolerance' items list per-field count, mean signed difference and maximum, so a systematic bias is visible (see README, Tolerances).")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
