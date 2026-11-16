# Decision register

This is the single source for accepted project decisions. Append entries; do not
rewrite history when a decision changes. Because this file keeps growing, never
name it as the `--authority` of a resolved blocker: name the owner's dated note
or the answered question, and cite that here.

## D001 — Adopt the v4 operating scaffold

- Status: accepted
- Date: replace during project intake
- Decision: Use `roadmap.yaml` for plan authority and the ledger for loop history.
- Reason: The project starts from this template.
- Supersedes: none

## D002 — Milestone executor mode

- Status: accepted with the template; confirm or withdraw during project intake
- Date: replace during project intake
- Decision: One capable agent, the milestone executor, may run a whole milestone
  under a run authorization approved by the owner
  (`05_governance/human_owner_notes/<MID>_run.md`). It operates the slice loop with
  the unchanged scripts, codes itself or through subagents, and has each slice
  reviewed by a fresh read-only subagent. It accepts a slice on a recorded pass
  without asking, with `ledger.py accept <slice> --commit`, and makes one hand-back
  commit at the end, of named paths and only when nothing is pending or staged. It
  never pushes, never edits the plan, the brief, the rules or the scripts, and
  never runs, records or closes the milestone review. The milestone review is
  prepared by the owner with the architect and done by a reviewer the owner
  starts. Defaults: two corrective rounds per slice; a stuck slice stops the run.
  The executor's ledger events carry the actor `architect`, meaning loop operator;
  no script is changed and no autonomy profile is declared. The executor is a lead
  developer, not a second architect: it has no authority over the plan or the
  design.
- Reason: Each milestone is executed in one go by a very capable agent, with a
  review after each slice and the independent check at the end of the milestone.
  Without this decision the architect hands over every slice, and the coder may
  neither commit nor run the loop.
- Rules: `AGENTS.md` (Milestone executor), `docs/milestone_run.md`,
  `initialization/executor.md`.
- Supersedes: the per-slice architect handover and the coder's commit ban, for
  authorized milestone runs only. A project that withdraws this decision works by
  `docs/operating.md` alone.
