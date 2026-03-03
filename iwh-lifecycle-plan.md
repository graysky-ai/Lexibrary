# IWH (I Was Here) Lifecycle Plan

Companion to `aindex-lifecycle-plan.md` and `design-lifecycle-plan.md`. IWH files are fundamentally different from the other artefact types — they're **ephemeral signals between agent sessions**, not persistent knowledge artifacts.

See `docs/user/artefact-lifecycle.md` for the question framework.

---

## Storage & Path Architecture

IWH files already live in the unified mirror tree under `.lexibrary/designs/`:

```
project/
  src/
    auth/
      login.py
    cli/
      app.py
  .lexibrary/
    designs/
      src/
        auth/
          .aindex          <- directory index
          .iwh             <- IWH signal for src/auth/
          login.py.md      <- design file
        cli/
          .aindex
          .iwh             <- IWH signal for src/cli/
          app.py.md
```

Path computed via `iwh_path(project_root, source_directory)` in `src/lexibrary/utils/paths.py`. Already migrated to `DESIGNS_DIR` alongside aindex.

**Gitignore**: IWH files are gitignored (`**/.iwh` pattern via `ensure_iwh_gitignored()`). This is correct — they're ephemeral, local-only signals. No change needed.

**One signal per directory**: Each directory has at most one `.iwh` file at any time.

---

## 1. Initialization

**Decision**: No initialization. IWH is reactive, not pre-computed.

IWH signals are agent-to-agent communication. There's no agent history before project initialization, so there's nothing to signal. `lexictl bootstrap` does not create or interact with IWH files.

- **Brand new project**: No signals. First IWH appears when an agent leaves work incomplete.
- **Existing project being onboarded**: No signals. The first agent session discovers the project state organically via aindex and design files.

---

## 2. Creating New IWH Files

**Decision**: Purely agent-triggered. The coding agent decides when to leave a signal.

### Flow

1. Agent determines it cannot complete its current work in a directory
2. Agent runs `lexi iwh write <dir> --scope {warning|incomplete|blocked} --body "description"`
3. IWH module writes `.iwh` file to `.lexibrary/designs/<rel-dir>/.iwh`
4. If an existing signal exists for that directory, it is silently overwritten (latest wins)

### Scopes

| Scope | Meaning |
|-------|---------|
| `warning` | Advisory info for next agent (non-blocking) |
| `incomplete` | Work started but unfinished in this directory |
| `blocked` | Cannot proceed until a specific blocker is resolved |

### Why Agent-Triggered Only

- Only the agent has the context to know when work is incomplete or blocked
- Automated detection (e.g., failing tests, lint errors) would produce too many false positives — not every modified directory needs a signal
- The CLAUDE.md rules instruct agents to write signals when leaving work unfinished

### Key Difference from Other Artefacts

Unlike design files (which need a skeleton + enrichment queue pattern) or aindex (which needs filesystem crawl), IWH creation is always a single atomic write. No queuing, no two-phase creation, no LLM involvement.

---

## 3. Maintaining IWH Files

**Decision**: Latest-wins overwrite. No history, no appending.

IWH files are **not maintained** — they're **consumed and replaced**. This is the sharpest divergence from aindex and design files.

- Each `lexi iwh write` overwrites the previous signal for that directory
- There's exactly 0 or 1 signal per directory at any time
- The previous signal is lost — this is correct because IWH signals are about *current state*, not history
- No comment/annotation layer (unlike design files)
- No overwrite warnings — the agent replacing a signal has the most current context

### Why No History

If an agent needs to understand *why* something was historically blocked or incomplete, that belongs in design file annotations (per the design lifecycle plan's §3), not in ephemeral signals. IWH is a sticky note system — one note per location, latest wins.

---

## 4. Deprecating / Cleaning Up IWH Files

**Decision**: Consume-on-read as primary mechanism + TTL auto-cleanup via `lexictl update` + orphan detection.

### Primary: Consume-on-Read

- `lexi iwh read <dir>` (without `--peek`) deletes the file after reading
- The session start protocol consumes all signals the agent addresses
- This handles the happy path — agent starts, reads signals, acts on them

### Safety Net: TTL Auto-Cleanup

For signals that are never consumed (agent crash, user kills session, signal forgotten):

- `lexictl update` includes IWH cleanup as part of its sweep
- Signals older than 72 hours are deleted
- TTL configurable in `.lexibrary/config.yaml`:

```yaml
iwh:
  enabled: true
  ttl_hours: 72  # default; signals older than this are auto-cleaned
```

72 hours is long enough to survive a weekend, short enough that truly abandoned signals don't persist.

### Orphan Detection

During `lexictl update`:
1. Walk `.lexibrary/designs/` for `.iwh` files
2. For each, check if the corresponding source directory still exists
3. If not, delete the `.iwh` (consistent with aindex orphan detection pattern)

### No Soft Deprecation

Unlike design files (which have `status: deprecated` with TTL countdown), IWH files are simply deleted. There's no historical value to preserve — the signal's purpose is consumed the moment an agent reads it.

---

## 5. Reading and Using IWH Files

> **DEFERRED**: Implementation deferred until aindex, design, and IWH usage are designed together. The tiered context model for all three artefact types must be coordinated.

### Design Intent

IWH signals should only be surfaced to the agent when it is **committed to making modifications in that directory**. Signals must not be consumed casually — an agent browsing or exploring should not trigger IWH consumption.

### Consumption Model

**Hooks peek, agent explicitly consumes.** Hook injections use peek mode (read without delete). The agent must explicitly run `lexi iwh read <dir>` to consume (delete) a signal, confirming it has been addressed.

### Planned Tiering (to be finalized alongside aindex/design usage plan)

| Tier | Trigger | Behavior | Consumes? |
|------|---------|----------|-----------|
| Tier 1 | Session start | List existence of pending signals (awareness only) | No |
| Tier 2 | Agent commits to modifying a directory | Inject full IWH content | No (peek) |
| Tier 3 | Agent explicitly runs `lexi iwh read` | Full content, signal deleted | Yes |

### Key Constraint: Avoid Casual Consumption

The critical design constraint is that agents must not consume IWH signals willy-nilly. Consumption must be a deliberate act after the agent has committed to working in that directory. This prevents:
- Signals being consumed during exploration without being acted on
- Drive-by reads that clear signals the agent never addresses
- Loss of context when the agent gets distracted after consuming

### How IWH Interacts with Other Artefacts

| Agent Activity | IWH Provides |
|---|---|
| Starting a session | Awareness that pending signals exist (not content) |
| Committed to modifying a directory | Full signal: scope, body, context from previous agent |
| Finishing incomplete work | Mechanism to leave context for the next agent |
| Understanding why something is broken | Blocked/warning context that supplements design file info |

---

## Resolved Decisions

| Question | Decision | Rationale |
|----------|----------|-----------|
| Initialization behavior | No initialization | IWH is reactive; no agent history before init |
| Creation trigger | Agent-triggered only | Only the agent knows when work is incomplete/blocked |
| Maintenance model | Latest-wins overwrite | Ephemeral signals about current state, not history |
| Cleanup mechanism | Consume-on-read + TTL (72h) + orphan detection | Three layers: primary, safety net, orphan handling |
| TTL default | 72 hours, configurable | Survives a weekend, doesn't persist indefinitely |
| Overwrite warning | No | Noise — the replacing agent has the most current context |
| Token budget | None | Signals are small; no need for a dedicated budget |
| §5 implementation timing | Deferred | Built alongside aindex and design usage plan |
| Casual consumption | Prevented by design | Hooks peek only; explicit `lexi iwh read` to consume |
