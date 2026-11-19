# Waivers

A waiver is the human owner's decision to accept work with one finding left as
it is. The scripts record a waiver; they cannot judge it.

## Who and what

- Only the human owner waives. The architect recommends and writes the waiver
  file. A milestone executor, coder or reviewer never waives and never writes
  that file; an executor gives its evidence in the run report.
- An exact P1 or P2 finding can be waived, one finding per waiver.
- P0 is never waived: it is fixed, or a reviewer regrades it.
- P3 needs no waiver; it is carried.

Look at two cheaper moves first. The grade: a fault reached only by input
outside the acceptance line's field, without data loss or security effect, is P3
(`AGENTS.md`, Reviewer). The contract: an acceptance line that promises more
than the project needs is corrected in `roadmap.yaml` before the next round
([method](method.md#rounds-and-reopening)).

## Guided waiver

All five conditions hold, each with one sentence of evidence in the waiver file:

1. **Shown.** The architect reproduced the finding, or showed what it rests on,
   and says what was run.
2. **Out of reach.** It needs input that the project's own cases, loaders,
   planned runs and documented use do not produce, and that crosses no trust
   boundary.
3. **Bounded.** It cannot lose data, has no security effect and gives no wrong
   result on a real case.
4. **Written down.** The limit is stated where a user reads it, and the finding
   stays in the backlog as waived.
5. **Human.** The architect recommends; the owner decides, in the owner's words.

## Forced waiver

For a finding that misses a condition. The waiver file names the condition and
says why the owner accepts that; its title and the report say `forced`. It
accepts a known fault that can be reached, so it is for extreme cases.

## The waiver file

Copy `questions/template_waiver.md` to a dated file of its own in
`05_governance/human_owner_notes/`. Fill it once and never edit it afterwards.

## Recording

`pass` and `override` both refuse open P0-P2 findings. A waiver is therefore a
human report with the verdict `override` that sets the finding to
`waived_by_human`, and `ledger.py record` takes a report only while the slice is
`reviewing`. After a needs-work review the slice is at `fix`, so the waiver takes
one more round in which nothing changes:

1. `python scripts/prompt.py <slice>`.
2. `python scripts/ledger.py coded <slice> --notes <notes>`; the notes say that
   nothing changed and name the waiver file.
3. `python scripts/verify.py <slice>`.
4. `python scripts/prompt.py <slice> --review`.
5. Write the report at the path that prompt names, in its contract: an empty
   `## Findings` table; `## Finding updates` with one row per waived finding
   (source report, its hash as the backlog prints it, finding ID,
   `waived_by_human`, `-`); the closure decision; `Verdict: override - next:
   Accept <slice>.` After the verdict line, a section `## Waiver` names the
   waiver file, says `guided` or `forced`, who drafted the report and that the
   owner decided.
6. The owner runs `python scripts/ledger.py record <report> --by human`.
7. `python scripts/ledger.py accept <slice>`, with `--commit` when authorized.

Three traps:

- Make no commit between step 3 and step 6, a hand-back commit included. The
  receipt is tied to the commit it was made on.
- An older finding is waived in `## Finding updates` only. Listed in
  `## Findings` as well, the record is refused.
- `--by human` records the owner as the actor. The owner runs the command, and
  the report says who drafted it.

## At the milestone review

The reviewer reads every `waived_by_human` row of the backlog that belongs to
the milestone, with its waiver file, and states for each whether the limit holds
in the finished product. A forced waiver is named in the report.
