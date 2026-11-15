# ephemeris-type-4-refused

An SGP4-XP element set (ephemeris type 4) is refused, never propagated as SGP4; its type-0 twin propagates

## Evidence basis

- Ephemeris type 4 marks an element set made for SGP4-XP, whose model and drag term differ from SGP4's; SGP4 run on one gives a position that looks right, with no error code. Vallado's C++ at the recipe's pin does not initialise a set whose type is not 0 ('the ephtype must be 0 for SGP4. SGP4-XP uses 4', SGP4.cpp's twoline2rv), so its propagation answers an error code at every step; python-sgp4 2.27 reads the type and propagates the set exactly as type 0, from the TLE and from OMM CSV (measured 2026-11-09; the owner's report https://github.com/brandon-rhodes/python-sgp4/issues/178).
- The inputs are set 20453 from derived/propagation-twins/twins.tle, which the corpus already ships, with line 1 column 63 set to 4 and the checksum recomputed, and OMM files whose values are exactly the TLE's; MEAN_ELEMENT_THEORY = SGP4-XP in one KVN is the corpus's spelling, labelled synthetic: how a provider writes it is not read, and the case grades EPHEMERIS_TYPE alone (the owner's ruling, 2026-11-01).

## What it tests

- sgp4-propagation
- ephemeris-type

## How to read a failure

A failing type-4 item names each file whose set the hook propagated as SGP4: the finding the case is for, an SGP4-XP set turned into positions that look right. A failing twins item with a passing type-4 item is a hook that refuses everything, or one whose type-0 answers miss the twins' reference. Skip means no propagate hook, none for any format, or an adapter that claims SGP4-XP (the type-4 item only).

## Checks

- **type4-not-propagated** — Set 20453 with EPHEMERIS_TYPE 4 (an SGP4-XP element set) as TLE, OMM CSV, JSON, XML and KVN, and a KVN also saying MEAN_ELEMENT_THEORY = SGP4-XP (the corpus's spelling, synthetic), each through the propagate hook: a position at any step fails the file, since SGP4 propagates such a set to positions that look right and are not, and so do error codes stamped beside positions; a refusal passes (a raise, Unsupported for the type-4 set alone, a refusal from parse while its twin is read, or an SGP4 error code at every step with no position, as Vallado's C++ answers). An adapter that sets propagates_sgp4_xp = True is not graded on it (the owner's ruling, 2026-11-01; D-409).
- **type4-twins-propagate** — Each type-4 file's twin, the same values with EPHEMERIS_TYPE 0, through the same hook: it must propagate within 2e-7 km and km/s of the twins' reference vectors (vectors/propagation-twins.json, D-406), its codes exact, so a hook that refuses every set fails here, and so does Unsupported for the twin alone (D-205, D-280); a format unsupported for both files is skipped and named (D-409).

## Coverage

Provides:

- one near-earth set with a non-zero BSTAR, type 4 and type 0, in TLE and the four OMM formats, six times each

Gaps (stated explicitly for this case):

- one set; SGP4-XP itself is not graded: gpconf has no SGP4-XP reference, and an adapter that claims it is not graded on the type-4 files
- ephemeris types 1 to 3 out of scope for 0.9.0 (the owner's ruling)
- an adapter's claim of SGP4-XP is taken as given: a library that claims it and propagates as SGP4 is not caught
- beside an error code at every step, only three finite numbers not all zero count as a position: SGP4's positions sent as strings are not caught
- WGS-72 and opsmode 'i' only for the twins

## Ambiguities recorded

- none

## Sources

Every file of this case ships with the repository; nothing is fetched.

| file | tier | HTTP | bytes | retrieved (UTC) | sha256 |
|---|---|---|---|---|---|
| `derived/ephemeris-type-4/type4.tle` | stable | none: derived file shipped with the repository | 168 | generated 2026-11-10T02:56:43Z | `01859a919ae42f90…` |
| `derived/ephemeris-type-4/type4.csv` | stable | none: derived file shipped with the repository | 463 | generated 2026-11-10T02:56:43Z | `51a2fa37f61468d5…` |
| `derived/ephemeris-type-4/type4.json` | stable | none: derived file shipped with the repository | 524 | generated 2026-11-10T02:56:43Z | `3512f770263c7c6c…` |
| `derived/ephemeris-type-4/type4.xml` | stable | none: derived file shipped with the repository | 1123 | generated 2026-11-10T02:56:43Z | `1ff0551c972ef2cd…` |
| `derived/ephemeris-type-4/type4.kvn` | stable | none: derived file shipped with the repository | 788 | generated 2026-11-10T02:56:43Z | `3cb851a38916465a…` |
| `derived/ephemeris-type-4/type4-sgp4-xp.kvn` | stable | none: specification vectors shipped with the repository | 791 | n/a (never fetched) | `d7b7abfec445374a…` |
| `derived/ephemeris-type-4/type0.tle` | stable | none: specification vectors shipped with the repository | 168 | n/a (never fetched) | `b3ad06c19a98463b…` |
| `derived/ephemeris-type-4/type0.csv` | stable | none: specification vectors shipped with the repository | 463 | n/a (never fetched) | `93fd3b83d74dc0b4…` |
| `derived/ephemeris-type-4/type0.json` | stable | none: specification vectors shipped with the repository | 524 | n/a (never fetched) | `850bdced13c2e776…` |
| `derived/ephemeris-type-4/type0.xml` | stable | none: specification vectors shipped with the repository | 1123 | n/a (never fetched) | `070c332fa9623e0d…` |
| `derived/ephemeris-type-4/type0.kvn` | stable | none: specification vectors shipped with the repository | 788 | n/a (never fetched) | `137e315bd2ce7a6d…` |
| `vectors/propagation-twins.json` | stable | none: the corpus's manifest, shipped with the repository | 12895 | n/a (never fetched) | `6fa8c3717f3b91f7…` |

Expected values: `fixtures/ephemeris-type-4-refused/expected.json` (schema_version 1.0).
