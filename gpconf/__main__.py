"""python -m gpconf: run a parser against the corpus and print a report; fetch: fetch the provider data the corpus
does not ship; list: the cases; check-tle: check a TLE file a tool wrote."""
import argparse
import importlib
import json
import os
import sys

from . import __version__
from . import locate
from .runner import Runner, CommandParser, CorpusIncomplete


def load_adapter(spec):
    mod, _, attr = spec.partition(":")
    sys.path.insert(0, os.getcwd())
    m = importlib.import_module(mod)
    obj = getattr(m, attr or "Parser")
    return obj() if isinstance(obj, type) else obj


def print_missing(results, unfetched, runner):
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
            # corrected by D-150: a normal fetch never requests a re-capture, so a later run does not bring it
            print("  A re-capture file is the same endpoint requested a second time when the corpus was built; the fetch requests it "
                  "only with --include-recaptures, once its original is at least two hours old, so a normal fetch leaves these cases without it.")
    # the fetch command only where a normal fetch would bring something: a missing re-capture it never requests (D-150)
    if any("recapture" not in os.path.basename(f) for r in results for f in r.missing()):
        print(f"Provider data is not shipped with the corpus; fetch it with {runner.hint()}.")


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
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv[:1] == ["fetch"]:  # its own options (tools/fetch.py's), parsed by gpconf/fetch.py (D-150)
        from .fetch import run as fetch_run
        return fetch_run(argv[1:], prog="gpconf fetch")
    ap = argparse.ArgumentParser(prog="gpconf", description="GP/OMM conformance corpus runner",
                                 epilog="gpconf fetch --help: the fetch subcommand's own options")
    ap.add_argument("command", choices=["run", "list", "presets", "check-tle", "fetch"])
    ap.add_argument("files", nargs="*", help="check-tle: TLE file(s) written by the tool under test")
    ap.add_argument("--against", help="check-tle: the source records the lines were written from (CSV/JSON/XML/KVN/TLE); enables the round-trip check")
    ap.add_argument("--preset", help="a shipped adapter by name: reference, naive, sgp4, pyephem, satellite.js, tle.js or tle.js-api (gpconf presets lists them)")
    ap.add_argument("--module", help="Node presets: the library's entry file, for a checkout the working directory cannot import by name")
    ap.add_argument("--adapter", help="python import path module:attr of a parser object or class")
    ap.add_argument("--cmd", help="external command; raw bytes on stdin, JSON array on stdout; {fmt} substituted; exit 3 = unsupported format")
    ap.add_argument("--vectors-cmd", help="external command for vector hooks (JSON {op,input} on stdin -> {result}|{error})")
    ap.add_argument("--write-cmd", help="external TLE writer for the writer case: one JSON record on stdin, 2-3 TLE lines on stdout; exit 3 = unsupported, other non-zero = refused")
    ap.add_argument("--root", help="corpus root (default: the clone this package sits in, else the corpus installed with it)")
    ap.add_argument("--data", help=f"folder holding the fetched provider files (default: ${locate.DATA_ENV}, else the clone, else a per-user cache folder)")
    ap.add_argument("--case", action="append", help="case id (repeatable)")
    ap.add_argument("--tag", action="append", help="test tag (repeatable)")
    ap.add_argument("--json", help="write the full report to this file")
    ap.add_argument("--verbose", "-v", action="store_true", help="print every item, not only failures and within-tolerance passes")
    args = ap.parse_args(argv)

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
    manifest = json.load(open(os.path.join(root, "manifest.json")))
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
        parser = load_adapter(args.adapter)
    parser_name = preset["label"] if preset else (args.cmd or args.write_cmd or args.adapter)
    runner = Runner(parser, root=root, verbose=args.verbose, data=loc["data"], data_why=loc["data_why"])
    try:
        results = runner.run(case_ids=args.case, tags=args.tag)
    except CorpusIncomplete as e:
        print(f"gpconf: {e}", file=sys.stderr)
        return 2
    print(f"gpconf {__version__} | corpus {manifest['corpus_version']} | parser: {parser_name}")
    if runner.data != root:  # a clone's output is unchanged; elsewhere the reader is told where the provider files were looked for
        print(f"provider data: {runner.data} ({runner.data_why})")
    print()
    print(f"{'case':40s} {'status':15s} exact  tol fail skip n/e n/f")
    for r in results:
        c = r.counts()
        print(f"{r.case_id:40s} {r.status:15s} {c['pass']:5d} {c['pass-tolerance']:4d} {c['fail']:4d} {c['skip']:4d} {c['not-exercised']:3d} {c['not-fetched']:3d}")
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
                print(f"  [{i.status}] {i.check} ({i.file or '-'}): {i.detail}")
    drifted = [(r.case_id, p) for r in results for p in r.drift]
    if drifted:
        print("\nSTABLE SOURCE DRIFT: " + ", ".join(f"{c}: {p}" for c, p in drifted)
              + "\n  These stable-tier files differ from the tested snapshot; the frozen expected values were not applied to them and the parser was compared against the reference reader instead. Run "
              + runner.hint("--check-drift") + ".")
    modes = {m for r in results for m in r.modes.values()}
    if "live" in modes:
        print("\nnote: some sources hash differently from the tested snapshot; for those, values were compared against the corpus's own reference reader, not the human-verified snapshot.")
    if args.json:
        import datetime as _dt
        with open(args.json, "w") as f:
            json.dump({"gpconf": __version__, "corpus_version": manifest["corpus_version"], "parser": parser_name,
                       **({"preset": {k: preset.get(k) for k in ("name", "library", "found", "tested_with", "runtime") if k != "runtime" or preset.get(k)}} if preset else {}),
                       "generated_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                       "results": [r.as_dict() for r in results], "gates": gates}, f, indent=1, default=str)
    failed = sum(1 for r in results if r.status == "fail")
    tol = sum(1 for r in results if r.status == "pass-tolerance")
    unfetched = [r for r in results if r.status == "not-fetched"]
    print(f"\n{len(results)} case(s): {sum(1 for r in results if r.status == 'pass')} pass (exact), {tol} pass within tolerance, {failed} fail, "
          f"{sum(1 for r in results if r.status == 'skip')} skip, {len(unfetched)} need fetched data, {sum(1 for r in results if r.status == 'not-exercised')} not exercised")
    print_missing(results, unfetched, runner)
    reused = {p: v for r in results for p, v in r.reused.items()}
    if reused:  # D-157: the report says which provider files were copied from an earlier version's cache, not fetched
        print(f"{len(reused)} provider file(s) were reused from corpus {', '.join(sorted(set(map(str, reused.values()))))}'s cache "
              "rather than fetched: stable tier, bytes matching this version's recorded SHA-256.")
    if tol:
        print("'pass within tolerance' items list per-field count, mean signed difference and maximum, so a systematic bias is visible (see README, Tolerances).")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
