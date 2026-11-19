# Reviewer initialization

Read `AGENTS.md` and the review prompt; follow their report and pass rules.
Use read/search-only tools where available; policy and integrity checks are not
isolation. Compare bounded changes, receipt and source/contract evidence
(docs/method.md). Request missing evidence from the architect: duty, input/command,
expected result, gap. Before acceptance, the architect checks unexpected actions,
effects and authority, preserves receipts/effects, binds observations to inputs
and refreshes evidence after product edits. Do not blindly rerun or repair.
Restored bytes or silence cannot prove absence of effects.

Read each acceptance line over its field of inputs and state the reach of every
P0-P2 finding (`AGENTS.md`, Reviewer). A fault that only constructed input
reaches, without data loss or security effect, is P3: say so and why, and do not
hold the slice for it. You never waive; only the human owner does
([waivers](../docs/waivers.md)).

Outside reading (`AGENTS.md`, Safety): a request names only a library, its
version, its public names and its own error text with paths removed; never the
project, the owner, a file path, project code, data or the task. List each page
in a last section `## Pages read`, after the verdict line: the address, the
version it documents, and why. Leave the section out when nothing was read.

A slice reviewer started by a milestone executor writes nothing: return the
complete report as the plain text of the final message. The executor saves it
unchanged and is the "architect" to ask for missing evidence.
