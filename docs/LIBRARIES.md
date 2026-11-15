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
| [SGP.NET](https://github.com/parzivail/SGP.NET) (C#) | Alpha-5 (#35) and KVN day-of-year epochs and units (#48), fixed by this project's #47 and #49 (merged, not yet released) |
| [akhenakh/sgp4](https://github.com/akhenakh/sgp4) (Go) | Alpha-5 refused and type 4 propagated (#16), fixed by the maintainer in v1.0.4 |
| [sgp4 crate](https://github.com/neuromorphicsystems/sgp4) (Rust) | type 4 propagated as SGP4 (#23), open |
| [brahe](https://github.com/duncaneddy/brahe) (Python/Rust) | four OMM and catalog-id findings (#620), open |
| [SGPKit / swift-sgp4](https://github.com/csanfilippo/swift-sgp4) (Swift) | six-digit ids refused (#4), fixed in 4.1.0; one bad set loses the file (#16), fixed by the maintainer's #17 (merged 2026-11-14, not yet released) |
| [SatelliteKit](https://github.com/gavineadie/SatelliteKit) (Swift) | B* exponent (#16, a fix in review as #17) and the deep-space Lyddane check (#24), open |
| [Basilisk](https://github.com/AVSLab/basilisk) | CelesTrak's KVN theory name skipped (#1673), a fix in review as #1675 |
| [satkit](https://github.com/ssmichael1/satkit) | one bad set drops the whole file (#286), open |
| [satvis](https://github.com/anttikuosmanen-rgb/satvis) | element set 999 written for 0 (#84), fixed by the maintainer on master |
| [strf](https://github.com/cbassa/strf) | a hardening suggestion, not a bug report: no range check above 339999 (#88), a fix in review as #89 |

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
