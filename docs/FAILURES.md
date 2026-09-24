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
passes every case. Draft upstream reports for the python-sgp4 findings are in `docs/upstream/`.

Generated 2026-09-24T01:17:23Z by `tools/make_failures.py` from the runner reports `tools/_out/report-<adapter>.json` — reference: run 2026-09-24T01:17:21Z with gpconf 0.2.1 on corpus 0.2.1 (parser tests.adapters.reference:Parser); naive: run 2026-09-24T01:17:22Z with gpconf 0.2.1 on corpus 0.2.1 (parser tests.adapters.naive:Parser); sgp4: run 2026-09-24T01:17:23Z with gpconf 0.2.1 on corpus 0.2.1 (parser tests.adapters.sgp4_adapter:Parser).

## Status by case

| case | reference | naive | python-sgp4 |
|---|---|---|---|
| `epoch-year-19xx` | pass (0 fail) | pass (0 fail) | pass-tolerance (0 fail) |
| `baseline-iss-five-formats` | pass (0 fail) | pass (0 fail) | pass-tolerance (0 fail) |
| `six-digit-omm-saramago` | pass (0 fail) | fail (8 fail) | pass-tolerance (0 fail) |
| `tle-omits-six-digit-objects` | pass (0 fail) | fail (1 fail) | pass-tolerance (0 fail) |
| `analyst-objects` | pass (0 fail) | fail (13 fail) | fail (2 fail) |
| `nine-digit-supgp-launch-nominals` | pass (0 fail) | fail (5 fail) | fail (4 fail) |
| `supgp-celestrak-classification-c` | pass (0 fail) | fail (5 fail) | fail (6 fail) |
| `bstar-and-derivative-forms` | pass (0 fail) | fail (1 fail) | pass-tolerance (0 fail) |
| `satcat-70000-cutoff` | pass (0 fail) | pass (0 fail) | pass (0 fail) |
| `csv-json-omitted-mandatory-fields` | pass (0 fail) | fail (8 fail) | fail (2 fail) |
| `mean-motion-derivative-convention` | pass (0 fail) | fail (7 fail) | pass (0 fail) |
| `tle-vs-omm-precision-loss` | pass (0 fail) | fail (7 fail) | pass-tolerance (0 fail) |
| `omm-xml-schema` | pass (0 fail) | fail (6 fail) | fail (3 fail) |
| `alpha5-encoding-vectors` | pass (0 fail) | fail (4 fail) | fail (2 fail) |
| `alpha5-tle-derived` | pass (0 fail) | fail (4 fail) | pass-tolerance (0 fail) |
| `kvn-syntax-variants` | pass (0 fail) | fail (4 fail) | skip (0 fail) |
| `tle-writer-alpha5` | pass (0 fail) | fail (3 fail) | fail (1 fail) |

## Naive parser: what failed and why

### `six-digit-omm-saramago`

8 failing item(s), shown as 1 bullet(s): 7 carried a detail identical to one shown.

- **parse** (saramago-first.csv): parser raised AssertionError: catalog number wider than five digits [8 items with this detail: saramago-first.csv, saramago-first.json, saramago-first.xml, saramago-first.kvn, saramago.csv, saramago.json, saramago.xml, saramago.kvn]

### `tle-omits-six-digit-objects`

1 failing item(s).

- **parse** (last-30-days.csv): parser raised AssertionError: catalog number wider than five digits

### `analyst-objects`

13 failing item(s), shown as 4 bullet(s): 9 carried a detail identical to one shown.

- **parse** (analyst.tle): parser raised ValueError: invalid literal for int() with base 10: '  ' [3 items with this detail: analyst.tle, analyst-recapture.tle, analyst-81011-first.tle]
- **parse** (analyst.csv): parser raised ValueError: invalid literal for int() with base 10: '' [5 items with this detail: analyst.csv, analyst.json, analyst.kvn, analyst-81011-first.csv, analyst-81011-first.json]
- **parse** (analyst.xml): parser raised TypeError: 'NoneType' object is not subscriptable
- **parse** (analyst-270449-first.csv): parser raised AssertionError: catalog number wider than five digits [4 items with this detail: analyst-270449-first.csv, analyst-270449-first.json, analyst-270449-first.xml, analyst-270449-first.kvn]

### `nine-digit-supgp-launch-nominals`

5 failing item(s), shown as 1 bullet(s): 4 carried a detail identical to one shown.

- **parse** (starlink-38381-799501621.csv): parser raised AssertionError: catalog number wider than five digits [5 items with this detail: starlink-38381-799501621.csv, starlink-38381-799501621.json, starlink-38381-799501621.xml, starlink-38381-799501621.kvn, starlink-all.csv]

### `supgp-celestrak-classification-c`

5 failing item(s), shown as 2 bullet(s): 3 carried a detail identical to one shown.

- **parse** (starlink-g15-27.csv): parser raised AssertionError:  [4 items with this detail: starlink-g15-27.csv, starlink-g15-27.json, starlink-g15-27.xml, starlink-g15-27.kvn]
- **parse** (starlink-g15-27.tle): parser raised AssertionError: classification

### `bstar-and-derivative-forms`

1 failing item(s).

- **parse** (decaying.csv): parser raised AssertionError: catalog number wider than five digits

### `csv-json-omitted-mandatory-fields`

8 failing item(s), shown as 2 bullet(s): 6 carried a detail identical to one shown.

- **parse** (saramago-first.csv): parser raised AssertionError: catalog number wider than five digits [6 items with this detail: saramago-first.csv, saramago-first.json, last-30-days.csv, decaying.csv, starlink-38381-799501621.csv, starlink-38381-799501621.json]
- **parse** (analyst.csv): parser raised ValueError: invalid literal for int() with base 10: '' [2 items with this detail: analyst.csv, analyst.json]

### `mean-motion-derivative-convention`

7 failing item(s), shown as 5 bullet(s): 2 carried a detail identical to one shown.

- **parse** (analyst.tle): parser raised ValueError: invalid literal for int() with base 10: '  ' [2 items with this detail: analyst.tle, analyst-81011-first.tle]
- **parse** (analyst.csv): parser raised ValueError: invalid literal for int() with base 10: '' [2 items with this detail: analyst.csv, analyst-81011-first.csv]
- **parse** (decaying.csv): parser raised AssertionError: catalog number wider than five digits
- **parse** (starlink-g15-27.tle): parser raised AssertionError: classification
- **parse** (starlink-g15-27.csv): parser raised AssertionError: 

### `tle-vs-omm-precision-loss`

7 failing item(s), shown as 5 bullet(s): 2 carried a detail identical to one shown.

- **parse** (analyst.tle): parser raised ValueError: invalid literal for int() with base 10: '  ' [2 items with this detail: analyst.tle, analyst-81011-first.tle]
- **parse** (analyst.csv): parser raised ValueError: invalid literal for int() with base 10: '' [2 items with this detail: analyst.csv, analyst-81011-first.csv]
- **parse** (decaying.csv): parser raised AssertionError: catalog number wider than five digits
- **parse** (starlink-g15-27.tle): parser raised AssertionError: classification
- **parse** (starlink-g15-27.csv): parser raised AssertionError: 

### `omm-xml-schema`

6 failing item(s), shown as 3 bullet(s): 3 carried a detail identical to one shown.

- **parse** (saramago-first.xml): parser raised AssertionError: catalog number wider than five digits [4 items with this detail: saramago-first.xml, saramago.xml, analyst-270449-first.xml, starlink-38381-799501621.xml]
- **parse** (analyst.xml): parser raised TypeError: 'NoneType' object is not subscriptable
- **parse** (starlink-g15-27.xml): parser raised AssertionError: 

### `alpha5-encoding-vectors`

4 failing item(s).

- **alpha5-decode** (alpha5.json): A0000 -> raised ValueError (expected 100000); E8493 -> raised ValueError (expected 148493); J2931 -> raised ValueError (expected 182931); P4018 -> raised ValueError (expected 234018); W1928 -> raised ValueError (expected 301928); Z9999 -> raised ValueError (expected 339999); A0000 -> raised ValueError (expected 100000); A9999 -> raised ValueError (expected 109999)
- **alpha5-encode** (alpha5.json): 100000 -> '100000' (expected 'A0000'); 148493 -> '148493' (expected 'E8493'); 182931 -> '182931' (expected 'J2931'); 234018 -> '234018' (expected 'P4018'); 301928 -> '301928' (expected 'W1928'); 339999 -> '339999' (expected 'Z9999'); 100000 -> '100000' (expected 'A0000'); 109999 -> '109999' (expected 'A9999')
- **ccsds-epoch-strings** (ccsds-epoch-strings.json): valid '2020-064T10:34:41.4264' rejected (ValueError); valid '2020-065T16:00:00' rejected (ValueError); valid '2002-204T15:56:23Z' rejected (ValueError); valid '2001-11-06T11:17:33' rejected (ValueError); valid '1998-11-20T06:49:59.999808Z' rejected (ValueError); valid '2016-12-31T23:59:60' rejected (ValueError)
- **catalog-number-is-integer** (norad-cat-id-text.json): '1000000000' accepted as 1000000000 (should be rejected: ten digits exceed 'up to nine digits'; schema xsd:integer would accept it, the standard's text does not)

### `alpha5-tle-derived`

4 failing item(s).

- **parse** (alpha5-A-100000-saramago-first.tle): parser raised ValueError: invalid literal for int() with base 10: 'A0000'
- **parse** (alpha5-T-270449-analyst-first.tle): parser raised ValueError: invalid literal for int() with base 10: 'T0449'
- **parse** (alpha5-A-last-30-days-snapshot.tle): parser raised ValueError: invalid literal for int() with base 10: 'A0404'
- **parse** (alpha5-T-analyst-27xxxx-snapshot.tle): parser raised ValueError: invalid literal for int() with base 10: 'T0000'

### `kvn-syntax-variants`

4 failing item(s).

- **parse** (v02-day-of-year-epoch-Z.kvn): parser raised ValueError: time data '1998-324T06:49:59.999808Z' does not match format '%Y-%m-%dT%H:%M:%S.%f'
- **parse** (v03-units-brackets-leading-zeros.kvn): parser raised ValueError: could not convert string to float: '16.05064833 [rev/day]'
- **parse** (v04-comments-blank-lines-whitespace-LF.kvn): parser raised ValueError: not enough values to unpack (expected 2, got 1)
- **parse** (v05-omm-3.0-header-optional-keywords-omitted.kvn): parser raised KeyError: 'NORAD_CAT_ID'

### `tle-writer-alpha5`

3 failing item(s).

- **tle-checksums-valid** (set): 4 of 607 record(s) correct; id 100000: line 1 is 70 characters, not 69; line 2 is 70 characters, not 69; id 270449: line 1 is 70 characters, not 69; line 2 is 70 characters, not 69; id 100404: line 1 is 70 characters, not 69; line 2 is 70 characters, not 69; id 100405: line 1 is 70 characters, not 69; line 2 is 70 characters, not 69; id 100406: line 1 is 70 characters, not 69; line 2 is 70 characters, not 69; id 100407: line 1 is 70 characters, not 69; line 2 is 70 characters, not 69; id 100408: line 1 is 70 characters, not 69; line 2 is 70 characters, not 69; id 100409: line 1 is 70 character …
- **tle-writer-catalog-field** (set): 4 of 607 catalog field(s) correct; id 100000: field '10000' written for 100000 (expected 'A0000'; decodes to 10000); id 270449: field '27044' written for 270449 (expected 'T0449'; decodes to 27044); id 100404: field '10040' written for 100404 (expected 'A0404'; decodes to 10040); id 100405: field '10040' written for 100405 (expected 'A0405'; decodes to 10040); id 100406: field '10040' written for 100406 (expected 'A0406'; decodes to 10040); id 100407: field '10040' written for 100407 (expected 'A0407'; decodes to 10040); id 100408: field '10040' written for 100408 (expected 'A0408'; decodes to …
- **tle-writer-refuses-unencodable** (set): 0 of 3 number(s) the TLE catalog field cannot represent (synthetic inputs, D-096) correctly refused; written instead of refused: id 340000: lines written instead of a refusal (line 1 columns 3-7 '34000', 70 characters); id 799501621: lines written instead of a refusal (line 1 columns 3-7 '79950', 73 characters); id -1: lines written instead of a refusal (line 1 columns 3-7 '-0001', 69 characters)
- passed: **tle-writer-column-layout** (4 record(s) with every field in its fixed columns); **tle-writer-round-trip** (607 record(s) read back at the TLE field resolution (rendering observed per field: epoch: exact 4; mean_motion: exact 4; eccentricity: exact 2, quantised 2; inclination: exact 4; ra_of_asc_node: exact 4; arg_of_pericente …)


## python-sgp4 2.27 through sgp4.omm / twoline2rv: what failed and why

### `analyst-objects`

2 failing item(s), shown as 1 bullet(s): 1 carried a detail identical to one shown.

- **parse** (analyst.xml): parser raised TypeError: 'NoneType' object is not subscriptable [2 items with this detail: analyst.xml, analyst-270449-first.xml]

### `nine-digit-supgp-launch-nominals`

4 failing item(s), shown as 1 bullet(s): 3 carried a detail identical to one shown.

- **parse** (starlink-38381-799501621.csv): parser raised ValueError: satellite number cannot exceed 339999, whose Alpha 5 encoding is 'Z9999' [4 items with this detail: starlink-38381-799501621.csv, starlink-38381-799501621.json, starlink-38381-799501621.xml, starlink-all.csv]

### `supgp-celestrak-classification-c`

6 failing item(s), shown as 2 bullet(s): 4 carried a detail identical to one shown.

- **values** (starlink-g15-27.csv): mismatch (details withheld: SupGP-derived values are not published, D-049; run the case on your own fetch, `python -m gpconf run --adapter <yours> --case supgp-celestrak-classification-c --json out.json`, and the report shows them) [3 items with this detail: starlink-g15-27.csv, starlink-g15-27.json, starlink-g15-27.xml]
- **classification-c** (starlink-g15-27.csv): C not preserved for [72000, 72001] [3 items with this detail: starlink-g15-27.csv, starlink-g15-27.json, starlink-g15-27.xml]

### `csv-json-omitted-mandatory-fields`

2 failing item(s), shown as 1 bullet(s): 1 carried a detail identical to one shown.

- **parse** (starlink-38381-799501621.csv): parser raised ValueError: satellite number cannot exceed 339999, whose Alpha 5 encoding is 'Z9999' [2 items with this detail: starlink-38381-799501621.csv, starlink-38381-799501621.json]

### `omm-xml-schema`

3 failing item(s), shown as 2 bullet(s): 1 carried a detail identical to one shown.

- **parse** (analyst.xml): parser raised TypeError: 'NoneType' object is not subscriptable [2 items with this detail: analyst.xml, analyst-270449-first.xml]
- **parse** (starlink-38381-799501621.xml): parser raised ValueError: satellite number cannot exceed 339999, whose Alpha 5 encoding is 'Z9999'

### `alpha5-encoding-vectors`

2 failing item(s).

- **alpha5-decode** (alpha5.json): I0000 accepted as 180000 (should be rejected: letter I is never used); O1234 accepted as 231234 (should be rejected: letter O is never used); a0000 accepted as 400000 (should be rejected: lowercase is not defined by Space-Track; a lenient decoder that accepts it disagrees with a strict one); A000 accepted as 100000 (should be rejected: field must be five characters)
- **alpha5-encode** (alpha5.json): -1 encoded as '-0001' (should be rejected: negative)

### `tle-writer-alpha5`

1 failing item(s).

- **tle-writer-refuses-unencodable** (set): 2 of 3 number(s) the TLE catalog field cannot represent (synthetic inputs, D-096) correctly refused (340000, 799501621); written instead of refused: id -1: lines written instead of a refusal (line 1 columns 3-7 '-0001', 69 characters)
- passed: **tle-checksums-valid** (607 record(s) written as two 69-character lines with valid checksums); **tle-writer-catalog-field** (607 catalog field(s) written correctly (five digits below 100000, Alpha-5 from 100000)); **tle-writer-column-layout** (607 record(s) with every field in its fixed columns); **tle-writer-round-trip** (607 record(s) read back at the TLE field resolution (rendering observed per field: epoch: exact 607; mean_motion: exact 607; eccentricity: exact 71, quantised 246, round 256, truncate 34; inclination: exact 607; ra_of_as …)

## How to read this

- `parse` failures mean the parser raised on real provider bytes; the detail carries the exception.
- `values` failures list the first mismatching fields against the frozen expected values (snapshot) or the reference reader (live).
- `not-exercised` means the data needed for that check was not present in the fetched snapshot (for example no nine-digit ids outside the days after a launch).
- Each case entry opens with its failing-item count; items whose first 80 characters of detail are identical are collapsed into one bullet that names the files it stands for, so the count can exceed the bullets. A detail ending in … was cut at 600 characters; the JSON report (`--json`) holds the full text.
- For the writer case (`tle-writer-alpha5`) each adapter's entry also lists the checks it passed, with their record counts, so a failure confined to the three synthetic refusal inputs (340000, 799501621, -1: numbers the TLE field cannot carry, for which a refusal is the correct output) cannot be read as a failure on real records.
- Re-run for your own parser: `python -m gpconf run --adapter your.module:Parser` (see README).
