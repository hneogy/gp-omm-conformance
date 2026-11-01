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
| `epoch` | core | a `datetime` (a naive one is read as UTC, an aware one converted to UTC) or a string your parser built: calendar or day-of-year form, with or without a fraction, `Z` or an offset. Never the input's own epoch text handed back: a string that is not in the calendar form `YYYY-MM-DDThh:mm:ss[.f]` and stands in the file as you return it fails the record's `values` (D-306) |
| `mean_motion` | core | revolutions per day |
| `eccentricity` | core | |
| `inclination`, `ra_of_asc_node`, `arg_of_pericenter`, `mean_anomaly` | core | degrees |
| `bstar` | core | as the TLE and the OMM carry it |
| `mean_motion_dot`, `mean_motion_ddot` | core | as the TLE prints them (rev/day² and rev/day³), which is also how the OMM carries them |
| `object_name`, `object_id`, `classification_type`, `center_name`, `ref_frame`, `time_system`, `mean_element_theory` | optional | strings |
| `ephemeris_type`, `element_set_no`, `rev_at_epoch` | optional | integers |

The element values, `mean_motion` to `mean_motion_ddot`, may be strings, `Decimal`, `int` or `float`. Every core field
must be in every record. An optional field is compared only when you return it: leave it out when your library does
not keep it, rather than inventing a value. `object_name` is compared without the blanks that end it, in every format,
so a name returned as a TLE name line holds it, padded to 24 columns, passes (D-369). Keys the runner does not know are ignored, so you can carry your own for
debugging; the shipped harnesses use keys that begin with `_`, such as `_catalog_field`. Two such keys have a meaning,
`_refused` and `_adapter`, described under [Refusals](#refusals-the-refusal-channel), and three are the runner's own,
`_notes`, `_bad` and `_record`, which it sets on records it reads: a key of yours by any of those names is dropped
(D-337, D-343).

For a format your library cannot read, raise `gpconf.runner.Unsupported`. The file is then reported as `skip`. A skip
says that the parser answered unsupported for that format everywhere in this run: the runner compares the answer with
every other read of the same format in the run and fails a mix, but it cannot tell a missing reader from a hidden
one, so a skip is the adapter's claim, reported and counted, never verified (D-312). From
v0.7.0 an outcome that is not a graded pass or fail (a skip, an `Unsupported`, a refusal, extra or duplicate
records) is either all-or-none for its whole scope or graded and counted; there are no partial skips (D-280, the
owner's rule after the audit of issue #1). Concretely: a format is unsupported for all of a run's inputs or none,
so an adapter that parses some files of a format and raises `Unsupported` on others fails those files instead of
skipping them, in the same case or another one of the same run.

### Values and tolerances

The expected values are exact decimal strings. A value you return as a string, a `Decimal` or an `int` must match
exactly. A string must be a plain decimal number: an optional sign, ASCII digits with an optional point, an optional
exponent, and nothing before or after it. Padding, an underscore between digits and the digits of another script are
not numbers here, though Python's `Decimal()` would read them; such text is a value the runner cannot read, and the
file fails as `parse` (D-319). A NaN or an infinity, as a `float` or a `Decimal`, is not a value either, and fails the file the same way; an infinite catalog number or counter fails as not an integer (D-325). An epoch string is held to ASCII digits in the same way, with nothing around it: whitespace before or after the epoch fails the file as `parse` (D-325). A value you return as a `float` passes within a relative 1e-12, and a zero must be an exact zero; an epoch
passes within 2 microseconds. A pass that needed a tolerance is reported as `pass-tolerance`, apart from `pass`, with
the per-field count, mean and maximum difference. The README's
[Tolerances](../README.md#tolerances-and-how-they-are-reported) section gives the reasons.

### What the runner reads, and what it trusts

gpconf grades wrong answers. A Python adapter runs in the runner's own process and returns Python objects, and an
object's own methods (`__eq__`, `__str__`, `strip()`, `keys()`, `strftime()`) would decide what a check sees whenever
the runner called them. So it calls none of them after your call has returned: inside the same guard that catches an
exit, everything you return is read once into plain built-in values, and every check works on those (D-337). A
subclass of `str`, `int`, `float`, `bytes` or `Decimal` is the value it holds, read past any method of its own; a
`datetime` is built again from its fields, and a timezone of your own becomes the fixed offset it gives; numpy's
integers are ints; numpy's floats, `float32` and `float16` included, are compared as the values they hold, not as the
short text they print, so a `float32` mean motion fails where its eight decimals do not survive the type; a
`datetime.timezone` is built again from the offset and name it holds; a `deque`, a `UserList` and a dict's
`keys()`, `values()` or `items()`, and any subclass of `deque`, `set` or `frozenset`, are read through their iteration
(a set's or a keys or items view's in an order of its own), each as a list, and a `UserString` as the text it holds; an integer longer than Python will write in decimal (its
own limit, `sys.get_int_max_str_digits()`, or 4,300 digits where the limit is off) is a marker text, which fails where a
number is read; in an integer field, a nonzero `Decimal` with that many digits before its point fails in words
too, and in an element field a `Decimal` is compared as the value it is. An exception your code raises or holds,
whose text is Python's own, keeps Python's words when what they read is plain (texts, numbers, classes, and plain
lists, tuples, dicts, sets and deques of them, no part met twice, no deeper than 32); otherwise it is written from the
plain reading of its arguments, so an argument that is an `Enum` member, an `OrderedDict` or an object of yours reads
as that reading (`{'a': 1}` for the `OrderedDict`; the others as the rule below writes them), not as Python writes it
(`<Mode.A: 1>`, `OrderedDict(...)`), and an
`OSError` or `SyntaxError` whose parts are not plain is written as its arguments, any other part Python's writing
reads (an `OSError`'s file name) named after them. Any other
object is its `str()`, made once in a reading however many records hold it, when the writing is your code or a
library's: your class's own `__str__` or `__repr__`, or a third-party library's, compiled or not (lxml's elements,
numpy's arrays and scalars), taking as long as it takes. An object whose writing is Python's own (a builtin or
standard-library type's, or a standard-library function's) and which holds any object besides its class, or more than
a megabyte itself, is never printed: that writing may walk what it holds as a tree, past any budget, so it is written
as its type's name, `<SimpleNamespace object>`, `<slice object>`, an `Enum` member as its class's name (`<Color
object>`), `<UUID object>`, `<Fraction object>`, `<ZoneInfo object>` on Python 3.10 and later, `<array object>` for a
large array (the owner's ruling, D-337). One that holds nothing and is small is Python's writing as before (a
`complex`, a `time`, a `range`, a small array, and a `ZoneInfo` on Python 3.9, where it shows nothing held). The fields
the checks read hold numbers, texts and epochs, and a container with a face is read through it, so no verdict moves by
the rule for any value a library is known to return there; a field no check reads loses detail; and a `Fraction`, or a
`ZoneInfo` on Python 3.10 and later, in a field a check reads is named, and fails where Python's writing (`"0"`,
`"UTC"`) would have read: stated limits. An object whose own code changes what it holds while it is read is written
as first met, and one whose writing raises is the parser's raise: stated limits. A list, tuple or dict in a record's
own field, or in a hook's answer or a written line, is handed on as its text: Python's writing of what was read (so
numpy's `float64(1.5)` is written `1.5`, and an object of your own its `str()`, quoted), up to 1,000 characters, and
past that the first 1,000 with a digest of all it holds, so that two containers that differ never read alike and the
checks write and compare no more than that. That text is the runner's own kind of text, never equal to a text your
parser returned that spells the same: a field that is `[5]` in one answer and `"[5]"` in another differs. Each
container, and each long text, bytes or `Decimal` inside one, is written and digested once in a reading, however many
fields or records share it, and a long subclass of `str`, `bytes` or `Decimal` (numpy's `str_` among them) is copied
once. The `_adapter` declaration (see [Refusals](#refusals-the-refusal-channel)) stays a mapping, and a key the runner
does not know is handed on as it was read and never written out. No check reads a container in a field: the fields
the checks read are numbers, texts and epochs. The reading has a budget for each answer (a `parse()` answer, a hook's
answer, a writer's answer, an exception, an exit code): ten million objects visited and a billion bytes copied,
hashed or written. Past either, the answer fails in words, "too large or too deeply shared to read" (the file as
`parse`; a hook's answer or a written record as its own item), rather than read without end; the largest reading in
the sixteen published runs and GPKit's visited 467,926 objects and copied, hashed or wrote none (D-337). The budget is
for each answer, not for a run: the writer case asks for 753 answers, so a writer whose every answer runs to the
budget takes that many times as long, and an in-process parser has no time limit of its own (a command has 120 seconds
a call). And a long text is read once, but the checks then hold and compare it in every record that carries it, so a
text of a megabyte in each of 750 records cost seconds and half a gigabyte, and one of many megabytes far more: stated
limits, for 0.8.1 (D-370). An iterable that never
ends is read up to the budget before it fails, holding what it has read until then (records of 17 fields: 8 s and
3.3 GB), a stated limit. An exception held inside another, in its arguments or its attributes, is worded once at each
depth it is met, and one that holds itself as a marker; when an exception is written from its arguments, each part's
text is cut at 1,000 characters with a digest of the whole, while Python's own words, where kept, are kept whole. An
`ExceptionGroup` is told by its type and keeps Python's words, its message and how many exceptions it holds. A container or a record
that holds one thing and shows another has no one answer, and fails the file in words: a `list` or `tuple` subclass
whose own iteration shows other entries than it holds (an answer's records may come in any order), and a `dict`
subclass whose own `keys()` and `[]` show other fields or values than it holds. Any other container is read through
one face, iteration for an answer's records and a writer's lines, `keys()` and `[]` for a record, and is graded by it:
its other faces (a mapping's `items()` or `get()`, a list's `[]` or `len()`) are not graded, so a container whose
other faces disagree with the one read is graded by the one read. That is a stated limit (D-337): storage is compared
only for a `dict`, `list` or `tuple` subclass; every other container, a `deque` or `UserList` subclass among them, is
graded by the face the runner reads. A transparent proxy (wrapt's `ObjectProxy`, lazy-object-proxy), which says
through `__class__` that it is what it wraps, is read as a record, an integer (any `numbers.Integral`), a datetime or
a date when it says it is one, through its own methods only: what a subclass behind it holds is not compared, a number
behind it other than an integer is its text, a text key behind it is no key, a text reason behind it is no refusal
reason, and a text block behind it from `write_tle` is read as an iterable. These are stated limits, by the owner's
ruling (D-337): no library hands back a proxied string, and the proxy rule stays with records, integers and datetimes.
A field a record lists twice with one value is one field; with two values the file fails. A record type whose `[]`, or
a list subclass whose own iteration, hands back equal copies of a container that holds a record on the path being read
is judged two-faced, a stated limit (D-337). A face is read before what is held, so a container that fills itself when
first read is judged full. A refusal's reason is text or it is none (see [Refusals](#refusals-the-refusal-channel)).
`write_tle` may answer a list or a tuple of lines, one text block, bytes, or any other iterable of lines. What your
code raises or exits with while it is read is yours, as from inside `parse()`.

The model, in the owner's words: "gpconf grades wrong answers. Any wrong value that survives conversion to plain
values is an escape and gets fixed. An in-process adapter that attacks the runner itself (patching it, reading
expected values, etc.) is out of scope — in-process adapters are trusted not to do that; untrusted parsers use
--cmd." A parser behind `--cmd` (below) cannot patch the runner or hand it objects: its answer is JSON, plain by
construction, and an exit is its own process's. It is not a sandbox: it runs as you, where you run gpconf, and could
read the expected values from disk, so the same trust applies to what it does there. A parser that may end its process
with `os._exit()`, which no in-process guard can stop, belongs behind `--cmd` too; a Ctrl-C, `KeyboardInterrupt`, is
the user's and ends the run.

### What happens when the output is unexpected

| what the adapter does | what the report says |
|---|---|
| raises `Unsupported` | the file is `skip` (`format-supported`) — unless this parser read another file of the same format in this run, which makes the skip a `fail` (D-280). A stated limit: in the corrupt-input case a raise on a whole corrupt input is not counted as reading its format, so a parser that raises on the cut CSV input and declares the CSV comparison file unsupported is not graded on CSV in a run without fetched data, and one that raises on all four TLE inputs and declares the TLE comparison file unsupported is not graded on TLE in a run that reads no other TLE file (`--case corrupt-input` alone); a run with fetched data reads other files of the format and catches either, and the whole no-data run catches the TLE form, since its other cases read TLE files, and not the CSV form (the owner's ruling, D-341; D-342) |
| raises anything else | the whole file fails as `parse`: "parser raised" with the exception's type and message (in the corrupt-input case a raise on a corrupt input is the file refused as a whole, and a raise on an unedited comparison file fails it as `parse`, D-339) |
| raises anything else from a hook's lookup (a property) or another place no check takes it | the case fails as `parser-raised`, in the exception's name and words (D-337) |
| ends the process (`sys.exit()`, or another exception that is not an `Exception`), in `parse()`, in a hook, in a property, or in a method of an object it returned while its answer is read (a value's `__str__`) | the case fails as `parser-exit`, the run goes on, and the run's exit status says a case failed (D-293, D-337). `os._exit()` and `KeyboardInterrupt` are not contained: see above |
| returns a value the runner cannot read as a decimal or an epoch (`"fast"`, `"yesterday"`, `" 15.49"`, `"15.49_32"`, `float("nan")`) | the whole file fails as `parse`: "the parser returned a value the runner cannot read", with the field and the value (D-325) |
| returns something other than an iterable of records (a dict, say, or strings) | the file fails as `parse` (in the corrupt-input case, under the input's own check; for the provider's empty answer, under `empty-answer-yields-no-records`): "the parser returned a value the runner cannot read: the answer is dict, not a list of records", or "… holds str at entry 1 …" (D-330, D-334). A list, a tuple, a generator or any other iterable of mappings is read, in full, when the parser returns it: a generator's body, a list subclass's own iteration and a mapping's own `keys()` and `[]` run then, so what they raise or exit with is the parser's. Each record is read into a plain dict of plain values (see above); a key that is not text is ignored, as any unknown key is. A container or a record whose faces disagree fails the file in those words (see above), and so does a record that holds one field twice with two values (D-337) |
| returns no records for a file the corpus's own reader reads records from | the file fails closed as `records-returned`, and no other check on it runs |
| returns more copies of a catalog number than the file holds | the record fails in the values item (D-311); in the pairs, facts and XML cases, which have no values item, the file fails as `records-returned`, in the same words, "id 25544: returned 2 times where the input holds it once (D-311)", and its other checks run (D-346) |
| returns a record under a catalog number the file does not hold, or with none | the values item fails it ("1 unexpected record id", "1 record without norad_cat_id"), the record counted misidentified, in a file whose frozen values cover part of it too (D-349); in the pairs, facts and XML cases the file fails as `records-returned`, in the same words, the second where the file's own records all carry a catalog number (D-348); and the TLE/OMM consistency check and `mmdot-is-tle-field-value` fail where the two files share a catalog number and no pair forms |
| returns an integer field that is not an integer (`"A0000"`, `100000.5`, `True`) | that record fails, and the report names the value and its type; a catalog number of that kind is counted as misidentified; on the KVN variant whose NORAD_CAT_ID keyword is left out, such a value, or an empty text, for one of the integer keywords it leaves out fails the record as a value where the keyword is absent (D-358) |
| leaves a core field out of a record | that record fails: "core field ... missing from parser output"; in the TLE/OMM consistency check and `mmdot-is-tle-field-value` a key left out is read as None, on either side, and a field every TLE carries (the mean motion, the angles and the epoch in the consistency check, the first derivative in `mmdot-is-tle-field-value`) left out or None fails the pair (D-358) |
| returns a key the runner does not know | nothing: it is ignored (a key named `_notes`, `_bad` or `_record` is dropped: those are the runner's own) |
| returns an answer too large or too deeply shared to read (an iterable that never ends; a structure whose reading passes ten million objects or a billion bytes) | the file fails as `parse`: "the answer was too large or too deeply shared to read", never a hang (D-337) |

### A complete minimal adapter: PyEphem

The PyEphem adapter handles TLEs only, so it is the smallest complete adapter that ships. Here it is whole, below its
docstring.

From [`gpconf/adapters/pyephem_adapter.py`](../gpconf/adapters/pyephem_adapter.py), lines 13 to 63:

```python
import math
from typing import Any

try:
    import ephem
except ImportError as e:  # pragma: no cover
    raise ImportError("this adapter needs PyEphem: pip install ephem") from e

from gpconf.runner import Unsupported

DECLARATION: dict[str, Any] = {"_adapter": {"refusals": True}}  # every element set readtle() refuses is reported as a refusal (D-144)


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
        out = [DECLARATION]
        for i, l in enumerate(lines):
            if l.startswith("1 "):  # with whatever line follows, a line 2 or not: the library answers (D-183)
                l2 = lines[i + 1] if i + 1 < len(lines) else ""
                name = lines[i - 1].strip() if i and not lines[i - 1].startswith(("1 ", "2 ")) else ""
                # readtle() rejects an empty name (db_tle returns -1 when the stripped name is empty), so a
                # name-less 2LE pair gets the catalog field as its name; object_name is then not reported
                call_name = name or l[2:7]
                try:
                    out.append(_rec(ephem.readtle(call_name, l, l2), name))
                except Exception as e:  # noqa: BLE001 -- the refusal channel (D-144): the library's own reason, the field as the line carried it
                    out.append({"_refused": f"{type(e).__name__}: {e}", "_field": l[2:7], "_input": l[:80]})
        return out
```

- `parse` accepts `tle` and `2le` and raises `Unsupported` for every other format.
- The loop hands each line 1 to the library with the line after it, whatever that line is, and takes the line before
  as the name when it is one. The library does the parsing: `ephem.readtle()`.
- `_rec` maps the library's attributes to the corpus's fields and converts radians to degrees. It leaves out what
  PyEphem does not keep, and says so. `mean_motion_ddot` is a core field, so its absence is reported in every values item:
  that is the library's gap, shown rather than hidden behind an invented zero.
- An element set `readtle()` rejects comes back as a refusal: the library's exception as the reason and the catalog
  field as the line carried it (see [Refusals](#refusals-the-refusal-channel)). The list begins with `DECLARATION`,
  which tells the runner that this adapter reports refusals, so a record it neither returns nor refuses counts as
  dropped silently.
- PyEphem reads one element set at a time, so the adapter splits the file, and it does not check that a line 2 follows:
  a line 1 with no line 2 after it reaches `readtle()` with the next line, and PyEphem's answer is what the report
  shows. Do the same in your own adapter if your library takes one set at a time: filtering the pairs by their prefixes
  first would measure your adapter's pairing instead of the library (D-183).

To run it: `pip install ephem`, then `python3 -m gpconf run --preset pyephem`, or the same adapter named directly:
`python3 -m gpconf run --adapter gpconf.adapters.pyephem_adapter:Parser`.

### A real one: python-sgp4

python-sgp4 reads TLE and three OMM formats, writes TLEs, and decodes Alpha-5, so its adapter shows the whole
protocol.

From [`gpconf/adapters/sgp4_adapter.py`](../gpconf/adapters/sgp4_adapter.py), lines 6 to 70:

```python
import io
import json
import math
from typing import Any

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


DECLARATION: dict[str, Any] = {"_adapter": {"refusals": True}}  # every record this adapter drops with an error is reported as a refusal (D-144)


class Parser:
    def parse(self, raw, fmt):
        text = raw.decode("utf-8")
        if fmt in ("tle", "2le"):
            lines = text.splitlines()
            out = [DECLARATION]
            for i, l in enumerate(lines):
                if l.startswith("1 "):  # with whatever line follows, a line 2 or not: the library answers (D-183)
                    l2 = lines[i + 1] if i + 1 < len(lines) else ""
                    name = lines[i - 1].strip() if i and not lines[i - 1].startswith(("1 ", "2 ")) else None
                    try:
                        out.append(_rec(Satrec.twoline2rv(l, l2), name))
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
[`gpconf/adapters/sgp4_adapter.py`](../gpconf/adapters/sgp4_adapter.py), lines 72 to 82:

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
  declaration (see [Refusals](#refusals-the-refusal-channel)); a UTF-8 byte-order mark before the array is read past,
  any other text before it fails the file (D-369), as before the lines a `--write-cmd` prints (where `check-tle`, which
  reads a file as a TLE reader would, still fails a file that begins with one);
- exit 3: the format is not supported, and the file is reported as `skip`;
- any other exit: the file fails as `parse`, with the last 300 characters of what the command wrote to standard
  error (in the corrupt-input case, on a corrupt input, it is that file refused as a whole, as a raise is);
- an end by a signal, a crash: the file fails as `parse`, "the parser's command was ended by signal 11 (SIGSEGV)", and
  a crash is never a refusal, so on a corrupt input it fails that input's check (D-341). From a shell command, an exit
  of 128 plus the number of SIGSEGV, SIGBUS, SIGABRT, SIGILL, SIGFPE, SIGTRAP, SIGSYS, SIGKILL, SIGXCPU or SIGXFSZ is
  how a shell reports that signal, and is read as it: refuse with exit 1, never with one of those (139, 134, 137, 152
  and 153 among them); any other exit is the "any other exit" above. An uncaught exception that ends the process by a
  signal is a crash too (C++'s `std::terminate` and a Zig panic call `abort()`; Swift's `fatalError` traps): catch
  your library's errors and exit 1. Stated limits: a crash the command does not report (an earlier command of a
  pipeline, a `|| true`, a wrapper that turns its child's signal into a plain exit) reads as what the command did
  report; behind a shell that does not exec the harness, an end by any other signal (SIGTERM, SIGINT, SIGHUP, SIGQUIT,
  SIGPIPE, SIGALRM, SIGUSR1 and SIGUSR2 among them) reads as that exit, an answer; and on Windows, which has no
  signals, a crash is its exit code (an `abort()` there exits 3, which reads as unsupported for `--cmd` and
  `--write-cmd` and as a rejection for `--vectors-cmd`, and a POSIX shell run inside `--cmd`, Git Bash, MSYS2, Cygwin
  or WSL, reports its child's signal as an exit like 139, which reads as an answer there), so this rule is POSIX's. A
  Python adapter that runs a `gpconf.runner.CommandParser` keeps its command's crash a crash when it passes it on
  unchanged, or when it is a `CommandParser` subclass; a copy of the crash raised by any other wrapper is that
  wrapper's raise (D-342);
- output that is not JSON: the file fails as `parse`, with the first 120 characters of the output;
- JSON that is not an array of objects: the file fails as `parse` (in the corrupt-input case under the input's own
  check; for the provider's empty answer under `empty-answer-yields-no-records`), "the parser returned a value the
  runner cannot read", saying what came instead, as for a Python adapter (D-334, D-337).

A command still running after 120 seconds on one file is killed (behind a shell, only the shell is, and its own
children may run on), and that is a crash, as above: the file fails as `parse`, and on a corrupt input it fails that
input's check (D-341). Standard error is otherwise not read, so it is the place for your own notes.

JSON numbers arrive as binary floats and are compared within the float tolerance; print a value as a string to have
it compared exactly. JSON has no NaN: `JSON.stringify` writes `null` in its place, and a `null` catalog number is
counted as a record without one, which hides what the library produced. The tle.js harness prints the string `"NaN"`
instead, so the report names the value and its type.

### A worked example: satellite.js

From [`gpconf/adapters/satellitejs.mjs`](../gpconf/adapters/satellitejs.mjs), lines 10 to 84:

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
    // a NaN year or day (a field that is not wholly numeric, from 7.1.0's successor on) has no epoch: null, noted below
    epoch: Number.isFinite(s.epochyr) && Number.isFinite(s.epochdays) ? isoEpoch(s.epochyr, s.epochdays) : null,
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
    if (l.startsWith('1 ')) {   // with whatever line follows, a line 2 or not: the library answers (D-183)
      const l2 = i + 1 < lines.length ? lines[i + 1] : '';
      const name = i > 0 && !/^[12] /.test(lines[i - 1]) ? lines[i - 1].trim() : '';
      try { out.push(record(twoline2satrec(l, l2), name)); }
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
for (const r of out) {
  if (r.epoch === null) process.stderr.write(`non-finite epoch for ${r.norad_cat_id}\n`);
  for (const [k, v] of Object.entries(r)) if (typeof v === 'number' && !Number.isFinite(v)) process.stderr.write(`non-finite ${k} for ${r.norad_cat_id}\n`);
}
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
standard input and prints `{"result": <value>}`, `{"error": "<reason>"}` to reject the input, or, from corpus 0.5.0,
`{"unsupported": "<reason>"}` for an operation your library does not have, which skips that hook's item with the
reason, as the item skips for a Python adapter without the hook; an operation answers unsupported for all of its
vectors or for none, and a mix fails the item. A non-zero exit counts as a rejection, exit 3 included (the vectors
protocol never gave it the meaning the parse and write commands do), and so does an answer that carries none of the
three keys. An end by a signal, or a command still running after 120 seconds, is a crash and never a rejection: the
vector fails, read as for `--cmd` (D-341). `parse_epoch` answers with an ISO string, which the runner converts; the vector's own text sent back as it came, where that is not already the calendar form, is a rejection (D-306). A Python adapter's hook raises `gpconf.runner.Unsupported` for
the same effect.

Once `--vectors-cmd` is given, the runner asks it for all five hooks. tle.js has no TLE writer and no OMM parser, so
its harness answers unsupported for `alpha5_encode`, `parse_epoch` and `parse_catalog_id`, and those three items skip
with the reason; before 0.5.0 there was no such answer, and an operation the library did not have answered an error,
which failed its valid vectors. Without `--vectors-cmd`, every vector item skips.

From [`gpconf/adapters/tlejs_vectors.mjs`](../gpconf/adapters/tlejs_vectors.mjs), lines 10 to 36:

```javascript
// it (D-154). GPCONF_NODE_MODULE, set by `--module PATH`, names the library's entry file instead.
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
    r = { unsupported: 'tle.js has no TLE writer' };
  } else if (op === 'parse_epoch' || op === 'parse_catalog_id') {
    r = { unsupported: 'tle.js reads TLE lines only; it has no OMM (CSV/JSON/XML/KVN) epoch or catalog-id parser' };
  } else r = { error: `unknown op ${op}` };
} catch (e) { r = { error: `${e.name}: ${e.message}` }; }
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
correct answer for a catalog number the TLE field cannot carry; an end by a signal, or a command still running after
120 seconds, is a crash and never a refusal, and that record fails, read as for `--cmd` (D-341). No shipped adapter writes through a command, so there
is no example here; `write_tle` in `sgp4_adapter.py`, above, follows the same contract.

## Refusals: the refusal channel

A library that rejects a record should be heard, not lost. An adapter reports a rejected record by putting, in the
same list as the records, an entry like this one from `gpconf/adapters/sgp4_adapter.py` (line 49):

```python
{"_refused": f"ValueError: {e}", "_field": l[2:7], "_input": l[:80]}
```

- `_refused` (required) is the library's reason, a non-empty string. The runner strips it; an empty reason, or one
  that is not a string, makes the refusal count as no refusal (it credits no record), and the file's `refusals` item
  fails (D-356).
- `_field` (optional) is the catalog field exactly as the input carried it. The runner decodes it itself, as digits
  or as Alpha-5 (one letter, then four digits) with the corpus's strict reader, and credits the refusal to that
  expected record. A field of any other form credits the refusal to no record (in the corrupt-input case, a field that
  is the invalid catalog field the edit introduced credits the corrupt record, D-360).
- `_input` (optional) is the offending input; the first 80 characters are kept for the report.

The declaration `{"_adapter": {"refusals": true}}`, anywhere in the list (`sgp4_adapter.py` defines it at line 33 and puts
it first in every list it returns),
says that every record you drop with an error is reported. With it, an expected record that comes back as neither a
record nor a refusal is reported as dropped silently. Without it, the report says that refusals were not reported by
this adapter, because zero refusals then means only that none were reported.

Why a reason is required: a refusal without one cannot be told apart from a crash or a record the adapter lost, so it is
no better than a drop and counts as no refusal, crediting no record (D-356). With the reason, a report can say what the
library objected to. From a run of python-sgp4 2.27 on the nine-digit case, the refusals item and the file's result:

```text
  [info] refusals (fixtures/nine-digit-supgp-launch-nominals/raw/starlink-38381-799501621.csv): 1 refused with a reason: "ValueError: satellite number cannot exceed 339999, whose Alpha 5 encoding is 'Z9999'" x1
  [fail] records-returned (fixtures/nine-digit-supgp-launch-nominals/raw/starlink-38381-799501621.csv): parser returned 0 of 1 record: 1 refused with a reason (ValueError: satellite number cannot exceed 339999, whose Alpha 5 encoding is 'Z9999')
```

A command reports refusals the same way: the same objects, in its JSON array.

## How your records are counted

Each file's values item carries counts, printed in its detail and written to the JSON report under `counts`:
`expected`, `returned` (records, not refusals), `loaded`, `misidentified`, `dropped`, `extra`, `ids_not_returned`,
`non_integer_id`, `refused`, `refused_matched`, `refused_without_reason`, `refusals_reported` (the declaration) and
`top_refusal_reason`. They count records, not catalog numbers: where the input holds an id more than once, each of its
records is an expected record of its own, and a refusal with a reason credits one of them (D-344); `ids_not_returned`
alone counts ids. In the values item the records without a catalog number count as one, as before, and
`ids_not_returned` counts them as one id in both items. On the corpus's KVN variant whose NORAD_CAT_ID keyword is left
out (`v05-omm-3.0-header-optional-keywords-omitted.kvn`, the id exempt), the records without one that are graded as
its expected record are loaded, not also counted misidentified, and a copy beyond the file's one is a duplicate copy,
as on a file that carries its id; a record whose id is not an integer is misidentified, and counted neither loaded nor
a duplicate copy, and where only such records came back, the file's record counts in `ids_not_returned` (D-357). Any
other file's records without an id are misidentified, as below.

- **loaded**: an expected record that came back with the expected integer catalog number (on the exempt KVN variant
  above, also without one, D-357). Loaded is about identity only: the record's values are checked separately, and may
  still fail.
- **misidentified**: a returned record whose catalog number is missing (but on the exempt KVN variant above, D-357),
  not an integer, or not one the file holds: 0, NaN, a raw string such as `"A0000"`, a wrong number. Where the frozen
  values cover part of a file (the nine-digit ids of `starlink-all.csv`), its other records are the file's own and in
  no count but `returned`; a copy beyond the file's own is counted in `extra` and `duplicate_copies`, as anywhere, and
  one of them that comes back neither as a record nor as a refusal with a reason that names it (its `_field`) fails
  the values item; their values are not compared (D-349).
- **refused**: a refusal with a reason; **refused_matched** counts those credited to an expected record through
  `_field`, which are not counted as dropped.
- **dropped**: an expected record with no returned record and no refusal credited to it, and no misidentified record
  standing in for it: the expected count less loaded, refused_matched and misidentified, never below 0.
- **ids_not_returned**: the expected ids no record came back under, whatever came back under other ids; the count
  `dropped` carried before corpus 0.5.0, kept so that nothing is lost.
- **extra**: records beyond the expected ones — misidentified records left unaccounted for, and, from v0.7.0,
  every surplus copy of an expected record, or of a partly frozen file's record outside the compared subset (D-349)
  (`duplicate_copies` carries the copy count on its own). A record
  fails when the parser returns more copies of its id than the input holds, exact copies included, and a copy
  that disagrees with the input's record it is compared with fails its record too (D-311, which reverses the second
  half of D-281, inside D-194's one-outcome-per-expected-record rule: the record keeps one outcome, however many
  copies came back, and every copy is compared). Where the input itself holds an id more than once (a live file can),
  each copy is compared with the input's record it matches, and the item says so where those records differ (D-343);
  before, every copy was compared with the last of them. A copy is paired first with the one record of its element set
  number and revolution when it fails nothing against it; the rest at least cost, exhaustively up to seven of each and,
  up to 10,000 copy-and-record pairs, by a pairing that fails nothing wherever one exists; beyond that, copies and
  records are paired in epoch order, a stated limit: where two of those records share an epoch, or lie within the
  tolerance of each other, and differ, a correct parser that returns them in another order can fail; a wrong parser
  never passes. Fewer copies than the input holds fail too, "returned once where the input holds it 2 times" (D-344):
  each record of the id is an expected record. The pivot, TLE/OMM consistency, OMM-formats-agree and presence checks
  read every copy of such an id: the pivot check matches each record's epoch with a returned copy of its own; the
  consistency and OMM-formats-agree checks pair one file's copies with another's by element set number and revolution
  where a copy gives both, or else nearest in epoch, and compare every copy, one beyond the other file's copies too; a
  presence check passes a record when a copy of its id answers for it. An id the input holds once is read as before,
  by its last copy (its first in each file, for OMM-formats-agree), however many copies come back (D-344). Where one
  file of a set holds an element set of such an id that the other file lacks, the two files disagree, and the
  consistency check fails for every parser, the reference adapter included.

One outcome per expected record (corpus 0.5.0, D-207): loaded, misidentified, refused_matched and dropped sum to the
expected count plus `extra`, less `duplicate_copies` (the surplus copies of expected records, and of a partly frozen
file's other records, which `extra` counts too from v0.7.0). A record returned with the wrong catalog number is counted once, as misidentified, and
stands in for one expected record: an adapter that returns 0 for every Alpha-5 field of a 256-record file shows 256
misidentified, 0 dropped and 256 ids_not_returned. Before 0.5.0 such a record was also counted as a dropped expected
one, and the same file showed 256 dropped as well.

The gate below the case table reads the same counts for its two files and puts them in words: "256 loaded", "256
misidentified", "256 dropped silently", or "(refusals not reported by this adapter)" when the declaration is absent,
"1 misidentified, 255 dropped silently" for one record returned under a wrong id and nothing for the rest, "1 refused"
with the top reason, and "dropped (the parser raised on the file)", or "dropped (the runner could not read a value the parser returned)" (D-325). The README's
[gate section](../README.md#the-gate-this-months-launches) describes the headline.

## The vector hooks

The vector case (`alpha5-encoding-vectors`) and the writer case (`tle-writer-alpha5`) do not parse files. They call
optional methods on your adapter instead:

| hook | gets | returns | raise when | item |
|---|---|---|---|---|
| `alpha5_decode(field)` | a catalog field, `str` | the catalog number, `int` | the field is invalid: `I` or `O`, lowercase, a letter after the first place, the wrong length | `alpha5-decode` |
| `alpha5_encode(n)` | a catalog number, `int` | the five-character field | the number cannot be written: 340000, 799501621 and -1 are tried | `alpha5-encode` |
| `two_digit_year(yy)` | a two-digit year, `str` | the four-digit year | never: a raise fails that vector | `two-digit-year-pivot` |
| `parse_epoch(text)` | a CCSDS epoch, `str` | a `datetime`, compared within 2 microseconds; a string fails the item, since the runner would be the one parsing it (D-306) | the text is not a CCSDS epoch (a one-digit month, a space for the `T`, an offset, a TLE epoch) | `ccsds-epoch-strings` |
| `parse_catalog_id(text)` | a `NORAD_CAT_ID` as text | the number, exactly an `int` | the text is not an integer of up to nine digits (`A0000`, ten digits, `25544.0`, empty) | `catalog-number-is-integer` |
| `write_tle(record)` | one record: integers for the catalog number and the counters, decimal strings for the elements, the epoch as an ISO string | two lines, three with a name, or one string holding them (a list, a tuple, bytes or any other iterable of lines will do, D-337); line 1 and line 2 in ASCII, as the format is (a name line may hold any characters) (D-325) | a record the TLE format cannot carry is refused with an exception; `Unsupported` must be the answer for every record or for none: a mix fails, and what was written stays graded (D-280). For every record, the case skips; that the library writes no TLE is the adapter's claim, which the runner reports and does not verify (D-312) | the writer case |

Any of the five vector hooks may raise `gpconf.runner.Unsupported` for an operation your library does not have; the
item then skips with the reason, provided every vector of that hook gets the same answer (D-205). The runner checks
that sameness and nothing more: that the operation is absent is the adapter's claim (D-312). `write_tle`
follows the same rule from v0.7.0.

Three more things the grader holds from v0.7.0, each found by the adversarial audit (issue #1; `tests/adversarial/`):
the catalog number and the counters (`ephemeris_type`, `element_set_no`, `rev_at_epoch`) must be `int` — a float or
a string that converts cleanly is reported with its value and type (D-131) and fails (D-283); a field with expected
values that your parser never returns shows in the case result as a visible gap (`fields-not-returned`,
not-exercised), and one returned for some records and omitted for others fails (D-284); where a format carries no
value for `center_name`, `ref_frame`, `time_system` or `mean_element_theory`, the runner accepts `None` or the OMM
constant defaults (`EARTH`, `TEME`, `UTC`, `SGP4`/`SGP/SGP4`) and fails anything else (D-285). In the corrupt-input
case a refusal credits the corrupt record only on evidence — a `_field` that decodes to it, an `_input` quoting text
the edit introduced (for a cut, an `_input` quoting the cut site), or a `_field` that is the catalog field of an element
line the edit introduced (an invalid catalog field decodes to no record, so that `_field` is the evidence, D-360); a
refusal that names no record credits none, as this document has always said (D-282).

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

From [`gpconf/adapters/reference.py`](../gpconf/adapters/reference.py), lines 45 to 87:

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
        if not re.fullmatch(r"\+?\d{1,9}", s, re.ASCII):  # ASCII digits (D-325); CCSDS: integer of up to nine digits; KVN allows a leading sign and zeros
            raise ValueError(f"not a NORAD_CAT_ID: {text!r}")
        return int(s)

    def parse_epoch(self, text):
        import re
        m = re.fullmatch(r"(\d{4})-(?:(\d{2})-(\d{2})|(\d{3}))T(\d{2}):(\d{2}):(\d{2})(\.\d+)?Z?", text, re.ASCII)
        if not m:
            raise ValueError(text)
        if m.group(4):
            # strptime's %j takes 366 in any year and returns the next year's 1 January (D-325); 001 to 365, or 366 in a leap year
            year, doy = int(m.group(1)), int(m.group(4))
            leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
            if not 1 <= doy <= (366 if leap else 365):
                raise ValueError(f"day of year {doy} is outside {year}: {text!r}")
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

Five cases run from files that ship with the corpus: the Alpha-5 vectors, the derived Alpha-5 lines, the KVN variants,
the writer case and the corrupt-input case. Twelve of the other thirteen read provider files, which you fetch once;
the thirteenth, `supgp-celestrak-classification-c`, reads a launch-window capture that no fetch requests, and reports
`not-available` (D-229):

```bash
python3 tools/fetch.py
```

That is 46 requests to CelesTrak, one at a time, each URL once, kept on disk and not requested again; the README's
[Fetching responsibly](../README.md#fetching-responsibly) section says what CelesTrak asks and what the fetch does.
The 9.4 MB legacy SATCAT file is not among them: one data check reads it and no parser, so the fetch brings it only
with `--include-satcat`, and without it `satcat-70000-cutoff` reports `not-exercised`, as it does with it (D-231,
D-232). `python3 tools/fetch.py --dry-run`
lists what it would request without requesting anything. Until the fetch, eleven of the twelve report `not-fetched`;
the twelfth is the SATCAT data check.

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
gpconf 0.8.0 | corpus 0.8.0 | parser: gpconf.adapters.reference:Parser

case                                     status          exact  tol fail skip n/e n/f n/a
alpha5-encoding-vectors                  pass                5    0    0    0   0   0   0
alpha5-tle-derived                       pass               18    0    0    0   0   0   0
```

followed by the gate and a count line. The first line names the runner, the corpus and the parser. Each case has one
status, the first of `fail`, `pass-tolerance`, `pass`, `not-exercised`, `not-fetched`, `not-available` and `skip` that
any of its items has, and counts of its items: passed exactly, passed within tolerance, failed, skipped, not exercised
(a data check, or data that did not occur, such as nine-digit ids outside a launch window), not fetched, and not
available (a launch-window capture, which no fetch requests, D-229). Below the table come the
gate over this month's launches, then the failing items and the passes within tolerance, grouped by case, and last
the count line, which says how many cases need fetched data and how many cannot run from a fetch.

A status does not say everything, and from v0.7.0 the run says the rest (D-312). A case that did not skip as a whole
but holds an item that skipped, or a file in which a field with expected values was never returned, carries that in
its status cell: `pass (1 item skipped)`, `pass (5 field gaps)`, `pass (1 item skipped, 2 field gaps)`. The status,
the counts and the exit status are what they were; the words in brackets are what the status leaves out. Under the
count line a sentence totals them across the run, and when cases were not graded for lack of provider data a line
says how many were: `5 of 18 cases graded offline; not a full conformance result.` A run on the five cases that
ship is a run on five cases. The exit status is 0 when no case failed, 1 when one did, and 2 when nothing could run: a
preset whose library is missing, a corpus copy that is incomplete, or a `--json` path that cannot be written; a report
that cannot be written after the run is 2 as well (D-370).

An item names the file it read or, for a check across the files of a set, the set: `iss-live`. The checks that
compare a set's TLE records with its OMM records (the TLE/OMM consistency check, `mmdot-is-tle-field-value` and the
two count checks) read each TLE file of the set, its `.tle` and its `.2le`, in items of their own, the first named
after the set and each other after the set and the file, `iss-live: iss.2le`, each compared with the first OMM file of
the set that the parser read; the OMM files are compared with one another by `omm-formats-agree` (D-345). A recapture,
a second fetch of the TLE answer made later, is not compared with the OMM records, which may be of an earlier time
(no set lists one as its first TLE file); it is graded on its own. A parser that declines one of `tle` and `2le` has
its set compared by the member it reads. Where a TLE file and the OMM file share a catalog number and no record of one
pairs with a record of the other, the TLE/OMM consistency check and `mmdot-is-tle-field-value` fail: they compared
nothing (D-348). `mmdot-is-tle-field-value` holds both OMM derivatives to the TLE fields: MEAN_MOTION_DOT as printed,
MEAN_MOTION_DDOT to the field's five rounded digits (D-358); MEAN_MOTION_DOT is that item's alone, the consistency
check leaving it out.

### Keep the report: `--json`

`--json FILE` writes all of it. A script should read this report or the exit status, never the printed lines, whose
wording can change from one version to the next (D-240). The top level holds `gpconf`, `corpus_version`, `parser` (and
`preset` for a preset), `generated_at`, `summary`, `inside_cases`, `results` and `gates`. `inside_cases`, from 0.7.0, holds
`items_skipped`, `field_gaps` and `cases_graded` for the run, and a result that has either of the first two carries them
as `annotations`. `summary`, from 0.6.0, holds the case totals
as numbers:
`cases`, the number of cases run, and one count for each status a case can end in, `pass`, `pass-tolerance`, `fail`,
`skip`, `not-fetched`, `not-available` and `not-exercised`, zeros included; they are the numbers of the count line and
they add up to `cases`. Each result holds `case`, `title`, `status`, `counts`, `modes` (whether each
file matched the tested snapshot or was compared live), `drift`, `items`, `reused` when provider files were copied
from an earlier version's cache, and `unexpected` when the fetch kept a response it did not expect for one of the
case's files (D-228), with `in_place` true where an earlier fetch saved that response in the data's place (D-351). Each item holds `check`, `status`, `file` and `detail`; a values item adds `counts`,
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
