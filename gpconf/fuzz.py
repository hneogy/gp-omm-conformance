# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""gpconf fuzz: an adapter fuzzed against the corpus's own reference reader, opt-in and never part of `gpconf run`
(Phase 3 item 7; lane C's design section 5; D-415). Its findings are reported only and never move a case verdict
(the owner's ruling on lane C's question 8).

Seeds are the corpus's shipped inputs (derived/), the formats the adapter reads; each fuzz input is one seed with one
mutation operator applied, drawn from a random generator seeded by --seed, so a run is repeated exactly by its seed.
The oracle is differential: the adapter must not crash or hang (a command's budget, its process isolation), and then
either refuses the input or returns what the reference reader makes of the same bytes. Where the reference refuses and
the adapter returns records, that is an observation, never a finding: a reader may be lenient. A finding's input is
minimised and saved with its seed. With --propagate, the propagate hook is fuzzed too: element values pushed to and
past SGP4's domain, and times far from the epoch; at every step the answer must be a non-zero SGP4 code or a finite
position and velocity ("silent NaN" otherwise), and no call may crash or hang. A Python adapter runs in gpconf's
process and has no budget, so a hang in it hangs the run."""
import collections
import csv
import io
import json
import math
import os
import random

from .runner import CommandCrashed, ParserExit, Unsupported, compare_value, norm_record, split_refusals, crashed
from .runner import UnreadableValue
from .words import qty

FORMATS = ("tle", "csv", "json", "xml", "kvn")
FINDINGS = ("crash", "unreadable", "differs", "dropped", "surplus")
COMPARED = ("norad_cat_id", "epoch", "mean_motion", "eccentricity", "inclination", "ra_of_asc_node", "arg_of_pericenter",
            "mean_anomaly", "bstar", "mean_motion_dot", "mean_motion_ddot", "ephemeris_type", "classification_type",
            "element_set_no", "rev_at_epoch")
NON_ASCII_DIGITS = "٠١٢٣٤٥٦٧٨٩"   # Arabic-Indic: digits to Python's int(), never to a TLE


def seeds(root):
    """The shipped inputs, (path relative to root, format), in a stable order."""
    out = []
    base = os.path.join(root, "derived")
    for d, _, names in sorted(os.walk(base)):
        for n in sorted(names):
            ext = n.rsplit(".", 1)[-1]
            if ext in FORMATS and not n.endswith(".provenance.json"):
                out.append((os.path.relpath(os.path.join(d, n), root).replace(os.sep, "/"), ext))
    return out


def _checksum(line68):
    return str(sum(int(c) if c.isdigit() else (1 if c == "-" else 0) for c in line68) % 10)


def _element_lines(lines):
    return [i for i, l in enumerate(lines) if l[:2] in ("1 ", "2 ") and len(l) >= 68]


def mutate(data, fmt, rng):
    """One mutation operator applied to one input -> (bytes, operator name). An operator the input offers no place
    for, or one whose draw changes nothing, falls back to one byte replaced by another, so every draw mutates."""
    out, op = _mutate(data, fmt, rng)
    if out != data:
        return out, op
    b = bytearray(data)
    if not b:
        return b"\n", "byte"
    i = rng.randrange(len(b))
    b[i] = rng.choice([c for c in b"0Ox-+ \n" if c != b[i]])
    return bytes(b), "byte"


def _mutate(data, fmt, rng):
    text = data.decode("utf-8", "replace")
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(nl)
    el = _element_lines(lines) if fmt == "tle" else []
    ops = ["line-endings", "truncate", "overlong", "blank-run", "non-ascii-digit", "duplicate-line", "drop-line"]
    if el:
        ops += ["shift-column", "checksum-broken", "checksum-recomputed", "alpha5-letter", "exponent-form", "letter-in-epoch"]
    if fmt in ("csv", "json", "xml", "kvn"):
        ops += ["value-nan", "value-overflow", "value-empty"]
    if fmt in ("xml", "kvn"):
        ops += ["syntax-break"]
    op = rng.choice(ops)
    if op == "line-endings":
        out = text.replace(nl, rng.choice([e for e in ("\n", "\r", "\r\n", "\n\r") if e != nl]))
    elif op == "truncate":
        out = text[: rng.randrange(1, max(2, len(text)))]
    elif op == "overlong":
        i = rng.randrange(len(lines))
        lines[i] = lines[i] + rng.choice(["0", " ", "X", "  12345"])
        out = nl.join(lines)
    elif op == "blank-run":
        i = rng.randrange(len(text))
        k = rng.randint(1, 8)   # the same number of characters, blanked: the line keeps its length
        out = text[:i] + " " * len(text[i:i + k]) + text[i + k:]
    elif op == "non-ascii-digit":
        idx = [i for i, c in enumerate(text) if c.isdigit() and c.isascii()]
        if not idx:
            return data, "none"
        i = rng.choice(idx)
        out = text[:i] + NON_ASCII_DIGITS[int(text[i])] + text[i + 1:]
    elif op == "duplicate-line":
        i = rng.randrange(len(lines))
        lines.insert(i, lines[i])
        out = nl.join(lines)
    elif op == "drop-line":
        if len(lines) < 2:
            return data, "none"
        del lines[rng.randrange(len(lines))]
        out = nl.join(lines)
    elif op in ("shift-column", "checksum-broken", "checksum-recomputed", "alpha5-letter", "exponent-form", "letter-in-epoch"):
        i = rng.choice(el)
        l = lines[i]
        if op == "shift-column":
            c = rng.randrange(2, 68)
            l = (l[:c] + " " + l[c:68]) if rng.random() < 0.5 else (l[:c] + l[c + 1:69] + " ")
        elif op == "checksum-broken":
            l = l[:68] + str((int(l[68]) + rng.randint(1, 9)) % 10 if l[68:69].isdigit() else 0) + l[69:]
        elif op == "checksum-recomputed":
            c = rng.randrange(18, 68)
            body = l[:c] + rng.choice("0123456789-+. ") + l[c + 1:68]
            l = body + _checksum(body) + l[69:]
        elif op == "alpha5-letter":
            body = l[:2] + rng.choice("IOabzZ") + l[3:68]
            l = body + _checksum(body) + l[69:]
        elif op == "exponent-form":   # BSTAR or the second derivative, columns 54-61 or 45-52 of line 1
            if l[0] != "1":
                return data, "none"
            field = rng.choice(["-11606-4", "+00000+0", " 11606 4", "11606-4 ", "1.1606-4", " 11606+9"])
            start = rng.choice([44, 53])
            body = l[:start] + field + l[start + 8:68]
            l = body + _checksum(body) + l[69:]
        elif op == "letter-in-epoch":
            if l[0] != "1":
                return data, "none"
            c = rng.randrange(18, 32)
            body = l[:c] + rng.choice("OlIS") + l[c + 1:68]
            l = body + _checksum(body) + l[69:]
        lines[i] = l
        out = nl.join(lines)
    elif op in ("value-nan", "value-overflow", "value-empty"):
        new = {"value-nan": "NaN", "value-overflow": "1e999", "value-empty": ""}[op]
        out = _replace_value(text, fmt, rng, new)
        if out is None:
            return data, "none"
    elif op == "syntax-break":
        if fmt == "kvn":
            idx = [i for i, l in enumerate(lines) if "=" in l]
            i = rng.choice(idx) if idx else 0
            lines[i] = lines[i].replace("=", rng.choice([" ", "==", ":"]), 1)
            out = nl.join(lines)
        else:
            cut = [i for i, c in enumerate(text) if c in "<>/"]
            i = rng.choice(cut) if cut else 0
            out = text[:i] + text[i + 1:]
    return out.encode("utf-8"), op


NUMBER_KEYS = ("MEAN_MOTION", "ECCENTRICITY", "INCLINATION", "RA_OF_ASC_NODE", "ARG_OF_PERICENTER", "MEAN_ANOMALY", "BSTAR",
               "MEAN_MOTION_DOT", "MEAN_MOTION_DDOT")


def _replace_value(text, fmt, rng, new):
    """One numeric OMM value replaced by `new`, in the format's own syntax; None when no value is found."""
    import re
    key = rng.choice(NUMBER_KEYS)
    if fmt == "kvn":
        pat = re.compile(rf"(?m)^(\s*{key}\s*=\s*)(\S+)")
    elif fmt == "xml":
        pat = re.compile(rf"(<{key}>)([^<]*)")
    elif fmt == "json":
        pat = re.compile(rf'("{key}"\s*:\s*)("?[^,}}"]*"?)')
    else:
        nl = "\r\n" if "\r\n" in text else "\n"
        lines = text.split(nl)
        head = next(csv.reader([lines[0]]), [])
        data_lines = [i for i in range(1, len(lines)) if lines[i].strip()]
        if key not in head or not data_lines:
            return None
        r = rng.choice(data_lines)
        row = next(csv.reader([lines[r]]), [])
        j = head.index(key)
        if j >= len(row):
            return None
        row[j] = new
        out = io.StringIO()
        csv.writer(out, lineterminator="").writerow(row)   # that row alone written again; the others keep their bytes
        lines[r] = out.getvalue()
        return nl.join(lines)
    hits = list(pat.finditer(text))
    if not hits:
        return None
    m = rng.choice(hits)
    value = (f'"{new}"' if new in ("NaN", "") else new) if fmt == "json" else new
    return text[:m.start(2)] + value + text[m.end(2):]


def reference_reading(data, fmt):
    """The reference reader's reading -> (records, refusals); a whole-file refusal is ([], [its reason])."""
    from .adapters.reference import Parser as Reference
    try:
        recs = Reference().parse(data, fmt)
    except Exception as e:
        return [], [{"id": None, "reason": f"{type(e).__name__}: {str(e)[:120]}"}]
    records, refusals, _ = split_refusals(recs)
    return records, refusals


def adapter_reading(parser, data, fmt):
    """-> (outcome, records or detail, refusals): "crash", "unsupported", "refused" (a raise), "unreadable" for an
    answer that is no list, or "answer" with the records and the refusals it returned."""
    try:
        recs = parser.parse(data, fmt)
    except Unsupported as e:
        return "unsupported", str(e)[:120], []
    except ParserExit as e:
        return "crash", str(e)[:200], []
    except Exception as e:
        c = crashed(e)
        return ("crash", c, []) if c else ("refused", f"{type(e).__name__}: {str(e)[:120]}", [])
    if not isinstance(recs, list):
        return "unreadable", f"the answer is {type(recs).__name__}, no list", []
    records, refusals, _ = split_refusals(recs)
    return "answer", records, refusals


FLOAT_MAX = 1.7976931348623157e308


def _by_id(recs):
    """-> ({id: [(normalised record, notes)]}, None) or (None, why) when a record cannot be read."""
    out: dict = {}
    for r in recs:
        try:
            n, notes, _ = norm_record(r)
        except (ValueError, UnreadableValue) as e:
            return None, f"a record the runner cannot read ({str(e)[:100]})"
        out.setdefault(n.get("norad_cat_id"), []).append((n, notes))
    return out, None


def _raw_id(r):
    """The catalog number a record the runner cannot normalise carries, read as plainly as possible, or None."""
    v = r.get("norad_cat_id") if isinstance(r, dict) else None
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def _past_float_range(recs):
    """True when a record holds an element value no binary float can carry: a reader converting it gives an
    infinity, the IEEE reading of a value the reference keeps as decimal text (the review of D-415)."""
    from decimal import Decimal
    for r in recs:
        for f in COMPARED:
            v = r.get(f)
            try:
                if v not in (None, "") and abs(Decimal(str(v))) > Decimal(FLOAT_MAX):
                    return True
            except Exception:
                continue
    return False


def _mismatches(k, a, notes, b):
    """The fields both readers read, compared; a field the reference reads as absent is not compared (a reader may
    give its default, as 0 for a blank derivative: the review of D-415)."""
    out = []
    for f in COMPARED:
        if f in a and f in b and a[f] is not None and b[f] is not None:
            res, _d = compare_value(f, a[f], b[f], notes.get(f))
            if res == "mismatch":
                out.append(f"id {k}: {f} reads {a[f]!s} where the reference reads {b[f]!s}")
    return out


def _match(rows, refs, k):
    """A largest matching of the reference's copies to agreeing adapter copies, in any order (augmenting paths;
    the copies of one id are few) -> (reference copies left unmatched, adapter copies left unmatched)."""
    agree = [[not _mismatches(k, a, notes, b) for (a, notes) in rows] for (b, _n) in refs]
    owner = [None] * len(rows)

    def take(i, seen):
        for j in range(len(rows)):
            if agree[i][j] and j not in seen:
                seen.add(j)
                if owner[j] is None or take(owner[j], seen):
                    owner[j] = i
                    return True
        return False
    unmatched_refs = [i for i in range(len(refs)) if not take(i, set())]
    unmatched_rows = [j for j in range(len(rows)) if owner[j] is None]
    return unmatched_refs, unmatched_rows


def _holds_a_value(r):
    """False for a record every value of which is None or empty text (0 and a blank are values)."""
    return not isinstance(r, dict) or any(v is not None and v != "" for v in r.values())


def judge(records, refusals, want, ref_refusals):
    """Record by record -> (category, detail). A record both read with a value that differs: "differs"; a record (or a
    copy of one) the reference reads that the adapter neither returns nor refuses: "dropped"; a record only the
    adapter returns, the reference refusing it or holding none of its id: "lenient", an observation. A record the
    runner cannot read (a NaN, an infinity) is judged by its own catalog number (D-417): a finding where a copy of that
    id the reference reads is left unmatched by the adapter's readable copies and no refusal of the reference names
    it, and the reference holds no value past a float's range there; otherwise an observation. Copies are counted
    by the rule of D-311 (the second blind audit's F1, the owner's ruling of 2026-11-10 for exact duplicates, D-421):
    one copy kept of an exact duplicate the input holds twice is a dropped copy, and a copy returned beyond those the
    reference reads, where the reference refuses nothing of that id and nothing unnamed, is a "surplus" finding."""
    # a record holding no value at all (a KVN header line written twice opens an empty message) is no record: neither
    # one to drop from the reference's reading nor a copy in the reader's answer (the review of D-421, D-429)
    want = [r for r in want if _holds_a_value(r)]
    records = [r for r in records if _holds_a_value(r)]
    ref, _ = _by_id(want)
    ref = ref or {}
    readable, unreadable = [], []
    for r in records:
        try:
            norm_record(r)
            readable.append(r)
        except (ValueError, UnreadableValue) as e:
            unreadable.append((_raw_id(r), f"a record the runner cannot read ({str(e)[:100]})"))
    got, _why = _by_id(readable)
    ref_refused = {r["id"] for r in ref_refusals if r.get("id") is not None}
    real = [r for r in refusals if r["ok"]]   # a refusal with no reason is no better than a drop (D-290's line)
    refused = collections.Counter(r["id"] for r in real if r["id"] is not None)
    unattributed = sum(1 for r in real if r["id"] is None)
    diffs, lenient, surplus, missing = [], [], [], []
    unnamed_ref_refusal = any(r.get("id") is None for r in ref_refusals)
    left_of = {}   # id -> the reference copies no readable copy of the adapter's matched
    for k in ref:
        rows = got.get(k, [])
        left_refs, left_rows = _match(rows, ref[k], k) if rows else (list(range(len(ref[k]))), [])
        still = []
        for i in left_refs:
            if left_rows:
                diffs += _mismatches(k, rows[left_rows[0]][0], rows[left_rows[0]][1], ref[k][i][0])
                left_rows = left_rows[1:]
            else:
                still.append(i)   # an exact duplicate kept once is a dropped copy too (D-311's count, D-421)
        left_of[k] = still
        if left_rows:
            if k not in ref_refused and not unnamed_ref_refusal:
                surplus.append(k)   # more copies than the input holds, agreeing or not (D-311, D-421)
            else:
                lenient.append(k)   # a copy more than the reference reads: an orphan line or a set it refuses
    lenient += [k for k in got if k not in ref]
    lenient_unreadable = []
    for rid, why in unreadable:
        if left_of.get(rid) and rid not in ref_refused and not _past_float_range([ref[rid][i][0] for i in left_of[rid]]):
            return "unreadable", why   # it stands for a record the reference reads, which no readable copy gave
        if left_of.get(rid):
            left_of[rid] = left_of[rid][1:]   # returned, though unreadable: never also a drop
        lenient_unreadable.append(why)
    for k, idx in left_of.items():
        missing += [k] * len(idx)
    dropped = []
    for k in missing:
        if refused.get(k, 0) > 0:
            refused[k] -= 1
        elif unattributed > 0:   # a refusal naming no id may be any of them
            unattributed -= 1
        else:
            dropped.append(k)
    if diffs:
        return "differs", "; ".join(diffs[:3])
    if dropped:
        return "dropped", f"ids {sorted(map(str, dropped))[:5]}, which the reference reads, neither returned nor refused"
    if surplus:
        return "surplus", f"ids {sorted(map(str, surplus))[:5]} returned more often than the input holds them"
    if lenient:
        return "lenient", f"returned ids {sorted(map(str, lenient))[:5]}, which the reference refused or does not read"
    if lenient_unreadable:
        return "lenient", f"returned what the reference refuses or keeps past a float's range: {lenient_unreadable[0]}"
    return "ok", ""


def classify(parser, data, fmt):
    """-> (category, detail): "crash", "unreadable", "differs", "dropped" and "surplus" are findings; "lenient" is an
    observation; "ok", "refused" (the whole input refused with a reason, an acceptable answer to a mutated file) and
    "unsupported" are neither."""
    got, detail, refusals = adapter_reading(parser, data, fmt)
    if got in ("crash", "unreadable"):
        return got, detail
    if got == "unsupported":
        return "unsupported", detail
    if got == "refused":   # counted apart from "ok", so a run of nothing but refusals can be told (D-459)
        return "refused", detail
    want, ref_refusals = reference_reading(data, fmt)
    return judge(detail, refusals, want, ref_refusals)


def minimise(parser, data, fmt, category, budget=200):
    """A smaller input with the same category, within `budget` parser calls (each a command run, with --cmd): chunks
    of lines removed, halves first and then smaller (delta debugging), then chunks of characters the same way."""
    calls, cur = 0, data
    for unit in ("line", "char"):
        parts = cur.split(b"\n") if unit == "line" else [cur[j:j + 1] for j in range(len(cur))]
        glue = b"\n" if unit == "line" else b""
        size = max(1, len(parts) // 2)
        while size >= 1 and calls < budget and len(parts) > 1:
            i, shrunk = 0, False
            while i < len(parts) and calls < budget:
                cand = parts[:i] + parts[i + size:]
                calls += 1
                if cand and classify(parser, glue.join(cand), fmt)[0] == category:
                    parts, shrunk = cand, True
                else:
                    i += size
            if not shrunk:
                size //= 2
        cur = glue.join(parts)
    return cur


def fuzz_parse(parser, root, seed, count, out_dir=None):
    """The parse fuzzing -> report dict."""
    pool = seeds(root)
    formats = {}
    for path, fmt in pool:   # a format the adapter reads: its first seed is not answered unsupported
        if fmt not in formats:
            with open(os.path.join(root, path), "rb") as f:
                formats[fmt] = adapter_reading(parser, f.read(), fmt)[0] != "unsupported"
    usable = [(p, f) for p, f in pool if formats.get(f)]
    findings, observations = [], []
    tally: dict = {}
    for i in range(count if usable else 0):
        rng = random.Random(f"{seed}:{i}")
        path, fmt = rng.choice(usable)
        with open(os.path.join(root, path), "rb") as f:
            data = f.read()
        mutant, op = mutate(data, fmt, rng)
        cat, detail = classify(parser, mutant, fmt)
        tally[cat] = tally.get(cat, 0) + 1
        row = {"index": i, "seed": seed, "source": path, "fmt": fmt, "operator": op, "category": cat, "detail": detail}
        if cat in FINDINGS:
            small = minimise(parser, mutant, fmt, cat)
            row["bytes"] = len(small)
            if out_dir:
                os.makedirs(out_dir, exist_ok=True)
                name = f"fuzz-{seed}-{i}.{fmt}"
                with open(os.path.join(out_dir, name), "wb") as fh:
                    fh.write(small)
                row["saved"] = name
            findings.append(row)
        elif cat == "lenient":
            observations.append(row)
    return {"seed": seed, "count": count, "formats": sorted(f for f, ok in formats.items() if ok),
            "formats_unsupported": sorted(f for f, ok in formats.items() if not ok), "tally": tally,
            "findings": findings, "observations": observations}


def _domain_sets(root):
    """Element values pushed to and past SGP4's domain, as OMM CSV rows from the twins' first set: one value changed
    in each (lane C's design section 5)."""
    with open(os.path.join(root, "derived", "propagation-twins", "twins.csv"), encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    head, base = rows[0], rows[1]
    edits = [("ECCENTRICITY", v) for v in ("0", "0.000000000001", "0.999999", "1")] + \
            [("MEAN_MOTION", v) for v in ("0.000001", "17.5", "20")] + \
            [("BSTAR", v) for v in ("1", "-1", "0")] + [("MEAN_MOTION_DOT", "0.99999999")] + \
            [("EPOCH", v) for v in ("1957-10-04T19:28:34.000000", "2056-12-31T23:59:59.000000")]
    out = []
    for k, v in edits:
        r = list(base)
        r[head.index(k)] = v
        s = io.StringIO()
        csv.writer(s, lineterminator="\r\n").writerows([head, r])
        out.append((f"{k}={v}", s.getvalue().encode("utf-8")))
    return out


TIMES = [0.0, 1440.0, -1440.0, 1e5, 1e6, -1e6, 1e9]


def fuzz_propagate(parser, root):
    """The propagate hook on the domain sets -> report dict; findings are crashes, hangs and silent NaN."""
    hook = getattr(parser, "propagate", None)
    if hook is None:
        return {"skipped": "parser exposes no propagate hook"}
    findings = []
    tally: dict = {}
    for label, raw in _domain_sets(root):
        try:
            ans = hook(raw, "csv", TIMES)
        except Unsupported as e:   # this set only: the others are still fuzzed (the review of D-415)
            cat, detail = "unsupported", str(e)[:120]
        except ParserExit as e:
            cat, detail = "crash", str(e)[:200]
        except Exception as e:
            c = crashed(e)
            cat, detail = ("crash", c) if c else ("refused", f"{type(e).__name__}: {str(e)[:120]}")
        else:
            cat, detail = _steps_category(ans)
        tally[cat] = tally.get(cat, 0) + 1
        if cat in ("crash", "silent-nan", "unreadable"):
            findings.append({"set": label, "category": cat, "detail": detail, "times": TIMES})
    if tally.get("unsupported") == len(_domain_sets(root)):
        return {"skipped": "propagation from csv unsupported"}
    return {"sets": len(_domain_sets(root)), "times": TIMES, "tally": tally, "findings": findings}


def _finite3(v):
    return isinstance(v, (list, tuple)) and len(v) == 3 and all(type(x) in (int, float) and math.isfinite(x) for x in v)


def _steps_category(ans):
    if not isinstance(ans, (list, tuple)) or len(ans) != len(TIMES) or not all(isinstance(a, dict) for a in ans):
        return "unreadable", "the answer is no list of one step per time"
    bad = [TIMES[i] for i, a in enumerate(ans) if a.get("error", 0) == 0 and not (_finite3(a.get("r")) and _finite3(a.get("v")))]
    if bad:
        return "silent-nan", f"code 0 without a finite position and velocity at t = {', '.join(f'{t:g}' for t in bad[:4])}"
    if any(type(a.get("error", 0)) is not int for a in ans):
        return "unreadable", "an error code is no integer"
    return "ok", ""


def print_report(rep, prop=None):
    t = rep["tally"]
    print(f"fuzz: {rep['count']} inputs, seed {rep['seed']}, formats {', '.join(rep['formats']) or 'none'}"
          + (f" (unsupported: {', '.join(rep['formats_unsupported'])})" if rep["formats_unsupported"] else ""))
    print("  " + ", ".join(f"{k} {v}" for k, v in sorted(t.items())))
    print(f"  {qty(len(rep['findings']), 'finding')}: a crash, an unreadable answer, a record read otherwise than the reference reads it, one dropped without a refusal, or one returned more often than the input holds it")
    for f in rep["findings"][:20]:
        print(f"    [{f['category']}] #{f['index']} {f['source']} ({f['operator']}): {f['detail'][:160]}"
              + (f" -> {f['saved']}, {f['bytes']} bytes" if f.get("saved") else ""))
    print(f"  {qty(len(rep['observations']), 'observation')}: accepted what the reference refused (a reader may be lenient)")
    for o in rep["observations"][:10]:
        print(f"    #{o['index']} {o['source']} ({o['operator']})")
    if prop is not None:
        if "skipped" in prop:
            print(f"propagate: skipped, {prop['skipped']}")
        else:
            print(f"propagate: {prop['sets']} sets at the edge of SGP4's domain, {len(prop['times'])} times each; "
                  + ", ".join(f"{k} {v}" for k, v in sorted(prop["tally"].items())))
            for f in prop["findings"][:20]:
                print(f"    [{f['category']}] {f['set']}: {f['detail'][:160]}")
    print("Findings are reported only and never move a case verdict (D-415); repeat this run with the same --seed and --count.")


def main_fuzz(parser, root, seed, count, out_dir, propagate, json_path=None, strict=False):
    """-> the exit code: 0 whatever the run finds, as ruled (D-415); with strict, 1 when it finds anything, for an
    adapter's own CI step (the owner's ruling of 2026-11-10, D-422). No case verdict moves either way."""
    from .runner import _Guarded
    parser = parser if type(parser) is _Guarded else _Guarded(parser, [])   # every call guarded, as in a run (D-337)
    rep = fuzz_parse(parser, root, seed, count, out_dir)
    prop = fuzz_propagate(parser, root) if propagate else None
    print_report(rep, prop)
    if json_path:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump({"parse": rep, "propagate": prop}, f, indent=1, default=str)
    found = len(rep["findings"]) + len((prop or {}).get("findings", []))
    judged = sum(v for k, v in rep["tally"].items() if k not in ("refused", "unsupported"))
    propagated = prop is not None and "skipped" not in prop
    if not judged and rep["count"]:   # D-459: say so; a refusal is a fine answer, so it is said, never a failure by itself
        print("fuzz: no input was read and compared with the reference "
              + ("(the adapter reads no format)" if not rep["formats"] else "(every input was refused)"))
    if strict and not rep["formats"] and not propagated:
        # nothing to fuzz at all: as `run` exits 2 when it grades nothing (D-389); a reader that refused every input
        # it was given is not this case (a correct strict reader can, on a small --count)
        print("--strict: exit 2, the adapter reads no format and nothing was propagated: nothing was fuzzed")
        return 2
    if strict and found:
        print(f"--strict: exit 1, {qty(found, 'finding')}")
        return 1
    return 0
