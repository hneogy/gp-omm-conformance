"""Gates (D-142): headlines read across existing cases, computed from the structured counts behind values items.

A gate answers one operational question over one snapshot, per format the parser reads, in words that name the
behaviour rather than grade the project. The first gate: given this month's launches as a provider serves them, does
the parser return them with the right identity? Its inputs already exist as case files: the CelesTrak CSV capture of
the last-30-days group (every object above 99999) and the corpus's Alpha-5 rendering of the same records, the form
Space-Track's TLE output carries. CelesTrak's own TLE output omits these objects (HTTP 404 for the group), a fact the
CSV case records; the gate says so for a parser that reads TLE only.

Per record and format there are four outcomes: loaded (returned with the expected integer id), misidentified
(returned with an id that is absent, not an integer, or not the expected one: 0, NaN, a raw string), refused (the
adapter reported the record with a reason through the refusal channel, D-144) and dropped (no record and no refusal).
An adapter that declares the channel makes "dropped" mean "dropped silently"; without the declaration the gate says
"refusals not reported by this adapter", since zero refusals then means only that none were reported. Every result carries the snapshot's date, its
record count and id range, and the letters its Alpha-5 fields begin with, because a decoder that is wrong from J upward
passes a snapshot whose ids all begin with A.
"""
import json
import os

from .tle import to_alpha5

GATES = [
    {
        "id": "last-30-days",
        "name": "this month's launches",
        "question": "given the objects launched in the last 30 days, as a provider serves them, does the parser return them with the right identity?",
        "formats": {
            "tle": {"case": "alpha5-tle-derived", "file": "derived/alpha5-tle/alpha5-A-last-30-days-snapshot.tle",
                    "label": "TLE (Alpha-5, as Space-Track serves them; rendered by the corpus from the CelesTrak CSV capture)"},
            "csv": {"case": "tle-omits-six-digit-objects", "file": "fixtures/tle-omits-six-digit-objects/raw/last-30-days.csv",
                    "label": "CSV (as CelesTrak serves them)"},
        },
        "snapshot_from": {"case": "tle-omits-six-digit-objects", "meta": "fixtures/tle-omits-six-digit-objects/raw/last-30-days.csv.meta.json"},
        "feed_fact": "CelesTrak's TLE feed omits these objects (the group's TLE request answers HTTP 404, 'No GP data found'), so a TLE-only parser on that feed has nothing to load",
    },
]


def snapshot_facts(root, gate):
    """Date, count, id range and leading letters of the gate's snapshot, read from the case data, never hard-coded."""
    exp = json.load(open(os.path.join(root, "fixtures", gate["snapshot_from"]["case"], "expected.json")))
    ids = sorted(int(r["norad_cat_id"]) for r in exp["records"])
    date = None
    meta = os.path.join(root, gate["snapshot_from"]["meta"])
    if os.path.exists(meta):
        date = json.load(open(meta)).get("retrieved_at")
    date = (date or exp.get("generated_at") or "")[:10]
    letters = sorted({to_alpha5(i)[0] for i in ids if i >= 100000})
    return {"date": date, "count": len(ids), "id_min": ids[0], "id_max": ids[-1], "alpha5_letters": letters}


def format_result(items):
    """One format's outcome from the items the runner recorded for its file."""
    for it in items:
        if it.check in ("values", "records-returned") and it.counts is not None:
            c = it.counts
            return {"state": "measured", "expected": c["expected"], "returned": c["returned"], "loaded": c["loaded"],
                    "misidentified": c["misidentified"], "dropped": c["dropped"], "refused": c.get("refused_matched", 0),
                    "refusals_reported": c.get("refusals_reported"), "top_refusal_reason": c.get("top_refusal_reason")}
    for it in items:
        if it.check == "parse" and it.status == "fail":
            return {"state": "measured", "note": "the parser raised on the file", "expected": None, "returned": 0, "loaded": 0, "misidentified": 0, "dropped": None}
    for it in items:
        if it.check == "format-supported" and it.status == "skip":
            return {"state": "not read"}
        if it.check == "source-present" and it.status == "skip":
            return {"state": "file absent"}
    return {"state": "not run"}


def _numbers(r, expected):
    if r.get("note"):
        return f"{expected} dropped ({r['note']})"
    parts = []
    for k in ("loaded", "misidentified"):
        if r.get(k):
            parts.append(f"{r[k]} {k}")
    if r.get("refused"):
        parts.append(f"{r['refused']} refused" + (f" ({r['top_refusal_reason'][:80]})" if r.get("top_refusal_reason") else ""))
    if r.get("dropped"):
        parts.append(f"{r['dropped']} dropped " + ("silently" if r.get("refusals_reported") else "(refusals not reported by this adapter)"))
    return ", ".join(parts) if parts else "0 returned"


def headline(formats, gate, snap):
    """Words that name the behaviour: 'reads this month's launches', 'only via CSV', 'not in any format it reads',
    'nothing to load from this feed'. Never a grade."""
    n = snap["count"]
    labels = {f: gate["formats"][f]["label"] for f in gate["formats"]}
    measured = {f: r for f, r in formats.items() if r["state"] == "measured"}
    unmeasured = {f: r["state"] for f, r in formats.items() if r["state"] != "measured"}
    full = [f for f, r in measured.items() if r["loaded"] == n]
    if not measured:
        text = "not measured: " + "; ".join(f"{labels[f]}: {st}" for f, st in unmeasured.items())
    elif len(full) == len(measured):
        text = f"reads {gate['name']} in every format it reads here: " + ", ".join(f"{labels[f]}: {n} loaded" for f in full)
    elif full:
        text = "only via " + " and ".join(f.upper() for f in full) + ": " + "; ".join(
            f"{labels[f]}: {_numbers(r, n)}" for f, r in measured.items())
    else:
        text = "not in any format it reads: " + "; ".join(f"{labels[f]}: {_numbers(r, n)}" for f, r in measured.items())
        if list(measured) == ["tle"]:
            text = f"nothing to load from this feed: {gate['feed_fact']}; as Space-Track serves them (Alpha-5): {_numbers(measured['tle'], n)}"
    if unmeasured and measured:
        text += "; " + "; ".join(f"{labels[f]}: {st}" for f, st in unmeasured.items())
    letters = ", ".join(snap["alpha5_letters"]) or "none"
    text += (f" [snapshot {snap['date']}, {n} objects, ids {snap['id_min']}-{snap['id_max']}, Alpha-5 fields beginning with {letters}: "
             f"a decoder wrong from J upward is not caught by this snapshot]")
    return text


def compute_gates(results, root):
    """Gate results from a run's CaseResults; a gate whose cases were not run says so."""
    by_case = {r.case_id: r for r in results}
    out = []
    for gate in GATES:
        snap = snapshot_facts(root, gate)
        formats = {}
        for fmt, spec in gate["formats"].items():
            res = by_case.get(spec["case"])
            items = [i for i in (res.items if res else []) if i.file == spec["file"]]
            formats[fmt] = {"label": spec["label"], **({"state": "not run"} if res is None else format_result(items))}
        out.append({"id": gate["id"], "name": gate["name"], "question": gate["question"], "snapshot": snap,
                    "formats": formats, "headline": headline({f: r for f, r in formats.items()}, gate, snap)})
    return out
