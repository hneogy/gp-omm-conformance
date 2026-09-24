# Decision policy

## The test for every decision

Choose the option that is logical, adds real value, and moves the project
toward its goal: a trustworthy, widely adopted conformance corpus that
establishes credibility in the space industry.

When two options are both correct, prefer the one that:
- makes the corpus more trustworthy (verifiable, sourced, honest about gaps)
- makes it more useful to more developers
- makes it more likely to be adopted and cited

## How to decide

Make the logical, best-supported choice yourself. Do not stop to ask me
for technical decisions. For each non-trivial choice, record it in
DECISIONS.md: what you chose, the alternatives, and a one-line reason.
If a choice turns out wrong, record the reversal rather than editing
history.

Default rules:
- Real data over synthetic. Omit a case rather than fabricate one.
- When a spec and practice disagree, record both; never silently pick.
- When uncertain, choose the more conservative, more reversible option.
- Respect CelesTrak rate limits: each URL once, cache, never loop.
- Interpret licences and terms strictly, never permissively.

## Stop and ask me ONLY for

- Accepting any terms of service or data-use agreement
- Anything requiring my credentials or accounts
- Making anything public: pushing to a public repo, publishing packages,
  posting anywhere
- Contacting any person or organisation
- Spending money
- Anything irreversible outside this repository

Everything else: decide, log it, keep going.

## Evidence quality and rework

Continuously check that the strength of our evidence matches the
strength of the claims resting on it. When a finding is important and
its provenance is weak, fix the provenance without being asked. This
includes re-fetching, re-running, re-verifying, or discarding a claim
we cannot support.

An entry that labels a claim untested, inferred, or taken from notes
or release notes records an open question, not a settled fact. Before
later work rests on such a claim, verify it; if it was wrong, add the
correcting entry. Mark such claims [untested] or [inferred] in the
entry. List one under "Open questions" in the handoff file only when
later work could rest on it or when evidence could settle it; an
incidental inference that fails both tests carries the marker and
nothing more. A correction entry quotes the evidence it rests on and
names what it checked; a correction that rests on a guess is the same
failure again.

Treat perishable evidence as urgent. Rolling windows, pre-catalog ids,
live feeds and anything else that will not reproduce later must be
captured cleanly the moment we realise it matters, ahead of other work.

Retrying, backtracking, or changing approach to get a result right is
expected, not a failure. Log it in DECISIONS.md and continue. Never
carry forward a weak result just because redoing it costs time.

A step that gates a commit passes on its own exit code, never on the
exit code of a filter after a pipe or on a line read from a log. Check
the code, then commit; a suite that printed FAILED has not passed.
In zsh write `${a}:Parser`, never `$a:Parser`: a colon after a bare
variable is a modifier, and the loop silently runs the wrong thing. A
loop that yields no output is a failure to look into, not an empty
result.

Commit messages carry no `Co-Authored-By` trailer, in this repository
or any other of the owner's (owner instruction, 2026-09-24). The AI
assistance is disclosed in the README; the trailer is not wanted.
Published history is not rewritten to remove it.

## Findings about other projects (Batch G convention, owner instruction 2026-09-24)

A decision entry that summarises a finding about another project which has not yet been
reported to that project names the library and says that a finding was recorded, and no
more; the specifics (the defect, the lines, the numbers, the draft) stay in the private
handoff under `docs/handoff/batch-g/` until the report is filed. `DECISIONS.md` is exported,
so anything more would publish the finding ahead of the maintainer hearing of it. Once the
report is filed, the entry is updated in place with the link; that addition is the one
in-place edit the append-only rule allows, because it completes the entry rather than
changing what was decided. D-128, D-132 and D-133 preceded this convention and carry the
specifics; they are not rewritten, and their drafts go out the week of 2026-09-24.
