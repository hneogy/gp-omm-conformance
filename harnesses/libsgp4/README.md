# libsgp4 (dnwrnr/sgp4)

| | |
|---|---|
| tested at | master `661e057a5d369d5ee424676cf1d69cbead95ff2c` ("Version 2", 2026-07-26), and the head of pull request #42, `2b8d14139fa266cdf57cb52ec9e1dfa041ee343d` (2026-03-26) |
| licence of the library | Apache-2.0 |
| what the harness compiles against | the library's own classes, `Tle` and `DateTime`, and every `.cc` file of `libsgp4/`, compiled without its CMake build. `Tle::FromCsv` exists only on master, so CSV is read only with `-DHAVE_CSV` |
| toolchain as run | Apple clang 21, C++17, macOS; built and run on 2026-09-24 |
| published result | 6 of 17 cases failed on master, 5 of 17 on PR #42, with the runner of 2026-09-24 (corpus D-138) |

Best-effort, not installable by pip. This harness uses the library's classes rather than its internals, so it is the
least likely of the five to break, but it is tied to the commits above: the constructor signatures and `FromCsv` are
what it was written against, and a later change to either can make it build and still read the wrong thing, with
nothing to say so.

`harness.cpp` reads TLE and 2LE through the `Tle(name, line1, line2)` constructor and, on master, CSV through
`Tle::FromCsv()` one data line at a time, as `LoadCsvTleFile()` does. `vectors.cpp` answers the corpus's vector hooks
through the same constructors. `common.h` is shared by both.

## Build, master

```bash
git clone https://github.com/dnwrnr/sgp4.git repo
git -C repo checkout 661e057a5d369d5ee424676cf1d69cbead95ff2c
mkdir -p build
for f in repo/libsgp4/*.cc; do clang++ -std=c++17 -O1 -c -I repo/libsgp4 -o "build/$(basename "$f" .cc).o" "$f"; done
clang++ -std=c++17 -O1 -DHAVE_CSV -I repo/libsgp4 -o build/harness harness.cpp build/*.o
clang++ -std=c++17 -O1 -DHAVE_CSV -I repo/libsgp4 -o build/vectors vectors.cpp build/*.o
```

For pull request #42, check out `2b8d14139fa266cdf57cb52ec9e1dfa041ee343d` instead (`git -C repo fetch origin
pull/42/head`), build into a separate folder, and leave out `-DHAVE_CSV`, since that tree predates CSV.

## Run

Note this folder, then run the corpus runner from the root of a corpus clone (or from anywhere, once `gpconf` is
installed):

```bash
H="$PWD"
cd ../..
python3 -m gpconf run --cmd "'$H/build/harness' {fmt}" --vectors-cmd "'$H/build/vectors'"
```
