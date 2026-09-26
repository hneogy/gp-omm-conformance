# Security

Report a vulnerability privately, through GitHub's private vulnerability reporting:
https://github.com/hneogy/gp-omm-conformance/security/advisories/new. Please do not open a public issue for it.

In scope: the runner (`gpconf/`), the adapters behind its presets (`gpconf/adapters/`), the fetch code
(`gpconf/fetch.py`, `tools/fetch.py`), the staging script that builds the package (`tools/stage_package.py`), the
GitHub Action (`action.yml`, `tools/action_report.py`), and the Space-Track verification tool
(`tools/verify_against_spacetrack.py`), which asks for your Space-Track username and password.

Not in scope: the corpus data, the expected values, derived files and vectors frozen from public provider responses
and published standards (a wrong value there is an ordinary issue); and `harnesses/`, best-effort recipes that
compile against other projects' internals.

The `gpconf` package has no runtime dependencies: it uses the Python standard library only. The optional extras,
`sgp4` and `pyephem`, install the libraries those presets test, and the Node.js presets use the Node and the library
you installed yourself.
