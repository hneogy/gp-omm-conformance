# Orekit's TLE reader (Java) — UNTESTED

| | |
|---|---|
| tested at | **not run.** Written 2026-11-10 for an Orekit 12 release (`org.orekit.propagation.analytical.tle.TLE`) on a machine with no JDK; the release to pin, and that its interface is as used here, were not checked from that machine [untested] |
| licence of the code | Orekit is Apache-2.0, Hipparchus too [not read on that machine]; nothing of either is copied here |
| hooks (D-451) | answers: parse; unsupported: alpha5_decode, alpha5_encode, two_digit_year, parse_epoch, parse_catalog_id, propagate, write (no --vectors-cmd or --write-cmd program yet) |
| what the harness calls | `TLE.isFormatOK(line1, line2)`, `new TLE(line1, line2, utc)` and its getters |
| toolchain | a JDK (11 or later), Orekit and Hipparchus jars, and an `orekit-data` folder (Orekit needs its leap-second table for UTC), named by `OREKIT_DATA` |
| published result | none |

Best-effort, not installable by pip. Not yet run once: the first form of the 0.9.0 plan's item b1, a recipe
behind `--cmd`. A preset needs a Python binding (`orekit-jpype`), which the plan leaves open. Until it has been built
and run nothing in it is a measurement; a getter whose unit is not the one assumed here would build and report wrong
values, with nothing to say so, so its first run reads its values against Orekit's documentation before a count is
kept.

```
javac -cp "orekit.jar:hipparchus-core.jar" -d build harnesses/orekit/Harness.java
OREKIT_DATA=/path/to/orekit-data python3 -m gpconf run --cmd "java -cp build:orekit.jar:hipparchus-core.jar Harness {fmt}"
```

What it returns, as Orekit holds it, turned into the corpus's units: the catalog number, the name (the line before
line 1), the designator from the launch year, number and piece, the epoch in UTC to the microsecond, the mean motion
from rad/s to revolutions per day, the angles from radians to degrees, BSTAR, the first and second derivatives turned
back into the TLE's printed values (rad/s² to rev/day² over 2, rad/s³ to rev/day³ over 6 [inferred from the TLE
definition; untested against Orekit]), classification, ephemeris type, element set and revolution numbers. A set that
`isFormatOK` turns away or the constructor throws on goes back through the refusal channel with Orekit's reason. Orekit
reads TLE lines only, so the OMM formats answer unsupported (exit 3); there is no `--vectors-cmd` program.
