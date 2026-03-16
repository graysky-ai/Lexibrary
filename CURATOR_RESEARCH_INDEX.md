# Curator Agent Research — File Index & Navigation

## Overview
This document maps research findings to their source files. Use this to navigate the project during curator implementation.

---

## SECTION 1: Knowledge Layer (blueprints/)

### Core Entry Points
| Finding | File | Lines | Purpose |
|---------|------|-------|---------|
| Project topology, package map, navigation by intent | `/blueprints/START_HERE.md` | 1-239 | Master index for all agents |
| Design file format spec, instructions for documentation | `/blueprints/BLUEPRINT_INSTRUCTIONS.md` | 1-192 | Workflow for populating blueprints |
| Session handoff template | `/blueprints/HANDOFF.md` | 1-8 | Session relay (5-8 lines max) |

### Design Files (src/lexibrary/)
| Subsystem | Files | Key Designs | Location |
|-----------|-------|------------|----------|
| **CLI Architecture** | 5 files | `lexi_app`, `lexictl_app`, `_shared` | `blueprints/src/lexibrary/cli/` |
| **Validation** | 3 files | `__init__` (registry), `checks` (13 checks), `report` (models) | `blueprints/src/lexibrary/validator/` |
| **Signals (IWH)** | 7 files | `model`, `parser`, `reader`, `writer`, `gitignore` | `blueprints/src/lexibrary/iwh/` |
| **Link Graph** | 4 files | `query` (read-only interface), `builder`, `schema` | `blueprints/src/lexibrary/linkgraph/` |
| **Concepts/Wiki** | 6 files | `index`, `resolver`, `parser`, `serializer`, `template` | `blueprints/src/lexibrary/wiki/` |
| **Artifacts** | 7 files | `concept`, `design_file`, `aindex`, serializers/parsers | `blueprints/src/lexibrary/artifacts/` |
| **Init/Rules** | 7 files | `scaffolder`, `wizard`, `detection`, rules for Claude/Cursor/Codex | `blueprints/src/lexibrary/init/` |

---

## SECTION 2: Validation & Health Checking

### 13 Validation Checks
**Reference:** `/blueprints/src/lexibrary/validator/checks.md` (lines 1-62)

#### Error Checks (§3, lines 9-11)
- `wikilink_resolution` — Parse `[[wikilinks]]`; verify resolution
- `file_existence` — Verify file paths exist on disk
- `concept_frontmatter` — Validate concept YAML fields

#### Warning Checks (§4, lines 15-22)
- `hash_freshness` — Design file `source_hash` vs current SHA-256
- `token_budgets` — START_HERE, HANDOFF, design files token counts
- `orphan_concepts` — Concepts with zero inbound wikilinks
- `deprecated_concept_usage` — Deprecated concepts still referenced

#### Info Checks (§5, lines 26-33)
- `forward_dependencies` — Design file `## Dependencies` verification
- `stack_staleness` — Referenced files with stale design files
- `aindex_coverage` — Directories lacking `.aindex` files
- `bidirectional_deps` — Design deps vs link graph mismatches
- `dangling_links` — Index entries whose files don't exist
- `orphan_artifacts` — Index entries for deleted files

### CLI Invocation
```bash
lexi validate --severity=warning      # Or lexictl validate
lexi validate --check=wikilink_resolution
lexi validate --json                  # For CI/parsing
```

---

## SECTION 3: IWH System (Signals)

### Quick Reference
**Reference Files:**
- Model: `/blueprints/src/lexibrary/iwh/model.md`
- Reader/Writer: `/blueprints/src/lexibrary/iwh/reader.md` + `writer.md`

### Key Classes
| Class | File | Purpose |
|-------|------|---------|
| `IWHFile` | `model.md` | Pydantic model with author, created, scope, body |
| `IWHScope` | `model.md` | Type alias: "warning" \| "incomplete" \| "blocked" |
| `read_iwh()` | `reader.md` | Non-destructive read |
| `consume_iwh()` | `reader.md` | Read + DELETE (even if corrupt) |
| `find_all_iwh()` | `reader.md` | Discover all signals under `.lexibrary/` |
| `write_iwh()` | `writer.md` | Create signal with auto directory creation |

### Storage Pattern
```
src/auth/.iwh          →  .lexibrary/src/auth/.iwh
src/api/.iwh           →  .lexibrary/src/api/.iwh
```

### CLI Commands
```bash
# Agent-facing
lexi iwh write src/auth --scope incomplete --body "..."
lexi iwh read src/auth [--peek]
lexi iwh list

# Maintenance
lexictl iwh clean --older-than 24
```

---

## SECTION 4: CLI Commands

### lexi_app (Agent-Facing)
**Reference:** `/blueprints/src/lexibrary/cli/lexi_app.md` (lines 1-100)

#### Command Summary
| Group | Commands | Key Design Docs |
|-------|----------|-----------------|
| Lookup & Navigation | `lookup`, `describe`, `search` | Lines 13-28 |
| Concepts & Knowledge | `concepts`, `concept new`, `concept link` | Lines 17-20 |
| Stack Q&A | `stack post/search/view/vote/accept/list` | Lines 21-26 |
| Inspection | `validate`, `status` | Lines 15-16 |
| Signals | `iwh write/read/list` | Lines 29-31 |
| Help | `agent_help` (as `lexi help`) | Line 18 |

#### Internal Helpers
- `_render_conventions()` — Format conventions grouped by scope (line 41)
- `_stack_dir()`, `_next_stack_id()`, `_slugify()`, `_find_post_path()` — Stack management (lines 37-40)

### lexictl_app (Maintenance)
**Reference:** `/blueprints/src/lexibrary/cli/lexictl_app.md` (lines 1-72)

#### Command Summary
| Group | Commands | Key Design Docs |
|-------|----------|-----------------|
| Initialization | `init` (wizard + rules) | Lines 11 |
| Content Generation | `update`, `bootstrap`, `index` | Lines 12-14 |
| Validation | `validate`, `status` | Lines 15-16 |
| Setup | `setup` (rules + hooks) | Line 17 |
| Daemon | `sweep`, `daemon` | Lines 18-19 |
| Maintenance | `iwh clean` | Line 20 |

### Shared Helpers
**Reference:** `/blueprints/src/lexibrary/cli/_shared.md`

| Helper | Purpose |
|--------|---------|
| `console` | Rich console for all output |
| `load_dotenv_if_configured()` | Load `.env` for LLM API keys |
| `require_project_root()` | Walk up to find `.lexibrary/` |
| `_run_validate()` | Shared validation runner |
| `_run_status()` | Shared status dashboard |

---

## SECTION 5: Link Graph Index

### Design Reference
**File:** `/blueprints/src/lexibrary/linkgraph/query.md` (lines 1-81)

### Key Query Classes
| Class | Purpose |
|-------|---------|
| `LinkGraph` | Read-only query interface (lines 14) |
| `ArtifactResult` | Lookup result: id, path, kind, title, status (lines 9) |
| `LinkResult` | Inbound edge: source_path, link_type, context (lines 10) |
| `ConventionResult` | Convention body scoped to directory (lines 12) |
| `TraversalNode` | Multi-hop traversal result (lines 11) |

### Key Query Methods (lines 35-44)
| Method | Return Type | Purpose |
|--------|-------------|---------|
| `get_artifact(path)` | `ArtifactResult \| None` | Lookup by path |
| `resolve_alias(alias)` | `ArtifactResult \| None` | Resolve concept alias |
| `reverse_deps(path, link_type=None)` | `list[LinkResult]` | Inbound links |
| `search_by_tag(tag)` | `list[ArtifactResult]` | Tag-based search |
| `full_text_search(query, limit=20)` | `list[ArtifactResult]` | FTS5 search |
| `get_conventions(dirs)` | `list[ConventionResult]` | Retrieve conventions by scope |
| `traverse(start_path, max_depth=3)` | `list[TraversalNode]` | Multi-hop traversal |
| `build_summary()` | `list[BuildSummaryEntry]` | Build statistics |

### Graceful Degradation (lines 46-62)
`LinkGraph.open()` returns `None` when:
- Database missing
- Database corrupt
- Schema version mismatch

---

## SECTION 6: Deprecation & Lifecycle

### Concept Lifecycle
**Reference:** `/blueprints/src/lexibrary/artifacts/concept.md` (lines 1-23)

### Status Field (line 9)
```python
status: Literal["draft", "active", "deprecated"]
superseded_by: str | None
```

### Deprecation Workflow
1. Set `status: deprecated` in concept frontmatter
2. Fill `superseded_by: ReplacementConcept` (optional)
3. Validator runs `deprecated_concept_usage` check (warning severity)
4. `lexi concepts --all` shows deprecated; hidden by default

### Hash-Based Staleness
**Reference:** `validator/checks.md` lines 15-19

- Stored in design file: `source_hash` (metadata)
- Checked against: current file SHA-256
- Validator check: `hash_freshness` (warning)
- CLI indicator: `lexi lookup` shows staleness warning

---

## SECTION 7: Architecture Decisions

### From MEMORY.md & Plans

**Lookup Extraction (lines 1-6)**
- Core logic must live in `src/lexibrary/lookup.py`
- Returns `LookupResult` dataclass
- CLI is thin renderer
- Enables MCP server, `--format json`, Python-direct calls

**Hook Output Format (lines 8-11)**
```json
{
  "hookSpecificOutput": {
    "hookEventName": "...",
    "additionalContext": "..."
  }
}
```

**Model Field Names (lines 13-15)**
- `DesignFileFrontmatter.description` (NOT `role`)
- `AIndexFile.entries` (NOT `members`)
- Filter `entry_type == "file"` for source files

---

## SECTION 8: Plans & Roadmap

### Strategic Documents
| Document | Location | Purpose |
|----------|----------|---------|
| v2 Master Plan | `/plans/v2-master-plan.md` | Strategic overview, 10 phases, critical path |
| Convention v2 Plan | `/plans/convention-v2-plan.md` | Deferred convention features (pattern scopes, LLM extraction) |
| Lookup Upgrade | `/plans/lookup-upgrade.md` | Structured lookup output, sibling awareness, concepts, Stack posts |
| Navigation Protocol | `/plans/navigation-protocol-review.md` | Agent navigation patterns |
| Lexibrary Overview | `/plans/lexibrary-overview.md` | Design document (authoritative) |

### Key Phases
- **Phase 1:** Foundation (CLI skeleton, config)
- **Phase 3:** AST Parser (interface extraction)
- **Phase 4:** Archivist (design files, START_HERE)
- **Phase 7:** Validation & Status
- **Phase 8a:** CLI Split
- **Phase 10:** Unified Link Graph

---

## SECTION 9: Curator Agent Design Implications

### Key Responsibilities (from §11 of research summary)
1. Health Checking — `lexi validate`
2. Deprecation Management — deprecated concepts
3. Staleness Detection — hash mismatches
4. Orphan Management — orphan concepts/artifacts
5. Cross-Artifact Consistency — bidirectional deps
6. IWH Signal Processing — `find_all_iwh`
7. Documentation Coherence — design vs source alignment
8. Token Budget Audits — START_HERE, HANDOFF

### Tools to Use
```bash
lexi validate --json              # Structured reports
lexi lookup <file>                # Context
lexi search <query>               # Discovery
lexi iwh list                     # Signal discovery
lexi concepts --all               # Concept inventory
```

### Python APIs (when available)
- `LinkGraph.open()` → query interface or None
- `open_index(project_root)` → LinkGraph or None
- `find_all_iwh(project_root)` → list of (dir, IWHFile)
- `validate_library()` → ValidationReport

---

## SECTION 10: Files to Read (Curator Implementation Priority)

### Tier 1: Critical (Read First)
1. `/blueprints/START_HERE.md` — Master index
2. `/blueprints/src/lexibrary/validator/checks.md` — Validation rules
3. `/blueprints/src/lexibrary/iwh/reader.md` — Signal discovery
4. `/blueprints/src/lexibrary/cli/lexi_app.md` — Agent commands

### Tier 2: Important (Before Implementation)
5. `/blueprints/src/lexibrary/linkgraph/query.md` — Graph queries
6. `/blueprints/src/lexibrary/artifacts/concept.md` — Concept lifecycle
7. `/blueprints/src/lexibrary/cli/lexictl_app.md` — Maintenance commands
8. `/plans/v2-master-plan.md` — Strategic overview

### Tier 3: Reference (During Implementation)
9. `/blueprints/src/lexibrary/cli/_shared.md` — Shared helpers
10. `/blueprints/src/lexibrary/init/rules/` — Agent rule generation
11. `/plans/convention-v2-plan.md` — Future features
12. `/blueprints/BLUEPRINT_INSTRUCTIONS.md` — Documentation workflow

---

## SECTION 11: Quick Lookup Tables

### Validation Check Matrix
```
Error    → wikilink_resolution, file_existence, concept_frontmatter
Warning  → hash_freshness, token_budgets, orphan_concepts, deprecated_concept_usage
Info     → forward_dependencies, stack_staleness, aindex_coverage, 
           bidirectional_deps, dangling_links, orphan_artifacts
```

### IWH Scope Values
```
warning     → Advisory signal
incomplete  → Unfinished work
blocked     → Cannot proceed
```

### CLI Command Prefix Map
```
lexi        → Agent-facing (exploration, lookup, concepts, stack)
lexictl     → Maintenance (init, update, validate, setup, daemon)
```

### Link Types in Graph
```
ast_import        → Source code import
wikilink          → [[Concept]] reference
concept_file_ref  → Concept file reference
stack_file_ref    → Stack post file reference
convention        → Scoped coding standard
```

---

## GLOSSARY (Quick Reference)

| Term | Definition |
|------|-----------|
| **aindex** | Structural directory index (`.aindex` files in `.lexibrary/` mirror tree) |
| **blueprints/** | Hand-maintained knowledge layer for Lexibrary development (NOT the output) |
| **concept** | Cross-cutting knowledge artifact with status (draft/active/deprecated) |
| **convention** | Coding standard scoped to project or directory |
| **design file** | YAML-frontmatter markdown for a source file (e.g., `src/auth/login.py.md`) |
| **IWH** | "I Was Here" ephemeral signal file (consumed by next agent) |
| **link graph** | SQLite index of artifact relationships and reverse dependencies |
| **staleness** | Design file's `source_hash` no longer matches source file's SHA-256 |
| **wikilink** | `[[ConceptName]]` cross-reference to concepts or Stack posts |
| **Stack post** | Q&A-style problem report with findings, votes, resolution tracking |

