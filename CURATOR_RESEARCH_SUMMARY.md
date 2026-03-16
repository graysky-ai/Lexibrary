# Lexibrary Curator Agent: Architecture & Knowledge Layer Research

## Executive Summary

The Lexibrary project is a sophisticated AI-friendly codebase indexer with a rich knowledge layer organized into three distinct systems:
1. **blueprints/** — Hand-maintained pseudo-lexibrary for Lexibrary itself (not the output it produces)
2. **.lexibrary/** — The output format Lexibrary produces for indexed projects
3. **.claude/agents/** and CLI commands — Existing agent patterns and orchestration

A "Curator" agent would orchestrate library maintenance tasks: validating consistency, managing deprecations, enforcing conventions, and coordinating cross-artifact updates.

---

## 1. KNOWLEDGE LAYER: blueprints/ STRUCTURE

### Location & Purpose
- **Path:** `/blueprints/` (hand-maintained, read-only for agents)
- **NOT** `.lexibrary/` (reserved for Lexibrary's own output)
- **Purpose:** Knowledge base for agents building Lexibrary itself

### Core Files
1. **START_HERE.md** (500+ lines)
   - Project topology (ASCII tree of `src/lexibrary/` package structure)
   - Package map (one-line role for each subpackage)
   - Navigation by intent (task → file mapping table)
   - Key constraints (annotations, pathspec patterns, rich.console, Pydantic 2)
   - Navigation protocol (design files are source of truth)

2. **BLUEPRINT_INSTRUCTIONS.md** (250 lines)
   - Directory structure conventions
   - Design file format template (150–300 tokens per file)
   - START_HERE.md format spec
   - HANDOFF.md format spec (5–8 lines max, post-it style)
   - Workflow for populating design files

3. **HANDOFF.md** (8 lines)
   - Task, Status, Next Step, Key Files, Watch Out
   - Overwritten completely on session end (never append)

### Design Files Structure (blueprints/src/lexibrary/)
- **24 subdirectories** mirroring source package structure
- **100+ markdown files** documenting each module
- **Format:** YAML frontmatter + markdown body

Each design file includes:
- **Summary:** One sentence — what the module does and why
- **Interface:** Table of public functions/classes with signatures and purpose
- **Dependencies:** Lexibrary-internal imports (bullet list)
- **Dependents:** Which modules import this one
- **Key Concepts:** Wikilink-style cross-references
- **Dragons:** Optional — real gotchas only

### Example Design File Coverage
```
src/lexibrary/cli/
  ├── __init__.md                  (re-export summary)
  ├── _shared.md                   (shared helpers: console, stubs)
  ├── lexi_app.md                  (agent-facing commands: lookup, concepts, stack)
  └── lexictl_app.md               (maintenance commands: init, update, validate, status)

src/lexibrary/validator/
  ├── __init__.md                  (13-check registry)
  ├── checks.md                    (3 error + 4 warning + 6 info checks)
  └── report.md                    (issue/summary/report models)

src/lexibrary/iwh/                 (I Was Here ephemeral signals)
  ├── __init__.md                  (public API re-exports)
  ├── model.md                     (IWHFile + IWHScope Pydantic model)
  ├── parser.md                    (YAML → IWHFile)
  ├── reader.md                    (read_iwh, consume_iwh, find_all_iwh)
  ├── writer.md                    (write_iwh with auto directory creation)
  └── gitignore.md                 (IWH gitignore integration)
```

---

## 2. DESIGN FILE ORGANIZATION

### Access Pattern (agents use this workflow)
1. Run `lexi search <query>` to find relevant files
2. Run `lexi lookup <file>` to get design context
3. Read the blueprint design file at `blueprints/src/lexibrary/<path>.md`

### Key Design Decisions Documented
- **Hook output format** (PreToolUse/PostToolUse hook JSON shape)
- **Lookup extraction** — core lookup logic lives in `src/lexibrary/lookup.py` (not CLI glue)
- **Model field names** — `description` (not `role`), `entries` (not `members`)
- **Graceful degradation** — link graph returns `None` when index unavailable

### Maintainability Pattern
> The source is truth; the design file is the explanation.

When agents edit source files, they MUST update the corresponding design file:
- Run `lexi lookup <file>` before editing
- Update design file frontmatter: `updated_by: agent`
- Run `lexi validate` to check for broken wikilinks

---

## 3. AGENT PATTERNS (from .claude/agents/)

### Explore Agent (.claude/agents/explore.md)
- **Model:** Haiku (lightweight)
- **Tools:** Read, Bash
- **Workflow:**
  1. Start with `lexi search <query>` for relevant files
  2. Before reading, run `lexi lookup <file>` for context
  3. For domain questions, use `lexi concepts <topic>`
  4. For standards, use `lexi conventions <path>`
- **Output:** Structured summary with absolute paths + line numbers
- **Fallback:** Only use `find`/`grep` if `.lexibrary/` doesn't exist

### Bead Agent (.claude/agents/bead-agent.md)
- **Model:** Opus (heavyweight)
- **Workflow:**
  1. Receive `<bead-id>` assignment
  2. Claim bead: `bd update <bead-id> --claim`
  3. Action tasks from OpenSpec change's `tasks.md`
  4. Close bead: `bd close <bead-id>`
  5. Report back to Orchestrator with summary
- **Output:** Structured report (Bead ID, Change, Group, Progress, Next)

### Agent Rules Generation (src/lexibrary/init/rules/)
- **Supported Environments:** Claude, Cursor, Codex
- **Generated Artifacts:**
  - `CLAUDE.md` + `.claude/commands/` (Claude)
  - `.cursor/rules/` + `.cursor/skills/` (Cursor)
  - `AGENTS.md` (Codex)
- **Rule Types:**
  - Core rules (from `base.py`)
  - Orient skill (`/lexi-orient` — lists working directory setup)
  - Search skill (`lexi search`, `lexi lookup`, `lexi concepts`)
  - Environment-specific rules

---

## 4. VALIDATION & MAINTENANCE (lexi validate / lexictl validate)

### Validation Check Registry (13 checks total)
Located in `blueprints/src/lexibrary/validator/checks.md`

#### Error-Severity (3 checks)
| Check | Purpose |
|-------|---------|
| `wikilink_resolution` | Parse `[[wikilinks]]` in design files/Stack posts; verify resolution via WikilinkResolver; unresolved → error with fuzzy-match suggestions |
| `file_existence` | Verify `source_path` in design files, `refs.files`/`refs.designs` in Stack posts point to existing files |
| `concept_frontmatter` | Validate concepts have mandatory fields: `title`, `aliases`, `tags`, `status` (enum: draft/active/deprecated) |

#### Warning-Severity (4 checks)
| Check | Purpose |
|-------|---------|
| `hash_freshness` | Compare design file `source_hash` against current SHA-256; mismatches = stale design file |
| `token_budgets` | Count tokens for START_HERE, HANDOFF, design files, concepts, .aindex files; over-budget = warning |
| `orphan_concepts` | Scan for `[[wikilinks]]`; concepts with zero inbound refs = warning |
| `deprecated_concept_usage` | Find deprecated concepts (`status: deprecated`) still referenced; includes `superseded_by` suggestions |

#### Info-Severity (6 checks)
| Check | Purpose |
|-------|---------|
| `forward_dependencies` | Parse `## Dependencies` in design files; verify listed paths exist on disk |
| `stack_staleness` | Check if referenced files' design files have stale `source_hash` |
| `aindex_coverage` | Walk scope_root; report directories lacking `.aindex` files |
| `bidirectional_deps` | Compare design file `## Dependencies` vs link graph `ast_import` links; report mismatches in both directions |
| `dangling_links` | Query all artifacts from `index.db`; verify backing files exist |
| `orphan_artifacts` | Query `index.db`; report entries whose backing files deleted; suggests index rebuild |

### Validation Invocation
```bash
lexi validate --severity=warning        # Only errors + warnings
lexi validate --check=wikilink_resolution  # Single check
lexi validate --json                    # JSON output for CI
```

### Output
- `ValidationReport` dataclass
- `ValidationIssue` objects (path, severity, message, suggestions)
- `ValidationSummary` (counts by severity)
- Exit code = 1 if errors found

---

## 5. DEPRECATION & LIFECYCLE MANAGEMENT

### Concept Lifecycle (artifacts/concept.md)
```python
status: Literal["draft", "active", "deprecated"]
superseded_by: str | None           # Points to replacement concept name
```

### Deprecation Patterns
1. **Concept deprecation:**
   - Set `status: deprecated`
   - Fill `superseded_by: ConceptName` (optional)
   - Validator checks `deprecated_concept_usage` (warning)
   - `lexi concepts --all` to show deprecated; hidden by default

2. **Design file staleness:**
   - Validator `hash_freshness` checks compares stored `source_hash` against current file
   - `lexi lookup` shows staleness warning
   - `lexi lookup --brief` includes status

3. **IWH (I Was Here) signals:**
   - Scope: `warning`, `incomplete`, `blocked`
   - Ephemeral (consumed/deleted after reading)
   - Used to mark unfinished work or blockers

---

## 6. IWH SYSTEM (Inter-Agent Signals)

### Purpose
Ephemeral, directory-scoped signals left by one agent session for the next.

### Model (iwh/model.md)
```python
@dataclass
class IWHFile:
    author: str                           # min_length=1
    created: datetime
    scope: Literal["warning", "incomplete", "blocked"]
    body: str = ""                        # free-form markdown
```

### Operations
| Operation | Function | Behavior |
|-----------|----------|----------|
| Write | `write_iwh(directory, scope, body, author)` | Create `.iwh` in `.lexibrary/<mirror-path>/.iwh` |
| Read | `read_iwh(directory)` | Non-destructive read; returns `IWHFile \| None` |
| Consume | `consume_iwh(directory)` | Read + DELETE (even if corrupt) |
| List | `find_all_iwh(project_root)` | Discover all `.iwh` files; returns sorted list with age |

### Storage
- `.iwh` files mirror source tree structure in `.lexibrary/`
- Example: `src/auth/.iwh` → `.lexibrary/src/auth/.iwh`
- Gitignored via `**/.iwh` pattern

### CLI Commands
```bash
lexi iwh write <dir> --scope incomplete --body "unfinished refactoring"
lexi iwh read <dir>              # Read + delete
lexi iwh read <dir> --peek       # Read only (no delete)
lexi iwh list                    # Show all signals with age, author, scope
lexictl iwh clean --older-than 24  # Remove signals older than 24 hours
```

### Disabled State
If `config.iwh.enabled` is `False`, all commands exit early with a warning.

---

## 7. CLI ARCHITECTURE: lexi vs lexictl

### lexi_app (Agent-Facing)
Located: `blueprints/src/lexibrary/cli/lexi_app.md`

**Command Groups:**
- **Lookup & Navigation:** `lookup`, `describe`, `search`
- **Concepts & Knowledge:** `concepts`, `concept new`, `concept link`
- **Stack Q&A:** `stack post`, `stack search`, `stack finding`, `stack vote`, `stack accept`, `stack view`, `stack list`
- **Inspection:** `validate`, `status`
- **Signals:** `iwh write`, `iwh read`, `iwh list`
- **Help:** `agent_help` (registered as `lexi help`)

**Key Behaviors:**
- All commands require project root (except `agent_help` and `iwh list`)
- Graceful degradation: link graph returns `None` → fall back to file scanning
- Conventions delivered via `ConventionIndex.find_by_scope_limited()`
- Stack post IDs auto-assigned by scanning `ST-NNN-*.md` and incrementing
- Design file staleness checked via SHA-256 hash comparison

### lexictl_app (Maintenance)
Located: `blueprints/src/lexibrary/cli/lexictl_app.md`

**Command Groups:**
- **Initialization:** `init` (wizard + agent rules)
- **Content Generation:** `update` (design files), `bootstrap` (batch .aindex), `index` (single .aindex)
- **Validation:** `validate`, `status`
- **Setup:** `setup` (agent rules + git hooks)
- **Daemon:** `sweep` (one-shot or periodic), `daemon` (deprecated watchdog)
- **Maintenance:** `iwh clean`

**Key Behaviors:**
- `init` requires non-TTY guard (forces `--defaults` if piped)
- `init` re-init guard (prevents overwriting existing `.lexibrary/`)
- `update` supports `--changed-only` for git hook usage
- `bootstrap` recursively generates `.aindex` files bottom-up
- `setup --hooks` installs post-commit hook
- `sweep --watch` for periodic updates
- All heavy imports lazy (inside command functions)

### Shared Helpers (_shared.md)
- `console` — Rich console for all output
- `load_dotenv_if_configured()` — Loads `.env` if `config.llm.api_key_source == "dotenv"`
- `require_project_root()` — Walk up to find `.lexibrary/`
- `_run_validate()` — Shared validation runner (both CLIs)
- `_run_status()` — Shared status dashboard (both CLIs)

---

## 8. LINK GRAPH INDEX (linkgraph/query.md)

### Purpose
SQLite-backed bidirectional link index for rapid lookups, tag search, FTS, and dependency traversal.

### Key Classes
| Class | Purpose |
|-------|---------|
| `LinkGraph` | Read-only query interface wrapping SQLite connection |
| `ArtifactResult` | Lookup result (id, path, kind, title, status) |
| `LinkResult` | Inbound edge (source_path, link_type, context) |
| `ConventionResult` | Convention body scoped to directory |
| `TraversalNode` | Node in multi-hop graph traversal |

### Query Methods
| Method | Purpose |
|--------|---------|
| `get_artifact(path)` | Look up single artifact by path |
| `resolve_alias(alias)` | Resolve concept alias (case-insensitive) |
| `reverse_deps(path, link_type=None)` | All inbound links to artifact |
| `search_by_tag(tag)` | Find artifacts by tag (exact match) |
| `full_text_search(query, limit=20)` | FTS5 full-text search |
| `get_conventions(directory_paths)` | Retrieve conventions scoped to directories; root-to-leaf ordering |
| `traverse(start_path, max_depth=3)` | Multi-hop graph traversal with cycle detection; max 10 depth |
| `build_summary()` | Aggregate build statistics from most recent index build |

### Graceful Degradation
`LinkGraph.open()` returns `None` when:
- Database file doesn't exist
- Database is corrupt
- Schema version mismatch

Callers should branch on `None` and fall back to file-scanning search.

---

## 9. CONCEPTS & CONVENTIONS

### Concepts (wiki/)
- **Files:** `.lexibrary/concepts/*.md` (YAML frontmatter + markdown body)
- **Frontmatter:**
  ```yaml
  title: Error Handling
  aliases: [error-management, exceptions]
  tags: [architecture, convention]
  status: draft | active | deprecated
  superseded_by: NewConcept (optional)
  ```
- **Index:** `ConceptIndex` (search by title, alias, tag, substring)
- **Resolver:** `WikilinkResolver` — resolves `[[wikilinks]]` to concepts or Stack posts

### Conventions (conventions/)
- **Files:** `.lexibrary/conventions/<directory>/*.md`
- **Scopes:** project-level or directory-level
- **Status:** draft, active, or deprecated
- **Features:**
  - Directory hierarchy matching (conventions inherit root-to-leaf)
  - Pattern-based scopes (deferred, phase v2-2)
  - LLM extraction via archivist (deferred, phase v2-2)

### Access Pattern (lexi lookup)
```
## Related Concepts
- **error-handling** (active, convention) — description here
- **link-graph** (active, architecture) — description here

## Inherited Conventions
[project-level]
- from __future__ import annotations

[src/]
- pathspec: "gitignore" pattern name

[src/lexibrary/]
- No circular imports
```

---

## 10. MAINTENANCE PATTERNS & LIFECYCLE

### Hash-Based Staleness Tracking
1. **Two-tier hashing:**
   - Content hash: SHA-256 of source file
   - Interface hash: Tree-sitter AST skeleton rendering
2. **Metadata stored:**
   - `source_hash` in design file frontmatter
   - `interface_hash` in `.aindex` YAML
3. **Validation check:** `hash_freshness` compares stored vs current hashes

### CLI Command Triggers
| Trigger | Command | Effect |
|---------|---------|--------|
| Manual | `lexictl update` | Full project update |
| Manual (git hook) | `lexictl update --changed-only <files>` | Batch update changed files |
| Manual (periodic) | `lexictl sweep --watch` | Periodic update loop |
| Deprecated | `lexictl daemon start` | Watchdog (deprecated) |

### Validation Cascade
1. `lexi validate --severity error` — Catch design/wikilink/concept issues
2. `lexi validate --severity warning` — Check staleness, budgets, orphans
3. `lexi validate --severity info` — Forward deps, stack staleness, coverage

---

## 11. CURATOR AGENT: DESIGN IMPLICATIONS

Based on the research above, a Curator agent should:

### Key Responsibilities
1. **Health Checking** — Run `lexi validate` and report issues
2. **Deprecation Management** — Find deprecated concepts, flag usage, suggest replacements
3. **Staleness Detection** — Identify hash mismatches, prompt `lexictl update`
4. **Orphan Management** — Find orphan concepts, orphan artifacts (from link graph)
5. **Cross-Artifact Consistency** — Check bidirectional deps, wikilink resolution
6. **IWH Signal Processing** — Find and react to `incomplete`/`blocked` signals
7. **Documentation Coherence** — Verify design file descriptions match source code purpose
8. **Token Budget Audits** — Check that START_HERE, HANDOFF stay under budgets

### Integration Points
1. **Scheduled:** Run `lexi validate` periodically (CI/webhook)
2. **Reactive:** React to IWH `blocked` signals left by other agents
3. **Maintenance:** Coordinate with `lexictl update` and index rebuilds
4. **Reporting:** Publish validation reports to dashboards or Slack

### Data Model
Should consume:
- Validation reports (13-check registry)
- Link graph queries (`reverse_deps`, `search_by_tag`, `full_text_search`, `traverse`)
- Design file metadata (staleness, source_hash)
- IWH signal discovery (`find_all_iwh`)
- Concept registry with deprecation status

### Tools Needed
- `lexi validate --json` for structured reporting
- `lexi lookup <file>` for context
- `lexi search <query>` for cross-artifact discovery
- `lexi iwh list` for pending signals
- `lexi concepts --all` for full concept inventory
- Link graph query API (when index available)

---

## 12. KEY ARCHITECTURAL DECISIONS FOR CURATOR

From `MEMORY.md` and plans:

### Extract Logic into Reusable Modules
- Lookup logic must live in `src/lexibrary/lookup.py` (returning `LookupResult` dataclass)
- CLI is a thin renderer; enables MCP server and `--format json` reuse
- Future curator could call Python directly, not scrape CLI output

### Hook Output Format
```json
{
  "hookSpecificOutput": {
    "hookEventName": "...",
    "additionalContext": "..."
  }
}
```
(Bug exists in `lexi-pre-edit.sh` — emits bare `{"additionalContext": ...}` — tracker in both lookup and search upgrade plans)

### Design File Format
- `DesignFileFrontmatter.description` — the one-line purpose (NOT `role`)
- `AIndexFile.entries` — list of entries (NOT `members`)
- Filter `entry_type == "file"` for source files vs subdirectories

### Graceful Degradation Pattern
```python
graph = open_index(project_root)
if graph is None:
    # Fall back to file-scanning
    ...
```

---

## 13. RECOMMENDED CURATOR FEATURES (from research)

### Phase 1: Foundation
- Wrap `lexi validate` output into structured `CuratorReport` dataclass
- Implement IWH signal discovery (`find_all_iwh`)
- Create `CuratorContext` dataclass (project root, config, link graph, validation results)

### Phase 2: Active Curation
- Deprecation detector: find usage of `status: deprecated` concepts
- Orphan finder: concepts with zero inbound wikilinks
- Staleness reporter: design files with mismatched hashes
- Token budget auditor: START_HERE, HANDOFF, concept, design file token counts

### Phase 3: Coordination
- React to IWH `blocked` signals (escalate to human)
- Coordinate `lexictl update` based on validation findings
- Link graph dependency validator (bidirectional dep checking)
- Wikilink resolution troubleshooter

### Phase 4: Reporting & Automation
- Publish validation dashboards
- Suggest concepts for archival (no usage for N days)
- Auto-promote `draft` conventions to `active` (post-review)
- Cost tracking for LLM calls via token budgets

---

## FILES TO READ FIRST (for curator implementation)

1. **blueprints/START_HERE.md** — Master index
2. **blueprints/src/lexibrary/cli/lexi_app.md** — Agent-facing commands
3. **blueprints/src/lexibrary/validator/checks.md** — Validation rules
4. **blueprints/src/lexibrary/iwh/reader.md** — Signal discovery
5. **blueprints/src/lexibrary/linkgraph/query.md** — Graph queries
6. **blueprints/src/lexibrary/artifacts/concept.md** — Concept lifecycle
7. **plans/v2-master-plan.md** — Strategic overview
8. **plans/convention-v2-plan.md** — Future convention features

---

## GLOSSARY

| Term | Meaning |
|------|---------|
| **blueprints/** | Hand-maintained knowledge layer for Lexibrary development (not the `.lexibrary/` output) |
| **aindex** | Structural directory index (`.aindex` files in `.lexibrary/` mirror) |
| **Design file** | YAML-frontmatter markdown document for a source file (e.g., `src/auth/login.py.md`) |
| **Concept** | Cross-cutting knowledge artifact (e.g., "Error Handling", "Authentication") |
| **Convention** | Coding standard scoped to project or directory |
| **IWH** | "I Was Here" ephemeral signal file (consumed by next agent) |
| **Link graph** | SQLite index of artifact relationships and reverse dependencies |
| **Staleness** | Design file's `source_hash` no longer matches source file's SHA-256 |
| **Wikilink** | `[[ConceptName]]` cross-reference to concepts or Stack posts |
| **Stack post** | Q&A-style problem report with findings, votes, resolution tracking |

