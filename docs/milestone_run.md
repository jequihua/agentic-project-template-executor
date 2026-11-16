# Milestone run

A milestone run lets one capable agent, the milestone executor, take a whole
milestone from its first slice to its last. It is the manual loop of
[operating](operating.md), operated by an agent under owner decision D002. It uses
the unchanged scripts and no autonomy profile. Roles and limits are in `AGENTS.md`.

## Who does what

| Role | In a milestone run |
| --- | --- |
| Owner | Approves the run. Prepares the milestone review with the architect and starts a reviewer of their own. Waives findings. Pushes. |
| Architect | Plans the milestone and prepares the run. Afterwards reads the run report and, with the owner, runs and records the milestone review and closes the milestone. |
| Milestone executor | Operates the slice loop, codes or delegates coding, has each slice reviewed, accepts recorded passes with a commit, hands back. Has no authority over the plan or the design. |
| Coding subagent | Codes a bounded part of a slice under the Coder rules. Never runs loop scripts, never commits. |
| Slice reviewer | A fresh read-only subagent. Reviews one slice from its review prompt and returns the report. |

The ledger knows the actors `human`, `architect` and `frutlups`. Events caused by
the executor carry `architect`, which in a run means loop operator. Who operated is
shown by the run authorization, the run report and the commits.

## Before the run (architect, with the owner)

1. The milestone is `active` in `roadmap.yaml`, with `holistic_review: true` and
   narrow slices whose acceptance lines can be observed.
2. `python scripts/prompt.py <slice> --preview` has been read for every slice.
3. The full verification command passes on the baseline; the tree is committed.
4. The run authorization is written, approved by the owner, cited from
   `00_brief/decisions.md` and committed:

```markdown
# Run authorization: M001

- Milestone and slices, in order: M001-S01, M001-S02, ...
- Authority: milestone executor as in AGENTS.md and docs/milestone_run.md.
- Corrective rounds per slice: 2.
- Budgets: for example hours of training, number of experiment attempts.
- Expected state at the start: a clean tree; what `ledger.py status` shows.
- Outside reading: public documentation of the libraries in use, or none.
- Excluded: anything the milestone's slices do not name.
- Approved by the owner on <date>: "<the owner's words>"
```

Start the executor in a new session with one instruction, for example: "Read
`AGENTS.md` and `initialization/executor.md`. Run milestone M001 under
`05_governance/human_owner_notes/M001_run.md`."

## The run (executor): eight steps per slice

Run the scripts with the project's Python, from the repository root.

| Step | Command or action |
| --- | --- |
| 1 | `python scripts/prompt.py <slice>` freezes the task and writes the coding prompt. Read it; it is the whole task of the slice. |
| 2 | Code inside the allowed prefixes, yourself or through subagents. Run the focused checks while working. |
| 3 | Save your notes (approach, then the four fact lists of the prompt) as `05_governance/reviews/<mid>/<slice>_r<round>_coder.md`. Run `python scripts/ledger.py coded <slice> --notes <that file>`. A change outside the boundary is refused: remove it, do not widen the boundary. |
| 4 | `python scripts/verify.py <slice>`. A failure starts the next round at step 1. |
| 5 | `python scripts/prompt.py <slice> --review` writes the review prompt. |
| 6 | Start a slice reviewer (below). Save its report, unchanged, at the path the review prompt names. |
| 7 | `python scripts/ledger.py record <report>`. |
| 8 | On `pass`: `python scripts/ledger.py accept <slice> --commit`, then the next slice. On `needs_work`: the next round at step 1; the new prompt carries the open findings. On `blocked`: stop. |

Between step 3 and step 7 do not touch the slice's product files: the receipt and
the review are bound to their recorded content, and a later change is refused as
drift. Keep scratch files in the ignored `local_state/`.

### Coding and delegation

The Coder rules of `AGENTS.md` bind you and every coding subagent. Give a subagent
the part of the coding prompt it needs and the write boundary. Subagents work in
this working tree, on files that do not overlap when they run at the same time.
They never run loop scripts and never commit. Slices are never run in parallel:
step 3 reads every change in the tree. You answer for delegated work. Read-only
subagents for search and reading are unrestricted.

### Outside reading

Unless the authorization says none, you, your coding subagents and the slice
reviewer may read the public documentation and public source of the libraries in
use, under the Safety rule of `AGENTS.md`. The rules grant no tool; the harness
does. Coders list their pages in their notes, the reviewer in `## Pages read`.

### The slice reviewer

A fresh subagent: no shared conversation, read and search tools only where the
harness offers that. Its whole brief is:

> Read `AGENTS.md` and `initialization/reviewer.md`. Then read and follow the review
> prompt at `<path written by step 5>`. Return the report as the plain text of
> your final message.

Add no summary, opinion or hint. Do not review your own work and do not edit the
report. If step 7 refuses the report for its format, ask the same reviewer to
repair the format only. To contest a finding, say so in the next round's notes;
only a reviewer closes a finding and only the owner waives one.

### Round limit

At most two corrective rounds per slice (three rounds in all), unless the
authorization states another number. A failed verification and a `needs_work`
review each use a round. At the limit, stop.

### Blockers and refusals

- Missing authority or evidence while coding: first `python scripts/ledger.py
  blocked <slice> --requirement ... --reason ... --actor ... --action ...`, and only
  then write the question in `questions/open/` from
  `questions/template_question.md`; then stop. In the other order the question
  file counts as a change outside the write boundary and `blocked` refuses.
- A coding subagent never creates a question file. It returns its blocker
  question as text; you record the blocker and save the question as above.
- An acceptance commit was interrupted: `python scripts/ledger.py recover` to
  inspect, `recover --execute` to finish only the missing git work. Never accept
  twice.
- Any other refusal you did not cause (evidence drift, a held lock, a malformed
  ledger line): stop. Never repair the ledger, and never use `--allow-dirty`,
  `reopen`, `resolve`, `cancel`, `attempt` or `--by human`.
- Do not skip a stuck slice to continue with later ones.

## Hand-back (executor)

Stop when all slices are accepted, on a blocker, at the round limit, when a budget
of the authorization is used up, or on a refusal you did not cause. Then write
`05_governance/reviews/<mid>/<MID>_run_report.md`:

- per slice: rounds, verdicts, the acceptance commit;
- what was delegated to subagents;
- every page read outside the project, per slice and role: address, version
  documented, reason;
- what could not be verified; deviations from the prompts;
- open questions and the reason for stopping.

Then the hand-back commit, which holds only that report and any new
`questions/open/` files. Make it only when both checks pass:

1. Nothing is pending: `python scripts/ledger.py status` prints no line
   `commit <id>: pending` and no `unresolved invocation`, and your last loop
   command did not refuse over a pending commit, a dispatch or a lock.
2. Nothing is staged: `git diff --cached --name-only` prints nothing.

If either check fails, do not commit, unstage, reset or clean anything. Leave the
report and the question files in the tree, and name their paths and the refusal in
your final message; the architect settles the pending work and commits them.

If both pass, name the paths in both commands, so that nothing else can enter:

```text
git add -- <report> <question files>
git commit -m "Hand back <MID>" -- <report> <question files>
git show --name-only --format= HEAD
```

The last command must list exactly those paths. Leave unfinished slice work in
the tree, uncommitted and unstaged. Do not run `prompt.py --holistic`,
`ledger.py record --milestone` or `ledger.py close`.

## Continuing an unfinished run

A run that stopped early is continued from its recorded state, never from step 1
by default. The architect prepares it (next section) and the owner approves a
continuation authorization. The executor then confirms that `git status --short`
shows exactly the uncommitted paths that authorization lists, and takes each
slice at the step `python scripts/ledger.py status` reports:

| State of the slice | Next move |
| --- | --- |
| `accepted` | Skip it. |
| `unstarted`, `fix` | Step 1: issue the coding prompt. |
| `coding` | Do not issue a prompt; it would be refused. Reuse the prompt already issued for this round (the newest file for the slice in `prompts/for_coding_agent/`), finish the work, continue at step 3. |
| `verifying` | Step 4. |
| `reviewing` | Step 6 with the review prompt already issued for this round; if there is none, step 5 first. |
| `accept_pending` | Step 8. |
| `blocked` | Not yours: the architect resolves it first, after which the state is `fix`. |
| any state with `commit <id>: pending` | Not yours: the architect recovers the commit first. |

Rounds already used count towards the round limit, and budgets already spent stay
spent, unless the continuation authorization says otherwise.

## After the run (architect, with the owner)

Read the run report and the open questions; inspect `python scripts/ledger.py
status`, `python scripts/ledger.py check` and `git status`. Then one of two routes.

**All slices accepted: the milestone review.**

1. `python scripts/prompt.py --holistic <MID>` writes the milestone review prompt
   for the owner's reviewer.
2. `python scripts/ledger.py record <report> --milestone <MID>`. `needs_work`
   reopens the slices concerned, for a further authorized run or manual rounds.
3. On `pass`: `python scripts/ledger.py close <MID>`, then mark the milestone done
   in `roadmap.yaml`, check and render ([operating](operating.md#steering-and-closure)).

**The run stopped early: prepare its continuation.** The milestone review is
refused until every slice is accepted.

1. Settle pending git work first: `python scripts/ledger.py recover`, then the
   steps of [upgrading](upgrading.md#exceptional-commands). If the executor could
   not make the hand-back commit, commit the run report and the question files
   yourself afterwards, by name; left untracked they would later count as a change
   outside a slice's write boundary.
2. Do not commit, stash or clean the unfinished work of a slice. `ledger.py coded`
   has to find it as that slice's change.
3. Answer the open questions and record what they change. Resolve a blocked slice
   with `python scripts/ledger.py resolve <slice> --reason ... --authority <file>`,
   naming a file written once, such as the owner's dated note: it is hashed whole
   and can never change again.
4. Write the continuation authorization, `05_governance/human_owner_notes/
   <MID>_run_2.md` (then `_3`, and so on), in the layout of the first, adding: the
   state of each unfinished slice as `ledger.py status` prints it; the uncommitted
   paths that belong to it, from `git status --short`; the corrective rounds and
   the budgets that remain. Have the owner approve it and commit that file alone,
   by name.

## What this mode trades

A slice is accepted on the subagent's review without a separate architect check.
That reviewer is started by the party it reviews, so it is not independent review;
the milestone review is. A defect missed by a slice review can be built upon until
the milestone ends: keep milestones modest. The rules and the scripts' integrity
checks are not isolation.
