# omm-xml-schema

CelesTrak OMM XML against the SANA schemas: valid as NDM/XML 2.0, invalid as 3.0 on the version attribute

## What it tests

- xml-schema

## How to read a failure

CelesTrak XML is valid NDM/XML 2.0 (schema set ndmxml-2.0.0, whose epoch pattern even accepts the empty CREATION_DATE) and invalid against the current 4.0.0/OMM 3.0 set solely because of the fixed version attribute. A validator pinned to the current schema rejects every CelesTrak file; a validator that follows the declared schemaLocation accepts them, but only as long as SANA keeps serving the 2.0.0 files at those direct URLs (the registry page no longer lists them; they resolved on 2026-09-21). The vendored copies under schemas/ remove that dependency for offline validation.

## Checks

- **xml-ndm-wrapper-omm-2.0** — CelesTrak XML has an <ndm> root containing one <omm> per record with id=CCSDS_OMM_VERS and version=2.0; CREATION_DATE and ORIGINATOR elements are present but empty.
- **omm-version-3-accepted** — CCSDS_OMM_VERS 3.0 messages (with CLASSIFICATION and MESSAGE_ID in the header) are accepted alongside 2.0.

## Coverage

Provides:

- 8 XML files validated against ndmxml-2.0.0 and ndmxml-4.0.0

Gaps (stated explicitly for this case):

- no CelesTrak XML with units attributes, comments or covariance exists; those constructs are covered only by the CCSDS examples and derived variants

## Ambiguities recorded

- **omm-version-2-vs-3** — CelesTrak declares OMM version 2.0 (Silver Book 2009) although the current standard is 3.0 (Blue Book 2023). The 2.0 XML schema set is still downloadable from SANA by direct URL; against the current 4.0.0/3.0 set the documents fail on the fixed version attribute.
- **empty-mandatory-header** — CCSDS Table 4-1 makes CREATION_DATE and ORIGINATOR mandatory; CelesTrak emits them empty in XML and blank in KVN. The 2.0 schema's epochType pattern accepts an empty string, so schema validation may pass; the KVN rule 7.5.1 is still violated.

## Sources

The `raw/` files below are not in the repository: `tools/fetch.py` creates them on your machine, one request per URL under CelesTrak's usage policy, and until they exist the runner reports this case's checks as skipped, not failed.

| file | tier | HTTP | bytes | retrieved (UTC) | sha256 |
|---|---|---|---|---|---|
| `fixtures/epoch-year-19xx/raw/iss-first.xml` | mixed | 200 | 1198 | 2026-09-21T00:43:41Z | `cdcfd5fbd9e8b476…` |
| `fixtures/baseline-iss-five-formats/raw/iss.xml` | mixed | 200 | 1208 | 2026-09-21T00:09:45Z | `1aea7dbbba3f0ce8…` |
| `fixtures/six-digit-omm-saramago/raw/saramago-first.xml` | mixed | 200 | 1204 | 2026-09-21T00:44:00Z | `c2523a59549f0e95…` |
| `fixtures/six-digit-omm-saramago/raw/saramago.xml` | mixed | 200 | 1205 | 2026-09-21T00:09:55Z | `763990333a9a4f48…` |
| `fixtures/analyst-objects/raw/analyst.xml` | mixed | 200 | 552351 | 2026-09-21T00:11:35Z | `8c76a7863573b288…` |
| `fixtures/analyst-objects/raw/analyst-270449-first.xml` | mixed | 200 | 1193 | 2026-09-21T00:44:15Z | `94c54614780dbe36…` |
| `fixtures/nine-digit-supgp-launch-nominals/raw/starlink-38381-799501621.xml` | mixed | 200 | 1206 | 2026-09-21T00:14:23Z | `60322eac8ef71de2…` |
| `fixtures/nine-digit-supgp-launch-nominals/raw/starlink-g15-27.xml` | mixed | 200 | 2201 | 2026-09-21T00:08:27Z | `92e227468743d56c…` |

URLs (each requested once when the fixtures were built):

- <https://celestrak.org/NORAD/elements/gp-first.php?CATNR=100000&FORMAT=XML>
- <https://celestrak.org/NORAD/elements/gp-first.php?CATNR=25544&FORMAT=XML>
- <https://celestrak.org/NORAD/elements/gp-first.php?CATNR=270449&FORMAT=XML>
- <https://celestrak.org/NORAD/elements/gp.php?CATNR=100000&FORMAT=XML>
- <https://celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=XML>
- <https://celestrak.org/NORAD/elements/gp.php?GROUP=analyst&FORMAT=XML>
- <https://celestrak.org/NORAD/elements/supplemental/sup-gp.php?CATNR=799501621&FORMAT=XML>
- <https://celestrak.org/NORAD/elements/supplemental/sup-gp.php?FILE=starlink-g15-27&FORMAT=XML>

Expected values: `fixtures/omm-xml-schema/expected.json` (schema_version 1.0).
