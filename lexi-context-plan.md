# `lexi context` — Detailed Implementation Plan

## Motivation

An agent about to edit code needs context from multiple artifact types: the
design file, applicable conventions, open stack posts, IWH signals, dependency
summaries, and referenced concepts. Today this requires 3-5 separate CLI calls
(`orient`, `lookup`, `search`, `concepts`, etc.) that the agent must
choreograph — deciding which calls to make, in what order, and how much context
to retain from each.

This is context engineering, and the agent is bad at it. It doesn't know which
artifacts are most relevant, can't estimate token cost, and can't prioritize
across artifact types. The result: agents skip calls, overload context with
low-value output, or make redundant queries.

`lexi context` is a single command that assembles a token-budgeted context
bundle from all relevant artifact types, prioritized by a configurable policy.
One call, one output. The library does the prioritization so the agent doesn't
have to.

---

## Design Principles

1. **Read-only assembler, not a new data store.** `lexi context` owns no data.
   It reads existing artifacts (design files, conventions, stack posts, IWH
   signals, link graph) and assembles a view. Maintenance = maintaining the
   underlying artifacts, which already has its own lifecycle.

2. **Token budget is a first-class constraint.** Every section competes for a
   finite budget. The output always fits within the declared budget. Agents
   never receive more than they asked for.

3. **Priority ordering is configurable.** Different teams value different
   artifact types. The default priority is sensible; the config makes it
   tunable without code changes.

4. **Subsumes `lookup --full`, extends beyond it.** `lookup --full` already
   does priority-based token budgeting for a single file. `lexi context`
   generalizes this to support file, directory, and multi-file scopes, adds
   dependency summaries and concept resolution, and exposes the budget as a
   CLI flag.

5. **Progressive detail.** High-priority sections are included in full.
   Lower-priority sections are abbreviated or omitted. The footer reports
   what was omitted and why, so the agent knows what's available if it needs
   to drill down with a targeted `lexi search` or `lexi stack search`.

---

## CLI Interface

```
lexi context <PATH> [--budget <N>] [--format markdown|json|plain]
```

### Arguments

| Argument | Description |
|---|---|
| `PATH` | File path, directory path, or glob pattern. Required. |
| `--budget` | Token budget for the output. Default from `config.yaml`. |
| `--format` | Output format. Inherits from `lexi --format` global flag. |

### Examples

```bash
# Single file — most common case (before editing)
lexi context src/lexibrary/archivist/pipeline.py

# Directory — broader scope (before working across a package)
lexi context src/lexibrary/archivist/

# Explicit budget — when the agent knows its remaining context capacity
lexi context src/lexibrary/archivist/pipeline.py --budget 8000

# JSON format — for programmatic consumption
lexi context src/lexibrary/archivist/pipeline.py --format json
```

---

## Scope Resolution

The `PATH` argument determines what artifacts are gathered. Scope resolution
is the first step in the pipeline.

### File scope

When `PATH` resolves to a single file:

1. **Primary target**: the file itself (its design file, conventions, etc.)
2. **Dependency fan-out**: the file's declared dependencies (from its design
   file `dependencies` list)
3. **Dependent fan-in**: files that import this file (from link graph
   `reverse_deps` with `link_type="ast_import"`)

### Directory scope

When `PATH` resolves to a directory:

1. **Primary target**: the directory's `.aindex` file (billboard + child list)
2. **Children**: all source files in the directory (one-liner summaries from
   their design files)
3. **Shared conventions**: conventions scoped to this directory or broader
4. **Aggregate IWH**: any IWH signals under this directory tree
5. **No dependency fan-out** — too broad. The agent should narrow to a file
   once they know what to edit.

### Resolution rules

```
PATH is file?
  → resolve to absolute path
  → find project root (walk up to .lexibrary/)
  → compute rel_path = target.relative_to(project_root)
  → find design file via mirror_path()

PATH is directory?
  → resolve to absolute path
  → find .aindex in that directory
  → list child source files

PATH doesn't exist?
  → error: "Path not found: {PATH}"
```

---

## Assembly Pipeline

The assembly pipeline gathers artifacts in priority order, renders each as a
text section, and truncates to fit the token budget. This is a generalization
of the existing `_truncate_lookup_sections()` pattern in `lexi_app.py:239-276`.

### Phase 1: Gather

Each gatherer produces a `ContextSection` dataclass:

```python
@dataclass
class ContextSection:
    """A single section of assembled context."""
    name: str                    # e.g. "design", "conventions", "stack"
    priority: int                # lower = more important
    content: str                 # rendered text
    token_estimate: int          # estimated tokens (chars // 4)
    source_paths: list[str]      # artifact paths that contributed
    drilldown_hint: str = ""     # e.g. "lexi stack search ..." for omitted sections
```

Gatherers are functions with signature:

```python
def gather_<name>(
    rel_path: str,
    project_root: Path,
    config: LexibraryConfig,
    link_graph: LinkGraph | None,
) -> ContextSection | None:
```

Each gatherer returns `None` if it has nothing to contribute (no conventions
exist, no stack posts reference this file, etc.). This keeps the output clean.

### Phase 2: Budget allocation

Sections are sorted by priority. The allocator walks the sorted list:

1. **Guaranteed sections** (priority 0-1): always included in full. These
   are the design summary and conventions — they're the minimum viable context.
   If they exceed the budget alone, the output is just these sections plus a
   truncation warning.

2. **Best-effort sections** (priority 2+): included in full if budget allows.
   If a section doesn't fit in full, it's truncated to the remaining budget.
   If nothing remains, it's omitted and its `drilldown_hint` is included in
   the footer.

3. **Footer**: always appended (costs ~50-100 tokens). Shows budget usage
   and lists omitted sections with their drilldown commands.

```python
def allocate_budget(
    sections: list[ContextSection],
    total_budget: int,
    guaranteed_priority: int = 1,
) -> tuple[list[ContextSection], list[str]]:
    """Return (included_sections, omitted_hints)."""
```

### Phase 3: Render

The renderer concatenates included sections with markdown headers and appends
the footer. Output formats:

- **markdown** (default): headers, code blocks, bullet lists. Optimized for
  LLM consumption — this is the format agents read best.
- **json**: structured dict with sections as keys. For programmatic use.
- **plain**: flat text, no markdown. For piping.

---

## Section Definitions

### Priority 0: Target Identity

**Always included. Cannot be truncated.**

For a file:
```
# Context: src/lexibrary/archivist/pipeline.py

Orchestrates the archivist pipeline: file discovery, change detection,
LLM-based design file generation, and enrichment queuing.
```

Source: design file frontmatter `description` field.

If no design file exists, falls back to the `.aindex` entry description.
If neither exists: `"No design file or index entry. Run lexictl update to generate."`

For a directory:
```
# Context: src/lexibrary/archivist/

<.aindex billboard description>

Files:
- pipeline.py — Orchestrates the archivist pipeline...
- service.py — Provides an async service that generates...
- change_checker.py — Provides logic to determine how a source file...
[...]
```

Source: `.aindex` file parsed via `parse_aindex()`.

**Estimated cost**: 50-150 tokens.

---

### Priority 1: Interface Contract

**Always included for file scope. Omitted for directory scope.**

```
## Interface Contract

```python
class ChangeLevel(str, Enum):
    UNCHANGED = "unchanged"
    CONTENT_CHANGED = "content_changed"
    INTERFACE_CHANGED = "interface_changed"
    ...

async def update_project(
    config: LexibraryConfig,
    archivist: ArchivistService,
    ...
) -> ErrorCollector:
    ...
`` `
```

Source: design file `interface_contract` section.

**Estimated cost**: 100-500 tokens (varies by file complexity).

---

### Priority 2: Applicable Conventions

**Always included (guaranteed). Truncated only if budget is critically low.**

```
## Conventions

- [error-handling] (project) Always use ErrorCollector for pipeline errors.
  Never bare raise — collect and continue.
- [async-pattern] (src/lexibrary/archivist) Pipeline orchestration functions
  are sync. LLM service calls are async. Don't mix.
```

Source: `ConventionIndex.find_by_scope_limited()` — same as `lookup`.

Display limit: `config.conventions.lookup_display_limit` (default 5).

**Estimated cost**: 50-200 tokens (depends on convention count and body length).

---

### Priority 3: IWH Signals

**Included if any exist for the target path. High priority because IWH signals
are time-sensitive inter-agent handoff information.**

```
## IWH Signal

- Scope: incomplete
- Author: claude-opus-4-6
- Created: 2026-03-17T14:30:00
- Body: Refactoring update_file() to add skeleton fallback. The skeleton
  write path is implemented but the check_change() extension for
  SKELETON_ONLY is not yet done. See max-token-fix.md Phase 3.

Run `lexi iwh read src/lexibrary/archivist` to consume this signal.
```

Source: `read_iwh()` from `lexibrary.iwh.reader`.

Checks both `designs/<rel_path>` and legacy `<rel_path>` mirror locations
(same logic as `_render_iwh_peek` in `lexi_app.py`).

**Estimated cost**: 50-150 tokens (body is truncated to 200 chars in preview).

---

### Priority 4: Open Stack Posts

**Included if any stack posts reference this file.**

```
## Known Issues

- [SP-0012] "StopReason: length on large files" (open, 3 votes)
  max_completion_tokens too low for lexi_app.py. See max-token-fix.md.
  → `lexi stack show SP-0012`

- [SP-0008] "ConventionIndex.load() silently skips malformed files" (open, 1 vote)
  → `lexi stack show SP-0008`
```

Source: link graph `reverse_deps(rel_path, link_type="stack_file_ref")`,
then `parse_stack_post()` for each, filtered to `status == "open"`, sorted
by votes descending.

Display limit: `config.stack.lookup_display_limit` (default 3).

**Estimated cost**: 30-150 tokens.

---

### Priority 5: Dependencies (with summaries)

**This is new — `lookup` only lists dependency names. `context` includes
one-line summaries from each dependency's design file.**

```
## Dependencies

- archivist/service.py — Provides an async service that generates design
  files using the BAML LLM infrastructure.
- archivist/change_checker.py — Provides logic to determine how a source
  file has changed relative to its corresponding design file.
- config/schema.py — Defines the project's canonical configuration schema
  and sane runtime defaults.
- errors.py — Provides a lightweight, structured way to capture, aggregate,
  and print errors encountered during pipeline runs.
- artifacts/design_file_parser.py — Provides robust parsing of design-file
  markdown artifacts.
- linkgraph/builder.py — Builds and populates the SQLite link graph index.
```

Source: design file `dependencies` list. For each dependency, load its
design file via `parse_design_file_frontmatter()` and extract `description`.
If no design file exists for a dependency, show the path alone (no summary).

**Estimated cost**: 20-40 tokens per dependency. A file with 6 dependencies
costs ~120-240 tokens.

---

### Priority 6: Dependents (brief)

**Files that import the target. Useful for understanding blast radius.**

```
## Dependents (5 files import this)

- cli/lexi_app.py
- cli/lexictl_app.py
- daemon/service.py
- archivist/__init__.py
- tests/test_archivist/test_pipeline.py
```

Source: link graph `reverse_deps(rel_path, link_type="ast_import")`.

No summaries — just paths. Summaries would be too expensive for what is
essentially a "who uses me?" glance.

**Estimated cost**: 5-10 tokens per dependent.

---

### Priority 7: Referenced Concepts

**Domain vocabulary terms that appear in the target file's design file wikilinks
or conventions. Helps agents use the right terminology.**

```
## Concepts

- [[design file]] — An LLM-generated per-file summary with dependency maps
  and interface contracts. Stored in .lexibrary/designs/.
- [[interface contract]] — The public API surface of a source file, extracted
  via AST parsing. Used for staleness detection.
```

Source: design file `wikilinks` list. For each wikilink, attempt to resolve
via `link_graph.resolve_alias()`. If it resolves to a concept artifact, load
the concept file and extract its summary (first sentence or `description`
from frontmatter).

Only include concepts that actually resolve. Dead wikilinks are silently
skipped (they'll show up in `lexi validate`).

**Estimated cost**: 30-60 tokens per concept.

---

### Footer (always appended)

```
---
Context budget: 3,800 / 6,000 tokens used
Omitted: dependents (5 files), concepts (3 terms)
  → `lexi impact src/lexibrary/archivist/pipeline.py` for full dependents
  → `lexi concepts "design file"` for concept details
```

The footer costs ~50-100 tokens and is always included. It tells the agent:
1. How much budget was used (transparency).
2. What was omitted (so the agent can drill down if needed).
3. The exact commands to get omitted information (actionable).

---

## Token Estimation

Use the existing `_estimate_tokens()` heuristic (`len(text) // 4`) from
`lexi_app.py:228-236`. This is fast (no imports, no encoding) and
sufficiently accurate for budgeting purposes.

Do NOT use `TiktokenCounter` here. The context command must be fast — agents
call it at the start of every task. A ~1ms character-division heuristic is
acceptable; a 10-20ms BPE encoding is not, especially when multiplied across
many dependency design files.

If accuracy becomes a problem later, the heuristic can be replaced without
changing the interface.

---

## Configuration

Add a new `ContextConfig` section to `LexibraryConfig`:

```python
class ContextConfig(BaseModel):
    """Context assembly configuration."""

    model_config = ConfigDict(extra="ignore")

    default_budget: int = 6000
    priorities: list[str] = Field(
        default_factory=lambda: [
            "identity",       # 0 — always included
            "interface",      # 1 — always included
            "conventions",    # 2 — always included
            "iwh",            # 3
            "stack",          # 4
            "dependencies",   # 5
            "dependents",     # 6
            "concepts",       # 7
        ]
    )
```

The `priorities` list determines section ordering. Sections not listed are
excluded. Reordering the list changes which sections get budget preference.
The first N entries (up to `guaranteed_priority_count`, default 3) are
guaranteed inclusion.

In `LexibraryConfig`:

```python
context: ContextConfig = Field(default_factory=ContextConfig)
```

In `config.yaml`:

```yaml
context:
  default_budget: 6000
  priorities:
    - identity
    - interface
    - conventions
    - iwh
    - stack
    - dependencies
    - dependents
    - concepts
```

---

## Module Structure

### New files

```
src/lexibrary/context/
    __init__.py          — Public API: assemble_context()
    assembler.py         — Assembly pipeline: gather, budget, render
    gatherers.py         — One function per section type
    models.py            — ContextSection, ContextResult dataclasses
```

### Why a new package (not inline in the CLI)

The assembly logic should be importable and testable independently of the
CLI layer. The CLI command is a thin wrapper that calls
`assemble_context()` and prints the result — same pattern as the `search.py`
module providing `SearchResults` that the CLI renders.

This also enables future consumers: hooks, IDE extensions, or (eventually)
an MCP server can call `assemble_context()` without going through the CLI.

### New CLI registration

In `lexi_app.py`:

```python
@lexi_app.command()
def context(
    path: Annotated[Path, typer.Argument(...)],
    *,
    budget: Annotated[int, typer.Option("--budget", ...)] = 0,
) -> None:
    """Assemble a token-budgeted context bundle for a file or directory."""
    ...
```

The `budget=0` default means "use `config.context.default_budget`".

---

## Implementation Phases

### Phase 1: Core assembler with file scope

**Deliverables:**
- `context/models.py` — `ContextSection`, `ContextResult` dataclasses
- `context/gatherers.py` — gatherers for: identity, interface, conventions,
  IWH, stack posts
- `context/assembler.py` — `assemble_context()` with budget allocation
- CLI command in `lexi_app.py`
- Config addition: `ContextConfig` in `schema.py`

**Scope:** File target only. No directory scope. No dependency/dependent
summaries. No concept resolution. This delivers the core value: one command
replaces orient + lookup + search for the common case.

**What it replaces:** An agent that previously did:
```
lexi orient
lexi lookup src/foo.py --full
lexi search "error handling"
```
Now does:
```
lexi context src/foo.py
```

**Tests:**
- Unit tests for each gatherer (mock project root with fixture design files)
- Integration test for `assemble_context()` with a real `.lexibrary/` tree
- Budget truncation tests (verify output stays within budget)
- CLI test (invoke via `CliRunner`, verify exit code and output structure)

### Phase 2: Dependency and dependent summaries

**Deliverables:**
- `gather_dependencies()` — reads each dependency's design file frontmatter
- `gather_dependents()` — queries link graph for `ast_import` reverse deps
- Wire into assembler priority chain

**Dependency:** Requires link graph to be populated (from `lexictl update`).
Graceful degradation: if link graph doesn't exist, these sections return
`None` and are silently omitted.

### Phase 3: Directory scope

**Deliverables:**
- Scope resolution for directory paths
- `.aindex` parsing for billboard + child list
- Aggregate IWH signal detection (walk subdirectories)
- Shared convention gathering (scoped to directory, not file)

### Phase 4: Concept resolution

**Deliverables:**
- `gather_concepts()` — resolves wikilinks from design file to concept
  artifacts, extracts summaries
- Requires link graph `resolve_alias()` and concept file parser

### Phase 5: JSON output format

**Deliverables:**
- Structured JSON output matching the `ContextResult` dataclass
- Useful for programmatic consumers, hook scripts, or test assertions

---

## Interaction with Existing Commands

### What `lexi context` replaces

For the common "about to edit" workflow, `lexi context` replaces the
multi-command ritual:

| Before | After |
|---|---|
| `lexi orient` | Not needed (topology is not per-file context) |
| `lexi lookup <file> --full` | `lexi context <file>` |
| `lexi search <topic>` | Still useful for ad-hoc questions mid-task |
| `lexi concepts <topic>` | Subsumed (concepts are in the bundle) |
| `lexi impact <file>` | Partially subsumed (dependents are in the bundle) |

### What `lexi context` does NOT replace

- `lexi orient` — still needed at session start for topology overview and
  IWH signal discovery. `context` is per-target; `orient` is per-project.
- `lexi search` — still needed for ad-hoc queries ("find all conventions
  about error handling"). `context` delivers what's relevant to a path, not
  what matches a query.
- `lexi stack search` / `lexi stack show` — still needed to drill into
  specific stack posts. `context` shows titles and IDs; the agent follows
  up with `stack show` if it needs the full post.
- `lexi validate` — still needed after editing. `context` is pre-edit;
  `validate` is post-edit.

### CLAUDE.md rule changes

Current rules:
```
## Before Editing Files
- Run `lexi lookup <file>` before editing any source file.
```

Proposed rules:
```
## Before Editing Files
- Run `lexi context <file>` before editing any source file to get a
  token-budgeted context bundle with design summary, conventions, known
  issues, and dependency context.
- Use `lexi lookup <file>` for a quick role check without full context.
- Use `lexi search <query>` for ad-hoc questions not tied to a specific file.
```

---

## Reuse of Existing Infrastructure

Almost every piece of the assembly pipeline already exists as a callable
function. The implementation is primarily wiring, not invention.

| Section | Existing function | Location |
|---|---|---|
| Identity | `parse_design_file_frontmatter()` | `artifacts/design_file_parser.py` |
| Interface | `parse_design_file()` → `.interface_contract` | `artifacts/design_file_parser.py` |
| Conventions | `ConventionIndex.find_by_scope_limited()` | `conventions/index.py` |
| IWH | `read_iwh()` | `iwh/reader.py` |
| Stack posts | `reverse_deps()` + `parse_stack_post()` | `linkgraph/query.py` + `stack/parser.py` |
| Dependencies | `parse_design_file()` → `.dependencies` | `artifacts/design_file_parser.py` |
| Dependents | `reverse_deps(link_type="ast_import")` | `linkgraph/query.py` |
| Concepts | `resolve_alias()` | `linkgraph/query.py` |
| Token estimation | `_estimate_tokens()` | `cli/lexi_app.py` (move to shared util) |
| Budget truncation | `_truncate_lookup_sections()` | `cli/lexi_app.py` (generalize) |
| `.aindex` parsing | `parse_aindex()` | `artifacts/aindex_parser.py` |

The `_estimate_tokens()` and `_truncate_lookup_sections()` functions should
be extracted from `lexi_app.py` into a shared utility (e.g.
`context/budget.py` or `utils/tokens.py`) since they'll be used by both
`lookup` and `context`.

---

## Error Handling and Graceful Degradation

The command must never fail hard. Agents call it at the start of every task —
a crash here blocks all downstream work.

| Condition | Behaviour |
|---|---|
| No `.lexibrary/` directory | Error message + exit 1 (same as `lookup`) |
| Path outside `scope_root` | Error message + exit 1 (same as `lookup`) |
| No design file for target | Fallback to `.aindex` entry description. If neither exists, show path + "No design file. Run `lexictl update`." Continue with other sections. |
| No link graph (index.db missing) | Skip sections that need it (stack, dependents, concepts). Include a note: "Link graph unavailable — run `lexictl update` to populate." |
| No conventions directory | Skip conventions section silently. |
| No IWH signals | Skip IWH section silently. |
| Design file for a dependency is missing | Show dependency path without summary. |
| Malformed design file | Skip that section, log warning. |
| Budget too small for guaranteed sections | Include guaranteed sections anyway (exceed budget), warn in footer: "Budget {N} is below minimum. Consider raising to {recommended}." |

---

## Performance Considerations

`lexi context` must be fast. It's called at the start of every agent task,
often before the agent does anything else. Target: **< 100ms** for file scope
with a warm filesystem cache.

### Cost analysis

| Operation | Cost | Count |
|---|---|---|
| `find_project_root()` | ~1ms (walk up dirs) | 1 |
| `load_config()` | ~2ms (YAML parse) | 1 |
| `parse_design_file_frontmatter()` | ~0.5ms (regex) | 1 + N deps |
| `parse_design_file()` | ~1ms (full parse) | 1 (target only) |
| `ConventionIndex.load()` | ~2ms (scan dir + parse) | 1 |
| `ConventionIndex.find_by_scope_limited()` | ~0.1ms | 1 |
| `LinkGraph.open()` | ~2ms (SQLite open) | 1 |
| `reverse_deps()` | ~0.5ms per query | 2-3 |
| `read_iwh()` | ~0.5ms | 1-2 |
| Token estimation | ~0.01ms per section | 7-8 |

**Total for file scope with 6 dependencies**: ~15-25ms. Well under 100ms.

The only potentially expensive operation is loading design file frontmatter
for each dependency (N file reads). With 10+ dependencies this could reach
~5-10ms. Still fine.

### What NOT to do

- Don't use `TiktokenCounter` for budget estimation — too slow for this path.
- Don't open and fully parse every dependency's design file — frontmatter
  only (description field is all we need).
- Don't walk the full link graph for concepts — resolve only wikilinks
  already listed in the target's design file.

---

## Open Questions

### Q1: Should `lexi context` accept multiple file paths?

Use case: agent is about to edit 3 files in the same package. Could call
`lexi context file1.py file2.py file3.py` instead of 3 separate calls.

- Pro: reduces to one subprocess call. Deduplicates shared conventions and
  dependencies.
- Con: adds complexity to scope resolution. Budget allocation across multiple
  targets is non-obvious (split evenly? proportional to file size?).
- Alternative: `lexi context src/lexibrary/archivist/` covers the directory
  case. Multi-file might be YAGNI.

**Recommendation**: defer to Phase 3 or later. File and directory scope cover
95% of use cases.

### Q2: Should guaranteed sections (priority 0-2) be truly un-truncatable?

If a file has a 2000-token interface contract and the budget is 3000, the
interface alone consumes 67% of the budget. Should the interface be truncated
to leave room for conventions and stack posts?

- Option A: guaranteed means guaranteed — never truncated.
- Option B: guaranteed means "always included, but can be truncated to a
  max of X% of budget" (e.g. interface contract capped at 40% of budget).
- Option C: guaranteed means "always included, truncated only if it alone
  exceeds the budget."

**Recommendation**: Option C. If the interface contract is huge, showing it
truncated plus conventions is more useful than showing it in full with nothing
else. But this should be rare — most interface contracts are 100-400 tokens.

### Q3: Should the default budget be higher than `lookup_total_tokens`?

`lookup_total_tokens` is currently 1200. This is tight for `context` which
includes more sections. Candidates:

- 4000 tokens (~16KB of text, ~4 pages)
- 6000 tokens (~24KB, ~6 pages)
- 8000 tokens (~32KB, ~8 pages)

**Recommendation**: 6000. Large enough to include all sections for a typical
file. Small enough that it doesn't dominate the agent's context window
(typical agent context is 128K-200K tokens).

### Q4: Should `lexi context` replace `lexi lookup` entirely?

`lookup` could become an alias for `context --budget 1200` (backward compat).
Or `lookup` stays as the "quick check" and `context` is the "full bundle."

- Pro of keeping both: `lookup` is fast and minimal for "should I edit this?"
  decisions. `context` is heavier for "I'm about to edit this."
- Con of keeping both: two commands for similar purposes is confusing.
  Agents already struggle with the multi-command ritual.

**Recommendation**: keep both, with different roles:
- `lookup` = quick role check (description + conventions + issue count).
  Stays as-is. Used for "what is this file?" questions.
- `context` = full working context. Used for "I'm about to edit this file."

Document the distinction clearly in CLAUDE.md and `--help`.

### Q5: How should `--format json` structure the output?

Option A — flat sections:
```json
{
  "target": "src/lexibrary/archivist/pipeline.py",
  "budget_used": 3800,
  "budget_total": 6000,
  "identity": { "description": "...", "source": "design_file" },
  "interface": { "contract": "...", "token_cost": 320 },
  "conventions": [ { "title": "...", "scope": "...", "rule": "..." } ],
  "stack": [ { "id": "SP-0012", "title": "...", "status": "open" } ],
  ...
  "omitted": ["dependents", "concepts"]
}
```

Option B — ordered array preserving priority:
```json
{
  "target": "src/lexibrary/archivist/pipeline.py",
  "budget": { "used": 3800, "total": 6000 },
  "sections": [
    { "name": "identity", "priority": 0, "content": "...", "tokens": 80 },
    { "name": "interface", "priority": 1, "content": "...", "tokens": 320 },
    ...
  ],
  "omitted": [
    { "name": "concepts", "drilldown": "lexi concepts ..." }
  ]
}
```

**Recommendation**: Option B. Preserves the priority ordering that is
central to the design. Consumers can filter or reorder as needed.

### Q6: Should `_estimate_tokens()` and `_truncate_lookup_sections()` be extracted now or during implementation?

These functions in `lexi_app.py` are currently private and tightly coupled
to the lookup command. `context` needs the same logic.

- Option A: extract to `utils/tokens.py` as a prerequisite PR.
- Option B: extract as part of the `context` implementation.

**Recommendation**: Option A — small, clean refactor. Separates concerns and
makes the `context` PR smaller and more reviewable. Also benefits any other
future consumer of token estimation.

### Q7: What happens when conventions and config change mid-session?

If an agent calls `lexi context`, then another agent modifies a convention
file, the first agent's context is stale. This is inherent to any read-at-
a-point-in-time system.

- This is not a problem to solve. The agent's context was correct when
  assembled. If conventions change, the next `lexi context` call gets fresh
  data. The staleness window is one agent task — typically minutes.
- Don't add caching, TTLs, or invalidation. Keep it stateless.

### Q8: Should `lexi context` include the orient topology summary?

`orient` shows the project topology (directory tree with descriptions).
Should `context` include a condensed version?

- Pro: eliminates the need for a separate `orient` call.
- Con: topology is project-wide, not target-specific. It's noise for a
  file-scoped context bundle. And it's expensive (~300 tokens for a
  medium project).

**Recommendation**: No. `orient` remains the session-start command.
`context` is the pre-edit command. Different purposes, different times.
