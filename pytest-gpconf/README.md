# pytest-gpconf

Run [gpconf](https://github.com/hneogy/gp-omm-conformance)'s conformance cases against your GP/OMM parser as
ordinary pytest tests: one test per case, which passes, fails with the failing items, or skips with gpconf's reason
(a case that needs the provider files you have not fetched, say).

```
pip install pytest-gpconf
pytest --gpconf-cmd "./my-adapter {fmt}" --gpconf-case alpha5-tle-derived --gpconf-case corrupt-input
```

The options are `gpconf run`'s: `--gpconf-preset`, `--gpconf-adapter module:Class` or `--gpconf-cmd "..."`, with
`--gpconf-vectors-cmd`, `--gpconf-write-cmd`, `--gpconf-root` and `--gpconf-case` (repeat it; every case when none is
given). Writing the adapter is `docs/ADAPTERS.md` in the corpus, and the corpus's `templates/` hold one in eight
languages.

The plugin runs gpconf once per session and reads its `--json` report (the results schema 1.0); it changes no
verdict. A case passes when gpconf says pass or pass within tolerance.

Tested with pytest 9.2 and gpconf 0.9.0.
