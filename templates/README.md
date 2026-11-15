# Adapter templates

A minimal `--cmd` adapter in each of eight languages: Python, JavaScript (Node), C++, Swift, Java, Rust, C# and Go.
Each reads one file on standard input and prints a JSON array of records, the command protocol of
[`docs/ADAPTERS.md`](../docs/ADAPTERS.md#the-command-protocol): records in the corpus's field names, refusals through
the refusal channel, exit 3 for a format it does not read, exit 1 (never a crash) for anything unexpected.

Each holds the same toy parser, a TLE reader of about a hundred lines, so that the template runs as it stands. It is
not a parser to use: replace the toy with a call to your library and keep the rest. The values are returned as the
file's own digits, as text, so gpconf compares them exactly; a library that gives binary floats returns numbers and
is compared within the float tolerance.

| language | file | build and run | run on |
|---|---|---|---|
| Python | [`python/adapter.py`](python/adapter.py) | `python3 -m gpconf run --cmd "python3 templates/python/adapter.py {fmt}"` | macOS; CI: Ubuntu, Windows |
| JavaScript | [`node/adapter.mjs`](node/adapter.mjs) | `python3 -m gpconf run --cmd "node templates/node/adapter.mjs {fmt}"` | macOS; CI: Ubuntu, Windows |
| C++ | [`cpp/adapter.cpp`](cpp/adapter.cpp) | `c++ -std=c++17 -O2 -o adapter templates/cpp/adapter.cpp`, then `--cmd "./adapter {fmt}"` | macOS; CI: Ubuntu, Windows |
| Swift | [`swift/adapter.swift`](swift/adapter.swift) | `swiftc -O -o adapter templates/swift/adapter.swift`, then `--cmd "./adapter {fmt}"` | macOS; CI: Ubuntu |
| Java | [`java/Adapter.java`](java/Adapter.java) | `--cmd "java templates/java/Adapter.java {fmt}"` (Java 11 and later) | CI: Ubuntu, Windows |
| Rust | [`rust/`](rust/) | `cargo build --release --manifest-path templates/rust/Cargo.toml`, then `--cmd "templates/rust/target/release/gpconf-adapter-template {fmt}"` | CI: Ubuntu, Windows |
| C# | [`csharp/`](csharp/) | `dotnet build -c Release templates/csharp/Adapter.csproj`, then `--cmd "dotnet templates/csharp/bin/Release/net8.0/Adapter.dll {fmt}"` | CI: Ubuntu, Windows |
| Go | [`go/adapter.go`](go/adapter.go) | `go build -o adapter templates/go/adapter.go`, then `--cmd "./adapter {fmt}"` (`adapter.exe` on Windows) | CI: Ubuntu |

"macOS" means built and run on the machine that wrote them (2026-11-10): there each of the first four passes the
ten cases a TLE reader can be graded on with the corpus's fetched data, fails none and skips the rest as formats it
does not read; without fetched data, the two offline TLE cases, `alpha5-tle-derived` and `corrupt-input`, pass.
The other four were written without their toolchains on that machine and first built and run by the corpus's CI
(2026-11-10, a private scratch run): each passed the two offline cases on Ubuntu, and Java, Rust and C# on Windows
too; Go's Windows run failed only because the test named the built program without `.exe`, since mended and not yet
run again (D-437). `tests/test_templates.py` builds and runs each template wherever its toolchain is found, and skips
it, saying why, where it is not (Swift has none on the Windows runner).

The two offline cases, from a clone:

```
python3 -m gpconf run --case alpha5-tle-derived --case corrupt-input --cmd "python3 templates/python/adapter.py {fmt}"
```

What the toy does, the same in every language: a set is a line beginning `1 ` followed by one beginning `2 `, with
the line before it as the name when it is neither blank nor an element line; both lines must be 69 characters, their
checksums right and their catalog fields equal; the catalog field is read as Alpha-5 (a digit or an uppercase letter
other than I and O, then four digits); the epoch's two-digit year pivots at 57 (57 to 99 are 1957 to 1999) and its
day of year, eight decimals, is a whole number of microseconds (1e-8 day is 864 µs), so the epoch is exact in
integers. A set that breaks any of these is refused with its reason and its catalog field, and the sets around it
still load; an element line that pairs with nothing is refused too.

The templates are the corpus's own code, under its Apache-2.0 licence; copy one into your project and change it as
you like.
