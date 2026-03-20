Consolidated Instruction Reflection
Category A — openspec apply does not exist
Frequency: 9/9 agents (every single agent hit this)

Every bead-agent attempted openspec apply <change-name> <task-group> and found no such subcommand exists. Agents worked around it by using openspec instructions tasks --change <name>, openspec show, or reading tasks.md directly.

Target file: bead-agent.md (and any skill that references openspec apply)

Proposed rewrite:

Instead of: openspec apply <change-name> <task-group>
Use: openspec instructions tasks --change <change-name> to get task context, or read the tasks.md file directly at openspec/changes/<change-name>/tasks.md.

Category B — CLAUDE.md agent rules conflict with bead-worker scope
Frequency: 5/9 agents (1p9.4, 1p9.5, 1p9.6, 1p9.7, 1p9.9)

CLAUDE.md mandates lexi orient at session start, lexi lookup <file> before editing, and lexi validate after editing. Bead-worker instructions are silent on whether these apply. Agents either skipped them (citing task scope) or ran them and found them low-value in context. The final bead was also blocked by the CLAUDE.md prohibition on lexictl commands vs. the explicit task requirement to run lexictl update.

Target file: bead-agent.md

Proposed addition:

CLAUDE.md agent rules and bead context: Bead workers follow bead-specific instructions. The CLAUDE.md lexi orient / lexi lookup / lexi validate rules are for general sessions and are optional during focused bead execution — skip them unless they are listed as explicit task steps. Exception: if a task group explicitly references a lexi or lexictl command, that command takes precedence and the CLAUDE.md prohibition on lexictl does not apply within that task's scope.

Category C — Broken existing tests: fix now or defer to test group?
Frequency: 3/9 agents (1p9.1, 1p9.7, 1p9.8)

When an implementation group's behavior changes break existing tests, agents were uncertain whether to fix them immediately or defer to the dedicated test group. All three agents chose to fix immediately (which was the right call), but the instructions don't say so explicitly.

Target file: bead-agent.md or tasks.md authoring guidelines

Proposed addition:

If your implementation changes break existing tests, fix those tests as part of the current group — do not defer them to a later test group. A failing test suite blocks verification of your work.

Category D — openspec status requires --change <name> flag
Frequency: 2/9 agents (1p9.4, 1p9.7)

Instructions reference openspec status but the command requires --change <change-name> to be useful. Agents discovered this via trial and error.

Target file: bead-agent.md

Proposed rewrite:

Instead of: openspec status
Use: openspec status --change <change-name>

Category E — "Already done" scenario has no guidance
Frequency: 2/9 agents (1p9.1 scope overlap, 1p9.2 verify-and-close)

When a prior bead implements something that a later bead's task also covers, there is no documented workflow for "verify implementation, check the box, close the bead." Bead 1p9.2 was entirely pre-done by 1p9.1 and the agent had to infer the correct approach.

Target file: bead-agent.md

Proposed addition:

If a task's implementation was already completed by a dependency bead, verify the implementation is correct, run tests, mark the task checkbox in tasks.md, and close the bead normally. Do not re-implement.

Category F — lexi validate pre-existing errors: new vs. total
Frequency: 1/9 agents (1p9.9)

lexi validate returned 1219 pre-existing wikilink errors. The task said "confirm no broken wikilinks" with no guidance on how to handle a baseline of existing errors.

Target file: tasks.md authoring guidelines (or bead-agent.md)

Proposed addition:

When running lexi validate, check for errors introduced by your changes specifically — not the total error count. If pre-existing errors exist, note their count and confirm no new errors appear in the files you modified.

Category G — bd subcommands not documented
Frequency: 1/9 agents (1p9.5)

Agent tried bd get (doesn't exist); correct command is bd show. The bd CLI subcommands are not documented in bead instructions.

Target file: bead-agent.md

Proposed addition:

Key bd commands: bd ready (list unblocked beads), bd show <bead-id> (show bead details), bd claim <bead-id> (claim a bead), bd close <bead-id> (close a bead).

Priority Order for Fixes
openspec apply → openspec instructions tasks --change — affects every agent, highest friction
CLAUDE.md rules vs. bead scope — affects 5 agents, causes confusion and inconsistent behavior; the lexictl conflict is a real blocker
Fix broken tests immediately — affects 3 agents, agents made the right call but only by inference
openspec status --change flag — affects 2 agents, minor but repeated
"Already done" scenario — affects 2 agents (different failure modes), easy to document
lexi validate pre-existing errors — affects 1 agent, low ambiguity in practice
bd subcommands — affects 1 agent, minor