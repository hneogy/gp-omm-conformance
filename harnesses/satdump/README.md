# SatDump (SatDump/SatDump)

| | |
|---|---|
| tested at | master `f3d82adbfe04e57c596b93479d687f4b830ee26c` (2026-09-21), and release 1.2.2, tag `1.2.2`, `7aef0fe8441bc3eb440b1b6ba053556da5e40991` (2024-11-29) |
| licence of the program | GPL-3.0 |
| what the harness compiles against | internal source files of SatDump's `src-core/`: `common/tracking/tle.cpp` (the TLE registry's parser, `parseTLEStream`), on master also `db/kepler/kepler_utils.cpp` (`ccsdsOmmToKepler`, the CSV reader), `common/utils.cpp` and `utils/string.cpp`, and the ten files of the bundled predict fork, `libs/predict/`, whose `predict_parse_tle` the harness also calls. The GUI, the database layer, HTTP and logging are not built |
| toolchain as run | Apple clang 21, C++17 and gnu99, libcurl, macOS; built and run on 2026-09-24 |
| published result | 3 of 17 cases failed on 1.2.2, 5 of 17 on master, with the runner of 2026-09-24 (corpus D-137) |

Best-effort, not installable by pip. This harness compiles internal source files of an application, chosen by hand
from its tree. If SatDump moves, renames or splits them, or changes what they reference, the harness may fail to link,
or link and read differently, with nothing to say so. Results hold only for the two commits above.

`harness.cpp` (master) and `harness-rel.cpp` (1.2.2) read TLE and 2LE through `parseTLEStream`, then run every
registry entry's lines through the predict fork's `predict_parse_tle`, and report both numbers; master also reads
CSV through `ccsdsOmmToKepler`, one line at a time.

## What you must add: the link needs these symbols

The files compiled here reference a few globals and helpers from parts of SatDump that are not built: logging,
configuration, HTTP and the database. The harness never calls them, so the link needs them only to exist. Define
each in a file of your own, `stand-ins.cpp` in the commands below, as an empty function, returning a zero or empty
value where it returns one, or as a default-constructed object. SatDump's headers declare every one, and the linker's
undefined-symbol errors name each with its full signature.

Master:

- `satdump::satdump_cfg` (an object)
- `satdump::db` (an object)
- `satdump::SATDUMP_VERSION` (an object)
- `satdump::DBHandler::get_meta` (a member function)
- `satdump::curl_write_std_string` (a function)
- `satdump::perform_http_request` (a function)
- `logger` (an object, in the global namespace)
- `slog::Logger::logf` (a member function)
- `format_notated<double>` (an explicit specialisation of a function template)

Release 1.2.2:

- `satdump::config::main_cfg` (an object)
- `curl_write_std_string` (a function, in the global namespace)
- `perform_http_request` (a function, in the global namespace)
- `logger` (an object, in the global namespace)
- `slog::Logger::logf` (a member function)
- `satdump::config::saveUserConfig` (a function)
- `satdump::eventBus` (an object)

The stand-in files the corpus used for its own run are not in this folder. They define SatDump's own functions and
objects rather than calling them, and the corpus keeps anything written to replace part of a GPL-licensed program out
of its MIT-licensed repository (corpus decision D-152).

## Build, master

```bash
git clone https://github.com/SatDump/SatDump.git master
git -C master checkout f3d82adbfe04e57c596b93479d687f4b830ee26c
mkdir -p build
for f in common/tracking/tle.cpp db/kepler/kepler_utils.cpp common/utils.cpp utils/string.cpp; do
  clang++ -std=c++17 -DSOURCE_PATH_SIZE=0 -DSATDUMP_DLL_EXPORT=1 -c -I master/src-core -I master/src-core/libs \
    -o "build/$(echo "$f" | tr / _ | sed 's/\.cpp$/.o/')" "master/src-core/$f"
done
for f in master/src-core/libs/predict/*.c; do
  clang -std=gnu99 -c -I master/src-core/libs/predict -o "build/predict-$(basename "$f" .c).o" "$f"
done
clang++ -std=c++17 -DSOURCE_PATH_SIZE=0 -DSATDUMP_DLL_EXPORT=1 -c -I master/src-core -I master/src-core/libs \
  -o build/stand-ins.o stand-ins.cpp
clang++ -std=c++17 -DSOURCE_PATH_SIZE=0 -I master/src-core -I master/src-core/libs -o build/satdump-harness harness.cpp \
  build/common_tracking_tle.o build/db_kepler_kepler_utils.o build/common_utils.o build/utils_string.o \
  build/stand-ins.o build/predict-*.o -lcurl
```

## Build, release 1.2.2

```bash
git clone --branch 1.2.2 --depth 1 https://github.com/SatDump/SatDump.git rel
mkdir -p build-rel
clang++ -std=c++17 -DSOURCE_PATH_SIZE=0 -DSATDUMP_DLL_EXPORT=1 '-DSATDUMP_VERSION="1.2.2"' -c \
  -I rel/src-core -I rel/src-core/libs -o build-rel/tle.o rel/src-core/common/tracking/tle.cpp
for f in rel/src-core/libs/predict/*.c; do
  clang -std=gnu99 -c -I rel/src-core/libs/predict -o "build-rel/predict-$(basename "$f" .c).o" "$f"
done
clang++ -std=c++17 -DSOURCE_PATH_SIZE=0 -DSATDUMP_DLL_EXPORT=1 '-DSATDUMP_VERSION="1.2.2"' -c \
  -I rel/src-core -I rel/src-core/libs -o build-rel/stand-ins.o stand-ins-rel.cpp
clang++ -std=c++17 -DSOURCE_PATH_SIZE=0 -DNO_KEPLER -I rel/src-core -I rel/src-core/libs -o build-rel/satdump-rel \
  harness-rel.cpp build-rel/tle.o build-rel/stand-ins.o build-rel/predict-*.o -lcurl
```

One step differs from the run of 2026-09-24, which linked the release with the predict objects compiled from master's
tree; compiling the release tree's own `libs/predict/` as above was not tried.

The harness files here differ from the ones built on 2026-09-24 in one respect: an unused call into the predict
fork, whose result was discarded, and its declaration were removed (corpus D-152). The output cannot change, and the
function it sat in gives identical output before and after when compiled on its own; the full harness has not been
rebuilt since.

## Run

Note this folder, then run the corpus runner from the root of a corpus clone (or from anywhere, once `gpconf` is
installed):

```bash
H="$PWD"
cd ../..
python3 -m gpconf run --cmd "'$H/build/satdump-harness' {fmt}"
python3 -m gpconf run --cmd "'$H/build-rel/satdump-rel' {fmt}"
```
