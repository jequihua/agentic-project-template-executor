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
`05_governance/human_owner_notes/`, one file per finding. Its first line is
`# Waiver: <finding ID> (guided)` or `(forced)`. Fill it once, commit it by name
before the waiver round, and never edit it afterwards.

## Recording

`pass` and `override` both refuse open P0-P2 findings. A waiver is therefore a
human report with the verdict `override` that sets the finding to
`waived_by_human`; `ledger.py waive` writes that report and records it. A report
is taken only while the slice is `reviewing`, and after a needs-work review the
slice is at `fix`. So the waiver takes one more round in which nothing changes:

1. `python scripts/prompt.py <slice>`.
2. `python scripts/ledger.py coded <slice> --notes <notes>`; the notes say that
   nothing changed and name the waiver file.
3. `python scripts/verify.py <slice>`.
4. The owner runs `python scripts/ledger.py waive <slice> --finding <ID>
   --authority <waiver file> --objective <status> --by human`, adding `--force`
   for a forced waiver. The status is `achieved`, `not_achieved` or
   `indeterminate`. Several findings take `--finding` and `--authority` in
   pairs; every open P0-P2 finding of the slice must be named.
5. `python scripts/ledger.py accept <slice>`, with `--commit` when authorized.

The command refuses a P0, a finding that is not open, a waiver file whose first
line does not name the finding and the kind, a living file, an automated seat
and any actor but `human`. It writes `<slice>_r<round>_waiver.md` beside the
slice's reviews: the update rows with source and hash, the verdict, the kind and
the waiver files.

The same report may be written by hand and recorded with `ledger.py record
<report> --by human`. Then an older finding belongs in `## Finding updates`
only, and the report says who drafted it.

Two traps:

- Make no commit between step 3 and step 4, a hand-back commit included. The
  receipt is tied to the commit it was made on.
- `--by human` records the owner as the actor: the owner runs the command.

## At the milestone review

The reviewer reads every `waived_by_human` row of the backlog that belongs to
the milestone, with its waiver file, and states for each whether the limit holds
in the finished product. A forced waiver is named in the report.
