# Test a Go parser with gpconf in five minutes

You need Python 3.9 or later (for gpconf itself), Go 1.21 or later, and git.

## 1. Get gpconf and the template (one minute)

```bash
git clone https://github.com/hneogy/gp-omm-conformance
cd gp-omm-conformance
```

The template is [`templates/go/adapter.go`](../../templates/go/adapter.go): a whole adapter around a toy TLE reader, so it runs before you change
anything.

## 2. Run the template as it stands (one minute)

```bash
go build -o adapter templates/go/adapter.go
```

```bash
python3 -m gpconf run --case alpha5-tle-derived --case corrupt-input --cmd "./adapter {fmt}"
```

Both cases pass and the command exits 0: that is the green run. `alpha5-tle-derived` reads catalog numbers above 99999
in TLE lines (Alpha-5); `corrupt-input` hands your reader broken sets between good ones and checks that the good ones
still load and the broken ones are refused, not misread.

## 3. Put your parser in (three minutes)

Open the template and replace the toy parser with a call to your library. Keep the rest: reading standard input,
returning one JSON object per record with the corpus's field names (`norad_cat_id`, `epoch`, `mean_motion`,
`eccentricity`, the angles in degrees, `bstar`, `mean_motion_dot`, `mean_motion_ddot`), a refusal entry
(`{"_refused": "why", "_field": "the catalog field"}`) for a record your library rejects, and exit 3 for a format it
does not read. Then run the same command again. A panic exits 2, which gpconf reads as a failed file: return errors instead.

A failure names the check, the file and what your reader returned against what was expected: that is a finding about
your parser, and `docs/ADAPTERS.md` says how each check reads.

## Next

- Every case, with the provider files: `python3 -m gpconf fetch` once (it asks CelesTrak for each file once), then
  `python3 -m gpconf run --cmd "..."` with no `--case`.
- The OMM formats (CSV, JSON, XML, KVN), the vector hooks, a TLE writer and SGP4 propagation: `docs/ADAPTERS.md`.
- In CI: the corpus's GitHub Action (`action.yml`), or `pytest-gpconf` once it is published.
