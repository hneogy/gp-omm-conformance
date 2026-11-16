# Libraries against gpconf

One line per library: the version gpconf ran, what it found, and where the reports stand. A result is about one
version on one date, not a verdict on a project, and many of these findings have since been fixed upstream. The site's
[Library status](https://gpconf.neogy.dev/library/) has each run in full, and its
[upstream record](https://gpconf.neogy.dev/upstream/) every report with who fixed it.

Most of the early findings are Alpha-5 TLE failures. CelesTrak serves no Alpha-5 at all, so a program that takes its
TLEs from CelesTrak does not meet them today; they matter to anyone reading Space-Track TLEs, and to anyone who will.

## Published runs

| library | version run (date, corpus) | in one line | reports, as of 2026-11-10 |
|---|---|---|---|
| [python-sgp4](https://github.com/brandon-rhodes/python-sgp4) | 2.27 (2026-10-11, 0.7.0) | Reads TLE and three OMM formats well; refuses nine-digit ids in OMM, and its writer puts I and O in Alpha-5 fields | empty OBJECT_ID fixed by this project's #172 (merged, not yet released); #173 writer letters, #178 type 4 propagated, #179 line numbers (out of scope by the maintainer's choice) |
| [satellite.js](https://github.com/shashwatak/satellite-js) | 7.1.0 (2026-09-27, 0.4.0) | OMM JSON epochs cut to milliseconds, the Alpha-5 field never decoded, a letter in a number read with no error | all three fixed by this project's #186, #187 and #197 (merged; released in 7.2.0, 2026-11-11) |
| [Gpredict](https://github.com/csete/gpredict) | 2.6 (2026-09-27, 0.4.0) | Mean motion lost its last digit on every record; a letter in the epoch field accepted; Alpha-5 read as 0 | mean motion fixed by this project's #428 and the epoch by Wahaj18's #430, both released in v2.7 |
| [gods-eye-view](https://github.com/bilawalsidhu/gods-eye-view) | 0.2.1 (2026-10-03, 0.5.0) | Alpha-5 satellites collapsed onto one entry; one set missing a line dropped the rest of its group | fixed by this project's #767 and xiehuanyi's #936, released in v0.3.0 |
| [tle.js](https://github.com/davidcalhoun/tle.js) | 5.0.3 (2026-09-27, 0.4.0) | Alpha-5 fields gave NaN, two-digit years pivoted at 50; a letter in the epoch field read with no error | Alpha-5 and the pivot fixed by this project's #64, released in v6.0.0; #63 open |
| [astroz](https://github.com/ATTron/astroz) | 0.14.0 (2026-09-27, 0.4.0) | Alpha-5 and epoch fixed after the report; keeps no object name | fixed by ATTron in v0.13.0 (#97, #98) |
| [libsgp4](https://github.com/dnwrnr/sgp4) | 3.0 (2026-09-27, 0.4.0) | Alpha-5 correct in v3.0; CelesTrak's SupGP CSV refused whole; some epochs 8 µs off | Alpha-5 fixed by dnwrnr in v3.0; #45 open |
| [PyEphem](https://github.com/brandon-rhodes/pyephem) | 4.2.1 (2026-09-27, 0.4.0) | Alpha-5 fields read as catalog number 0, silently; a letter in a number read with no error | #296 open; #297 closed without a change, by the maintainer's choice for a legacy library |
| [SatDump](https://github.com/SatDump/SatDump) | 1.2.2 and master (2026-09-24, 0.2.1) | Alpha-5 sets dropped silently; master's CSV reader refuses SupGP files whole | #1221 closed by this project after the maintainers said both fixes were planned |
| [GPKit](https://github.com/hneogy/GPKit) (by gpconf's author) | 1.3.0 (2026-11-10, 0.9.0 in development) | 21 cases: 17 pass, 2 within tolerance, 1 fails, 1 is a data check; the failure is `sgp4-ver-propagation` on one very eccentric set, from GPKit's exact epoch against Vallado's rounded one. With its opt-in `.vallado` epoch, reported apart: none fails | — |

GPKit is maintained by gpconf's author; its results are graded exactly like every other library's.

## Run and reported, not yet published as rows

These libraries were run and their findings reported to their maintainers on the dates their reports carry (September to
November 2026); their rows are published with gpconf 0.9.0's re-measure, at the version current then.

| library | reports |
|---|---|
| [SGP.NET](https://github.com/parzivail/SGP.NET) (C#) | Alpha-5 (#35) and KVN day-of-year epochs and units (#48), fixed by this project's #47 and #49, released in v1.6.1 |
| [akhenakh/sgp4](https://github.com/akhenakh/sgp4) (Go) | Alpha-5 refused and type 4 propagated (#16), fixed by the maintainer in v1.0.4 |
| [sgp4 crate](https://github.com/neuromorphicsystems/sgp4) (Rust) | type 4 propagated as SGP4 (#23), open |
| [brahe](https://github.com/duncaneddy/brahe) (Python/Rust) | four OMM and catalog-id findings (#620), open |
| [SGPKit / swift-sgp4](https://github.com/csanfilippo/swift-sgp4) (Swift) | six-digit ids refused (#4), fixed in 4.1.0; one bad set loses the file (#16), fixed by the maintainer's #17, released in 4.5.0 |
| [SatelliteKit](https://github.com/gavineadie/SatelliteKit) (Swift) | B* exponent (#16, a fix in review as #17) and the deep-space Lyddane check (#24), open |
| [Basilisk](https://github.com/AVSLab/basilisk) | CelesTrak's KVN theory name skipped (#1673), fixed by the maintainer's #1675 (merged, not yet released); type 4 sets run as SGP4, and one bad set fails the whole file (#1676), fixed by this project's #1677 (merged, not yet released) |
| [satkit](https://github.com/ssmichael1/satkit) | one bad set drops the whole file (#286), fixed by the maintainer's #287 (`on_error`, the default unchanged), released in v0.24.3 |
| [satvis](https://github.com/anttikuosmanen-rgb/satvis) | element set 999 written for 0 (#84), fixed by the maintainer on master |
| [strf](https://github.com/cbassa/strf) | a hardening suggestion, not a bug report: no range check above 339999 (#88), a fix in review as #89 |

## Every finding reported upstream

The full list, not highlights (D-552), the same table as the README's: generated from the maintainer's upstream record (`docs/upstream/table.json`) and checked against GitHub by `tools/check_upstream_table.py`, in CI on every change and weekly. A link the record can only infer says so. Findings not yet reported upstream are not listed.

<!-- upstream-table:begin (generated by tools/upstream_table.py from docs/upstream/table.json; do not edit) -->
| library | finding | status | proof | release | date |
|---|---|---|---|---|---|
| python-sgp4 | an empty `OBJECT_ID` in OMM XML raised `TypeError` | merged, not yet released | [PR #172](https://github.com/brandon-rhodes/python-sgp4/pull/172) |  | 2026-09-24 (merged) |
| satellite.js | OMM JSON epochs truncated to the millisecond | released | [PR #186](https://github.com/shashwatak/satellite-js/pull/186) | [7.2.0](https://github.com/shashwatak/satellite-js/releases/tag/7.2.0) | 2026-09-26 (merged) |
| satellite.js | no decoder for Alpha-5 catalog fields | released | [PR #187](https://github.com/shashwatak/satellite-js/pull/187) | [7.2.0](https://github.com/shashwatak/satellite-js/releases/tag/7.2.0) | 2026-09-28 (merged) |
| satellite.js | a stray letter in a TLE field read with no error | released | [PR #197](https://github.com/shashwatak/satellite-js/pull/197) | [7.2.0](https://github.com/shashwatak/satellite-js/releases/tag/7.2.0) | 2026-10-14 (merged) |
| Gpredict | the mean motion lost its last digit on every record | released | [PR #428](https://github.com/csete/gpredict/pull/428) | [v2.7](https://github.com/csete/gpredict/releases/tag/v2.7) | 2026-10-08 (merged) |
| gods-eye-view | Alpha-5 satellites collapsed onto one entry keyed NaN, the rest dropped | released | [PR #767](https://github.com/bilawalsidhu/gods-eye-view/pull/767) | [v0.3.0](https://github.com/bilawalsidhu/gods-eye-view/releases/tag/v0.3.0) | 2026-10-17 (merged) |
| tle.js | Alpha-5 fields gave NaN; two-digit years pivoted at 50 | released | [PR #64](https://github.com/davidcalhoun/tle.js/pull/64) | [v6.0.0](https://github.com/davidcalhoun/tle.js/releases/tag/v6.0.0) | 2026-10-19 (merged) |
| SGP.NET | Alpha-5 TLEs refused (reproduced and fix verified with gpconf) | released | [PR #47](https://github.com/parzivail/SGP.NET/pull/47) | [v1.6.1](https://github.com/parzivail/SGP.NET/releases/tag/v1.6.1) | 2026-11-10 (merged) |
| SGP.NET | `OmmKvnParser` refused a day-of-year EPOCH and a unit in brackets | released | [PR #49](https://github.com/parzivail/SGP.NET/pull/49) | [v1.6.1](https://github.com/parzivail/SGP.NET/releases/tag/v1.6.1) | 2026-11-10 (merged) |
| Basilisk | `satTle2elem` runs type 4 sets as SGP4, and a blank designator, a name starting with 1 or 2, or one bad set fails the whole file | merged, not yet released | [PR #1677](https://github.com/AVSLab/basilisk/pull/1677) |  | 2026-11-12 (merged) |
| astroz | Alpha-5 decoded without skipping I and O | released | [PR #99](https://github.com/ATTron/astroz/pull/99) | [v0.13.0](https://github.com/ATTron/astroz/releases/tag/v0.13.0) | 2026-09-26 (merged) |
| astroz | `Tle.epoch` off by hundreds of days | released | [PR #99](https://github.com/ATTron/astroz/pull/99) | [v0.13.0](https://github.com/ATTron/astroz/releases/tag/v0.13.0) | 2026-09-26 (merged) |
| astroz | seconds passed through a half-precision float, up to 15.5 ms off | released | [PR #104](https://github.com/ATTron/astroz/pull/104) | [v0.14.0](https://github.com/ATTron/astroz/releases/tag/v0.14.0) | 2026-09-26 (merged) |
| libsgp4 | every Alpha-5 field refused (results posted on the open PR) | released | [PR #46](https://github.com/dnwrnr/sgp4/pull/46) | [v3.0](https://github.com/dnwrnr/sgp4/releases/tag/v3.0) | 2026-09-26 (merged) |
| Gpredict | a letter in the epoch field accepted | released | [PR #430](https://github.com/csete/gpredict/pull/430) | [v2.7](https://github.com/csete/gpredict/releases/tag/v2.7) | 2026-10-10 (merged) |
| gods-eye-view | a set missing a line dropped the rest of its group | released | [PR #936](https://github.com/bilawalsidhu/gods-eye-view/pull/936) | [v0.3.0](https://github.com/bilawalsidhu/gods-eye-view/releases/tag/v0.3.0) | 2026-10-12 (merged) |
| SGPKit (swift-sgp4) | satellites numbered 100000 and up refused | released | [4.1.0 release notes](https://github.com/csanfilippo/swift-sgp4/releases/tag/4.1.0); likely fixing commit (inferred: only code change in 4.1.0, no commit references #4): [a416eea](https://github.com/csanfilippo/swift-sgp4/commit/a416eea220625c55a1a9cff5549643c395359ef0) | [4.1.0](https://github.com/csanfilippo/swift-sgp4/releases/tag/4.1.0) | 2026-10-11 (released) |
| satvis | `ommToTle` wrote element set 999 for `ELEMENT_SET_NO` 0 | merged; the project has no releases | [PR #85](https://github.com/anttikuosmanen-rgb/satvis/pull/85) |  | 2026-11-10 (merged) |
| akhenakh/sgp4 | Alpha-5 catalog numbers refused; a type 4 TLE propagated as SGP4 | released | [44978c8](https://github.com/akhenakh/sgp4/commit/44978c8e5c175200f792451dbf924514e8e59500) | [v1.0.4](https://github.com/akhenakh/sgp4/releases/tag/v1.0.4) | 2026-11-10 (merged) |
| Basilisk | `satOmm2elem` skipped CelesTrak's KVN (`MEAN_ELEMENT_THEORY = SGP/SGP4`) | merged, not yet released | [PR #1675](https://github.com/AVSLab/basilisk/pull/1675) |  | 2026-11-11 (merged) |
| satkit | `TLE.from_lines` dropped a whole file for one bad set | released | [PR #287](https://github.com/ssmichael1/satkit/pull/287) | [v0.24.3](https://github.com/ssmichael1/satkit/releases/tag/v0.24.3) | 2026-11-11 (merged) |
| SGPKit (swift-sgp4) | `TLEDecoder.decodeCollection` dropped every TLE in a file for one bad set; found by gpconf (`corrupt-input`) | released | [PR #17](https://github.com/csanfilippo/swift-sgp4/pull/17) | [4.5.0](https://github.com/csanfilippo/swift-sgp4/releases/tag/4.5.0) | 2026-11-14 (merged) |
| CelesTrak's fundamentals-of-astrodynamics (SGP4 reference code) | `twoline2rv` reads an Alpha-5 field beginning with I or O as a five-digit number | merged, not yet released | [PR #175](https://github.com/CelesTrak/fundamentals-of-astrodynamics/pull/175) |  | 2026-11-15 (merged) |
| PyEphem | Alpha-5 fields read as catalog number 0, silently | open | [#296](https://github.com/brandon-rhodes/pyephem/issues/296) |  | 2026-09-25 (reported) |
| python-sgp4 | `Satrec.sgp4init` writes I and O as Alpha-5 letters | open | [#173](https://github.com/brandon-rhodes/python-sgp4/issues/173) |  | 2026-10-10 (reported) |
| python-sgp4 | a type 4 (SGP4-XP) TLE propagated as plain SGP4 | open | [#178](https://github.com/brandon-rhodes/python-sgp4/issues/178) |  | 2026-11-08 (reported) |
| python-sgp4 | line 2's catalog number not checked against line 1's | open | [#179](https://github.com/brandon-rhodes/python-sgp4/issues/179) |  | 2026-11-08 (reported) |
| CelesTrak's fundamentals-of-astrodynamics (SGP4 reference code) | `twoline2rv` returns the element set and revolution numbers with the checksum digit attached | open | [#174](https://github.com/CelesTrak/fundamentals-of-astrodynamics/issues/174) |  | 2026-10-08 (reported) |
| strf | no range check in `number_to_alpha5` above 339999 | open | [#88](https://github.com/cbassa/strf/issues/88) |  | 2026-09-23 (reported) |
| libsgp4 | epoch rounded by 8 µs; `FromCsv` reads stray microseconds | open | [#45](https://github.com/dnwrnr/sgp4/issues/45) |  | 2026-09-24 (reported) |
| tle.js | `getEpochDay()` reads up to a stray letter and `isValidTLE()` calls the TLE valid | open | [#63](https://github.com/davidcalhoun/tle.js/issues/63) |  | 2026-09-28 (reported) |
| SatelliteKit | B* read from a TLE as e-53 instead of e-05 | open | [#16](https://github.com/gavineadie/SatelliteKit/issues/16) |  | 2026-10-08 (reported) |
| SatelliteKit | deep-space Lyddane check on `abs(inclination)` where the reference SGP4 code's is signed | open | [#24](https://github.com/gavineadie/SatelliteKit/issues/24) |  | 2026-11-09 (reported) |
| brahe | `OMM.from_str` refuses CelesTrak's ndm-wrapped XML and KVN with an empty CREATION_DATE; `parse_norad_id("A+123")` accepted; Alpha-5 encoding below 100000 unpadded | open | [#620](https://github.com/duncaneddy/brahe/issues/620) |  | 2026-11-10 (reported) |
| sgp4 crate (Rust) | a type 4 (SGP4-XP) TLE propagated as plain SGP4 | open | [#23](https://github.com/neuromorphicsystems/sgp4/issues/23) |  | 2026-11-10 (reported) |
| PyEphem | a letter in the epoch field accepted and the epoch read up to it | declined | [#297](https://github.com/brandon-rhodes/pyephem/issues/297) |  | 2026-10-01 (closed) |
| SatDump | Alpha-5 sets dropped silently; SupGP CSV rejected whole on master | closed (maintainers said planned) | [#1221](https://github.com/SatDump/SatDump/issues/1221) |  | 2026-09-27 (closed) |
| python-sgp4 | nine-digit NORAD_CAT_ID refused by the OMM reader (reported by another user; gpconf tested the fix) | another user's report, open upstream | [#169](https://github.com/brandon-rhodes/python-sgp4/issues/169) |  | 2026-08-20 (reported) |

38 findings: 10 fixed by this project's pull requests, 13 by maintainers and contributors after this project's report, 12 still open, 3 others: 2 that ended another way and 1 another user's report; as of 2026-11-16.
<!-- upstream-table:end -->

## Known gaps

What this page does not tell you, so that nobody reads more into it than it holds:

- **Old corpus versions.** Most published rows were measured with corpus 0.2.1 to 0.5.0. Later releases added cases
  and stricter checks, so a row can read better than its library would today; every row is re-measured for 0.9.0.
- **Old library versions.** Several libraries have released fixes since their row was measured (satellite.js once it
  releases, Gpredict 2.7, gods-eye-view 0.3.0, tle.js 6.0.0, astroz, libsgp4 3.0). The row is the version it names.
- **Libraries not covered.** Orekit has a recipe and no run yet; many libraries have none. A library missing here
  has not been tested, which says nothing either way.
- **What gpconf does not test.** Space-Track data is never used; CelesTrak's files are fetched on your machine. There
  are no OCM, OEM or CDM cases yet. The propagation tier is new in 0.9.0: its Vallado case grades only where Vallado's
  verification files are on your machine (otherwise it is not exercised), and its other two cases use the corpus's own
  reference vectors.
- **One run per library.** A row is one run, on one machine, through gpconf's own harness or adapter for that
  library; a harness that reads a library wrongly would show as the library's fault. Each harness is in
  `harnesses/` or `gpconf/adapters/`, so it can be checked.
