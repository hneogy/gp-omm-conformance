"""python -m gpconf: run a parser against the corpus and print a report."""
import argparse
import importlib
import json
import os
import sys

from . import __version__
from .runner import Runner, CommandParser


def load_adapter(spec):
    mod, _, attr = spec.partition(":")
    sys.path.insert(0, os.getcwd())
    m = importlib.import_module(mod)
    obj = getattr(m, attr or "Parser")
    return obj() if isinstance(obj, type) else obj


def main(argv=None):
    ap = argparse.ArgumentParser(prog="gpconf", description="GP/OMM conformance corpus runner")
    ap.add_argument("command", choices=["run", "list"])
    ap.add_argument("--adapter", help="python import path module:attr of a parser object or class")
    ap.add_argument("--cmd", help="external command; raw bytes on stdin, JSON array on stdout; {fmt} substituted; exit 3 = unsupported format")
    ap.add_argument("--vectors-cmd", help="external command for vector hooks (JSON {op,input} on stdin -> {result}|{error})")
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
    if not args.adapter and not args.cmd:
        ap.error("run needs --adapter or --cmd")
    parser = CommandParser(args.cmd, args.vectors_cmd) if args.cmd else load_adapter(args.adapter)
    runner = Runner(parser, root=root, verbose=args.verbose)
    results = runner.run(case_ids=args.case, tags=args.tag)
    print(f"gpconf {__version__} | corpus {manifest['corpus_version']} | parser: {args.cmd or args.adapter}")
    print()
    print(f"{'case':40s} {'status':15s} exact  tol fail skip n/e")
    for r in results:
        c = r.counts()
        print(f"{r.case_id:40s} {r.status:15s} {c['pass']:5d} {c['pass-tolerance']:4d} {c['fail']:4d} {c['skip']:4d} {c['not-exercised']:3d}")
    print()
    for r in results:
        shown = [i for i in r.items if args.verbose or i.status in ("fail", "pass-tolerance")]
        if shown:
            print(f"== {r.case_id}")
            for i in shown:
                print(f"  [{i.status}] {i.check} ({i.file or '-'}): {i.detail}")
    modes = {m for r in results for m in r.modes.values()}
    if "live" in modes:
        print("\nnote: some sources hash differently from the tested snapshot; for those, values were compared against the corpus's own reference reader, not the human-verified snapshot.")
    if args.json:
        import datetime as _dt
        with open(args.json, "w") as f:
            json.dump({"gpconf": __version__, "corpus_version": manifest["corpus_version"], "parser": args.cmd or args.adapter,
                       "generated_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                       "results": [r.as_dict() for r in results]}, f, indent=1, default=str)
    failed = sum(1 for r in results if r.status == "fail")
    tol = sum(1 for r in results if r.status == "pass-tolerance")
    print(f"\n{len(results)} case(s): {sum(1 for r in results if r.status == 'pass')} pass (exact), {tol} pass within tolerance, {failed} fail, "
          f"{sum(1 for r in results if r.status == 'skip')} skip, {sum(1 for r in results if r.status == 'not-exercised')} not exercised")
    if tol:
        print("'pass within tolerance' items list per-field count, mean signed difference and maximum, so a systematic bias is visible (see README, Tolerances).")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
