# Gpredict (csete/gpredict)

| | |
|---|---|
| tested at | tag v2.6, `c9fa018f2f16bff6dd1c5c51befb8188fe5a5e35` ("Version 2.6", 2026-08-16) |
| licence of the application | GPL-2.0 |
| what the harness compiles against | Gpredict's internal SGP4 module, the six files of `src/sgpsdp/` it needs, compiled on their own without the GTK application; the harness calls the module's `Get_Next_Tle_Set()` directly. `stubs/` stands in for GLib, whose only use by the module is `g_ascii_strtod`, mapped to the C library's `strtod`: in the C locale, which the harness never changes, the two are the same conversion |
| toolchain as run | Apple clang 21 (`cc -std=gnu99`), macOS; built and run on 2026-09-24. Gpredict's own SGP4 test, `test-001.c`, built the same way, ran and exited 0 |
| published result | 6 of 17 cases failed, with the runner of 2026-09-24 (corpus D-133) |

Best-effort, not installable by pip. This harness compiles internal source files of an application, not a library
interface. If a later Gpredict renames or splits those files, changes `Get_Next_Tle_Set()`, or starts using more of
GLib, the harness may fail to build, or build and read differently, with nothing to say so. Results hold for v2.6.

`harness.c` reads TLE text on stdin, hands every name-plus-two-line set, or a name-less pair given a placeholder
name, to `Get_Next_Tle_Set()`, and prints the parsed `tle_t` records as JSON. TLE and 2LE only.

## Build

```bash
git clone https://github.com/csete/gpredict.git repo
git -C repo checkout c9fa018f2f16bff6dd1c5c51befb8188fe5a5e35
cc -std=gnu99 -O1 -Wall -I stubs -I repo/src/sgpsdp -o gpredict-harness harness.c \
  repo/src/sgpsdp/sgp_in.c repo/src/sgpsdp/sgp_time.c repo/src/sgpsdp/sgp_math.c \
  repo/src/sgpsdp/sgp4sdp4.c repo/src/sgpsdp/sgp_obs.c repo/src/sgpsdp/solar.c -lm
```

Building against an installed GLib instead of `stubs/` should give the same results, since the module's one call is
the same conversion; that build was not tried.

## Run

Note this folder, then run the corpus runner from the root of a corpus clone (or from anywhere, once `gpconf` is
installed):

```bash
H="$PWD"
cd ../..
python3 -m gpconf run --cmd "'$H/gpredict-harness' {fmt}"
```
