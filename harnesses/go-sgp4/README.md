# akhenakh/sgp4 (Go)

| | |
|---|---|
| tested at | built and run in the corpus's private scratch CI on 2026-11-10 (Ubuntu 24.04, offline cases only): first in run 42831534654, then in its present form, with the harness fixes that run led to (corpus D-439), in run 42847814047 (corpus D-440); never on the machine that wrote it. Moved to `v1.0.4` (`b2e5162d8b5e5e78717891786ce6a7614785b60f`), pinned in `go.mod`, with the `alpha5_decode` and `alpha5_encode` ops and the writer (corpus D-451, after D-445): those three are [untested] until the scratch CI builds them. Written 2026-11-10 for `v1.0.2` (`06ae3b63682a4432b2941d7a038b8f1b93d368dc`) from its source read on GitHub, on a machine with no Go toolchain; the corpus's scratch CI is to build and run it first [untested] |
| licence of the code | Apache-2.0 (the repository's); nothing of it is copied here |
| hooks (D-451) | answers: parse (TLE, 2LE, OMM JSON, OMM CSV), alpha5_decode, alpha5_encode, propagate, write; unsupported: two_digit_year, parse_epoch, parse_catalog_id |
| what the harness calls | `ParseTLELines` (TLE, 2LE), `ParseOMMs` (OMM JSON), `ParseOMMsCSV` (OMM CSV), `(*TLE).EpochTime`, `(*TLE).FindPosition(tsince)`, `ParseAlpha5`, `FormatAlpha5`, and for the writer `(*OMM).ToTLE` and `(*TLE).TLEString` |
| toolchain | Go 1.23 or later (the module is fetched by `go mod tidy`) |
| published result | none; its findings were reported as https://github.com/akhenakh/sgp4/issues/16, fixed in v1.0.3 and v1.0.4 |

Best-effort, not installable by pip. Chosen for Go (0.9.0 item b4) because the most used Go SGP4 library,
joshuaferrara/go-satellite (BSD-2-Clause), is not gradable: no exported parsed fields, whole-second propagation only;
akhenakh/sgp4 exports its `TLE` and `OMM` fields and propagates by minutes since epoch. A field whose unit is not the one read here would build and report wrong values, with nothing to
say so, so its first run is read against the library's source before any count is kept. Its findings were reported as
akhenakh/sgp4#16 (Alpha-5 refused, type 4 propagated), fixed in v1.0.3 and v1.0.4 (corpus D-444, D-445).

**The recipe rule (D-445, D-451):** when a library gains a writer or an encoder, its recipe exposes it before the
library's row is re-run. At v1.0.2 this harness answered `alpha5_encode` unsupported and had no `--write-cmd`, because
the library had neither; v1.0.3 added `FormatAlpha5` and `TLELines`, whose ceiling bug (109999 for 339999) the run of
D-444 could not see. `tests/test_harnesses.py` holds every recipe's README to its `hooks` row.

```
cd harnesses/go-sgp4 && go mod tidy && go build -o gpconf-go-sgp4 . && cd ../..
python3 -m gpconf run --cmd "harnesses/go-sgp4/gpconf-go-sgp4 parse {fmt}" --vectors-cmd "harnesses/go-sgp4/gpconf-go-sgp4 vectors" --write-cmd "harnesses/go-sgp4/gpconf-go-sgp4 write"
```

What it returns, as the library holds it: from a TLE, the catalog number, the name, the epoch from `EpochTime()`,
the elements in degrees and rev/day, BSTAR, the two derivatives, classification, element set and revolution numbers;
a set `ParseTLELines` refuses goes back through the refusal channel. From an OMM, the `OMM` struct's fields, the
epoch as the file's text (the library keeps it as `EpochStr`; gpconf reads a calendar-form string, D-306). XML and
KVN answer unsupported (exit 3). `propagate` runs `FindPosition` and maps the library's errors to Vallado's codes
(decay 6; eccentricity limits 1; the perturbed eccentricity 3; the semi-latus rectum 4; any other 99, the library's
"deep-space orbit not supported" among them) [inferred, untested].
`alpha5_decode` and `alpha5_encode` answer through `ParseAlpha5` and `FormatAlpha5`, a refusal as `{"error": ...}` with
the library's reason. `write` builds the library's `OMM` from the writer case's record (decimal strings read with
`strconv.ParseFloat`, the counters as integers, the epoch as its ISO text), converts it with `(*OMM).ToTLE` and prints
`(*TLE).TLEString()`: the name line and lines 1 and 2, or the two lines without a name; a record the library refuses
(a catalog number above 339999 among them) exits 1 with its reason [untested until the scratch CI builds it].
