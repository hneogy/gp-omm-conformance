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

The reference and naive columns were measured on the 0.9.0 re-measure's fresh fetch (2026-11-11) with the corpus's ten
launch-window captures added. A new user's fetch cannot obtain those files (D-229). Both figures, of 21 cases:
- with the ten captures, as in the table below: the reference passes 17 and the naive adapter fails 14;
- from a fresh fetch alone: the reference passes 16 and the naive adapter fails 13.
The one case between them is `supgp-celestrak-classification-c`. It reads only launch-window captures, so without them
it reports `not-available`: a pass for the reference, a fail for naive. The python-sgp4 column comes from the
re-measure's own run on the fresh fetch alone, without the captures (D-483): it fails 7 of 21, and that case shows
`not-available` there.
python-sgp4 propagating an element set of ephemeris type 4 as SGP4, in `ephemeris-type-4-refused` below, is reported as
[brandon-rhodes/python-sgp4#178](https://github.com/brandon-rhodes/python-sgp4/issues/178) (filed 2026-11-08).

Generated 2026-11-11T16:35:03Z (0.9.0's code before its version bump, which is why the runs below say gpconf 0.8.0) by `tools/make_failures.py` from the runner reports `tools/_out/report-<adapter>.json` — reference: run 2026-11-11T16:00:17Z with gpconf 0.8.0 on corpus 0.8.0 (parser preset reference); naive: run 2026-11-11T16:00:19Z with gpconf 0.8.0 on corpus 0.8.0 (parser preset naive (a demonstration of failure, not a parser anyone should use)); sgp4: run 2026-11-11T14:39:08Z with gpconf 0.8.0 on corpus 0.8.0 (parser preset sgp4 (python-sgp4 2.27, the version it was tested with)).

## Status by case

| case | reference | naive | python-sgp4 |
|---|---|---|---|
| `epoch-year-19xx` | pass (0 failing) | pass (0 failing) | pass-tolerance (0 failing) |
| `baseline-iss-five-formats` | pass (0 failing) | pass (0 failing) | pass (0 failing) |
| `six-digit-omm-saramago` | pass (0 failing) | fail (8 failing) | pass-tolerance (0 failing) |
| `tle-omits-six-digit-objects` | pass (0 failing) | fail (1 failing) | pass-tolerance (0 failing) |
| `analyst-objects` | pass (0 failing) | fail (12 failing) | fail (2 failing) |
| `nine-digit-supgp-launch-nominals` | pass (0 failing) | fail (5 failing) | fail (2 failing) |
| `supgp-celestrak-classification-c` | pass (0 failing) | fail (5 failing) | not-available (0 failing) |
| `bstar-and-derivative-forms` | pass (0 failing) | pass (0 failing) | pass-tolerance (0 failing) |
| `satcat-70000-cutoff` | not-exercised (0 failing) | not-exercised (0 failing) | not-exercised (0 failing) |
| `csv-json-omitted-mandatory-fields` | pass (0 failing) | fail (7 failing) | pass (0 failing) |
| `mean-motion-derivative-convention` | pass (0 failing) | fail (6 failing) | pass-tolerance (0 failing) |
| `tle-vs-omm-precision-loss` | pass (0 failing) | fail (6 failing) | pass-tolerance (0 failing) |
| `omm-xml-schema` | pass (0 failing) | fail (6 failing) | fail (2 failing) |
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

## Naive parser: what failed and why

### `six-digit-omm-saramago`

8 failing items, shown as 1 bullet: 7 carried a detail identical to one shown.

- **parse** (saramago-first.csv): parser raised AssertionError: catalog number wider than five digits [8 items with this detail: saramago-first.csv, saramago-first.json, saramago-first.xml, saramago-first.kvn, saramago.csv, saramago.json, saramago.xml, saramago.kvn]

### `tle-omits-six-digit-objects`

1 failing item.

- **parse** (last-30-days.csv): parser raised AssertionError: catalog number wider than five digits

### `analyst-objects`

12 failing items, shown as 4 bullets: 8 carried a detail identical to one shown.

- **parse** (analyst.tle): parser raised ValueError: invalid literal for int() with base 10: '  ' [2 items with this detail: analyst.tle, analyst-81011-first.tle]
- **parse** (analyst.csv): parser raised ValueError: invalid literal for int() with base 10: '' [5 items with this detail: analyst.csv, analyst.json, analyst.kvn, analyst-81011-first.csv, analyst-81011-first.json]
- **parse** (analyst.xml): parser raised TypeError: 'NoneType' object is not subscriptable
- **parse** (analyst-270449-first.csv): parser raised AssertionError: catalog number wider than five digits [4 items with this detail: analyst-270449-first.csv, analyst-270449-first.json, analyst-270449-first.xml, analyst-270449-first.kvn]

### `nine-digit-supgp-launch-nominals`

5 failing items, shown as 1 bullet: 4 carried a detail identical to one shown.

- **parse** (starlink-38381-799501621.csv): parser raised AssertionError: catalog number wider than five digits [5 items with this detail: starlink-38381-799501621.csv, starlink-38381-799501621.json, starlink-38381-799501621.xml, starlink-38381-799501621.kvn, starlink-all.csv]

### `supgp-celestrak-classification-c`

5 failing items, shown as 2 bullets: 3 carried a detail identical to one shown.

- **parse** (starlink-g15-27.csv): parser raised AssertionError:  [4 items with this detail: starlink-g15-27.csv, starlink-g15-27.json, starlink-g15-27.xml, starlink-g15-27.kvn]
- **parse** (starlink-g15-27.tle): parser raised AssertionError: classification

### `csv-json-omitted-mandatory-fields`

7 failing items, shown as 2 bullets: 5 carried a detail identical to one shown.

- **parse** (saramago-first.csv): parser raised AssertionError: catalog number wider than five digits [5 items with this detail: saramago-first.csv, saramago-first.json, last-30-days.csv, starlink-38381-799501621.csv, starlink-38381-799501621.json]
- **parse** (analyst.csv): parser raised ValueError: invalid literal for int() with base 10: '' [2 items with this detail: analyst.csv, analyst.json]

### `mean-motion-derivative-convention`

6 failing items, shown as 4 bullets: 2 carried a detail identical to one shown.

- **parse** (analyst.tle): parser raised ValueError: invalid literal for int() with base 10: '  ' [2 items with this detail: analyst.tle, analyst-81011-first.tle]
- **parse** (analyst.csv): parser raised ValueError: invalid literal for int() with base 10: '' [2 items with this detail: analyst.csv, analyst-81011-first.csv]
- **parse** (starlink-g15-27.tle): parser raised AssertionError: classification
- **parse** (starlink-g15-27.csv): parser raised AssertionError: 

### `tle-vs-omm-precision-loss`

6 failing items, shown as 4 bullets: 2 carried a detail identical to one shown.

- **parse** (analyst.tle): parser raised ValueError: invalid literal for int() with base 10: '  ' [2 items with this detail: analyst.tle, analyst-81011-first.tle]
- **parse** (analyst.csv): parser raised ValueError: invalid literal for int() with base 10: '' [2 items with this detail: analyst.csv, analyst-81011-first.csv]
- **parse** (starlink-g15-27.tle): parser raised AssertionError: classification
- **parse** (starlink-g15-27.csv): parser raised AssertionError: 

### `omm-xml-schema`

6 failing items, shown as 3 bullets: 3 carried a detail identical to one shown.

- **parse** (saramago-first.xml): parser raised AssertionError: catalog number wider than five digits [4 items with this detail: saramago-first.xml, saramago.xml, analyst-270449-first.xml, starlink-38381-799501621.xml]
- **parse** (analyst.xml): parser raised TypeError: 'NoneType' object is not subscriptable
- **parse** (starlink-g15-27.xml): parser raised AssertionError: 

### `alpha5-encoding-vectors`

4 failing items.

- **alpha5-decode** (alpha5.json): A0000 -> raised ValueError (expected 100000); E8493 -> raised ValueError (expected 148493); J2931 -> raised ValueError (expected 182931); P4018 -> raised ValueError (expected 234018); W1928 -> raised ValueError (expected 301928); Z9999 -> raised ValueError (expected 339999); A0000 -> raised ValueError (expected 100000); A9999 -> raised ValueError (expected 109999)
- **alpha5-encode** (alpha5.json): 100000 -> '100000' (expected 'A0000'); 148493 -> '148493' (expected 'E8493'); 182931 -> '182931' (expected 'J2931'); 234018 -> '234018' (expected 'P4018'); 301928 -> '301928' (expected 'W1928'); 339999 -> '339999' (expected 'Z9999'); 100000 -> '100000' (expected 'A0000'); 109999 -> '109999' (expected 'A9999')
- **ccsds-epoch-strings** (ccsds-epoch-strings.json): valid '2020-064T10:34:41.4264' rejected (ValueError); valid '2020-065T16:00:00' rejected (ValueError); valid '2002-204T15:56:23Z' rejected (ValueError); valid '2001-11-06T11:17:33' rejected (ValueError); valid '1998-11-20T06:49:59.999808Z' rejected (ValueError); valid '2016-12-31T23:59:60' rejected (ValueError); valid '1972-06-30T23:59:60' rejected (ValueError); valid '2016-366T23:59:60.5Z' rejected (ValueError)
- **catalog-number-is-integer** (norad-cat-id-text.json): '1000000000' accepted as 1000000000 (should be rejected: ten digits exceed 'up to nine digits'; schema xsd:integer would accept it, the standard's text does not)

### `alpha5-tle-derived`

8 failing items.

- **parse** (alpha5-A-100000-saramago-first.tle): parser raised ValueError: invalid literal for int() with base 10: 'A0000'
- **parse** (alpha5-T-270449-analyst-first.tle): parser raised ValueError: invalid literal for int() with base 10: 'T0449'
- **parse** (alpha5-A-last-30-days-snapshot.tle): parser raised ValueError: invalid literal for int() with base 10: 'A0404'
- **parse** (alpha5-T-analyst-27xxxx-snapshot.tle): parser raised ValueError: invalid literal for int() with base 10: 'T0000'
- **parse** (alpha5-synthetic-letters.tle): parser raised ValueError: invalid literal for int() with base 10: 'A9999'
- **parse** (alpha5-synthetic-epoch-years.tle): parser raised ValueError: invalid literal for int() with base 10: 'Z0100'
- **parse** (alpha5-synthetic-day-366.tle): parser raised ValueError: invalid literal for int() with base 10: 'Z0200'
- **parse** (alpha5-synthetic-classification.tle): parser raised ValueError: invalid literal for int() with base 10: 'Z0205'

### `kvn-syntax-variants`

5 failing items.

- **parse** (v02-day-of-year-epoch-Z.kvn): parser raised ValueError: time data '1998-324T06:49:59.999808Z' does not match format '%Y-%m-%dT%H:%M:%S.%f'
- **parse** (v03-units-brackets-leading-zeros.kvn): parser raised ValueError: could not convert string to float: '16.05064833 [rev/day]'
- **parse** (v04-comments-blank-lines-whitespace-LF.kvn): parser raised ValueError: not enough values to unpack (expected 2, got 1)
- **parse** (v05-omm-3.0-header-optional-keywords-omitted.kvn): parser raised KeyError: 'NORAD_CAT_ID'
- **parse** (v08-synthetic-epochs.kvn): parser raised ValueError: time data '1996-366T06:49:59.999808' does not match format '%Y-%m-%dT%H:%M:%S.%f'

### `tle-writer-alpha5`

3 failing items.

- **tle-checksums-valid** (set): 5 of 759 records correct; id 100000: line 1 is 70 characters, not 69; line 2 is 70 characters, not 69; id 270449: line 1 is 70 characters, not 69; line 2 is 70 characters, not 69; id 100404: line 1 is 70 characters, not 69; line 2 is 70 characters, not 69; id 100405: line 1 is 70 characters, not 69; line 2 is 70 characters, not 69; id 100406: line 1 is 70 characters, not 69; line 2 is 70 characters, not 69; id 100407: line 1 is 70 characters, not 69; line 2 is 70 characters, not 69; id 100408: line 1 is 70 characters, not 69; line 2 is 70 characters, not 69; id 100409: line 1 is 70 characters, …
- **tle-writer-catalog-field** (set): 5 of 759 catalog fields correct; id 100000: field '10000' written for 100000 (expected 'A0000'; decodes to 10000); id 270449: field '27044' written for 270449 (expected 'T0449'; decodes to 27044); id 100404: field '10040' written for 100404 (expected 'A0404'; decodes to 10040); id 100405: field '10040' written for 100405 (expected 'A0405'; decodes to 10040); id 100406: field '10040' written for 100406 (expected 'A0406'; decodes to 10040); id 100407: field '10040' written for 100407 (expected 'A0407'; decodes to 10040); id 100408: field '10040' written for 100408 (expected 'A0408'; decodes to 1 …
- **tle-writer-refuses-unencodable** (set): 0 of 3 numbers the TLE catalog field cannot represent (synthetic inputs, D-096) correctly refused; written instead of refused: id 340000: lines written instead of a refusal (line 1 columns 3-7 '34000', 70 characters); id 799501621: lines written instead of a refusal (line 1 columns 3-7 '79950', 73 characters); id -1: lines written instead of a refusal (line 1 columns 3-7 '-0001', 69 characters)
- passed: **tle-writer-column-layout** (5 records with every field in its fixed columns); **tle-writer-round-trip** (759 records read back at the TLE field resolution (rendering observed per field: epoch: exact 5; mean_motion: exact 5; eccentricity: exact 3, quantised 2; inclination: exact 5; ra_of_asc_node: exact 5; arg_of_pericenter: …); **tle-writer-secondary-not-changed** (5 records with each side field kept, or zeroed or left out as documented)

### `corrupt-input`

9 failing items, shown as 5 bullets: 4 carried a detail identical to one shown.

- **corrupt-tle-line-short** (c2-line-2-short.tle): built a record from the corrupt input: mean_motion = Decimal('1.623733631'), from the unedited file Decimal('11.62373363'); eccentricity = Decimal('0.148004'), from the unedited file Decimal('0.1487004'); mean_anomaly = Decimal('45.3718'), from the unedited file Decimal('345.3718')
- **corrupt-input-neighbours-load** (c3-letter-in-epoch.tle): the parser refused the file as a whole (ValueError: could not convert string to float: '189.7O990935'), so the 2 valid sets around the corrupt one were given up with it [4 items with this detail: c3-letter-in-epoch.tle, c9-letter-in-epoch-first.tle, c10-letter-in-epoch-last.tle, c11-letter-in-epoch-second-of-five.tle]
- **corrupt-tle-missing-line-2** (c4-line-2-missing.tle): the corrupt record dropped (refusals not reported by this adapter)
- **corrupt-input-neighbours-load** (c6-invalid-catalog-field.tle): the parser refused the file as a whole (ValueError: invalid literal for int() with base 10: 'I9999'), so the 2 valid sets around the corrupt one were given up with it [2 items with this detail: c6-invalid-catalog-field.tle, c7-letter-o-catalog-field.tle]
- **corrupt-tle-line-fields-differ** (c8-line-fields-differ.tle): read a set whose two lines name different objects as one record (D-391) (line 2's catalog field (columns 3 to 7) changed from '69999' to '69998', so that the two lines name different objects, line 2's checksum recomputed (8 to 7); line 1 is the real line)


## python-sgp4 2.27 through sgp4.omm / twoline2rv: what failed and why

### `analyst-objects`

2 failing items, shown as 1 bullet: 1 carried a detail identical to one shown.

- **parse** (analyst.xml): parser raised TypeError: 'NoneType' object is not subscriptable [2 items with this detail: analyst.xml, analyst-270449-first.xml]

### `nine-digit-supgp-launch-nominals`

2 failing items.

- **values** (starlink-all.csv): mismatch (details withheld: SupGP-derived values are not published, D-049; run the case on your own fetch, `python -m gpconf run --adapter <yours> --case nine-digit-supgp-launch-nominals --json out.json`, and the report shows them)
- **classification-c** (starlink-all.csv): C not preserved for [100001, 100002, 100003]

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
- **corrupt-tle-letter-in-number** (c3-letter-in-epoch.tle): built a record from the corrupt input: epoch = '2026-07-08T16:48:00.000000', from the unedited file '2026-07-08T17:02:16.167840'; bstar = Decimal('0.0'), from the unedited file Decimal('-0.000007051700000000001'); mean_motion_dot = Decimal('0.0'), from the unedited file Decimal('-2.3E-7') [3 items with this detail: c3-letter-in-epoch.tle, c10-letter-in-epoch-last.tle, c11-letter-in-epoch-second-of-five.tle]
- **corrupt-tle-missing-line-2** (c4-line-2-missing.tle): built a record from the corrupt input: mean_motion = Decimal('0.0'), from the unedited file Decimal('11.62373363'); eccentricity = Decimal('0.0'), from the unedited file Decimal('0.1487004'); inclination = Decimal('0.0'), from the unedited file Decimal('34.2417')
- **corrupt-tle-invalid-catalog-field** (c6-invalid-catalog-field.tle): the corrupt record dropped silently; 1 record the file does not hold, built from garbage [2 items with this detail: c6-invalid-catalog-field.tle, c7-letter-o-catalog-field.tle]
- **corrupt-tle-line-fields-differ** (c8-line-fields-differ.tle): the corrupt record dropped silently; 1 record the file does not hold, built from garbage
- **parse** (c9-letter-in-epoch-first.tle): the parser returned a value the runner cannot read: bstar = nan is not a finite number (D-325)

### `ephemeris-type-4-refused`

1 failing item.

- **type4-not-propagated** (set): type4.tle propagated as SGP4: positions for an SGP4-XP set (EPHEMERIS_TYPE 4) look right and are not; type4.csv propagated as SGP4: positions for an SGP4-XP set (EPHEMERIS_TYPE 4) look right and are not; skipped, unsupported for both files: type4.json, type4.xml, type4.kvn, type4-sgp4-xp.kvn

## How to read this

- `parse` failures mean the parser raised on real provider bytes, or returned a value the runner cannot read; the detail says which.
- `values` failures list the first mismatching fields against the frozen expected values (snapshot) or the reference reader (live).
- `not-exercised` means the data needed for that check was not present in the fetched snapshot (for example no nine-digit ids outside the days after a launch), or that the check involves no parser at all (the SATCAT data check, the same for every parser).
- Each case entry opens with its failing-item count; items whose first 80 characters of detail are identical are collapsed into one bullet that names the files it stands for, so the count can exceed the bullets. A detail cut at 600 characters shows … where it was cut, and a closing sentence saying the input holds an id more than once is kept whole after it; the JSON report (`--json`) holds the full text.
- For the writer case (`tle-writer-alpha5`) each adapter's entry also lists the checks it passed, with their record counts, so a failure confined to the three synthetic refusal inputs (340000, 799501621, -1: numbers the TLE field cannot carry, for which a refusal is the correct output) cannot be read as a failure on real records.
- Re-run for your own parser: `python -m gpconf run --adapter your.module:Parser` (see README).
