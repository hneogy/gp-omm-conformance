# Writing an adapter

This guide is for a maintainer who wants to run the corpus against their own parser and has twenty minutes. It
assumes you know your library and nothing about the corpus.

An adapter is a thin layer between the two. The runner hands it one file at a time, exactly as the provider served
it; the adapter returns what your library read from that file, in the corpus's field names; the runner compares that
with the expected values and reports, case by case, what broke. The adapter decides nothing itself: it reports what
the library does (the last section says why).

If your library is one of the presets, you need no adapter. `python3 -m gpconf presets` lists them: the corpus's own
readers (`reference`), a deliberately naive parser (`naive`), python-sgp4, PyEphem, satellite.js and tle.js. The
presets are adapters of both kinds described here, and they are this guide's examples: every code block below is
copied from a file that ships with the corpus, and says which one.

Commands are shown as `python3 -m gpconf ...`, run from a clone of the repository. Installed from PyPI (from v0.3.0),
the same commands run as `gpconf ...` from any folder.

## Two ways to write one

**A Python class the runner imports** (`--adapter module:Class`). Right when your parser can be called from Python:
a Python library, or one with Python bindings. Values keep their types, so a `datetime` or a `Decimal` arrives as it
is, and a record your library rejects is an exception you catch in a loop.

**A command, for a parser in any other language** (`--cmd`). The runner starts your program once per file, writes the
file to its standard input and reads a JSON array of records from its standard output. Right for JavaScript, C++,
Rust or anything else that can read standard input and print JSON, and for a Python parser you would rather keep out
of the runner's process. JSON has no decimal type: numbers you print as JSON numbers are compared as binary floats,
with a tolerance, and numbers you print as strings are compared exactly.

Both return the same records, both can report a record the library refused, and both can answer the vector hooks.
Use the Python class if you can import your parser; otherwise the command.

## The Python protocol

### What the runner calls

`--adapter module:attribute` imports `module` from the folder you run in (the runner puts it first on `sys.path`) and
takes `attribute` from it: a class is instantiated with no arguments; anything else is used as it is. For each file a
case names, the runner calls `parse(raw, fmt)` on that object, or calls the object itself if it has no `parse`:

- `raw` is the file's bytes, exactly as the provider served them (or, for the corpus's own derived files, as they
  ship);
- `fmt` is one of `tle`, `2le`, `csv`, `json`, `xml` or `kvn`.

`parse` returns a list with one dict per record, keyed by the corpus's field names:

| field | | what the runner expects |
|---|---|---|
| `norad_cat_id` | core | an integer |
| `epoch` | core | a `datetime` (a naive one is read as UTC, an aware one converted to UTC) or a string: calendar or day-of-year form, with or without a fraction, `Z` or an offset |
| `mean_motion` | core | revolutions per day |
| `eccentricity` | core | |
| `inclination`, `ra_of_asc_node`, `arg_of_pericenter`, `mean_anomaly` | core | degrees |
| `bstar` | core | as the TLE and the OMM carry it |
| `mean_motion_dot`, `mean_motion_ddot` | core | as the TLE prints them (rev/day² and rev/day³), which is also how the OMM carries them |
| `object_name`, `object_id`, `classification_type`, `center_name`, `ref_frame`, `time_system`, `mean_element_theory` | optional | strings |
| `ephemeris_type`, `element_set_no`, `rev_at_epoch` | optional | integers |

The element values, `mean_motion` to `mean_motion_ddot`, may be strings, `Decimal`, `int` or `float`. Every core field
must be in every record. An optional field is compared only when you return it: leave it out when your library does
not keep it, rather than inventing a value. Keys the runner does not know are ignored, so you can carry your own for
debugging; the shipped harnesses use keys that begin with `_`, such as `_catalog_field`. Two such keys have a meaning,
`_refused` and `_adapter`, described under [Refusals](#refusals-the-refusal-channel).

For a format your library cannot read, raise `gpconf.runner.Unsupported`. The file is then reported as `skip`, which
in this corpus means exactly that: the parser has no reader for the format.

### Values and tolerances

The expected values are exact decimal strings. A value you return as a string, a `Decimal` or an `int` must match
exactly. A value you return as a `float` passes within a relative 1e-12, and a zero must be an exact zero; an epoch
passes within 2 microseconds. A pass that needed a tolerance is reported as `pass-tolerance`, apart from `pass`, with
the per-field count, mean and maximum difference. The README's
[Tolerances](../README.md#tolerances-and-how-they-are-reported) section gives the reasons.

### What happens when the output is unexpected

| what the adapter does | what the report says |
|---|---|
| raises `Unsupported` | the file is `skip` (`format-supported`) |
| raises anything else | the whole file fails as `parse`: "parser raised" with the exception's type and message |
| returns a value the runner cannot read as a decimal or an epoch (`"fast"`, `"yesterday"`) | the same: the runner's own conversion raises, and the whole file fails as `parse` |
| returns something other than a list of dicts (a dict, say) | the same |
| returns no records for a file the corpus's own reader reads records from | the file fails closed as `records-returned`, and no other check on it runs |
| returns an integer field that is not an integer (`"A0000"`, `100000.5`, `True`) | that record fails, and the report names the value and its type; a catalog number of that kind is counted as misidentified |
| leaves a core field out of a record | that record fails: "core field ... missing from parser output" |
| returns a key the runner does not know | nothing: it is ignored |

### A complete minimal adapter: PyEphem

The PyEphem adapter handles TLEs only, so it is the smallest complete adapter that ships. Here it is whole, below its
docstring.

From [`gpconf/adapters/pyephem_adapter.py`](../gpconf/adapters/pyephem_adapter.py), lines 9 to 55:

```python
import math

try:
    import ephem
except ImportError as e:  # pragma: no cover
    raise ImportError("this adapter needs PyEphem: pip install ephem") from e

from gpconf.runner import Unsupported


def _rec(s, name):
    d = s._epoch.datetime()  # ephem.Date -> naive UTC datetime, microsecond resolution
    return {
        "norad_cat_id": s.catalog_number,
        "object_name": name or None,
        "epoch": d,
        "mean_motion": s._n,
        "eccentricity": s._e,
        "inclination": math.degrees(s._inc),
        "ra_of_asc_node": math.degrees(s._raan),
        "arg_of_pericenter": math.degrees(s._ap),
        "mean_anomaly": math.degrees(s._M),
        "bstar": s._drag,
        "mean_motion_dot": s._decay,
        # mean_motion_ddot: PyEphem keeps no second derivative (no attribute on EarthSatellite); omitted on purpose
        "rev_at_epoch": s._orbit,
        # object_id, classification_type, element_set_no, ephemeris_type: not exposed by PyEphem
    }


class Parser:
    def parse(self, raw, fmt):
        if fmt not in ("tle", "2le"):
            raise Unsupported(fmt)
        lines = raw.decode("utf-8").splitlines()
        out = []
        for i, l in enumerate(lines):
            if l.startswith("1 ") and i + 1 < len(lines) and lines[i + 1].startswith("2 "):
                name = lines[i - 1].strip() if i and not lines[i - 1].startswith(("1 ", "2 ")) else ""
                # readtle() rejects an empty name (db_tle returns -1 when the stripped name is empty), so a
                # name-less 2LE pair gets the catalog field as its name; object_name is then not reported
                call_name = name or l[2:7]
                try:
                    out.append(_rec(ephem.readtle(call_name, l, lines[i + 1]), name))
                except Exception:  # noqa: BLE001 -- the library refused the element set: dropped, as in the hand run
                    pass
        return out
```

- `parse` accepts `tle` and `2le` and raises `Unsupported` for every other format.
- The loop pairs each line 1 with the line 2 after it and takes the line before as the name when it is one. The
  library does the parsing: `ephem.readtle()`.
- `_rec` maps the library's attributes to the corpus's fields and converts radians to degrees. It leaves out what
  PyEphem does not keep, and says so. `mean_motion_ddot` is a core field, so its absence is reported in every values item:
  that is the library's gap, shown rather than hidden behind an invented zero.
- An element set `readtle()` rejects is dropped (`except Exception: pass`). This adapter does not report refusals
  yet, so the runner counts those records as dropped and says that refusals were not reported. The next example
  reports them.

To run it: `pip install ephem`, then `python3 -m gpconf run --preset pyephem`, or the same adapter named directly:
`python3 -m gpconf run --adapter gpconf.adapters.pyephem_adapter:Parser`.

### A real one: python-sgp4

python-sgp4 reads TLE and three OMM formats, writes TLEs, and decodes Alpha-5, so its adapter shows the whole
protocol.

From [`gpconf/adapters/sgp4_adapter.py`](../gpconf/adapters/sgp4_adapter.py), lines 4 to 66:

```python
import io
import json
import math

from gpconf.runner import Unsupported
from gpconf import tle as tlemod

try:
    from sgp4.api import Satrec
    from sgp4 import omm, exporter
    from sgp4.conveniences import sat_epoch_datetime
    from sgp4.alpha5 import from_alpha5, to_alpha5
except ImportError as e:  # pragma: no cover
    raise ImportError("this adapter needs python-sgp4: pip install sgp4") from e

XPDOTP = 1440.0 / (2.0 * math.pi)


def _rec(s, name=None):
    return {"norad_cat_id": s.satnum, "object_name": name, "epoch": sat_epoch_datetime(s),
            "mean_motion": s.no_kozai * XPDOTP, "eccentricity": s.ecco, "inclination": math.degrees(s.inclo),
            "ra_of_asc_node": math.degrees(s.nodeo), "arg_of_pericenter": math.degrees(s.argpo), "mean_anomaly": math.degrees(s.mo),
            "bstar": s.bstar, "mean_motion_dot": s.ndot * XPDOTP * 1440.0, "mean_motion_ddot": s.nddot * XPDOTP * 1440.0 * 1440.0,
            "ephemeris_type": s.ephtype, "classification_type": s.classification, "element_set_no": s.elnum, "rev_at_epoch": s.revnum}


DECLARATION = {"_adapter": {"refusals": True}}  # every record this adapter drops with an error is reported as a refusal (D-144)


class Parser:
    def parse(self, raw, fmt):
        text = raw.decode("utf-8")
        if fmt in ("tle", "2le"):
            lines = text.splitlines()
            out = [DECLARATION]
            for i, l in enumerate(lines):
                if l.startswith("1 ") and i + 1 < len(lines) and lines[i + 1].startswith("2 "):
                    name = lines[i - 1].strip() if i and not lines[i - 1].startswith(("1 ", "2 ")) else None
                    try:
                        out.append(_rec(Satrec.twoline2rv(l, lines[i + 1]), name))
                    except ValueError as e:  # the refusal channel (D-144): the library's own reason, the field as the line carried it
                        out.append({"_refused": f"ValueError: {e}", "_field": l[2:7], "_input": l[:80]})
            return out
        if fmt == "csv":
            fields_iter = omm.parse_csv(io.StringIO(text))
        elif fmt == "xml":
            fields_iter = omm.parse_xml(io.StringIO(text))
        elif fmt == "json":
            fields_iter = json.loads(text)
        else:
            raise Unsupported(fmt)
        out = [DECLARATION]
        for fields in fields_iter:
            s = Satrec()
            try:
                omm.initialize(s, fields)
            except ValueError as e:  # e.g. a nine-digit NORAD_CAT_ID: refused with the library's reason, not dropped (D-144)
                out.append({"_refused": f"ValueError: {e}", "_field": str(fields.get("NORAD_CAT_ID")), "_input": str(fields.get("NORAD_CAT_ID"))})
                continue
            r = _rec(s, fields.get("OBJECT_NAME"))
            r["object_id"] = fields.get("OBJECT_ID") or None
            out.append(r)
        return out
```

- Four formats: TLE and 2LE through `Satrec.twoline2rv`, CSV, XML and JSON through the library's `sgp4.omm` module.
  KVN raises `Unsupported`.
- Units: the library keeps mean motion in radians per minute and angles in radians, and `_rec` converts them to the
  corpus's units (`XPDOTP`, 1440/2π, turns radians per minute into revolutions per day). Converting a unit expresses
  the library's value; it does not change it.
- Refusals: every list begins with `DECLARATION`, and an element set the library rejects becomes a refusal carrying
  the library's own message, the catalog field as the input carried it and the start of the input. The
  [refusal channel](#refusals-the-refusal-channel) section explains each key.

The rest of the file answers the writer case and two of the vector hooks with the library's own functions. From
[`gpconf/adapters/sgp4_adapter.py`](../gpconf/adapters/sgp4_adapter.py), lines 68 to 78:

```python
    def write_tle(self, record):
        # omm.initialize raises ValueError for a catalog number above 339999: the correct answer for the writer case
        s = Satrec()
        omm.initialize(s, tlemod.omm_fields_from_record(record))
        return exporter.export_tle(s)

    def alpha5_decode(self, field):
        return from_alpha5(field)

    def alpha5_encode(self, n):
        return to_alpha5(n)
```

`omm.initialize` raises for a catalog number above 339999, and the writer case counts that as the correct answer,
since the TLE's catalog field cannot carry the number.

To run it: `pip install sgp4`, then

```bash
python3 -m gpconf run --adapter gpconf.adapters.sgp4_adapter:Parser --json report.json
```

## The command protocol

### Parsing

`--cmd` gives a shell command. For each file, the runner replaces `{fmt}` in the command with the file's format (the
only placeholder it substitutes), runs the command, writes the file's bytes to its standard input and reads its
standard output:

- exit 0 and a JSON array: the records, one object per record with the keys above, plus any refusal entries and the
  declaration (see [Refusals](#refusals-the-refusal-channel));
- exit 3: the format is not supported, and the file is reported as `skip`;
- any other exit, output that is not JSON, or JSON that is not an array: the file fails as `parse`, with the last 300
  characters of what the command wrote to standard error.

A command still running after 120 seconds on one file fails that file the same way. Standard error is otherwise not
read, so it is the place for your own notes.

JSON numbers arrive as binary floats and are compared within the float tolerance; print a value as a string to have
it compared exactly. JSON has no NaN: `JSON.stringify` writes `null` in its place, and a `null` catalog number is
counted as a record without one, which hides what the library produced. The tle.js harness prints the string `"NaN"`
instead, so the report names the value and its type.

### A worked example: satellite.js

From [`gpconf/adapters/satellitejs.mjs`](../gpconf/adapters/satellitejs.mjs), lines 8 to 77:

```javascript
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

const target = process.env.GPCONF_NODE_MODULE;
const { twoline2satrec, json2satrec } = await import(target ? pathToFileURL(target).href : 'satellite.js');

const [fmt] = process.argv.slice(1);
const XPDOTP = 1440.0 / (2.0 * Math.PI);   // satellite.js constants.xpdotp
const RAD2DEG = 180.0 / Math.PI;

function isoEpoch(epochyr, epochdays) {
  // the library's own pivot (io.js line 102); day-of-year form with microseconds, from the double the library kept
  const year = epochyr < 57 ? epochyr + 2000 : epochyr + 1900;
  let doy = Math.floor(epochdays);
  let us = Math.round((epochdays - doy) * 86400e6);
  if (us >= 86400e6) { us -= 86400e6; doy += 1; }
  const h = Math.floor(us / 3600e6), m = Math.floor((us % 3600e6) / 60e6), s = Math.floor((us % 60e6) / 1e6), f = us % 1e6;
  const p = (n, w) => String(n).padStart(w, '0');
  return `${year}-${p(doy, 3)}T${p(h, 2)}:${p(m, 2)}:${p(s, 2)}.${p(f, 6)}`;
}

function record(s, name) {
  const raw = s.satnum;                       // a string in this library, never decoded
  // digits -> int (what any consumer must do); anything else (an Alpha-5 field) is passed through as the string the
  // library returns, and the runner reports the value and its type (corpus D-131)
  const id = /^\s*\d+\s*$/.test(raw) ? Number(raw) : raw;
  const mm = s.nokozai ?? s.no_kozai ?? s.no; // the Kozai mean motion as parsed, if the library keeps it apart
  return {
    norad_cat_id: id,
    _catalog_field: raw,
    object_name: name || null,
    epoch: isoEpoch(s.epochyr, s.epochdays),
    mean_motion: mm * XPDOTP,
    eccentricity: s.ecco,
    inclination: s.inclo * RAD2DEG,
    ra_of_asc_node: s.nodeo * RAD2DEG,
    arg_of_pericenter: s.argpo * RAD2DEG,
    mean_anomaly: s.mo * RAD2DEG,
    bstar: s.bstar,
    mean_motion_dot: s.ndot * XPDOTP * 1440.0,
    mean_motion_ddot: s.nddot * XPDOTP * 1440.0 * 1440.0,
    _mm_field: s.nokozai !== undefined ? 'nokozai' : (s.no_kozai !== undefined ? 'no_kozai' : 'no'),
  };
}

const raw = readFileSync(0, 'utf8');
const out = [];
if (fmt === 'tle' || fmt === '2le') {
  const lines = raw.split(/\r?\n/);
  for (let i = 0; i < lines.length; i++) {
    const l = lines[i];
    if (l.startsWith('1 ') && i + 1 < lines.length && lines[i + 1].startsWith('2 ')) {
      const name = i > 0 && !/^[12] /.test(lines[i - 1]) ? lines[i - 1].trim() : '';
      try { out.push(record(twoline2satrec(l, lines[i + 1]), name)); }
      catch (e) { process.stderr.write(`satellite.js refused line ${i + 1}: ${e && e.message}\n`); }
    }
  }
} else if (fmt === 'json') {
  let data;
  try { data = JSON.parse(raw); } catch (e) { process.stderr.write(`not JSON: ${e.message}\n`); process.exit(1); }
  for (const obj of Array.isArray(data) ? data : [data]) {
    try { out.push(record(json2satrec(obj), obj.OBJECT_NAME)); }
    catch (e) { process.stderr.write(`satellite.js refused record ${obj && obj.NORAD_CAT_ID}: ${e && e.message}\n`); }
  }
} else {
  process.exit(3);
}
// NaN and Infinity have no JSON form: JSON.stringify writes null, which the runner reads as "absent"; say so on stderr
for (const r of out) for (const [k, v] of Object.entries(r)) if (typeof v === 'number' && !Number.isFinite(v)) process.stderr.write(`non-finite ${k} for ${r.norad_cat_id}: ${v} -> null\n`);
process.stdout.write(JSON.stringify(out));
```

- It reads the format from its arguments and the file from standard input, prints one JSON array, and exits 3 for
  CSV, XML and KVN.
- It converts units as the python-sgp4 adapter does.
- The catalog number: satellite.js keeps it as a string. The harness turns digits into a number, as any consumer of
  the library must, and passes anything else, an Alpha-5 field, through as the string the library returned. It does
  not decode Alpha-5 itself, so the report shows the string and its type, which is what the library does.
- An element set the library rejects is written to standard error and not returned: this harness does not report
  refusals, so those records count as dropped.

How it runs: the preset `satellite.js` runs `node --input-type=module --eval <this file's source> -- {fmt}` in the
folder you run from, so `import 'satellite.js'` resolves from your project as it would for a script there. The same
run with the preset and as an explicit `--cmd`, from your Node project's folder, with a clone of the corpus at
`$CORPUS`:

```bash
PYTHONPATH="$CORPUS" python3 -m gpconf run --root "$CORPUS" --preset satellite.js
PYTHONPATH="$CORPUS" python3 -m gpconf run --root "$CORPUS" --cmd "node --input-type=module --eval \"\$(cat '$CORPUS/gpconf/adapters/satellitejs.mjs')\" -- {fmt}"
```

A harness of your own is simpler: a file in your project, run as `node your-harness.mjs {fmt}`. It then reads the
format from `process.argv[2]`, because a script run as a file sees its own path at `process.argv[1]`; the shipped
harnesses read `process.argv.slice(1)` because under `--eval` there is no script path.

### Vector hooks by command

`--vectors-cmd` gives a second command, run once per vector. It gets `{"op": "<hook name>", "input": <value>}` on
standard input and prints `{"result": <value>}`, or `{"error": "<reason>"}` to reject the input. A non-zero exit also
counts as a rejection, and so does an answer that carries neither key. `parse_epoch` answers with an ISO string.

Once `--vectors-cmd` is given, the runner asks it for all five hooks: there is no per-hook "unsupported". An operation
your library does not have answers with an error, and its valid vectors then fail rather than skip. tle.js has no TLE
writer, so its `alpha5_encode` answers an error and the `alpha5-encode` item fails. Without `--vectors-cmd`, every
vector item skips.

From [`gpconf/adapters/tlejs_vectors.mjs`](../gpconf/adapters/tlejs_vectors.mjs), lines 8 to 34:

```javascript
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

const target = process.env.GPCONF_NODE_MODULE;
const T = await import(target ? pathToFileURL(target).href : 'tle.js');
const L1 = '1 25544U 98067A   26263.52959654  .00008422  00000+0  15975-3 0  9997';
const L2 = '2 25544  51.6355 213.4302 0003462 300.5590  59.5075 15.49866287 66880';
const withChecksum = (l) => l.slice(0, 68) + String(T.computeChecksum(l));
const { op, input } = JSON.parse(readFileSync(0, 'utf8'));
let r;
try {
  if (op === 'alpha5_decode') {
    const f = String(input).padStart(5, ' ').slice(0, 5);
    const tle = withChecksum(L1.slice(0, 2) + f + L1.slice(7)) + '\n' + withChecksum(L2.slice(0, 2) + f + L2.slice(7));
    const v = T.getCatalogNumber(tle);
    r = { result: Number.isNaN(v) ? 'NaN' : v };
  } else if (op === 'two_digit_year') {
    const yy = String(input).padStart(2, '0');
    const tle = withChecksum(L1.slice(0, 18) + yy + L1.slice(20)) + '\n' + L2;
    r = { result: new Date(T.getEpochTimestamp(tle)).getUTCFullYear() };
  } else if (op === 'alpha5_encode') {
    r = { error: 'tle.js has no TLE writer' };
  } else if (op === 'parse_epoch' || op === 'parse_catalog_id') {
    r = { error: 'tle.js reads TLE lines only; it has no OMM (CSV/JSON/XML/KVN) epoch or catalog-id parser' };
  } else r = { error: `unknown op ${op}` };
} catch (e) { r = { error: `${e.name}: ${e.message}` }; }
process.stdout.write(JSON.stringify(r));
```

Each operation puts the input into a valid line pair, recomputes the checksums with the library's own function and
asks the library's getter, so the answer is the library's. With the tle.js parse harness beside it, from a Node
project with tle.js installed:

```bash
PYTHONPATH="$CORPUS" python3 -m gpconf run --root "$CORPUS" --case alpha5-encoding-vectors --cmd "node --input-type=module --eval \"\$(cat '$CORPUS/gpconf/adapters/tlejs.mjs')\" -- {fmt}" --vectors-cmd "node --input-type=module --eval \"\$(cat '$CORPUS/gpconf/adapters/tlejs_vectors.mjs')\""
```

### Writing TLEs by command

`--write-cmd` gives a command run once per input of the writer case. It gets one JSON object on standard input, the
record `write_tle` would get (see [the vector hooks](#the-vector-hooks)), and prints the two or three TLE lines. Exit
0: written. Exit 3: writing is not supported, and the case skips. Any other exit: the record was refused, which is the
correct answer for a catalog number the TLE field cannot carry. No shipped adapter writes through a command, so there
is no example here; `write_tle` in `sgp4_adapter.py`, above, follows the same contract.

## Refusals: the refusal channel

A library that rejects a record should be heard, not lost. An adapter reports a rejected record by putting, in the
same list as the records, an entry like this one from `gpconf/adapters/sgp4_adapter.py` (line 45):

```python
{"_refused": f"ValueError: {e}", "_field": l[2:7], "_input": l[:80]}
```

- `_refused` (required) is the library's reason, a non-empty string. The runner strips it; an empty reason, or one
  that is not a string, makes the refusal count as a drop, and the file's `refusals` item fails.
- `_field` (optional) is the catalog field exactly as the input carried it. The runner decodes it itself, as digits
  or as Alpha-5 (one letter, then four digits) with the corpus's strict reader, and credits the refusal to that
  expected record. A field of any other form credits the refusal to no record.
- `_input` (optional) is the offending input; the first 80 characters are kept for the report.

The declaration `{"_adapter": {"refusals": true}}`, anywhere in the list (`sgp4_adapter.py` defines it at line 30 and puts
it first in every list it returns),
says that every record you drop with an error is reported. With it, an expected record that comes back as neither a
record nor a refusal is reported as dropped silently. Without it, the report says that refusals were not reported by
this adapter, because zero refusals then means only that none were reported.

Why a reason is required: a refusal without one cannot be told apart from a crash or a record the adapter lost, so it
is no better than a drop and is counted as one. With the reason, a report can say what the library objected to. From
a run of python-sgp4 2.27 on the nine-digit case, the refusals item and the file's result:

```text
  [info] refusals (fixtures/nine-digit-supgp-launch-nominals/raw/starlink-38381-799501621.csv): 1 refused with a reason: "ValueError: satellite number cannot exceed 339999, whose Alpha 5 encoding is 'Z9999'" x1
  [fail] records-returned (fixtures/nine-digit-supgp-launch-nominals/raw/starlink-38381-799501621.csv): parser returned 0 of 1 record(s): 1 refused with a reason (ValueError: satellite number cannot exceed 339999, whose Alpha 5 encoding is 'Z9999')
```

A command reports refusals the same way: the same objects, in its JSON array.

## How your records are counted

Each file's values item carries counts, printed in its detail and written to the JSON report under `counts`:
`expected`, `returned` (records, not refusals), `loaded`, `misidentified`, `dropped`, `non_integer_id`, `refused`,
`refused_matched`, `refused_without_reason`, `refusals_reported` (the declaration) and `top_refusal_reason`.

- **loaded**: an expected record that came back with the expected integer catalog number. Loaded is about identity
  only: the record's values are checked separately, and may still fail.
- **misidentified**: a returned record whose catalog number is missing, not an integer, or not one the file holds:
  0, NaN, a raw string such as `"A0000"`, a wrong number.
- **refused**: a refusal with a reason; **refused_matched** counts those credited to an expected record through
  `_field`, which are not counted as dropped.
- **dropped**: an expected record with no returned record and no refusal credited to it.

A record returned with the wrong catalog number is counted twice, as a misidentified record and as a dropped expected
one: an adapter that returns 0 for every Alpha-5 field of a 256-record file shows 256 misidentified and 256 dropped.

The gate below the case table reads the same counts for its two files and puts them in words: "256 loaded", "256
misidentified", "256 dropped silently", or "(refusals not reported by this adapter)" when the declaration is absent,
"1 refused" with the top reason, and "dropped (the parser raised on the file)". The README's
[gate section](../README.md#the-gate-this-months-launches) describes the headline.

## The vector hooks

The vector case (`alpha5-encoding-vectors`) and the writer case (`tle-writer-alpha5`) do not parse files. They call
optional methods on your adapter instead:

| hook | gets | returns | raise when | item |
|---|---|---|---|---|
| `alpha5_decode(field)` | a catalog field, `str` | the catalog number, `int` | the field is invalid: `I` or `O`, lowercase, a letter after the first place, the wrong length | `alpha5-decode` |
| `alpha5_encode(n)` | a catalog number, `int` | the five-character field | the number cannot be written: 340000, 799501621 and -1 are tried | `alpha5-encode` |
| `two_digit_year(yy)` | a two-digit year, `str` | the four-digit year | never: a raise fails that vector | `two-digit-year-pivot` |
| `parse_epoch(text)` | a CCSDS epoch, `str` | a `datetime`, or an ISO string, compared within 2 microseconds | the text is not a CCSDS epoch (a one-digit month, a space for the `T`, an offset, a TLE epoch) | `ccsds-epoch-strings` |
| `parse_catalog_id(text)` | a `NORAD_CAT_ID` as text | the number, exactly an `int` | the text is not an integer of up to nine digits (`A0000`, ten digits, `25544.0`, empty) | `catalog-number-is-integer` |
| `write_tle(record)` | one record: integers for the catalog number and the counters, decimal strings for the elements, the epoch as an ISO string | two lines, three with a name, or one string holding them | the record cannot be written as a TLE; raise `Unsupported` to skip the case | the writer case |

The writer case reads the lines `write_tle` returns back with the corpus's own reader. They must be two 69-character
lines with valid checksums, with every field in its fixed columns, and with the catalog field as five digits below
100000 and in Alpha-5 from 100000; read back, each element must equal the record at the field's resolution, by
truncation or by rounding half up, since both provider conventions exist. The report says which convention it saw per
field, and reports separately, without failing, how the writer treated the derivatives, the element set number, the
revolution number and the name. For a catalog number the field cannot carry, a refusal is the correct output and
passes.

A hook you leave out is reported as `skip` for its item, never as a failure, and a case whose items all skip reports
`skip`. (By command, see [Vector hooks by command](#vector-hooks-by-command): all five are asked once `--vectors-cmd`
is given.)

The corpus's own readers implement all five vector hooks.

From [`gpconf/adapters/reference.py`](../gpconf/adapters/reference.py), lines 39 to 75:

```python
    def alpha5_decode(self, field):
        if len(field) != 5 or field != field.strip():
            raise ValueError("field must be five characters")
        return tlemod.from_alpha5(field)

    def alpha5_encode(self, n):
        return tlemod.to_alpha5(n)

    def two_digit_year(self, yy):
        return ref.two_digit_year(yy)

    def parse_catalog_id(self, text):
        import re
        s = text.strip()
        if not re.fullmatch(r"\+?\d{1,9}", s):  # CCSDS: integer of up to nine digits; KVN allows a leading sign and zeros
            raise ValueError(f"not a NORAD_CAT_ID: {text!r}")
        return int(s)

    def parse_epoch(self, text):
        import re
        m = re.fullmatch(r"(\d{4})-(?:(\d{2})-(\d{2})|(\d{3}))T(\d{2}):(\d{2}):(\d{2})(\.\d+)?Z?", text)
        if not m:
            raise ValueError(text)
        s = text.rstrip("Z")
        frac = m.group(8) or ""
        base = s[: len(s) - len(frac)]
        fmt = "%Y-%jT%H:%M:%S" if m.group(4) else "%Y-%m-%dT%H:%M:%S"
        try:
            t = dt.datetime.strptime(base, fmt)
        except ValueError:
            if base.endswith(":60"):  # leap second: valid per CCSDS, not representable in datetime
                t = dt.datetime.strptime(base[:-3] + ":59", fmt)
            else:
                raise
        if frac:
            t = t + dt.timedelta(microseconds=int(round(float("0" + frac) * 1e6)))
        return t
```

## Running it

### Fetch the provider data, once

Four cases run from files that ship with the corpus: the Alpha-5 vectors, the derived Alpha-5 lines, the KVN variants
and the writer case. The other thirteen read provider files, which you fetch once:

```bash
python3 tools/fetch.py
```

That is about 60 requests to CelesTrak, 2 seconds apart, each URL once, cached and never repeated; the README's
[Fetching responsibly](../README.md#fetching-responsibly) section has the rules. `python3 tools/fetch.py --dry-run`
lists what it would request without requesting anything. Until the fetch, the thirteen report `not-fetched`.

### Run

```bash
python3 -m gpconf run --adapter gpconf.adapters.reference:Parser --case alpha5-tle-derived --case alpha5-encoding-vectors
```

`--adapter` takes `module:attribute`, found from the folder you run in; `--cmd` and `--preset` take its place for a
command or a preset. `--case ID` and `--tag TAG` select, and repeat; `python3 -m gpconf list` prints the cases and
their tags; `-v` prints every item, not only the failures and the passes within tolerance.

### Read the report

The command above prints:

```text
gpconf 0.2.1 | corpus 0.2.1 | parser: gpconf.adapters.reference:Parser

case                                     status          exact  tol fail skip n/e n/f
alpha5-encoding-vectors                  pass                5    0    0    0   0   0
alpha5-tle-derived                       pass               12    0    0    0   0   0
```

followed by the gate and a count line. The first line names the runner, the corpus and the parser. Each case has one
status, the first of `fail`, `pass-tolerance`, `pass`, `not-exercised`, `not-fetched` and `skip` that any of its items
has, and counts of its items: passed exactly, passed within tolerance, failed, skipped, not exercised (a data check,
or data that did not occur, such as nine-digit ids outside a launch window) and not fetched. Below the table come the
gate over this month's launches, then the failing items and the passes within tolerance, grouped by case, and last
the count line, which says how many cases need fetched data. The exit status is 0 when no case failed, 1 when one did, and 2 when nothing could run: a
preset whose library is missing, or a corpus copy that is incomplete.

### Keep the report: `--json`

`--json FILE` writes all of it. The top level holds `gpconf`, `corpus_version`, `parser` (and `preset` for a preset),
`generated_at`, `results` and `gates`. Each result holds `case`, `title`, `status`, `counts`, `modes` (whether each
file matched the tested snapshot or was compared live), `drift`, `items`, and `reused` when provider files were copied
from an earlier version's cache. Each item holds `check`, `status`, `file` and `detail`; a values item adds `counts`,
the numbers above, and a pass within tolerance adds `tolerance_stats`.

## What not to do

- **No network.** The runner hands your adapter the file. An adapter that fetches its own data tests something else,
  and turns every run into requests to the provider, which the corpus's fetch exists to avoid: it asks CelesTrak for
  each URL once. Nothing the corpus checks needs the network.
- **No writing to the corpus.** The files under `fixtures/`, `derived/` and `vectors/`, and `manifest.json`, are what
  your parser is judged against. The runner checks each provider file's SHA-256 against the manifest, and a changed
  stable-tier file is reported as drift, not as a result. Keep your own notes elsewhere.
- **Report, don't correct.** The adapter's job is to show what the library does. Converting a unit or a type is fine:
  that is the library's value in the corpus's terms, as `sgp4_adapter.py` turns radians into degrees. Deciding for the
  library is not: decoding an Alpha-5 field the library returned as a string, defaulting a field it does not keep,
  retrying a record it rejected, or catching an exception and returning a guess. The shipped adapters show the line:
  `satellitejs.mjs` passes satellite.js's undecoded catalog string through, `pyephem_adapter.py` leaves out the second
  derivative PyEphem does not keep, and `sgp4_adapter.py` passes on the library's own refusal message. A result is
  worth having only if it is the library's.
