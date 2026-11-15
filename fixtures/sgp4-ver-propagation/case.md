# sgp4-ver-propagation

Propagation against Vallado's SGP4 verification file: 33 element sets, TEME position and velocity within 2e-7, SGP4 error codes exact

## Evidence basis

- The reference is Vallado, Crawford, Hujsak and Kelso's verification pair from the code accompanying AIAA 2006-6753: SGP4-VER.TLE (33 element sets, each with its run of minutes) and tcppver.out (the C++ driver's TEME position and velocity per step). gpconf ships neither file (D-388): it locates them (--sgp4-ver, else the installed python-sgp4 package, which carries both) and holds them to the corpus's manifest of their bytes before grading.
- The bar, 2e-7 km and km/s per component, is python-sgp4's own test bar for these files (the owner's ruling on lane C's question 5, 2026-11-01); python-sgp4 2.27 lands within 9.7e-8 km and 5e-10 km/s on all 33 (measured 2026-11-08), and with WGS-84 constants fails 32 of them.
- The error codes and the steps they come at are the corpus's own measurement, in the manifest (tools/make_vallado_manifest.py), cross-checked with python-sgp4's published list.

## What it tests

- sgp4-propagation

## How to read a failure

A failing position item names each step beyond 2e-7 km or km/s with its differences: a few thousandths of a kilometre means other constants (WGS-72-old) or an older formula, kilometres a wrong gravity model (WGS-84) or opsmode 'a', a whole set wrong a reading fault in the TLE. A failing code item names the step: an error before the reference's is a false decay, none where it errs a silent propagation (the library returns positions for an orbit SGP4 cannot represent). Not exercised means Vallado's files were not found with the corpus's bytes; skip means the parser has no propagate hook.

## Checks

- **sgp4-ver-positions** — Each of Vallado's 33 verification element sets (SGP4-VER.TLE, located on this machine and held to the corpus's manifest of its bytes; never shipped, D-388) propagated by the parser's propagate hook to the verification driver's times: every TEME position (km) and velocity (km/s) component within 2e-7 of tcppver.out, WGS-72 and opsmode 'i' only, the largest differences printed (D-401).
- **sgp4-ver-error-codes** — Where a verification run ends in an SGP4 error, the code is the reference's (measured by the corpus, in its manifest) at the step after the run's last printed line, and no step before it errs: a false decay and a silent propagation each fail (D-401).

## Coverage

Provides:

- 33 element sets: near-earth and deep-space, resonant and synchronous orbits, low perigee, high eccentricity, the branches SGP4-VER.TLE's comments name; 7 runs ending in an SGP4 error (codes 1, 1, 6, 6, 4, 3, 6), one of them at t = 0

Gaps (stated explicitly for this case):

- graded only where Vallado's files are on the machine (the hash manifest, D-388)
- WGS-72 and opsmode 'i' only; WGS-84 report-only, later (the owner's ruling, 2026-10-25)
- TLE input only: the TLE/OMM twins (D-406) and the ephemeris-type-4 case (D-409) are their own cases; fuzzing is gpconf fuzz, outside the cases (D-415)

## Ambiguities recorded

- none

## Sources

The graded files, Vallado's SGP4-VER.TLE and tcppver.out, ship nowhere: the runner locates them on your machine (--sgp4-ver DIR, or the installed python-sgp4 package) and uses them only when their bytes are the ones in the corpus's own manifest below, which ships (D-388, D-401).

| file | tier | HTTP | bytes | retrieved (UTC) | sha256 |
|---|---|---|---|---|---|
| `harnesses/vallado/reference-manifest.json` | stable | none: the corpus's manifest, shipped with the repository | 5732 | n/a (never fetched) | `e090af8edb3ee641…` |

Expected values: `fixtures/sgp4-ver-propagation/expected.json` (schema_version 1.0).
