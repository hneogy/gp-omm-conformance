# Vallado's SGP4 C++, as CelesTrak publishes it (CelesTrak/fundamentals-of-astrodynamics)

| | |
|---|---|
| tested at | `4b04ddce172a3f5d958b4256a29ea996c8e666be` (2026-09-28), the first commit that carries the repository's NOTICE. The two files compiled were last changed by `7e0078a10e9aed2a44eef0ab646c0018ca69e1ad` (2026-08-31) and are byte-identical at both commits and on `main` on 2026-10-03; the first form of the harness was run at both, with the same items |
| licence of the code | the repository is AGPL-3.0. Its NOTICE, in the tree at the commit pinned, says that the SGP4 C++ source (`software/cpp/SGP4/`) derives from Vallado, Crawford, Hujsak and Kelso, AIAA 2006-6753, and "retains those original unrestricted terms". The NOTICE entered the repository with that commit: at `7e0078a`, where the code last changed, the tree has none and its README names the AGPL alone, which is why the pin is the later commit. Nothing of the repository is copied here |
| what the harness compiles against | `SGP4.cpp` and `SGP4.h`, the two source files of `software/cpp/SGP4/SGP4/`, and nothing else of the repository: the one reader, `SGP4Funcs::twoline2rv()`, and the `elsetrec` structure it fills, both declared in `SGP4.h` |
| toolchain as run | Apple clang 21, C++17, macOS; built and run on 2026-10-03 |
| published result | none: this recipe has no row on the site. Run on 2026-10-03 against corpus v0.5.0's eighteen cases, 8 of 18 cases failed (corpus D-216) |
| from a fresh fetch | These counts were measured with the corpus's launch-window captures, files a new user's fetch cannot obtain (corpus D-229). One of the failing cases, `supgp-celestrak-classification-c`, cannot run without them, so a run from a fresh fetch reproduces fewer. |

Best-effort, not installable by pip. The harness calls one function and reads one structure, both part of the code's
own header, so it is less exposed than a harness built on internals, but it is tied to the commit above: a change to
`twoline2rv()`'s arguments, to the fields of `elsetrec` or to their units can make it build and still report the wrong
thing, with nothing to say so.

This is the reference implementation the other SGP4 libraries descend from, read directly: python-sgp4's accelerated
class wraps the same code and adjusts what goes in and what comes out, so a run through python-sgp4 measures the
wrapper as well. The code reads TLE lines only. It has no OMM reader, no TLE writer and no Alpha-5 encoder, so the
OMM cases, the writer case and three of the vector items skip.

`harness.cpp` reads TLE and 2LE through `twoline2rv()`. Each line goes to the reader as the file carries it, its
checksum digit included, in the 130-character buffer the function writes into, with an `elsetrec` that starts zeroed
and the arguments python-sgp4's wrapper passes (`' '`, `' '`, `'i'`, `wgs72`), with which the function asks nothing
of the terminal. The record is what the reader left in the structure, with its units turned back into the TLE's: the
mean motion to revolutions per day, the angles to degrees, the two derivatives as the line prints them; the catalog
number is the reader's integer `satnum`; the epoch is the Julian date the reader stored, written as a calendar
instant to the microsecond by the harness's own integer arithmetic. `elnum`, `revnum`, `ephtype` and `classification`
are returned as the structure holds them. A value the reader leaves non-finite is written as `null`, with a note on
standard error.

A set the reader throws on comes back through the runner's refusal channel, with the exception's type and message
as its reason (corpus D-144). The structure's error flag is not treated as a refusal (corpus D-218). It is the
propagation model's return code on the elements, left by the call to `sgp4init()` inside `twoline2rv()`, and
`SGP4.cpp` documents it on `sgp4init()` and `sgp4()`, not on the reader; for a malformed set it depends on what the
structure held before the call, so it is not the reader's verdict on the line. The harness carries it in the record
as `_error`, which the runner does not grade, and says so on standard error when it is non-zero. Each line 1 goes to
the reader with whatever line follows it, so the reader, not the harness, answers for a line 1 with no line 2 after
it (corpus D-183). `vectors.cpp` answers the
corpus's vector hooks through the same call; a field that is not five characters long is turned away by the helper
itself, since it cannot be placed in the line. `common.h` is shared by both.

## Build

```bash
git clone --filter=blob:none --no-checkout https://github.com/CelesTrak/fundamentals-of-astrodynamics.git repo
git -C repo sparse-checkout set software/cpp/SGP4
git -C repo checkout 4b04ddce172a3f5d958b4256a29ea996c8e666be
mkdir -p build
clang++ -std=c++17 -O1 -w -I repo/software/cpp/SGP4/SGP4 -c -o build/SGP4.o repo/software/cpp/SGP4/SGP4/SGP4.cpp
clang++ -std=c++17 -O1 -Wall -I repo/software/cpp/SGP4/SGP4 -o build/harness harness.cpp build/SGP4.o
clang++ -std=c++17 -O1 -Wall -I repo/software/cpp/SGP4/SGP4 -o build/vectors vectors.cpp build/SGP4.o
```

The sparse checkout takes the SGP4 C++ folder and the repository's top-level files, the NOTICE among them, and none of
its other code.
`-w` silences the warnings of `SGP4.cpp`, which is compiled as it is. Built with `-O0` as well, the run gives the same
186 items, status for status and word for word.

## Run

Note this folder, then run the corpus runner from the root of a corpus clone (or from anywhere, once `gpconf` is
installed):

```bash
H="$PWD"
cd ../..
python3 -m gpconf run --cmd "'$H/build/harness' {fmt}" --vectors-cmd "'$H/build/vectors'"
```
