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

## Outreach text (owner convention, 2026-09-27)

Every message to another project (an issue, a comment, a pull request's description, a reply)
is written for a maintainer to read, not to carry the corpus's record. A SatDump collaborator
asked, on #1221, not to be sent LLM-generated text: hard to read; focus on the actual issue
(https://github.com/SatDump/SatDump/issues/1221#issuecomment-5857824841). The owner adopted
that as a standing convention for all outreach from 2026-09-27:

- Lead with the one-sentence finding. Then one reproduction and one measured number. Stop.
- No [tested]/[inferred] brackets in filed text. They belong in the corpus's own records,
  not a maintainer's inbox.
- No structured tables, no section headers, no bulleted inventories in a first report.
  Prose.
- File:line citations only where the line is the point.
- The evidence lives in the corpus; the message points at it.

What this does not change: the verification standard behind every claim stays exactly as it
is. Every sentence of a message rests on a run or a source read recorded in the handoff, with
its markers there, and a claim that is not verified stays out of the message. What changes is
how much of the evidence goes in the message.

The lengths, in words of the posted text, measured 2026-09-27. The length that drew the
complaint: the original #1221 report, 459 words, three numbered points, two of them under
bold headings, and a bracket on each, followed by a 79-word narrowing the next day
(https://github.com/SatDump/SatDump/issues/1221). The length that has worked: the #44 comment
on dnwrnr/sgp4 after v3.0, 194 words
(https://github.com/dnwrnr/sgp4/issues/44#issuecomment-5848881779); the astroz #99
confirmation, 128 words (https://github.com/ATTron/astroz/pull/99#issuecomment-5850276993);
and the reply to the complaint on #1221, 39 words
(https://github.com/SatDump/SatDump/issues/1221#issuecomment-5857935271). The first two predate
the convention and each carries a [tested] bracket; they are cited for their length, not for
their brackets. A draft written before 2026-09-27 is checked against this section before it
goes out.

## Voice, for anything posted under the owner's name (owner convention, 2026-10-06)

The section above says what goes in a message. This one says how it sounds, and it covers
everything posted publicly under the owner's name: issues, pull requests, comments, forum posts.
The owner's words:

> Rules: short and casual, contractions, first person, one finding per message, no bracketed
> tags like [tested], no exhaustive edge-case lists — mention extras in one line or leave them
> for a follow-up. Plain words, no "for whenever". Every draft is something I'd say out loud.
>
> Disclosure stays honest: if anyone asks whether AI was involved, the answer is yes, plainly,
> in the same casual voice. Never claim I did something by hand that the tools did.

Writing to it:

- Start with the finding, said the way you would say it to the maintainer in person. A second
  finding is a second message.
- No headers, tables or bullet lists in the posted text. A code block for the reproduction is
  fine.
- Extras get one line or wait for a follow-up.
- "I" is for what the owner did, thinks or offers. For work a session did, name what ran
  ("this came up running gpconf against 2.0") or leave it out. A draft that says "I ran these"
  is true only once the owner has run them.
- Asked whether AI was involved, the owner's answer is: "Yeah, I use AI tools a lot for this
  project and check what comes out. The README has the details."
- Read the project's own contribution rules before anything is posted there.

The verification standard is unchanged, and so is the rule that nothing is posted without the
owner's word for that message. Working notes and the check to run before a draft goes out are
in the private handoff, `docs/handoff/voice-guide.md`.

## Grader changes (owner rule, 2026-10-09)

Any change that adds or touches a way for the runner to not grade something — a skip, an `Unsupported`, a
refusal, a tolerance, a deduplication, an optional field — must come with a wrong-on-purpose adapter in
`tests/adversarial/` that tries to use it to hide a bug, plus a twin showing the same bug fails without it.
No adversarial adapter, no merge.
