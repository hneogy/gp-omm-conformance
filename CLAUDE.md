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

Treat perishable evidence as urgent. Rolling windows, pre-catalog ids,
live feeds and anything else that will not reproduce later must be
captured cleanly the moment we realise it matters, ahead of other work.

Retrying, backtracking, or changing approach to get a result right is
expected, not a failure. Log it in DECISIONS.md and continue. Never
carry forward a weak result just because redoing it costs time.
