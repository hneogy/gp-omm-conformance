# GPKit (Swift), by gpconf's author

GPKit is maintained by gpconf's author; its results are graded exactly like every other library's.

| | |
|---|---|
| tested at | release `v1.3.0`, commit `1f5405bd3c27a61d79824af7e4f6c3b0bf4c995a` (2026-11-10, corpus D-456); before it v1.2.0, `971b642bc35d4f9d10bf3fbe017ae55ba785bbfd`, and first v1.1.0, `0c4d39667cc6de1fa59c04172390e87225d0fe56` |
| project | https://github.com/hneogy/GPKit, by the same author as gpconf (the owner's ruling, corpus D-378) |
| licence of the code | Apache-2.0 (the project's own LICENSE); nothing of it is copied here |
| hooks (D-451) | answers: parse, alpha5_decode, alpha5_encode, two_digit_year, parse_epoch, parse_catalog_id, propagate, write, all through the project's own adapter (propagate from 1.2.1); unsupported: none |
| the adapter | the project's own, `Sources/gpconf-adapter` (product `gpkit-gpconf`), which answers `parse`, `vectors` and `write` by command; this recipe adds no harness code |
| toolchain as run | Swift 6 (Apple's, with the Xcode command-line tools), SwiftPM; built and run on 2026-11-10 |
| published result | the project's README: 17 of 18 cases pass against gpconf 0.8.0 (2026-11-05), the eighteenth not exercised |

Best-effort, not installable by pip. The adapter is GPKit's and moves with GPKit: at any other commit it may build
and report something other than what v1.3.0 reports, with nothing to say so, so a count means something only at
the pin above.

A recipe so that GPKit's run is reproducible from the corpus, as the 0.9.0 plan's item b5 asks. GPKit carries its
own adapter, in its own repository, so the recipe is the pin and the commands; the project's CI runs the same
adapter on every push.

```
git clone https://github.com/hneogy/GPKit && cd GPKit && git checkout v1.3.0
swift build --product gpkit-gpconf
B="$PWD/.build/debug/gpkit-gpconf"
cd /path/to/gp-omm-conformance
python3 -m gpconf run --cmd "$B parse {fmt}" --vectors-cmd "$B vectors" --write-cmd "$B write" --json gpkit-report.json
```

**Measured, 2026-11-10, against the 0.9.0 work in progress (the corpus's private branch, with its fetched data):**
at v1.2.0, 21 cases, 17 pass exactly, none fails, 3 skip, 1 not exercised. At v1.1.0 the same run gave 16 passes and
one failure, `alpha5-encoding-vectors` on `ccsds-epoch-strings`: 1.1.0 accepted second 60 on 30 June or 31 December
of a year with no leap second (`1960-06-30T23:59:60`, `2026-12-31T23:59:60` and four more), which gpconf 0.8.0 passed
and 0.9.0 does not (corpus D-382, SM-26's L2); 1.2.0 is the release with that fix (corpus D-438). The three
propagation cases skip: the adapter has no `propagate` op (the propagation tier is new in 0.9.0; the op belongs to the
project, as the other harnesses' do). `satcat-70000-cutoff` checks data and runs no parser.

**Measured at v1.3.0, 2026-11-10 (corpus D-456), against the 0.9.0 work in progress with its fetched data and the
corpus's private copy of Vallado's files,** built from `git archive v1.3.0`:

- **The main row, GPKit's default epoch (`.exact`), as above:** 21 cases, 17 pass exactly, 2 within tolerance, 1 fails,
  1 not exercised. The failure is `sgp4-ver-propagation` on set 23333 (eccentricity 0.97): 4.11e-6 km at t = 0, past the
  2e-7 bar. GPKit takes a TLE's epoch exactly, where Vallado's C++ reader, which made `tcppver.out`, reads the day as a
  `Double`; the two differ by up to about 20 microseconds, and set 23333 is where that shows (GPKit's own 1.3.0
  changelog says the same). The twins and the type-4 case pass within tolerance (9.71e-10 km; type 4 refused).
- **A separate, labelled row, `.vallado`:** the same commands with `--epoch vallado` before `parse` and `vectors`, so the
  adapter declares `"epoch": "vallado"` in its constants declaration: 17 pass exactly, 3 within tolerance, none fails, 1
  not exercised; `sgp4-ver-positions` within 1.17e-7 km and 5e-10 km/s over 666 steps. It is the mode for matching
  Vallado's file to its last digits, never the default (the owner's ruling, 2026-11-10), and is reported beside the main
  row, not in its place.

