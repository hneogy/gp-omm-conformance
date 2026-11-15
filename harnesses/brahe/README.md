# brahe (Python package of duncaneddy/brahe)

| | |
|---|---|
| tested at | brahe `1.8.1` from PyPI (release v1.8.1, 2026-10-31), run on 2026-11-10 with Python 3.14 |
| licence of the code | MIT (the repository's); nothing of it is copied here |
| hooks (D-451) | answers: parse (OMM CSV, JSON, XML, KVN), alpha5_decode, alpha5_encode; unsupported: two_digit_year, parse_epoch, parse_catalog_id, propagate, write |
| what the adapter calls | `brahe.GPRecord.from_json` (OMM JSON, one object at a time), `brahe.ccsds.OMM.from_str` (OMM CSV, XML, KVN), `parse_norad_id` and `norad_id_numeric_to_alpha5` (two vector hooks) |
| toolchain | Python 3.9 or later with `pip install brahe==1.8.1`; the adapter installs brahe's zero Earth-orientation provider, so nothing is downloaded |
| published result | none; its findings were reported as https://github.com/duncaneddy/brahe/issues/620, filed by the owner on 2026-11-10 |

Best-effort, not installable by pip. It is an adapter file for `--adapter`, not a preset (whether brahe
becomes a packaged preset is the owner's). A new brahe release can change what these calls return and build and run
the same, with nothing to say so, so a count means something only at the version above.

```
pip install brahe==1.8.1
cd harnesses/brahe
python3 -m gpconf run --root ../.. --adapter brahe_adapter:Parser
```

TLE answers Unsupported: brahe's TLE interface gives back the catalog number, the epoch and the six Keplerian elements
but not the mean motion as the line holds it, BSTAR or the derivatives, so a record in the corpus's terms would need
values the adapter decided (the adapter's docstring says more). The results of the corpus's run are not published
until the library's maintainers have heard them (the corpus's rule for every library).
