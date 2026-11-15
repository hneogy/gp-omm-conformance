# SGP.NET (C#, parzivail/SGP.NET)

| | |
|---|---|
| tested at | built and run in the corpus's private scratch CI on 2026-11-10 (Ubuntu 24.04, offline cases only): first in run 42831534654, then in its present form, with the harness fixes that run led to (corpus D-439), in run 42847814047 (corpus D-440); never on the machine that wrote it. Written 2026-11-10 for SGP.NET `1.6.0` (release v1.6.0, 2026-09-23; NuGet `SGP.NET`, pinned exactly in `Harness.csproj`) from its source read on GitHub, on a machine with no .NET SDK; the corpus's scratch CI is to build and run it first [untested] |
| licence of the code | MIT (the package's licence expression); nothing of it is copied here |
| hooks (D-451) | answers: parse; unsupported: alpha5_decode, alpha5_encode, two_digit_year, parse_epoch, parse_catalog_id, propagate, write (no --vectors-cmd or --write-cmd program) |
| what the harness calls | `new Tle(name, line1, line2)` (TLE and 2LE), and the library's OMM readers `OmmCsvParser`, `OmmJsonParser`, `OmmXmlParser` and `OmmKvnParser` (`Parse(string)`, a list of `OmmData`) |
| toolchain | the .NET 8 SDK (NuGet restores the package) |
| published result | none; its findings were reported upstream, the latest as https://github.com/parzivail/SGP.NET/issues/48 |

Best-effort, not installable by pip. Chosen for C# (0.9.0 item b4) over one_Sgp4 (more stars, last change 2025-03)
because SGP.NET is maintained and reads all five of the corpus's formats. A property whose unit is not the one read
here would build and report wrong values, with nothing to say so, so its first run is read against the library's
source before any count is kept, Its findings were reported:
parzivail/SGP.NET#35 (Alpha-5, fixed by #47) and #48 (a day-of-year epoch and a unit in brackets in KVN, fixed by #49),
both merged 2026-11-10, after release v1.6.0; the rest of its run is not published.

```
dotnet build -c Release -o build harnesses/sgp-net/Harness.csproj
python3 -m gpconf run --cmd "dotnet harnesses/sgp-net/build/Harness.dll {fmt}"
```

What it returns, as the library holds it: from a TLE, the catalog number (`NoradNumber`), the name (the library
puts the catalog field there when the set has none, and the harness passes that on), the epoch to the microsecond,
the mean motion in rev/day, eccentricity, the angles in degrees (`Angle.Degrees`), BSTAR, the TLE's printed
derivatives (`MeanMotionDtOver2`, `MeanMotionDdtOver6`) and the revolution number; from an OMM, every `OmmData`
field gpconf grades. A set the `Tle` constructor throws on goes back through the refusal channel; an OMM file a
parser throws on is refused whole (exit 1) with the library's message.
