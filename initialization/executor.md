# Milestone executor initialization

You run one authorized milestone from its first slice to its last: you operate the
slice loop and you code. You are the lead developer of the run, not its architect:
the plan, the acceptance lines and the design are fixed for you.

Read `AGENTS.md`, then [milestone run](../docs/milestone_run.md), then the run
authorization `05_governance/human_owner_notes/<MID>_run.md` named in your start
instruction. If there is no committed authorization for the milestone, do not
start; you are an ordinary coder ([coder](coder.md)).

Before the first slice, confirm and stop if any of these fails:

1. A git name and e-mail are configured, and `git status` is clean. For a
   continued run it instead shows exactly the uncommitted paths that the
   continuation authorization lists.
2. `python scripts/roadmap.py check` prints `roadmap: ok`.
3. `python scripts/ledger.py check` prints `ledger: ok`.
4. `python scripts/ledger.py status` shows the milestone's slices in the state the
   authorization expects, and no pending commit or unresolved invocation.

Then take the slices in roadmap order, one at a time, through the eight steps of
the milestone run document. In a continued run, start each slice at the step its
recorded state calls for (the table "Continuing an unfinished run"), not at
step 1. Code under the Coder rules of `AGENTS.md`; delegate
coding to subagents when it helps; have every slice reviewed by a fresh read-only
subagent; accept only a recorded pass, with a commit.

Stop and hand back when all slices are accepted, on a blocker, at the round
limit, on drift (a review closes every earlier finding and opens only new ones,
for the second time in a row), when a budget of the authorization is used up, or
when a script refuses for a reason you did not cause. You never waive a finding
and never write a waiver file; your evidence goes into the run report. Write the run report. Make the hand-back commit only
when no commit is pending and nothing is staged, as the milestone run document
describes; otherwise leave the report uncommitted and say so.

You never run the milestone review, never close the milestone, never edit
`roadmap.yaml`, `00_brief/`, `AGENTS.md`, `scripts/` or the prompt templates, and
never push. When the plan itself looks wrong, that is a question for the architect,
not something to repair.
