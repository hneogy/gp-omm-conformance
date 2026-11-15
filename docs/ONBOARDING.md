# Add an adapter in five minutes

An adapter is the small piece that hands gpconf's test files to your parser and gives back what it read. This page
gets you to a first run; [`docs/ADAPTERS.md`](ADAPTERS.md) is the full protocol, and [`docs/guides/`](guides/README.md)
has a five-minute guide per language with a template that already runs.

## 1. Pick a route (30 seconds)

- **Your parser is importable from Python:** a Python class, run in gpconf's process (`--adapter module:Class`).
- **Anything else** (JavaScript, C++, Rust, Go, C#, Java, Swift, or Python you would rather keep separate): a
  program gpconf runs once per file (`--cmd "your-program {fmt}"`). It reads the file on standard input and prints a
  JSON array of records.

## 2. Write it (three minutes)

A Python adapter, whole, around a library that has `parse_tle(text)` returning objects:

```python
# my_adapter.py
from gpconf.runner import Unsupported
import mylib

class Parser:
    def parse(self, raw, fmt):
        if fmt not in ("tle", "2le"):
            raise Unsupported(fmt)                     # a format your library does not read: the file is skipped
        records = []
        for sat in mylib.parse_tle(raw.decode("ascii")):
            records.append({
                "norad_cat_id": sat.catalog_number,    # an integer, never the five-character field
                "epoch": sat.epoch,                    # a datetime (UTC) or a calendar-form string you built
                "mean_motion": sat.mean_motion,        # rev/day
                "eccentricity": sat.eccentricity,
                "inclination": sat.inclination,        # degrees, as are the next three
                "ra_of_asc_node": sat.raan,
                "arg_of_pericenter": sat.argp,
                "mean_anomaly": sat.mean_anomaly,
                "bstar": sat.bstar,
                "mean_motion_dot": sat.ndot,           # as the TLE prints it
                "mean_motion_ddot": sat.nddot,
            })
        return records
```

If your library refuses a set, say so in the same list rather than dropping it silently:
`{"_refused": "the library's reason", "_field": line1[2:7]}`. A command adapter prints the same records as JSON and
exits 3 for a format it does not read.

## 3. Run it (one minute)

The two TLE cases below run offline, from the files the package ships:

```bash
pip install gpconf
gpconf run --adapter my_adapter:Parser --case alpha5-tle-derived --case corrupt-input
# or, for a program: gpconf run --cmd "your-program {fmt}" --case alpha5-tle-derived --case corrupt-input
```

Each case prints `pass`, `fail` or `skip`, and a failure names the check, the file and what your parser returned
against what was expected. Exit 0 means every graded case passed.

## 4. Next

- Every case: `gpconf fetch` once (it asks CelesTrak for each file once, under its usage policy), then the same `run`
  without `--case`.
- OMM (CSV, JSON, XML, KVN), the vector hooks, a TLE writer, SGP4 propagation: [`docs/ADAPTERS.md`](ADAPTERS.md).
- In CI: the GitHub Action (`action.yml`) runs a preset or a Python adapter; for a command adapter, a workflow step
  that runs `pip install gpconf` and the same `gpconf run`.
- What each failure usually means and how to fix it: [`docs/MIGRATION.md`](MIGRATION.md).
