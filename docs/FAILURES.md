# Parser breakage catalogue

What actually breaks when a parser written for five-digit TLEs meets today's data. Every entry
below is a runner result (`python -m gpconf run`) against the corpus, not a hypothetical. Three
parsers were run:

- **reference** — the corpus's own readers (`tests/adapters/reference.py`); the control.
- **naive** — the parser most projects have (`tests/adapters/naive.py`): `int()` on five
  columns, one epoch format, classification assumed `U`, every column assumed present, KVN as
  strict `KEY = value`. Written deliberately with those shortcuts.
- **python-sgp4** — `tests/adapters/sgp4_adapter.py`, exposing python-sgp4 2.27 as-is (TLE via
  `twoline2rv`, CSV/XML/JSON via `sgp4.omm`; no KVN reader).

A failure here is a statement about the parser, not about the corpus: the reference parser
passes every case that exercises a parser; `satcat-70000-cutoff` is a data check the runner makes itself and
reports as not exercised for every parser, on a file the fetch brings only on request (D-231). Draft upstream reports for the python-sgp4 findings are in `docs/upstream/`.
The Alpha-5 letters I and O that python-sgp4's compiled `Satrec` writes, in the writer case below, are reported as
[brandon-rhodes/python-sgp4#173](https://github.com/brandon-rhodes/python-sgp4/issues/173) (filed 2026-10-10, D-307).

All three columns come from one run, on the platform named below the intro, graded on the public export, the corpus as
published, which leaves out the SupGP expected values (D-049), from the 0.9.0 re-measure's fresh fetch (2026-11-11).
The corpus's ten operator-sourced launch-window captures are excluded (D-002), as a new user's fetch cannot obtain
them either (D-229), so these figures are fetch-only, and `supgp-celestrak-classification-c`, which reads only those
captures, reports `not-available`, where with the captures it is a pass for the reference and a fail for naive. Of 21
cases, the reference passes 16, the naive adapter fails 13 and python-sgp4 fails 7. With the ten captures, 0.9.0's
recorded measurement (D-489, on the re-measure's fresh fetch with the ten captures copied in, not this run) was: the
reference passes 17 and the naive adapter fails 14. python-sgp4's answer to one corrupt input differs by platform: for
`c9-letter-in-epoch-first.tle` in `corrupt-input` it returned bstar NaN in this run, and was seen to return 0.0 on
macOS arm64 with Python 3.14.6 (D-593); the case fails either way.
python-sgp4 propagating an element set of ephemeris type 4 as SGP4, in `ephemeris-type-4-refused` below, is reported as
[brandon-rhodes/python-sgp4#178](https://github.com/brandon-rhodes/python-sgp4/issues/178) (filed 2026-11-08).

Generated 2026-11-15T22:40:19Z by `tools/make_failures.py` from the runner reports `tools/_out/report-<adapter>.json` — reference: run 2026-11-15T22:40:14Z with gpconf 0.10.0 on corpus 0.10.0 (parser preset reference); naive: run 2026-11-15T22:40:15Z with gpconf 0.10.0 on corpus 0.10.0 (parser preset naive (a demonstration of failure, not a parser anyone should use)); sgp4: run 2026-11-15T22:40:19Z with gpconf 0.10.0 on corpus 0.10.0 (parser preset sgp4 (python-sgp4 2.27, the version it was tested with)).

Platform, as the reports record it: Linux-7.0.0-1017-azure-x86_64-with-glibc2.39; Python 3.12.16; python-sgp4 2.27.

## Status by case

| case | reference | naive | python-sgp4 |
|---|---|---|---|
| `epoch-year-19xx` | pass (0 failing) | pass (0 failing) | pass-tolerance (0 failing) |
| `baseline-iss-five-formats` | pass (0 failing) | pass (0 failing) | pass (0 failing) |
| `six-digit-omm-saramago` | pass (0 failing) | fail (8 failing) | pass-tolerance (0 failing) |
| `tle-omits-six-digit-objects` | pass (0 failing) | fail (1 failing) | pass-tolerance (0 failing) |
| `analyst-objects` | pass (0 failing) | fail (12 failing) | fail (2 failing) |
| `nine-digit-supgp-launch-nominals` | pass (0 failing) | fail (1 failing) | fail (2 failing) |
| `supgp-celestrak-classification-c` | not-available (0 failing) | not-available (0 failing) | not-available (0 failing) |
| `bstar-and-derivative-forms` | pass (0 failing) | pass (0 failing) | pass-tolerance (0 failing) |
| `satcat-70000-cutoff` | not-exercised (0 failing) | not-exercised (0 failing) | not-exercised (0 failing) |
| `csv-json-omitted-mandatory-fields` | pass (0 failing) | fail (5 failing) | pass (0 failing) |
| `mean-motion-derivative-convention` | pass (0 failing) | fail (4 failing) | pass-tolerance (0 failing) |
| `tle-vs-omm-precision-loss` | pass (0 failing) | fail (4 failing) | pass-tolerance (0 failing) |
| `omm-xml-schema` | pass (0 failing) | fail (4 failing) | fail (2 failing) |
| `alpha5-encoding-vectors` | pass (0 failing) | fail (4 failing) | fail (2 failing) |
| `alpha5-tle-derived` | pass (0 failing) | fail (8 failing) | pass-tolerance (0 failing) |
| `kvn-syntax-variants` | pass (0 failing) | fail (5 failing) | skip (0 failing) |
| `tle-writer-alpha5` | pass (0 failing) | fail (3 failing) | fail (3 failing) |
| `corrupt-input` | pass (0 failing) | fail (9 failing) | fail (9 failing) |
| `sgp4-ver-propagation` | skip (0 failing) | skip (0 failing) | pass-tolerance (0 failing) |
| `propagation-tle-omm-twins` | skip (0 failing) | skip (0 failing) | pass-tolerance (0 failing) |
| `ephemeris-type-4-refused` | skip (0 failing) | skip (0 failing) | fail (1 failing) |

## Gate: this month's launches

One headline per parser, read across existing cases from the record counts behind their values items (D-142): words that name the behaviour, never a grade on the project. Snapshot facts and the letter caveat travel with each.

- **reference**: reads this month's launches in every format it reads here: TLE (Alpha-5, as Space-Track serves them; rendered by the corpus from the CelesTrak CSV capture): 256 loaded, CSV (as CelesTrak serves them); live capture fetched 2026-11-11, 246 objects, not the snapshot: 246 loaded [snapshot 2026-09-21, 256 objects, ids 100404-100789, Alpha-5 fields beginning with A: a decoder wrong from J upward is not caught by this snapshot]
- **naive**: not in any format it reads: TLE (Alpha-5, as Space-Track serves them; rendered by the corpus from the CelesTrak CSV capture): 256 dropped (the parser raised on the file); CSV (as CelesTrak serves them); live capture fetched 2026-11-11, not the snapshot: every record dropped (the parser raised on the file) [snapshot 2026-09-21, 256 objects, ids 100404-100789, Alpha-5 fields beginning with A: a decoder wrong from J upward is not caught by this snapshot]
- **python-sgp4**: reads this month's launches in every format it reads here: TLE (Alpha-5, as Space-Track serves them; rendered by the corpus from the CelesTrak CSV capture): 256 loaded, CSV (as CelesTrak serves them); live capture fetched 2026-11-11, 246 objects, not the snapshot: 246 loaded [snapshot 2026-09-21, 256 objects, ids 100404-100789, Alpha-5 fields beginning with A: a decoder wrong from J upward is not caught by this snapshot]

## Naive parser, the corpus's control: what failed

The naive parser is the corpus's own, wrong on purpose, to show that each case catches what it is built to catch. Its item-by-item failures are in `python -m gpconf run --preset naive` (add `--case <case>` for one).

| case | failing items | checks that failed |
|---|---|---|
| `six-digit-omm-saramago` | 8 | `parse` |
| `tle-omits-six-digit-objects` | 1 | `parse` |
| `analyst-objects` | 12 | `parse` |
| `nine-digit-supgp-launch-nominals` | 1 | `parse` |
| `csv-json-omitted-mandatory-fields` | 5 | `parse` |
| `mean-motion-derivative-convention` | 4 | `parse` |
| `tle-vs-omm-precision-loss` | 4 | `parse` |
| `omm-xml-schema` | 4 | `parse` |
| `alpha5-encoding-vectors` | 4 | `alpha5-decode`, `alpha5-encode`, `ccsds-epoch-strings`, `catalog-number-is-integer` |
| `alpha5-tle-derived` | 8 | `parse` |
| `kvn-syntax-variants` | 5 | `parse` |
| `tle-writer-alpha5` | 3 | `tle-checksums-valid`, `tle-writer-catalog-field`, `tle-writer-refuses-unencodable` |
| `corrupt-input` | 9 | `corrupt-tle-line-short`, `corrupt-input-neighbours-load`, `corrupt-tle-missing-line-2`, `corrupt-tle-line-fields-differ` |

## python-sgp4 2.27 through sgp4.omm / twoline2rv: what failed and why

### `analyst-objects`

2 failing items, shown as 1 bullet: 1 carried a detail identical to one shown.

- **parse** (analyst.xml): parser raised TypeError: 'NoneType' object is not subscriptable [2 items with this detail: analyst.xml, analyst-270449-first.xml]

### `nine-digit-supgp-launch-nominals`

2 failing items.

- **values** (starlink-all.csv): mismatch (details withheld: SupGP-derived values are not published, D-049; run the case on your own fetch, `python -m gpconf run --adapter <yours> --case nine-digit-supgp-launch-nominals --json out.json`, and the report shows them)
- **classification-c** (starlink-all.csv): C not preserved for [100001, 100002, 100003] and 11196 more

### `omm-xml-schema`

2 failing items, shown as 1 bullet: 1 carried a detail identical to one shown.

- **parse** (analyst.xml): parser raised TypeError: 'NoneType' object is not subscriptable [2 items with this detail: analyst.xml, analyst-270449-first.xml]

### `alpha5-encoding-vectors`

2 failing items.

- **alpha5-decode** (alpha5.json): 'I0000' accepted as 180000 (should be rejected: letter I is never used); 'O1234' accepted as 231234 (should be rejected: letter O is never used); 'a0000' accepted as 400000 (should be rejected: lowercase is not defined by Space-Track; a lenient decoder that accepts it disagrees with a strict one); 'A000' accepted as 100000 (should be rejected: field must be five characters); 'A１２３４' accepted as 101234 (should be rejected: full-width digits are not the digits 0 to 9: the four characters after the letter are ASCII digits (D-370)); 'A1_23' accepted as 100123 (should be rejected: an underscore ins …
- **alpha5-encode** (alpha5.json): -1 encoded as '-0001' (should be rejected: negative)

### `tle-writer-alpha5`

3 failing items.

- **tle-writer-catalog-field** (set): 755 of 759 catalog fields correct; id 180000: field 'I0000' written for 180000 (expected 'J0000'; catalog field 'I0000' is neither five digits nor Alpha-5); id 189999: field 'I9999' written for 189999 (expected 'J9999'; catalog field 'I9999' is neither five digits nor Alpha-5); id 230000: field 'O0000' written for 230000 (expected 'P0000'; catalog field 'O0000' is neither five digits nor Alpha-5); id 239999: field 'O9999' written for 239999 (expected 'P9999'; catalog field 'O9999' is neither five digits nor Alpha-5)
- **tle-writer-round-trip** (set): 755 of 759 records correct; id 180000: reference reader raised ValueError: invalid Alpha-5 field 'I0000': one digit or uppercase letter (never I or O) followed by four digits; id 189999: reference reader raised ValueError: invalid Alpha-5 field 'I9999': one digit or uppercase letter (never I or O) followed by four digits; id 230000: reference reader raised ValueError: invalid Alpha-5 field 'O0000': one digit or uppercase letter (never I or O) followed by four digits; id 239999: reference reader raised ValueError: invalid Alpha-5 field 'O9999': one digit or uppercase letter (never I or O) follo …
- **tle-writer-refuses-unencodable** (set): 2 of 3 numbers the TLE catalog field cannot represent (synthetic inputs, D-096) correctly refused (340000, 799501621); written instead of refused: id -1: lines written instead of a refusal (line 1 columns 3-7 '-0001', 69 characters)
- passed: **tle-checksums-valid** (759 records written as two 69-character lines with valid checksums); **tle-writer-column-layout** (759 records with every field in its fixed columns); **tle-writer-secondary-not-changed** (755 records with each side field kept, or zeroed or left out as documented)

### `corrupt-input`

9 failing items, shown as 6 bullets: 3 carried a detail identical to one shown.

- **corrupt-tle-line-short** (c2-line-2-short.tle): built a record from the corrupt input: eccentricity = Decimal('0.148004'), from the unedited file Decimal('0.1487004'); rev_at_epoch = 189308, from the unedited file 18930
- **corrupt-tle-letter-in-number** (c3-letter-in-epoch.tle): built a record from the corrupt input: epoch = '2026-07-08T16:48:00.000000', from the unedited file '2026-07-08T17:02:16.167840'; bstar = Decimal('0.0'), from the unedited file Decimal('-0.000007051700000000001'); mean_motion_dot = Decimal('0.0'), from the unedited file Decimal('-2.3E-7'); … and 1 more [3 items with this detail: c3-letter-in-epoch.tle, c10-letter-in-epoch-last.tle, c11-letter-in-epoch-second-of-five.tle]
- **corrupt-tle-missing-line-2** (c4-line-2-missing.tle): built a record from the corrupt input: mean_motion = Decimal('0.0'), from the unedited file Decimal('11.62373363'); eccentricity = Decimal('0.0'), from the unedited file Decimal('0.1487004'); inclination = Decimal('0.0'), from the unedited file Decimal('34.2417'); … and 4 more
- **corrupt-tle-invalid-catalog-field** (c6-invalid-catalog-field.tle): the corrupt record dropped silently; 1 record the file does not hold, built from garbage [2 items with this detail: c6-invalid-catalog-field.tle, c7-letter-o-catalog-field.tle]
- **corrupt-tle-line-fields-differ** (c8-line-fields-differ.tle): the corrupt record dropped silently; 1 record the file does not hold, built from garbage
- **parse** (c9-letter-in-epoch-first.tle): the parser returned a value the runner cannot read: bstar = nan is not a finite number (D-325)

### `ephemeris-type-4-refused`

1 failing item.

- **type4-not-propagated** (set): fails in 2 sets: type4.csv, type4.tle; type4.tle propagated as SGP4: positions for an SGP4-XP set (EPHEMERIS_TYPE 4) look right and are not; type4.csv propagated as SGP4: positions for an SGP4-XP set (EPHEMERIS_TYPE 4) look right and are not; skipped, unsupported for both files: type4.json, type4.xml, type4.kvn, type4-sgp4-xp.kvn

## How to read this

- `parse` failures mean the parser raised on real provider bytes, or returned a value the runner cannot read; the detail says which.
- `values` failures list the first mismatching fields against the frozen expected values (snapshot) or the reference reader (live).
- `not-exercised` means the data needed for that check was not present in the fetched snapshot (for example no nine-digit ids outside the days after a launch), or that the check involves no parser at all (the SATCAT data check, the same for every parser).
- Each case entry opens with its failing-item count; items whose first 80 characters of detail are identical are collapsed into one bullet that names the files it stands for, so the count can exceed the bullets. A detail cut at 600 characters shows … where it was cut, and a closing sentence saying the input holds an id more than once is kept whole after it; the JSON report (`--json`) holds the full text.
- For the writer case (`tle-writer-alpha5`) each adapter's entry also lists the checks it passed, with their record counts, so a failure confined to the three synthetic refusal inputs (340000, 799501621, -1: numbers the TLE field cannot carry, for which a refusal is the correct output) cannot be read as a failure on real records.
- Re-run for your own parser: `python -m gpconf run --adapter your.module:Parser` (see README).
