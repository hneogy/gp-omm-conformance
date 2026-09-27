# corrupt-input

Corrupt input between valid records: a wrong checksum digit, a line one character short, a letter in a numeric field, a set missing its second line, a file cut mid-record

## Evidence basis

- Corrupt provider output cannot be captured on demand, so the inputs are made, under the D-096 precedent for synthetic-derived provenance (PLAN.md section 2.1 reserves it for owner approval): the owner approved these five inputs on 2026-09-27 (DECISIONS D-171). Each is a real record frozen in this corpus with one stated edit, placed between valid real records; each file's provenance record (derived/corrupt-input/*.provenance.json) names the records, the files their values were frozen from with those files' SHA-256, and the edit.
- Every record is rendered by the corpus from values in this corpus's public expected.json files (tools/derive_corrupt_inputs.py reads no provider file). The TLE lines use the renderer that reproduces CelesTrak's lines for 304 of 304 records, checked here against each record's frozen TLE fields, so the unedited lines equal CelesTrak's own; the CSV and JSON follow CelesTrak's column order and line endings and write the frozen values in plain decimal notation.
- Owner decisions of 2026-09-25 (v0.4.0 plan, section 10) applied here: a parser that validates no checksum is reported, not failed, since the corpus's own reference reader treats the checksum as data (decision 2); a whole-file refusal of a cut file passes, with the complete records it gives up counted (decision 3); the shifted-column input is held (decision 4).
- The outcomes are counted in the vocabulary of D-142 and D-144: loaded (returned with its id and exactly the values the same parser returns for it from the unedited file), misidentified (a record built from garbage: returned with other values than from the unedited file, or with an id the file does not hold), refused (with a reason, through the refusal channel or by the parser raising on the file) and dropped (neither).
- Every record a parser returns from an input is compared with the same parser's reading of the matching unedited file (derived/corrupt-input/unedited-*: the same records laid out as the input lays them out, with no edit), exactly, so the case measures what the edit changes (D-175). Comparing with the frozen expected values, as the case first did, graded how exactly a parser reads these records a second time: a parser that reads them imprecisely everywhere failed the neighbours item in every file whatever it did with the corrupt input. That is the values check's question, asked of the same records in epoch-year-19xx and bstar-and-derivative-forms. Where a parser does not return a record from the unedited file either, the items that would rest on it are not exercised: nothing then isolates the edit.

## What it tests

- corrupt-input
- fail-closed
- resynchronisation

## How to read a failure

Each file hands the parser one corrupt input between valid records. The right answer is a refusal with a reason: for that record, through the refusal channel (docs/ADAPTERS.md), with the records around it still loaded; or, for the file cut mid-record only, a refusal of the whole file, which is fail-closed (the complete records it gives up are counted, not failed). A record built from a corrupt input fails as misidentified, and so does a silent drop. Every record the parser returns is compared, exactly, with what the same parser returns from the input's unedited file (derived/corrupt-input/unedited-*: the same records with no edit), so the case grades what the edit changes and not how exactly the parser reads these records, which the values check grades in the records' own cases (DECISIONS D-175); a record the parser does not return from the unedited file either is not graded. A parser that raises on a whole TLE file for one bad set fails corrupt-input-neighbours-load, since the valid sets around it are lost with it. Line 2 one character short has lost a digit mid-line, so a parser that reads fixed columns without checking the length reads every field after the cut one column off and builds a record from garbage. The one exception is the wrong checksum digit: a parser that validates no checksum reads the set as the record it carries, and the case reports that ('validates no checksum') rather than failing it, because the corpus's own reference reader treats the checksum as data (owner decision, DECISIONS D-171). The inputs are synthetic-derived: real records frozen in this corpus, each with one stated edit (derived/corrupt-input/*.provenance.json); the shifted CSV column the plan also listed is held.

## Checks

- **corrupt-tle-checksum-digit** — A TLE set whose line 1 carries a wrong checksum digit, every other character real, is refused with a reason. A parser that validates no checksum returns the set exactly as it returns it from the unedited file: that is reported, not failed, since the corpus's own reference reader treats the checksum as data (owner decision, D-171). A record that differs from that reading fails, as does a silent drop.
- **corrupt-tle-line-short** — A TLE set whose line 2 has lost one character mid-line (a digit of the eccentricity), so that it is 68 characters and every column after the cut has moved one to the left, is refused with a reason. A record read from it fails as misidentified, since its values are not the set's, and so does a silent drop.
- **corrupt-tle-letter-in-number** — A TLE set with the letter O in place of a 0 in line 1's epoch field is refused with a reason, not read as a record with a wrong epoch and not dropped silently. The line's checksum is still valid, since a letter counts 0 as the digit it replaced did, so the checksum cannot catch it.
- **corrupt-tle-missing-line-2** — A TLE set whose line 1 is followed directly by the next set's name line: the orphan line 1 is refused with a reason. Passing over it without a word counts as dropped, and pairing it with the lines after it builds a record from garbage.
- **corrupt-file-cut** — A file cut mid-record, as a CSV that ends inside its last row and as a JSON array missing its closing bracket: the complete records load and the cut is reported with a reason, or the file is refused as a whole with a reason, which is fail-closed; the complete records a whole-file refusal gives up are counted, not failed (owner decision, D-171). Loading the complete records while saying nothing of the cut is silent partial loading and fails, as does a record read from the cut row.
- **corrupt-input-neighbours-load** — The valid records around each corrupt input load exactly as the same parser reads them from the unedited file: the corrupt input changes nothing about them, so the parser picks up again after it. How exactly a parser reads these records is not graded here, since the values check grades it on the same records in their own cases (D-175). A parser that refuses a whole TLE file for one bad set gives up the valid sets with it and fails here; for a file cut mid-record, the complete records a whole-file refusal gives up are reported, not failed.

## Coverage

Provides:

- five corrupt inputs, each one stated edit of 69999's first record (a stable-tier record): line 1's checksum digit changed from 6 to 1; line 2 one character short, the eccentricity's fourth digit (column 30) lost so that every column after it moves left; the letter O for the 0 in column 26 of line 1, inside the epoch field, the checksum still valid; line 1 with no line 2 after it; the file cut mid-record, as a CSV that ends inside its last row's MEAN_MOTION_DOT value and as a JSON array whose closing bracket is missing
- each TLE input between two valid sets, 25544's first record before it and 20453 from the decaying snapshot after it, so that the counts on the neighbours measure whether a parser picks up again; the CSV holds the same two records before the cut row, the JSON all three records complete
- no provider file: every record rendered by the corpus from values frozen in this corpus's public expected.json files, a public clone rebuilding the same bytes
- three unedited files, the inputs' records with no edit (one TLE file for inputs 1 to 4, the CSV with its last row whole, the JSON array closed), against which every record a parser returns from an input is compared (D-175)

Gaps (stated explicitly for this case):

- the shifted CSV column (the plan's input 6) is held, not included (owner decision 4, D-171)
- one edit per input, on one record: a parser is characterised only for what is edited here (line 1's checksum digit, line 2's length, a letter in the epoch field, a missing line 2, the end of a CSV or JSON file); a letter in another numeric column, a wrong checksum on line 2 or a line cut elsewhere is not exercised
- no corrupt KVN, XML or 2LE input
- a line cut short at its end, which loses only the checksum digit and leaves every value readable, is not an input: a parser that accepts it reads the right values, and accepting a malformed line whose values survive is what the wrong checksum digit already shows (D-171)
- any non-empty reason counts as a refusal's reason; whether it names the right defect is not checked

## Library behaviour observed

- python-sgp4 2.27 through the built-in adapter (run 2026-09-27; its three failing items in docs/FAILURES.md): the fast Satrec.twoline2rv, the C++ extension, reads line 2 one character short and the epoch field with a letter in it without an error, building records with an eccentricity of 0.148004 for 0.1487004 and a revolution number of 189308 for 18930, and with an epoch of day 189.7 for 189.70990935 and BSTAR and the first derivative 0; the pure-Python sgp4.io.twoline2rv raises ValueError on both lines. The split is documented and by design: the maintainer does not add checks to the C++ code (python-sgp4 #116, 2023), and python-sgp4's README section "Double-checking your TLE lines" tells users to validate with the slow twoline2rv. The orphan line 1 is passed over by the adapter's own line pairing, since python-sgp4 reads one set at a time, and the cut CSV row stops omm.initialize with a TypeError, which refuses the whole file, a pass under owner decision 3 (DECISIONS D-171, D-173).

## Ambiguities recorded

- none

## Sources

Every file of this case ships with the repository; nothing is fetched.

| file | tier | HTTP | bytes | retrieved (UTC) | sha256 |
|---|---|---|---|---|---|
| `derived/corrupt-input/c1-checksum-digit.tle` | stable | none: derived file shipped with the repository | 504 | generated 2026-09-27T06:48:07Z | `7917ac5e69fa2d2a…` |
| `derived/corrupt-input/c2-line-2-short.tle` | stable | none: derived file shipped with the repository | 503 | generated 2026-09-27T06:48:07Z | `08771a837aeb57b0…` |
| `derived/corrupt-input/c3-letter-in-epoch.tle` | stable | none: derived file shipped with the repository | 504 | generated 2026-09-27T06:48:07Z | `8103d578599f1322…` |
| `derived/corrupt-input/c4-line-2-missing.tle` | stable | none: derived file shipped with the repository | 433 | generated 2026-09-27T06:48:07Z | `9ad3679e9be32faf…` |
| `derived/corrupt-input/c5-cut-last-row.csv` | stable | none: derived file shipped with the repository | 692 | generated 2026-09-27T06:48:07Z | `c1cdfc2530b0dc13…` |
| `derived/corrupt-input/c5-cut-closing-bracket.json` | stable | none: derived file shipped with the repository | 1278 | generated 2026-09-27T06:48:07Z | `6d711e2b69fd9fd8…` |
| `derived/corrupt-input/unedited-sets.tle` | stable | none: derived file shipped with the repository | 504 | generated 2026-09-27T15:12:19Z | `6d53b5f62556841e…` |
| `derived/corrupt-input/unedited-rows.csv` | stable | none: derived file shipped with the repository | 698 | generated 2026-09-27T15:12:19Z | `5c0ee080f1312fb6…` |
| `derived/corrupt-input/unedited-array.json` | stable | none: derived file shipped with the repository | 1281 | generated 2026-09-27T15:12:19Z | `54e8a8e19244f296…` |

Expected values: `fixtures/corrupt-input/expected.json` (schema_version 1.0).
