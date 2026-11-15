# The Rust `sgp4` crate (neuromorphicsystems/sgp4)

| | |
|---|---|
| tested at | built and run in the corpus's private scratch CI on 2026-11-10 (Ubuntu 24.04, offline cases only), in its present form in run 42864317570 (corpus D-442), after a type error (run 42831534654) and a run on the crate's default WGS-84 constants (run 42847814047); never on the machine that wrote it; the crate version's existence is shown by that build. Written 2026-11-10 for crate version `=2.2.0`, pinned in `Cargo.toml`, on a machine with no Rust toolchain; that the version exists and that its interface is as used here were not checked from that machine [untested] |
| licence of the code | the crate's own, MIT or Apache-2.0 as its Cargo metadata says [not read on that machine]; nothing of it is copied here |
| hooks (D-451) | answers: parse (TLE, 2LE, OMM JSON), propagate; unsupported: alpha5_decode, alpha5_encode, two_digit_year, parse_epoch, parse_catalog_id, write |
| what the harness calls | `sgp4::Elements::from_tle`, the crate's `serde` reading of OMM JSON into `Elements`, `sgp4::Constants::from_elements` and `propagate(MinutesSinceEpoch)` |
| toolchain | Rust and Cargo (any recent stable) |
| published result | none; its findings were reported upstream, the latest as https://github.com/neuromorphicsystems/sgp4/issues/23 |

Best-effort, not installable by pip. The 0.9.0 plan's item b2, written without a Rust toolchain and first built by
the corpus's CI. A field name or a unit wrong for the crate would build and report wrong values, with nothing to say
so: its first runs were read item by item, and one difference they showed was the harness's own (the crate's default
constants are WGS-84; it now builds WGS-72 and declares it). Its finding was reported as
neuromorphicsystems/sgp4#23 (a type 4 set propagated as SGP4), filed by the owner on 2026-11-10; the rest of its run
is not published.

```
cargo build --release --manifest-path harnesses/rust-sgp4/Cargo.toml
H=harnesses/rust-sgp4/target/release/gpconf-rust-sgp4
python3 -m gpconf run --cmd "$H parse {fmt}" --vectors-cmd "$H vectors" --json rust-sgp4-report.json
```

What it returns, as the crate holds it: the catalog number, the name the harness passes it (the line before line 1),
the epoch to the microsecond, the elements in the TLE's units (degrees, revolutions per day), the drag term as BSTAR,
the two derivatives, the ephemeris type, element set and revolution numbers. A set `from_tle` refuses goes back
through the refusal channel with the crate's error. OMM JSON is read through the crate's own `serde` support; the
other OMM formats answer unsupported (exit 3), and so do the five vector hooks other than `propagate`, which the crate
has no interface for. `propagate` builds WGS-72 constants with the IAU sidereal time through the crate's
`Constants::new` (its default, `Constants::from_elements`, uses WGS-84, read in its source at the 2.2.0 commit
`82ec9fb`; corpus D-441), declares them as `{"gravity": "wgs72", "opsmode": "i"}`, and maps the crate's errors to Vallado's codes by their names, 99 for any other
[inferred, untested].
