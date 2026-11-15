# Contributing to gpconf

Thanks for helping. gpconf is small and kept strict, so a short read first saves a round trip.

## Ways to help

- **Run gpconf against a parser** and tell us what you found: an issue with the command you ran, the case name and
  the output. `docs/ONBOARDING.md` gets you to a first run in five minutes.
- **A wrong expected value, a case that passes a wrong parser, or a case that fails a right one**: open an issue with
  the case name, the file and the record. These are the most valuable reports gpconf gets.
- **An adapter or recipe for a library gpconf does not cover yet**: see `docs/ADAPTERS.md` and the templates in
  `templates/`.
- Issues labelled `good first issue` are small and self-contained.

Security problems go through private reporting, not issues: see `SECURITY.md`.

## Rules that keep the corpus trustworthy

- **No provider data in the repository.** Raw CelesTrak responses are fetched on each user's machine (`gpconf fetch`)
  and never committed; Space-Track data never enters it in any form. Expected values are frozen from fetched files
  and say where they came from (`manifest.json`).
- **No invented element sets.** Derived files change one thing in a real record (the catalog number, the epoch, the
  classification) and record what changed and why in a provenance file beside them.
- **One decision, one entry.** A change to what passes or fails, or to what the corpus claims, gets an entry in
  `DECISIONS.md` saying what changed, why, and what else was considered. The log is append-only: a correction is a
  new entry, never an edit of an old one.
- **Changes that can move a result** are listed first in the changelog, under "Changes that can move your result".

## Making a change

```bash
git clone https://github.com/hneogy/gp-omm-conformance
cd gp-omm-conformance
python3 -m unittest discover -s tests -t .     # the whole suite; Python 3.9 or later, no dependencies
python3 -m gpconf run --preset reference       # the reference reader against every case it can grade offline
```

Keep the standard library only in `gpconf/`. A new case comes with its `case.md` (what it tests, how to read a
failure, its coverage gaps) and its expected values, and, where it can, a wrong-on-purpose adapter in
`tests/adversarial/` that it fails.

## Reporting a finding to a library's maintainers

If gpconf finds a problem in someone else's parser, report it to them before saying so anywhere else, and make it
easy to check: one sentence for the finding, one short repro in their language, and **the exact gpconf command and
case name** that shows it, for example

```bash
gpconf run --adapter their_adapter:Parser --case alpha5-tle-derived
```

Be kind and specific: a result is about one version on one date, not a verdict on a project.

## Licence

gpconf is Apache-2.0 (`LICENSE`). By contributing you agree that your contribution is licensed under the same terms.
