# propagation-tle-omm-twins

Propagation from a TLE and from its exact OMM twin: seven shipped sets, the corpus's own reference vectors, within 2e-7

## Evidence basis

- The sets are ones the corpus already ships (derived/corrupt-input/unedited-sets.tle: 25544 at its 1998 epoch, 20453, 69999; derived/alpha5-tle: 100000, 100686, 100530, 270354), copied byte for byte: near-earth and deep-space, low and high eccentricity, Alpha-5 ids. Each OMM CSV twin holds exactly the TLE's values as the corpus's reference reader reads them, the epoch's eight-digit day fraction a whole number of 864 microseconds (tools/derive_twins.py).
- The reference vectors are the corpus's own (the owner's ruling on lane C's question 3, 2026-11-01): SGP4's output by Vallado's C++ (tools/sgp4_reference_vectors.cpp, built against SGP4.cpp at the recipe's pin), WGS-72 and opsmode 'i', cross-checked with python-sgp4 2.27 at every step.

## What it tests

- sgp4-propagation
- tle-omm-equivalence

## How to read a failure

A failing TLE item names each step beyond 2e-7 against the corpus's reference vectors, as the Vallado case does; a failing OMM item with a passing TLE item is the finding the case is for: the library's OMM path reads a value otherwise than its TLE path (the angles in radians, the mean motion in another unit, BSTAR scaled, the epoch shifted, which only the two deep-space sets show). The agreement item compares the two answers directly. Skip means no propagate hook, or none for CSV.

## Checks

- **twins-tle-positions** — Each of seven shipped TLE sets (derived/propagation-twins/twins.tle) through the parser's propagate hook at six times (-1 day, -1 hour, 0, +1 hour, +1 day, +7 days): every TEME position and velocity component within 2e-7 km and km/s of the corpus's own reference vectors (vectors/propagation-twins.json: SGP4 by Vallado's C++, WGS-72, opsmode 'i', cross-checked with python-sgp4), every SGP4 error code exact (every reference step propagates, so a false decay is what the codes catch). The TLE is sent as its two element lines (D-406).
- **twins-omm-positions** — The same for each set's OMM CSV twin (derived/propagation-twins/twins.csv), whose values are exactly the TLE's: a library whose OMM path reads the angles, the mean motion, the eccentricity or BSTAR otherwise than its TLE path fails here, and the epoch through the two deep-space sets (100530, 270354) only, since near-earth SGP4 in TEME does not depend on it (D-406).
- **twins-tle-omm-agree** — For each set the parser propagated from both renderings, its TLE and OMM answers within 2e-7 of each other at every step, their codes the same (D-406).

## Coverage

Provides:

- 7 TLE sets and their exact OMM CSV twins, 6 times each, near-earth and deep-space

Gaps (stated explicitly for this case):

- OMM CSV only: the other OMM formats' twins are later
- seven shipped sets, not the design's 33 SGP4-VER sets (never shipped, D-388) or the 304 provider pairs, whose OMM carries more digits than the TLE and which are to be reported, never graded (lane C's design section 3)
- the epoch is graded through the two deep-space sets only; MEAN_MOTION_DOT and MEAN_MOTION_DDOT, which SGP4 does not use, not at all
- every reference step propagates: the codes catch a false decay, not a missing error
- WGS-72 and opsmode 'i' only

## Ambiguities recorded

- none

## Sources

Every file of this case ships with the repository; nothing is fetched.

| file | tier | HTTP | bytes | retrieved (UTC) | sha256 |
|---|---|---|---|---|---|
| `derived/propagation-twins/twins.tle` | stable | none: derived file shipped with the repository | 1176 | generated 2026-11-08T12:12:14Z | `a764b0f23df5399c…` |
| `derived/propagation-twins/twins.csv` | stable | none: derived file shipped with the repository | 1248 | generated 2026-11-08T12:12:14Z | `16c5ba64b47f7a6f…` |
| `vectors/propagation-twins.json` | stable | none: the corpus's manifest, shipped with the repository | 12895 | n/a (never fetched) | `6fa8c3717f3b91f7…` |

Expected values: `fixtures/propagation-tle-omm-twins/expected.json` (schema_version 1.0).
