# astroz (ATTron/astroz)

| | |
|---|---|
| tested at | main `d558933ec3a9c9ee826eb8de665b6e5d229ebecb` ("refactor: cleanup omm (#92)", 2026-04-23), two commits past tag v0.12.0 |
| licence of the library | GPL-3.0 |
| what the harness compiles against | the library's source file `src/Tle.zig`, used directly as a module named `astroz` rather than through the package's build: `Tle.MultiIterator` and `Tle.parseLines` for TLE and 2LE, `Tle.parseOmmArray` for OMM JSON |
| toolchain as run | Zig 0.16.0 (Homebrew), macOS; built and run on 2026-09-24. The library's own parser tests passed on it (`zig test src/Tle.zig`, 10 of 10). The harness uses Zig 0.16's process and I/O interfaces, so earlier Zig versions will not build it; later ones were not tried |
| published result | 9 of 17 cases failed, with the runner of 2026-09-24 (corpus D-140) |

Best-effort, not installable by pip. This harness compiles a source file of the library directly, by its path in the
tree, and depends on Zig's standard library as of 0.16. If astroz moves, renames or reshapes `src/Tle.zig`, or Zig
changes those interfaces again, the harness may fail to build, or build and read differently, with nothing to say so.

`harness.zig` takes the format and an epoch mode: `fields` rebuilds the epoch from the parsed year and day fields,
`jd` takes it from the parser's Julian date, the value the propagators use. Both modes gave 9 of 17 failing cases.
`vectors.zig` answers the corpus's vector hooks through the same module. `common.zig` is shared by both.

## Build

```bash
git clone https://github.com/ATTron/astroz.git repo
git -C repo checkout d558933ec3a9c9ee826eb8de665b6e5d229ebecb
zig build-exe --dep astroz -Mmain=harness.zig -Mastroz=repo/src/Tle.zig -femit-bin=harness -O ReleaseSafe
zig build-exe --dep astroz -Mmain=vectors.zig -Mastroz=repo/src/Tle.zig -femit-bin=vectors -O ReleaseSafe
```

## Run

Note this folder, then run the corpus runner from the root of a corpus clone (or from anywhere, once `gpconf` is
installed):

```bash
H="$PWD"
cd ../..
python3 -m gpconf run --cmd "'$H/harness' {fmt} fields" --vectors-cmd "'$H/vectors'"
```
