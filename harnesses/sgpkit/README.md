# SGPKit (Swift, csanfilippo/swift-sgp4)

| | |
|---|---|
| tested at | release 3.1.0, `30bb5731715a1e048636ab7cbb25a24a773e1220` (2025-11-09), run on 2026-10-06 against gpconf 0.6.1, where the harness was written (the owner's swift-satellite workspace, phase 1); moved here on 2026-11-10 by the owner's word, and run again that day on GitHub's macOS runner in the corpus's private scratch CI (run 42847814047, Apple Swift 6.1.2, offline cases only; corpus D-440). At 4.4.0 (`285e70d0b609788ce44abb472ecae8e6c2726f1d`, the newest release on 2026-11-10) the harness does not build: the bridge includes `Wrapper.hpp`, which 4.x renamed `SGP4LibWrapper.h` |
| licence of the code | MIT (the repository's); SGPKit bundles a copy of libsgp4 (dnwrnr/sgp4, Apache-2.0); nothing of either is copied here |
| hooks (D-451) | answers: parse, alpha5_decode, two_digit_year; unsupported: alpha5_encode, parse_epoch, parse_catalog_id, propagate, write (the library has no writer or encoder and no OMM reader) |
| what the harness compiles against | SGPKit's own targets (`sgp4Lib`, `SGP4LibWrapper`, `SGPKit`) over a clone at the tag, unmodified, declared in this folder's `Package.swift` with one file, `TLEInterpreter.swift`, left out; `SGPKitBridge`, a C interface of this folder's over the library's bridge function `createTLE()`; `support/`, shared helpers for output, input and calendar arithmetic |
| toolchain | Swift 6 with SwiftPM and C++17 (Apple's Command Line Tools, Swift 6.4, as run) |
| published result | none; two findings are public, https://github.com/csanfilippo/swift-sgp4/issues/4 (catalog numbers of 100000 and up refused, filed by the owner on 2026-10-08, fixed in 4.1.0) and https://github.com/csanfilippo/swift-sgp4/issues/16 (`decodeCollection` loses a file for one bad set, at 4.4.0, filed 2026-11-10) |

Best-effort, not installable by pip. The harness compiles against the project's internal targets and its bridge
function, which are not a published interface: at another release it may stop building, or build and test something
other than what the library's users get, with nothing to say so. A count means something only at the pin above, and
4.x needs the bridge brought up to its renamed wrapper first.

Why the targets are declared here and SGPKit is not a dependency: its one file that calls into C++,
`TLEInterpreter.swift`, needs the Swift overlay of the C++ standard library, and the toolchain the harness was built
with ships that overlay's static library without its Swift module; `Package.swift` says more.

```
cd harnesses/sgpkit
git clone https://github.com/csanfilippo/swift-sgp4.git upstream
git -C upstream checkout 30bb5731715a1e048636ab7cbb25a24a773e1220
swift build
G="$PWD/.build/debug"
cd ../..
python3 -m gpconf run --cmd "'$G/sgpkit-harness' {fmt}" --vectors-cmd "'$G/sgpkit-vectors'"
```

`sgpkit-harness` reads TLE lines through SGPKit's `TLEDecoder.decodeCollection`, its file reader, and answers exit 3
for every other format; `HARNESS_MODE=per-set` in front of it inside `--cmd` reads one set at a time instead.
`sgpkit-vectors` answers the vector hooks the library has. The results of the corpus's run beyond the one reported
finding are not published until the project's maintainer has heard them (the corpus's rule for every library).

**SGPKit 4.x.** From 4.2.0 SGPKit is an ordinary package dependency, and 4.x replaced the wrapper this harness's bridge
calls: its public API holds a TLE's three lines and propagates to a geodetic state, and no parsed field is exposed,
so no gpconf reader harness can grade 4.x. `v4/` is a probe of one behaviour instead: `sgpkit-v4-probe FILE...`
prints what `TLEDecoder().decodeCollection` gives back for each file, run on the corpus's corrupt-input TLE files
beside the valid ones (`cd v4 && swift build`, SGPKit pinned exactly at 4.4.0).
