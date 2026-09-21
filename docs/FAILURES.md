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

Generated 2026-09-21T03:16:37Z by `tools/make_failures.py` from the runner reports `tools/_out/report-<adapter>.json` — reference: run 2026-09-21T03:16:36Z with gpconf 0.1.0.dev0 on corpus 0.1.0.dev0 (parser tests.adapters.reference:Parser); naive: run 2026-09-21T03:16:36Z with gpconf 0.1.0.dev0 on corpus 0.1.0.dev0 (parser tests.adapters.naive:Parser); sgp4: run 2026-09-21T03:16:37Z with gpconf 0.1.0.dev0 on corpus 0.1.0.dev0 (parser tests.adapters.sgp4_adapter:Parser).

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

## Naive parser: what failed and why

### `six-digit-omm-saramago`

- **parse** (saramago-first.csv): parser raised AssertionError: catalog number wider than five digits

### `tle-omits-six-digit-objects`

- **parse** (last-30-days.csv): parser raised AssertionError: catalog number wider than five digits

### `analyst-objects`

- **parse** (analyst.tle): parser raised ValueError: invalid literal for int() with base 10: '  '
- **parse** (analyst.csv): parser raised ValueError: invalid literal for int() with base 10: ''
- **parse** (analyst.xml): parser raised TypeError: 'NoneType' object is not subscriptable
- **parse** (analyst-270449-first.csv): parser raised AssertionError: catalog number wider than five digits

### `nine-digit-supgp-launch-nominals`

- **parse** (starlink-38381-799501621.csv): parser raised AssertionError: catalog number wider than five digits

### `supgp-celestrak-classification-c`

- **parse** (starlink-g15-27.csv): parser raised AssertionError: 
- **parse** (starlink-g15-27.tle): parser raised AssertionError: classification

### `bstar-and-derivative-forms`

- **parse** (decaying.csv): parser raised AssertionError: catalog number wider than five digits

### `csv-json-omitted-mandatory-fields`

- **parse** (saramago-first.csv): parser raised AssertionError: catalog number wider than five digits
- **parse** (analyst.csv): parser raised ValueError: invalid literal for int() with base 10: ''

### `mean-motion-derivative-convention`

- **parse** (analyst.tle): parser raised ValueError: invalid literal for int() with base 10: '  '
- **parse** (analyst.csv): parser raised ValueError: invalid literal for int() with base 10: ''
- **parse** (decaying.csv): parser raised AssertionError: catalog number wider than five digits
- **parse** (starlink-g15-27.tle): parser raised AssertionError: classification
- **parse** (starlink-g15-27.csv): parser raised AssertionError: 

### `tle-vs-omm-precision-loss`

- **parse** (analyst.tle): parser raised ValueError: invalid literal for int() with base 10: '  '
- **parse** (analyst.csv): parser raised ValueError: invalid literal for int() with base 10: ''
- **parse** (decaying.csv): parser raised AssertionError: catalog number wider than five digits
- **parse** (starlink-g15-27.tle): parser raised AssertionError: classification
- **parse** (starlink-g15-27.csv): parser raised AssertionError: 

### `omm-xml-schema`

- **parse** (saramago-first.xml): parser raised AssertionError: catalog number wider than five digits
- **parse** (analyst.xml): parser raised TypeError: 'NoneType' object is not subscriptable
- **parse** (starlink-g15-27.xml): parser raised AssertionError: 

### `alpha5-encoding-vectors`

- **alpha5-decode** (alpha5.json): A0000 -> raised ValueError (expected 100000); E8493 -> raised ValueError (expected 148493); J2931 -> raised ValueError (expected 182931); P4018 -> raised ValueError (expected 234018); W1928 -> raised ValueError (expected 301928); Z9999 -> raised ValueError (expected 339999); A0000 -> raised ValueError (expected 100000); A9999 -> raised ValueError (expected 109999)
- **alpha5-encode** (alpha5.json): 100000 -> '100000' (expected 'A0000'); 148493 -> '148493' (expected 'E8493'); 182931 -> '182931' (expected 'J2931'); 234018 -> '234018' (expected 'P4018'); 301928 -> '301928' (expected 'W1928'); 339999 -> '339999' (expected 'Z9999'); 100000 -> '100000' (expected 'A0000'); 109999 -> '109999' (expected 'A9999')
- **ccsds-epoch-strings** (ccsds-epoch-strings.json): valid '2020-064T10:34:41.4264' rejected (ValueError); valid '2020-065T16:00:00' rejected (ValueError); valid '2002-204T15:56:23Z' rejected (ValueError); valid '2001-11-06T11:17:33' rejected (ValueError); valid '1998-11-20T06:49:59.999808Z' rejected (ValueError); valid '2016-12-31T23:59:60' rejected (ValueError)
- **catalog-number-is-integer** (norad-cat-id-text.json): '1000000000' accepted as 1000000000 (should be rejected: ten digits exceed 'up to nine digits'; schema xsd:integer would accept it, the standard's text does not)

### `alpha5-tle-derived`

- **parse** (alpha5-A-100000-saramago-first.tle): parser raised ValueError: invalid literal for int() with base 10: 'A0000'
- **parse** (alpha5-T-270449-analyst-first.tle): parser raised ValueError: invalid literal for int() with base 10: 'T0449'
- **parse** (alpha5-A-last-30-days-snapshot.tle): parser raised ValueError: invalid literal for int() with base 10: 'A0404'
- **parse** (alpha5-T-analyst-27xxxx-snapshot.tle): parser raised ValueError: invalid literal for int() with base 10: 'T0000'

### `kvn-syntax-variants`

- **parse** (v02-day-of-year-epoch-Z.kvn): parser raised ValueError: time data '1998-324T06:49:59.999808Z' does not match format '%Y-%m-%dT%H:%M:%S.%f'
- **parse** (v03-units-brackets-leading-zeros.kvn): parser raised ValueError: could not convert string to float: '16.05064833 [rev/day]'
- **parse** (v04-comments-blank-lines-whitespace-LF.kvn): parser raised ValueError: not enough values to unpack (expected 2, got 1)
- **parse** (v05-omm-3.0-header-optional-keywords-omitted.kvn): parser raised KeyError: 'NORAD_CAT_ID'


## python-sgp4 2.27 through sgp4.omm / twoline2rv: what failed and why

### `analyst-objects`

- **parse** (analyst.xml): parser raised TypeError: 'NoneType' object is not subscriptable

### `nine-digit-supgp-launch-nominals`

- **parse** (starlink-38381-799501621.csv): parser raised ValueError: satellite number cannot exceed 339999, whose Alpha 5 encoding is 'Z9999'

### `supgp-celestrak-classification-c`

- **values** (starlink-g15-27.csv): value mismatch (details withheld: SupGP-derived values are not published, D-049)
- **classification-c** (starlink-g15-27.csv): C not preserved for [72000, 72001]

### `csv-json-omitted-mandatory-fields`

- **parse** (starlink-38381-799501621.csv): parser raised ValueError: satellite number cannot exceed 339999, whose Alpha 5 encoding is 'Z9999'

### `omm-xml-schema`

- **parse** (analyst.xml): parser raised TypeError: 'NoneType' object is not subscriptable
- **parse** (starlink-38381-799501621.xml): parser raised ValueError: satellite number cannot exceed 339999, whose Alpha 5 encoding is 'Z9999'

### `alpha5-encoding-vectors`

- **alpha5-decode** (alpha5.json): I0000 accepted as 180000 (should be rejected: letter I is never used); O1234 accepted as 231234 (should be rejected: letter O is never used); a0000 accepted as 400000 (should be rejected: lowercase is not defined by Space-Track; a lenient decoder that accepts it disagrees with a strict one); A000 accepted as 100000 (should be rejected: field must be five characters)
- **alpha5-encode** (alpha5.json): -1 encoded as '-0001' (should be rejected: negative)

## How to read this

- `parse` failures mean the parser raised on real provider bytes; the detail carries the exception.
- `values` failures list the first mismatching fields against the frozen expected values (snapshot) or the reference reader (live).
- `not-exercised` means the data needed for that check was not present in the fetched snapshot (for example no nine-digit ids outside the days after a launch).
- Re-run for your own parser: `python -m gpconf run --adapter your.module:Parser` (see README).
