# Coder initialization

Read `AGENTS.md` and the coding prompt. The prompt contains the whole task and
its read/write boundary. Make the smallest correct useful change, run focused checks
while working and the full check once, never commit, and finish with the four
fact lists required by the prompt after one short approach paragraph.

If no coding prompt was supplied, do not invent a slice. If evidence or
authority is external, state a blocker question in your final message, with the
fields of `questions/template_question.md`, and stop. Do not create the question
file: it lies outside your write boundary. The architect or the milestone
executor saves it and records the blocker.

A coding subagent of a milestone executor follows this file: it codes its part
inside the write boundary, never runs the loop scripts and never commits. An agent
with a run authorization reads [executor](executor.md) instead.
