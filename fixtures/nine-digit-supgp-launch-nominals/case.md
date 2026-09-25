# nine-digit-supgp-launch-nominals

Nine-digit catalog numbers: launch nominals of the 18th Space Defense Squadron (18 SDS), 7995016xx, in CelesTrak SupGP data

## What it tests

- 9-digit-catalog-number
- tle-unavailable-above-99999

## How to read a failure

Nine-digit ids exist today only in CelesTrak SupGP launch nominals, for roughly a week after a launch. A parser must accept 799501621 as an integer in CSV/JSON/XML/KVN; the TLE format cannot carry it. python-sgp4 2.27 (and Skyfield through it) raise ValueError on these records because they store the catalog number as an Alpha-5 string. If your fetch finds no nine-digit ids, the case reports that state instead of failing.

## Checks

- **nine-digit-ids-parse** — NORAD_CAT_ID values >= 100000000 parse and round-trip as integers in CSV, JSON, XML and KVN.
- **catalog-number-is-integer** — NORAD_CAT_ID parses as an integer in every OMM format, including values of six and nine digits, and a ten-digit value is rejected (CCSDS allows up to nine digits); leading zeros and an explicit '+' are legal in KVN.
- **omm-formats-agree** — For the same object and snapshot, CSV, JSON, XML and KVN yield identical canonical values for every OMM keyword present in all of them.
- **tle-format-omits-ids-above-99999** — A TLE/3LE/2LE request returns only objects with catalog numbers below 100000; if none qualify the response is HTTP 404 'No GP data found'.
- **empty-answer-yields-no-records** — A provider answer that carries no data (HTTP 404, body 'No GP data found' or 'No SupGP data found') is an empty but valid result: handed to the parser, it yields zero records and no error. An error here collapses 'nothing to load' into 'unreadable' (D-143).
- **supgp-extra-keys-tolerated** — SupGP CSV/JSON add non-OMM keys (RMS, DATA_SOURCE); parsers must ignore unknown keys rather than fail.
- **classification-c** — CLASSIFICATION_TYPE may be 'C' (CelesTrak supplemental) rather than 'U'.

## Coverage

Provides:

- one 9-digit object (799501621) in CSV, JSON, XML and KVN; TLE request -> 404 'No SupGP data found'
- 27 nine-digit ids 799501621-799501647 in the full Starlink SupGP file at the snapshot

Gaps (stated explicitly for this case):

- perishable: nominals exist only for roughly 5-8 days after a launch (CelesTrak); a user's fetch may contain none, in which case the check nine-digit-ids-parse reports not-exercised rather than failing
- no 9-digit id exists in 18 SDS GP data; only SupGP
- identity over time is out of scope, stated here as an open question: a nine-digit id is a launch nominal that CelesTrak serves "for the typical 5-8 days between launch and when 18 SDS starts releasing GP data" (docs/RESEARCH.md, TLE Retriever help quotation), after which the same object is expected in GP data under a catalog number of 100000 or above [inferred from that statement and "all newly cataloged objects will have 6-digit catalog numbers of 100000+"; no source states how the two records are linked]. The corpus checks that both forms parse (this case; six-digit ids in six-digit-omm-saramago and tle-omits-six-digit-objects) and holds no object in both: the 27 nominals captured on 2026-09-21 belong to launch 2026-219 (epochs 2026-09-20), and the last-30-days group fetched the same day lists launches 2026-156 to 2026-220 but not 2026-219 [tested]. What a tracker should store as the stable key across the change, and how a nominal's history merges into the catalogued object's, the corpus cannot say: it has no ground truth for the correlation, and the one link it observed, OBJECT_ID, is not one-to-one at this stage, since the placeholders 72000 and 72001 carry 2026-219A and 2026-219B and so do two of the per-satellite nominals [tested]. That is a data-relationship question for the provider's documentation, not a parsing property a fixture can freeze, which is why it is out of scope rather than missing

## Library behaviour observed (docs/CROSSCHECK.md)

- python-sgp4 2.27 sgp4.omm.initialize and Skyfield 1.55 EarthSatellite.from_omm raise ValueError('satellite number cannot exceed 339999') for every nine-digit record: 28 distinct records (27 in the full Starlink SupGP file plus one single-object query), 29 file-records counting that object's CSV and XML renderings separately.

## Ambiguities recorded

- **supgp-extra-keys** — SupGP CSV/JSON carry RMS and DATA_SOURCE, which are not OMM keywords (CCSDS 7.9.2.2 allows only Table 4-x keywords in an OMM); CelesTrak's CSV/JSON are OMM-keyword-based formats, not OMM instances, so this is a format extension rather than a violation. Parsers must tolerate unknown keys.
- **supgp-redistribution** — SupGP data derives from operator-provided data (some explicitly 'with permission' to CelesTrak). Under the corpus design no raw bytes are shipped; the snapshot values for one SupGP record are published as a dated reference and may be removed by the owner before publication.
- **tle-epoch-resolution** — The TLE epoch has 1e-8 day (864 microsecond) resolution. CelesTrak GP epochs convert exactly between the two representations; SupGP epochs do not (86 microsecond difference observed), so a TLE->OMM epoch comparison needs a tolerance of half the TLE resolution.

## Sources

The `raw/` files below are not in the repository: `tools/fetch.py` creates them on your machine, one request per URL under CelesTrak's usage policy, and until they exist the runner reports this case's checks as skipped, not failed.

| file | tier | HTTP | bytes | retrieved (UTC) | sha256 |
|---|---|---|---|---|---|
| `fixtures/nine-digit-supgp-launch-nominals/raw/starlink-38381-799501621.csv` | live | 200 | 407 | 2026-09-21T00:14:18Z | `6a44cde5358a4e30…` |
| `fixtures/nine-digit-supgp-launch-nominals/raw/starlink-38381-799501621.json` | live | 200 | 462 | 2026-09-21T00:14:20Z | `d8fdca20c5e39499…` |
| `fixtures/nine-digit-supgp-launch-nominals/raw/starlink-38381-799501621.xml` | live | 200 | 1206 | 2026-09-21T00:14:23Z | `60322eac8ef71de2…` |
| `fixtures/nine-digit-supgp-launch-nominals/raw/starlink-38381-799501621.kvn` | live | 200 | 634 | 2026-09-21T00:14:25Z | `9bb04dc1bdcedb21…` |
| `fixtures/nine-digit-supgp-launch-nominals/raw/starlink-38381-799501621.tle` | live | 404, expected: the body is "No SupGP data found" | 19 | 2026-09-21T00:14:27Z | `08ed5e8c54339ed1…` |
| `fixtures/nine-digit-supgp-launch-nominals/raw/starlink-all.csv` | live | 200 | 1802376 | 2026-09-21T00:11:59Z | `762cac2d33b68de6…` |

URLs (each requested once when the fixtures were built):

- <https://celestrak.org/NORAD/elements/supplemental/sup-gp.php?CATNR=799501621&FORMAT=CSV>
- <https://celestrak.org/NORAD/elements/supplemental/sup-gp.php?CATNR=799501621&FORMAT=JSON>
- <https://celestrak.org/NORAD/elements/supplemental/sup-gp.php?CATNR=799501621&FORMAT=KVN>
- <https://celestrak.org/NORAD/elements/supplemental/sup-gp.php?CATNR=799501621&FORMAT=TLE>
- <https://celestrak.org/NORAD/elements/supplemental/sup-gp.php?CATNR=799501621&FORMAT=XML>
- <https://celestrak.org/NORAD/elements/supplemental/sup-gp.php?FILE=starlink&FORMAT=CSV>

Expected values: `fixtures/nine-digit-supgp-launch-nominals/expected.json` (schema_version 1.0).
