# Plan: Hook-Based Agent Onboarding

> **Status**: Superseded by [`plans/start-here-dismantling.md`](start-here-dismantling.md).
>
> After the START_HERE dismantling, the generated document will be slim enough
> (~300 tokens) that agents can read it directly without hook injection. The
> hook mechanism pattern (SessionStart/SubagentStart context injection) was
> extracted to [`plans/hook-based-context-injection.md`](hook-based-context-injection.md)
> for future use in the agent rule template system.
>
> **What was preserved**: The conditional filtering by agent type, the tiered
> context budget analysis (15/50/240 lines), the hook output format
> (`hookSpecificOutput.additionalContext`), evidence/sources, and the
> verification plan are all in the extracted plan.
