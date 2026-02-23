# Backlog

Living backlog for Lexibrary. Extracted from the master plan's "Implementation Backlog"
section, inline TODOs, open questions, and deferred plans.

**Workflow:** Items start here as quick captures. When ready to implement, promote to an
OpenSpec change (`opsx:new`) or GitHub Issue.

## Statuses

| Status | Meaning |
|--------|---------|
| `planned` | Confirmed — we intend to build this |
| `proposed` | Likely useful but needs design/scoping before committing |
| `suggestion` | Nice-to-have idea — not committed, may never happen |
| `blocked` | Waiting on a prerequisite or decision |
| `resolved` | Done or no longer relevant (keep briefly for audit trail, then delete) |

## Importance

| Level | Meaning |
|-------|---------|
| `critical` | Blocks launch or core workflows |
| `high` | Significant usability or correctness gap |
| `medium` | Meaningful improvement, not blocking |
| `low` | Polish, convenience, or edge-case coverage |

---

## CLI Gaps

Items where the overview or design describes a CLI command/flag that doesn't exist yet.

| Importance | Status | Item | Context |
|------------|--------|------|---------|
| medium | proposed | `lexi concepts --tag <t>` | Overview §4/§9 specifies this flag. Current impl only accepts positional `<topic>`. Phase 5. |
| low | proposed | `lexi concepts --status <s>` | Filter draft/deprecated concepts. Added to overview §4/§9. Phase 5. |
| low | proposed | `lexi concepts --all` | Overview §9. May be moot if bare `lexi concepts` already shows everything — decide if default should be "active only." Phase 5. |
| medium | proposed | `lexi stack mark-outdated <post-id>` | Mutation `mark_outdated()` exists in code but has no CLI surface. Phase 6. |
| low | proposed | `lexi stack duplicate <post-id> --of <id>` | Mutation `mark_duplicate()` exists in code but has no CLI surface. Phase 6. |
| high | planned | `lexictl update --dry-run` | Preview what would change without LLM calls. See overview Q-005. Phase 4. |
| medium | planned | `lexictl update --start-here` | Regenerate START_HERE.md independently without a full project update. Phase 4. |
| medium | proposed | `lexictl validate --fix` | Auto-remediate fixable issues (refresh stale hashes, remove broken wikilinks). Scope TBD. See D-047. Phase 7. |

## Feature Gaps

Design-described capabilities that aren't delivered yet.

| Importance | Status | Item | Context |
|------------|--------|------|---------|
| high | blocked | Mapping strategy evaluation | `mapping.strategies` config field is an empty stub. The 1:1/grouped/abridged/skipped strategies from overview §2 are never evaluated. Needs: pattern matching engine, strategy-specific templates, grouped file aggregation. Blocked on design decisions (overview Q-010). Post-Phase 4. |
| medium | planned | Concurrency for `lexictl update` | D-025 establishes sequential MVP with async architecture ready. Needs config key (`update.max_concurrent`). Not urgent — locks in `utils/locks.py` are pre-wired as no-ops. Post-Phase 4. |
| low | suggestion | `start_here.topology_format` config | Overview §1 says topology format is "configurable" (Mermaid vs ASCII). No config key exists. See overview Q-009. Phase 8b. |

## Configuration Suggestions

Potential config improvements — none committed.

| Importance | Status | Item | Rationale |
|------------|--------|------|-----------|
| medium | suggestion | `llm.archivist_model` | Use a cheaper/faster model for design file generation vs START_HERE. Archivist does repetitive work on many files; a cheaper model may suffice. |
| medium | suggestion | `crawl.max_files` | Hard limit on files per `lexictl update` run. Safety valve for enormous projects where accidental full updates are expensive. |
| low | suggestion | `validate.disabled_checks` | Persist disabled checks in project config (suppress `orphan_concepts` during early setup). Currently CLI-only via `--check` / `--severity`. |
| low | suggestion | `scope_root` as list | Multiple source roots for monorepos (e.g., `["src/", "lib/"]`). See overview Q-007. |
| low | suggestion | Stack post token warning | Optional warning threshold for large Stack posts. See overview Q-006. |

## Tech Debt

Inline TODOs and code-level improvements.

| Importance | Status | Item | Location |
|------------|--------|------|----------|
| medium | planned | Track stale LLM fallback summaries | `src/lexibrary/crawler/engine.py:220` — Add a flag to detect files where we fell back to a cached summary so persistent LLM failures can be re-queued. |
| low | proposed | Log or surface validator check failures | `src/lexibrary/validator/__init__.py:134` — Individual check exceptions are silently swallowed. Could log them or surface as issues. |
| low | proposed | v1 crawler rework | `src/lexibrary/crawler/engine.py:19` — v1 indexer retired in Phase 1, crawler tagged for rework in a later phase. Decide if this is still relevant or should be removed entirely. |

## Refactors

Larger structural changes.

| Importance | Status | Item | Context |
|------------|--------|------|---------|
| high | planned | Rename `lexibrary` → `lexibrary` | ~470 files across src/, tests/, blueprints/, openspec/, plans/, config. Full plan in `plans/rename-lexibrary-to-lexibrary.md`. Daemon dotfiles: Option A chosen — move `.lexibrary.log`/`.pid` into `.lexibrary/`. |

## Open Questions

Unresolved design decisions from the master plan (some block backlog items above).

| Status | Question | Context |
|--------|----------|---------|
| proposed | Mapping strategy config — confirm glob-pattern approach for 1:1/grouped/abridged/skipped | Blocks "Mapping strategy evaluation" above. |
| proposed | Tree-sitter grammar installation — bundled or on-demand? | Leaning on-demand with clear error message. |
| proposed | `baml-py` version pin — bump from `0.218.0`? | Check if newer version needed for current prompt patterns. |

## Resolved

Items kept briefly for audit trail. Periodically delete these.

| Item | Resolution |
|------|------------|
| `lexi init` vs `lexi setup` | D-054 — Combined into `lexictl init` wizard. `lexictl setup --update` refreshes rules only. |
| Skills/commands generation | Scoped and delivered in Phase 8c. |
| Persist agent environment in config | D-058 — `lexictl init` wizard persists `agent_environment`. |
| `lexi stack list` | Implemented (was missing from spec, now added to overview §9). |
