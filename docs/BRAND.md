# How the project names and describes itself

This file is the single source for the project's name and for the lines it uses to describe itself. Every place
that names or describes the project, in this repository, on PyPI, on the site and elsewhere, takes its text from
here. A change is made here first, with an entry in `DECISIONS.md`, and then carried to the places that use it.
Recorded 2026-10-04 (D-241); applied to the surfaces, with the two titles below, by D-242.

## Name

**gpconf.** The product name, everywhere a person reads it.

The repository stays `gp-omm-conformance`. "The GP/OMM conformance corpus" is the descriptive subtitle.

The GitHub Action is named gpconf too, and its job summary is headed with the name. A workflow still calls it by the
repository, `uses: hneogy/gp-omm-conformance@<tag>`.

The title a citation quotes, in `CITATION.cff` and from the next release on Zenodo:

> gpconf: a conformance corpus for orbital-data parsers crossing the five-digit catalog-number boundary

The Zenodo records of releases up to 0.5.1 keep the title they were published with.

## What the name means

GP is what CelesTrak and Space-Track call the orbital data: general perturbations. Conf is conformance: whether
your code reads that data the way it is actually served, not the way it used to be.

## Slogan

> Test what your parser actually reads.

## The sentence

Spoken:

> gpconf is a free test kit that tells you whether your satellite software can handle catalog numbers above 99,999.

Written:

> gpconf is a free test kit that tells you whether your satellite software handles catalog numbers above 99,999 — built from real CelesTrak data, with every expected answer traced to its source.

## About line

The short form, for a repository's About line and a package's summary:

> Free test kit: does your satellite software handle catalog numbers above 99,999? Built from real CelesTrak data.

## Headline

> The satellite catalog passed 99,999. Does your software know?

The short form, for titles and social posts:

> The satellite catalog passed 99,999. Is your code ready?

The headline stays as written. The line beneath it explains that the five-digit TLE range ended at 69,999, and it
does not say "not 99,999" directly under a headline that says 99,999:

> On 11 July 2026 the catalog assigned number 100000, and every object catalogued since has a six-digit number. The usable five-digit range had already run out at 69,999 (CelesTrak).

The facts behind those two lines, as the README states them: on 11 July 2026 the catalog assigned number 100000,
after exhausting the five-digit range, which ends at 69999; CelesTrak is the source for where that range ends. So
the catalog passed 99,999, and its five-digit range ended at 69999. Neither line says that the catalog's five-digit
numbers ran to 99,999 (D-188).

## Order

Where they appear together: the headline, then the written sentence, then the install command.

```bash
pip install gpconf
```

The name's meaning and the slogan go lower, on an About page or in an About section.
