# Conventions as a First-Class Artifact

> **Status**: Design decisions settled (D1-D12). Split out from
> `plans/start-here-reamagined.md` ([Open Thread: Conventions](#open-thread-conventions-as-a-first-class-artifact),
> lines 236-273) to give the topic the depth it requires.
>
> Key decisions (D1-D12) are recorded in the [Decisions](#decisions) section.
> Pattern-based scopes, LLM extraction, and archivist backup pipeline are
> deferred to v2 — see `plans/convention-v2-plan.md`.
> Ready for implementation planning via OpenSpec.

---

## Current State

Conventions are referenced in 8+ locations across the codebase. Every one of
them is either empty, unused, or consuming data that does not exist. The
pipeline is fully plumbed but has zero data flowing through it.

### 1. Model field: `AIndexFile.local_conventions`

**File**: `src/lexibrary/artifacts/aindex.py:26`

```python
class AIndexFile(BaseModel):
    ...
    local_conventions: list[str] = []
```

The field exists on the Pydantic model. Its type is `list[str]` -- a flat list
of convention text strings, scoped to the directory represented by the
`.aindex` file. Default is `[]`.

### 2. Generator: hard-coded to empty

**File**: `src/lexibrary/indexer/generator.py:162-166`

```python
return AIndexFile(
    directory_path=rel_source,
    billboard=billboard,
    entries=entries,
    local_conventions=[],    # <-- always empty
    metadata=metadata,
)
```

`generate_aindex()` is the only function that creates `AIndexFile` instances
from directory contents. It unconditionally sets `local_conventions=[]`. There
is no code path that populates this field -- not from config, not from LLM
extraction, not from any other source.

### 3. Serializer: writes "(none)"

**File**: `src/lexibrary/artifacts/aindex_serializer.py:52-61`

```python
parts.append("## Local Conventions")
parts.append("")
if not data.local_conventions:
    parts.append("(none)")
else:
    for convention in data.local_conventions:
        parts.append(f"- {convention}")
```

The serializer correctly handles both cases. Every `.aindex` file on disk will
have a `## Local Conventions` section containing `(none)`.

### 4. Parser: reads conventions (but finds none)

**File**: `src/lexibrary/artifacts/aindex_parser.py:130-137`

```python
local_conventions: list[str] = []
for line in _section_lines("Local Conventions"):
    stripped = line.strip()
    if stripped == "(none)":
        break
    if stripped.startswith("- "):
        local_conventions.append(stripped[2:])
```

The parser correctly handles the `## Local Conventions` section. It would
parse conventions if any existed in the file. Since the generator always
produces `(none)`, the parser always returns `[]`.

### 5. Link graph schema: table exists, index exists

**File**: `src/lexibrary/linkgraph/schema.py:99-107, 164`

```sql
CREATE TABLE IF NOT EXISTS conventions (
    artifact_id    INTEGER NOT NULL REFERENCES artifacts(id) ON DELETE CASCADE,
    directory_path TEXT    NOT NULL,
    ordinal        INTEGER NOT NULL DEFAULT 0,
    body           TEXT    NOT NULL,
    UNIQUE(directory_path, ordinal)
);
```

```sql
CREATE INDEX IF NOT EXISTS idx_conventions_dir ON conventions(directory_path);
```

The table is created on every schema init. It supports directory-scoped
conventions with ordering (ordinal). The `artifact_id` foreign key links to
the `artifacts` table where `kind = 'convention'` is a valid value
(schema.py:51). The `convention_concept_ref` link type is also defined in the
`links` table CHECK constraint (schema.py:76).

### 6. Link graph builder: full processing logic exists

**File**: `src/lexibrary/linkgraph/builder.py:849-940` (full build),
`builder.py:1553-1664` (incremental update)

The builder has complete convention processing logic:

- `_scan_aindex_files()` (line 838): discovers all `.aindex` files
- `_process_aindex_conventions()` (line 849): for each `.aindex` file:
  1. Parses `local_conventions` from the file
  2. Creates a `kind='convention'` artifact with synthetic path
     `{directory_path}::convention::{ordinal}`
  3. Inserts a row in the `conventions` table
  4. Extracts `[[wikilinks]]` from convention text and creates
     `convention_concept_ref` links to concept artifacts
  5. Inserts an FTS row for full-text search
- `_handle_changed_aindex()` (line 1553): incremental update handler that
  deletes old convention artifacts and reinserts from the updated `.aindex`

All of this logic works correctly. It simply never finds any conventions to
process because `local_conventions` is always `[]`.

### 7. Link graph query: `get_conventions()` returns nothing

**File**: `src/lexibrary/linkgraph/query.py:435-484`

```python
def get_conventions(self, directory_paths: list[str]) -> list[ConventionResult]:
```

The query method accepts a list of directory paths (ordered root-to-leaf for
inheritance) and returns `ConventionResult` dataclasses with `body`,
`directory_path`, and `ordinal`. Results are sorted by path order then ordinal
-- giving convention inheritance (root conventions first, then more specific
overrides). The `ConventionResult` dataclass is defined at line 82.

This is a well-designed query that implements hierarchical convention
inheritance. It returns `[]` because the `conventions` table is empty.

### 8. CLI: `lexi lookup` renders "Applicable Conventions"

**File**: `src/lexibrary/cli/lexi_app.py:164-194`

```python
conventions_by_dir: list[tuple[str, list[str]]] = []
current_dir = target.parent
while True:
    ...
    if aindex is not None and aindex.local_conventions:
        ...
        conventions_by_dir.append((display_dir, list(aindex.local_conventions)))
    ...
if conventions_by_dir:
    console.print("\n## Applicable Conventions\n")
    ...
```

The lookup command walks parent directories from the target file up to the
scope root, collecting `local_conventions` from each `.aindex` file. It
renders them grouped by directory. Since `local_conventions` is always `[]`,
the `if conventions_by_dir:` guard is never true, and the "Applicable
Conventions" section is never rendered.

Note: the CLI reads conventions directly from `.aindex` files (via the
parser), NOT from the link graph. This means it bypasses the `get_conventions()`
query method entirely. There are two parallel convention retrieval paths that
produce the same empty result.

### 9. Validator: conventions explicitly skipped

**File**: `src/lexibrary/validator/checks.py:932-972, 1002-1048`

Both `check_dangling_links()` and `check_orphan_artifacts()` explicitly skip
convention artifacts:

```python
# check_dangling_links, line 969-971:
"WHERE kind IN ('source', 'design', 'concept', 'stack')"
# check_orphan_artifacts, line 1047-1048:
"WHERE kind != 'convention'"
```

Convention artifacts use synthetic paths (`{dir}::convention::{ordinal}`) that
have no backing file, so file-existence checks are correctly skipped. However,
there are **no convention-specific validation checks** -- no freshness check,
no orphan detection, no conflict detection between scopes.

### 10. BAML prompts: convention extraction is hallucination-only

**File**: `baml_src/archivist_start_here.baml:42-43`

```
4. **convention_index**: A compact bulleted list of naming conventions,
   patterns, or rules observed in the project. 3-8 items.
```

**File**: `baml_src/types.baml:39`

```
convention_index string
```

The START_HERE generation prompt asks the LLM to produce a `convention_index`
from directory tree structure and billboard summaries. The LLM cannot read
source code at this stage -- it infers conventions from file names and
structural descriptions. This is the **only place conventions are generated**,
and they exist only in the START_HERE.md output, not flowing back into any
structured storage.

### 11. Config: no convention-related fields

**File**: `src/lexibrary/config/schema.py` (entire file)

`LexibraryConfig` has no fields for declaring conventions. There is no
`conventions` key in the config schema, no `ConventionConfig` model, and no
mechanism for users to declare project-wide or directory-scoped conventions in
`.lexibrary/config.yaml`.

### 12. Agent rules: reference conventions but cannot deliver them

**File**: `src/lexibrary/init/rules/base.py:114, 124, 137, 202, 207, 213, 218`

The agent rules text mentions conventions in multiple places:
- "Read START_HERE.md to understand project structure and conventions"
- "Run `lexi lookup <file>` ... to understand its role, dependencies, and conventions"
- "Check for existing project conventions and concepts"

These instructions direct agents to seek conventions that do not exist in the
structured system. The only conventions they can find are the hallucinated ones
in START_HERE.md.

### The Broken Pipeline (End-to-End)

```
Source code
    |
    v
generate_aindex()  -->  local_conventions=[]  (hard-coded)
    |
    v
serialize_aindex()  -->  "## Local Conventions\n(none)"
    |
    v
parse_aindex()  -->  local_conventions=[]
    |                       |
    |                       v
    |              lexi lookup  -->  (no conventions to display)
    v
_process_aindex_conventions()  -->  (no conventions to insert)
    |
    v
conventions table  -->  (empty)
    |
    v
get_conventions()  -->  []

Meanwhile, separately:

archivist_start_here.baml  -->  LLM hallucinates convention_index string
    |
    v
_assemble_start_here()  -->  "## Convention Index\n{hallucinated text}"
    |
    v
START_HERE.md  -->  (the ONLY place conventions exist, and they're unreliable)
```

---

## Requirements

### What conventions need to do

1. **Scope hierarchy**: Conventions must support at minimum two scopes:
   project-wide (apply everywhere) and directory-scoped (apply within a
   subtree). File-pattern scoping (e.g., "all `*_test.py` files") is
   desirable but not essential for v1.

2. **Inheritance**: A file at `src/auth/middleware.py` should inherit
   conventions from `src/auth/`, `src/`, and the project root, in that
   order. More specific conventions can refine or override broader ones.
   This is already modeled in `get_conventions()` (query.py:435) and the
   CLI's parent-directory walk (lexi_app.py:169-186).

3. **Queryability**: Conventions must be retrievable by directory path (for
   `lexi lookup`), by keyword (for search), and in aggregate (for project
   overview). The link graph already supports the first via the
   `conventions` table and the third via FTS.

4. **Editability**: Users must be able to create, modify, and delete
   conventions. LLM-discovered conventions should be reviewable and
   editable. This implies a storage format that humans can read and write.

5. **Provenance tracking**: It should be clear whether a convention was
   user-declared (authoritative) or LLM-extracted (advisory). This affects
   trust and editing workflows.

6. **Lifecycle**: Conventions should support at least active/deprecated
   states, similar to concepts. A deprecated convention should warn when
   still referenced but not block.

### What agents need from conventions

1. **At edit time**: When an agent is about to edit a file, it needs to know
   the applicable conventions for that file's location. This is the
   `lexi lookup` use case -- the most critical delivery point.

2. **Project-wide awareness**: During session start, agents need to know the
   project's global conventions (coding style, import patterns, naming
   rules). Currently this comes from START_HERE's hallucinated convention
   index.

3. **Low friction**: Convention retrieval must be fast and automatic. The
   pre-edit hook (`lexi-pre-edit.sh`) auto-runs `lexi lookup`, so
   conventions surfaced there require zero agent effort. For environments
   without hooks, agents must be directed to run `lexi lookup` or a
   conventions command.

4. **Actionable format**: Conventions should be concrete and prescriptive
   ("use `from __future__ import annotations` in every module") rather than
   vague ("follow Python best practices").

---

## Design Options

### Option 1: File-Based (like Concepts)

Convention files stored in `.lexibrary/conventions/` as markdown with YAML
frontmatter, analogous to concept files in `.lexibrary/concepts/`.

**Storage format example:**
```yaml
---
title: Future annotations import
scope: project
tags: [python, imports]
status: active
source: user
---

Every Python module must include `from __future__ import annotations` as the
first import. This enables PEP 604 union syntax (`X | Y`) and forward
references without string quoting.
```

**Directory-scoped convention:**
```yaml
---
title: Pathspec pattern name
scope: src/lexibrary/ignore
tags: [pathspec, configuration]
status: active
source: llm-extracted
---

When using pathspec, always pass `"gitignore"` as the pattern name, never
`"gitwildmatch"`. The latter is technically correct but causes compatibility
issues.
```

| Criterion | Assessment |
|-----------|------------|
| **Editability** | Excellent. Human-readable markdown files, editable with any text editor. Same workflow as concept files. |
| **Queryability** | Good. Can build a `ConventionIndex` class (parallel to `ConceptIndex`). Link graph indexing via builder already exists. |
| **Versioning** | Excellent. Files are tracked in git. Diffs are readable. History is preserved. |
| **Scalability** | Good for tens of conventions. A project with 100+ directory-scoped conventions would create many files. Scope field must be queryable efficiently. |
| **Implementation effort** | Medium-high. Requires: new Pydantic model (`ConventionFile`), parser, serializer, index class, builder integration, CLI commands, and changes to `lexi lookup` to read from this new source. Much infrastructure can be copied from the concepts system. |
| **Scope resolution** | Requires mapping the `scope` field to directories. A convention with `scope: src/auth` applies to `src/auth/**`. Root/project scope uses `scope: project` or `scope: .`. Pattern scopes need regex/glob matching. |

### Option 2: Database-Only (link graph conventions table)

Conventions live exclusively in the `conventions` table in the link graph
SQLite database, populated by the archivist during design file generation or
by a CLI command that writes directly to the database.

| Criterion | Assessment |
|-----------|------------|
| **Editability** | Poor. Users cannot directly edit SQLite rows. A CLI wrapper (`lexi convention edit`) would be needed, adding friction. No way to edit conventions in a text editor. |
| **Queryability** | Excellent. SQL queries are fast, flexible, and already implemented (`get_conventions()`). FTS search already wired up. |
| **Versioning** | Poor. SQLite binary database is not diffable in git. Convention changes are invisible in code review. The database is regenerated on `lexictl update`, so user edits would be overwritten unless protected. |
| **Scalability** | Excellent. SQLite handles thousands of rows trivially. Directory-path indexing is already in place. |
| **Implementation effort** | Low. The schema, builder logic, and query interface already exist. Only the population pipeline needs work. |
| **Scope resolution** | Built-in. The `directory_path` column is already the scope key. `get_conventions()` already does hierarchical inheritance by accepting an ordered list of paths. |

### Option 3: Hybrid (conventions in `.aindex` + link graph)

Conventions are declared as part of `.aindex` files (the `local_conventions`
field that already exists) and indexed into the link graph by the builder
(which already has this logic). The `.aindex` files are the source of truth;
the link graph is a derived index.

This is what the current architecture **already assumes** -- it just lacks a
population mechanism.

| Criterion | Assessment |
|-----------|------------|
| **Editability** | Moderate. `.aindex` files are markdown, but they are auto-generated by the indexer. Manual edits to `local_conventions` would be overwritten on the next `lexictl update` unless the generator is made convention-aware (reads existing conventions before regenerating). |
| **Queryability** | Good. The link graph indexes conventions from `.aindex` files. `get_conventions()` already works. Direct `.aindex` reading also works (the CLI already does this). |
| **Versioning** | Good. `.aindex` files are text and can be diffed. However, they are in `.lexibrary/` which is typically gitignored. Conventions embedded in `.aindex` would share this fate. |
| **Scalability** | Good. Conventions are distributed across `.aindex` files, one per directory, so no single file grows large. |
| **Implementation effort** | Low-medium. The hardest part is populating `local_conventions` in `generate_aindex()`. If LLM-extracted, needs a new BAML prompt and archivist step. If config-declared, needs config schema changes and a merge strategy. The downstream pipeline (serializer, parser, builder, query, CLI) already works. |
| **Scope resolution** | Natural. Each `.aindex` file is inherently directory-scoped. Project-wide conventions go in the root `.aindex`. The CLI already walks parent directories for inheritance. |

**Key problem**: `.aindex` files are regenerated from scratch by `generate_aindex()`.
Any convention data must either be re-derived on each generation (LLM cost)
or preserved across regenerations (requires the generator to read existing
conventions before overwriting). The current `list[str]` type is also
limited -- no provenance, no status, no lifecycle metadata.

---

## Population Pipeline

Conventions need to enter the system somehow. Three sources are envisioned,
and they are not mutually exclusive:

### Source 1: User-declared in config

Users add conventions to `.lexibrary/config.yaml`:

```yaml
conventions:
  - body: "Use `from __future__ import annotations` in every module"
    scope: project
    tags: [python, imports]
  - body: "pathspec pattern name must be 'gitignore', not 'gitwildmatch'"
    scope: src/lexibrary/ignore
    tags: [pathspec]
```

This requires a `ConventionConfig` model in `config/schema.py` and a
pipeline to inject these into either `.aindex` files or convention files or
the link graph at build time.

**Advantages**: Deterministic, user-controlled, no LLM cost, survives
regeneration. Good for project-wide rules that are well-known.

**Disadvantages**: Manual effort. Users must know and articulate their
conventions. Does not discover implicit conventions.

### Source 2: LLM-extracted during archivist pipeline

During design file generation, the archivist LLM already reads source code.
A secondary extraction step could identify conventions:

1. After generating a design file for `src/auth/middleware.py`, the LLM
   (or a separate prompt) identifies patterns: "all handlers use
   `@require_auth` decorator", "errors are raised as `AuthError`", etc.
2. These extracted conventions are scoped to the directory and stored.
3. Extraction happens per-directory: once all files in `src/auth/` have
   design files, the conventions for that directory are synthesized.

This could be a new BAML prompt (`archivist_extract_conventions.baml`) or
an addition to the existing design file prompt.

**Advantages**: Discovers implicit conventions automatically. Scales with
codebase size. Based on actual source code, not structural guesses.

**Disadvantages**: LLM cost per directory. Risk of hallucinated conventions.
Requires review/approval workflow. Must handle conflicts when regenerating
(new extraction may differ from previous).

### Source 3: Agent creation via CLI (PRIMARY for v1)

The `lexi convention new` command is the **primary population mechanism**
in v1. Coding agents create conventions when they discover repeating
patterns during their work:

```bash
lexi convention new --scope src/auth --body "All endpoints require auth"
lexi convention new --scope project --body "Use rich.console, no bare print()"
```

Agent-created conventions are written with `status: draft` and
`source: agent`. They appear in `lexi lookup` with a `[draft]` marker and
require human approval via `lexi convention approve <name>`.

**Advantages**: Conventions emerge from actual coding work. Agents see real
patterns while editing files and can formalize them immediately. Scales
with the number of agents working on the codebase.

**Disadvantages**: Requires agent harnessing changes (rules/skills that
instruct agents to create conventions). Quality depends on the agent's
judgment — the draft/approve workflow is the safety net.

**Harnessing requirements**: Agent rules (`src/lexibrary/init/rules/base.py`)
must include instructions like: "When you notice a repeating pattern that
should be followed consistently, create a convention with `lexi convention
new --scope <dir> --body <rule>`." The `_CONVENTION_SKILL` template must
describe when and how to create conventions.

### Recommended combination (v1)

- **CLI creation** (`lexi convention new`) as the **primary** population
  mechanism. Coding agents create conventions via this command when they
  discover patterns during their work. This requires agent harnessing changes
  (rules/skills that instruct agents to create conventions when they notice
  repeating patterns). See `plans/agent-start-plan.md` for harnessing context.
- **Config-declared** for project-wide baseline conventions. Users seed known
  rules (coding style, import patterns) in `config.yaml` before agents start
  working. These are authoritative and always `status: active`.

### Deferred to v2 (`plans/convention-v2-plan.md`)

- **LLM-extracted** during archivist pipeline as a **backup** discovery
  mechanism. The archivist reads source code for design files — a secondary
  extraction step could identify conventions. This is the fallback for
  conventions that coding agents miss, not the primary path.
- **Pattern-based scopes** (glob/fnmatch) for cross-cutting conventions.

---

## Delivery Mechanisms

### 1. `lexi lookup` "Applicable Conventions" (exists, needs data)

**File**: `src/lexibrary/cli/lexi_app.py:164-194`

Already implemented. Walks parent `.aindex` files, collects
`local_conventions`, renders grouped by directory. This is the **primary**
convention delivery mechanism because it runs automatically via the pre-edit
hook and gives file-specific, scope-aware results.

If the storage model changes from `.aindex` to standalone files, this code
needs updating to query the new source. If the hybrid model is kept, no
changes are needed beyond populating the data.

### 2. `lexi conventions` CLI command (new)

Does not exist today. Should provide:
- `lexi conventions` -- list all conventions (project-wide first, then by scope)
- `lexi conventions <path>` -- show conventions applicable to a file/directory
- `lexi conventions --scope <dir>` -- filter by scope
- `lexi conventions --tag <tag>` -- filter by tag

This parallels `lexi concepts` and would use either the convention index
(file-based) or the link graph (database/hybrid).

### 3. Pre-edit hook injection

**File**: `src/lexibrary/init/rules/claude.py` (hook setup)

The pre-edit hook currently runs `lexi lookup <file>`, which would include
conventions once the data exists. No hook changes needed -- just data.

For richer injection, the hook could emit conventions in the
`hookSpecificOutput` format so they appear as structured context rather than
raw CLI output.

### 4. START_HERE procedural assembly

**File**: `src/lexibrary/archivist/start_here.py:91-112`

If conventions become a first-class artifact, START_HERE no longer needs to
hallucinate them. Two options:

- **Pointer only**: "Run `lexi lookup <file>` to see applicable conventions."
  (Recommended -- keeps START_HERE lean.)
- **Root conventions summary**: Procedurally assemble the project-wide
  conventions (from root `.aindex` or config) into START_HERE. Would require
  reading them during `generate_start_here()` and passing them to
  `_assemble_start_here()`.

---

## Areas Touched

### Artifact models (`src/lexibrary/artifacts/`)

| File | Change |
|------|--------|
| `aindex.py:26` | **Remove** `local_conventions: list[str]` field entirely (D9). Pre-launch, no migration needed (D8). |
| `aindex_parser.py:130-137` | **Remove** the `## Local Conventions` parsing block. |
| `aindex_serializer.py:52-61` | **Remove** the `## Local Conventions` section from output. |
| (new) `convention.py` | New `ConventionFile` Pydantic model with frontmatter (title, scope, tags, status, source, priority) and body. |

### Indexer (`src/lexibrary/indexer/`)

| File | Change |
|------|--------|
| `generator.py:166` | **Remove** `local_conventions=[]` argument from `AIndexFile()` constructor call. |

### Link graph (`src/lexibrary/linkgraph/`)

| File | Change |
|------|--------|
| `schema.py:99-107` | Extend conventions table schema: add `source` (user/agent/config), `status` (draft/active/deprecated), `priority` (integer) columns. |
| `builder.py:849-940` | Replace `.aindex` convention processing with convention-file processing. Read from `.lexibrary/conventions/*.md` instead of `.aindex` `local_conventions`. |
| `query.py:82-92, 435-484` | Extend `ConventionResult` with metadata (source, status, priority). Add `get_all_conventions()`, `search_conventions()` query methods. |

### Config (`src/lexibrary/config/`)

| File | Change |
|------|--------|
| `schema.py` | Add `ConventionConfig` model with `lookup_display_limit: int = 5` (D5). Add `ArtifactReviewConfig` model with per-artifact-type auto/manual sign-off (D4). Add both as fields on `LexibraryConfig`. Add `convention_file_tokens` to `TokenBudgetConfig`. |
| `loader.py` | No structural change (Pydantic handles new fields via `extra="ignore"`). |

### CLI (`src/lexibrary/cli/`)

| File | Change |
|------|--------|
| `lexi_app.py:164-194` | Replace `.aindex` parent-directory walk with `ConventionIndex.find_by_scope()` call (D10). |
| `lexi_app.py` (new command) | Add `lexi conventions` command group with list/show/search subcommands. |
| `lexi_app.py` (new command) | Add `lexi convention new --scope <s> --body <b>` and `lexi convention approve <name>` commands. |

### Scaffolder (`src/lexibrary/init/`)

| File | Change |
|------|--------|
| `scaffolder.py` | Add `.lexibrary/conventions/` with `.gitkeep` to `create_lexibrary_skeleton()` and `create_lexibrary_from_wizard()`. |

### Archivist (`src/lexibrary/archivist/`)

| File | Change |
|------|--------|
| `start_here.py:91-112` | Remove `convention_index` parameter from `_assemble_start_here()`. Replace with pointer to `lexi lookup` / `lexi conventions`. |

### BAML prompts (`baml_src/`)

| File | Change |
|------|--------|
| `archivist_start_here.baml:42-43` | Remove `convention_index` from the prompt. |
| `types.baml:39` | Remove `convention_index` from `StartHereOutput`. |
| (new) `archivist_conventions.baml` | If LLM-extracted: new prompt for convention extraction. |

### Convention index (`src/lexibrary/conventions/` — new package)

| File | Change |
|------|--------|
| (new) `src/lexibrary/conventions/__init__.py` | Package init. |
| (new) `src/lexibrary/conventions/index.py` | `ConventionIndex` class (parallel to `ConceptIndex`). Load from directory, find by scope, search, filter by tag. |
| (new) `src/lexibrary/conventions/parser.py` | Parse convention markdown files (YAML frontmatter + body). |
| (new) `src/lexibrary/conventions/serializer.py` | Serialize convention files. |

### Validator (`src/lexibrary/validator/`)

| File | Change |
|------|--------|
| `checks.py` | Add convention-specific checks: convention freshness, orphan conventions (scoped to directories that no longer exist), conflicting conventions across scopes. |

### Agent rules (`src/lexibrary/init/rules/`)

| File | Change |
|------|--------|
| `base.py` | Update skill descriptions to reference `lexi conventions` command. Minimal changes to core rules text. |

---

## Comparison with Concepts

| Dimension | Concepts | Conventions |
|-----------|----------|-------------|
| **Nature** | Descriptive (definitions, explanations) | Prescriptive (rules, patterns, requirements) |
| **Storage** | `.lexibrary/concepts/*.md` | `.lexibrary/conventions/*.md` (D1) |
| **Frontmatter** | title, aliases, tags, status, superseded_by | title, scope, tags, status, source, priority |
| **Body** | Freeform markdown with sections (summary, related concepts, linked files, decision log) | Typically shorter -- a rule statement with optional rationale |
| **Scope** | Global (concepts are project-wide knowledge) | Hierarchical (project-wide, directory-scoped, possibly file-pattern) |
| **Lifecycle** | draft -> active -> deprecated (with superseded_by) | draft -> active -> deprecated (agent-created start as draft, config-declared start as active) |
| **Aliases** | Yes (multiple names resolve to same concept) | Probably not needed (conventions are identified by scope + content) |
| **Cross-references** | Wikilinks in body, linked_files, related_concepts | Could reference concepts via wikilinks (already supported: `convention_concept_ref` link type) |
| **Index class** | `ConceptIndex` (wiki/index.py) -- in-memory, load from directory | Would need `ConventionIndex` if file-based |
| **CLI** | `lexi concepts [topic]` with --tag, --status, --all | `lexi conventions [path]` with --scope, --tag |
| **Link graph artifact kind** | `'concept'` | `'convention'` (already defined) |
| **Link graph link types** | `concept_file_ref`, `wikilink` | `convention_concept_ref` (already defined) |
| **Builder processing** | Concept files parsed, artifacts created, aliases indexed, FTS populated | Convention processing logic exists (builder.py:849-940) but receives no data |
| **Validator checks** | concept_frontmatter, orphan_concepts, deprecated_concept_usage | None exist yet |

### What can be reused from the concepts system

If file-based storage is chosen:

1. **Model pattern**: `ConceptFile` / `ConceptFileFrontmatter` pattern maps
   directly to `ConventionFile` / `ConventionFileFrontmatter`. Pydantic
   models with YAML frontmatter + markdown body.

2. **Parser pattern**: `parse_concept_file()` (wiki/parser.py) uses the same
   `_FRONTMATTER_RE` regex and YAML safe_load approach. Convention parser
   would be structurally identical.

3. **Serializer pattern**: `serialize_concept_file()` (wiki/serializer.py)
   is 36 lines. Convention serializer would be similar.

4. **Index pattern**: `ConceptIndex` (wiki/index.py) provides load-from-
   directory, find-by-name, search, and by-tag. A `ConventionIndex` would
   add find-by-scope (the main difference).

5. **CLI pattern**: `lexi concepts` command structure (lexi_app.py:241-299)
   can be mirrored for `lexi conventions`.

6. **Builder processing**: The concept processing in the builder (artifact
   creation, alias insertion, wikilink extraction, FTS population) is
   closely parallel to the convention processing that already exists.

### What is different

1. **Scope resolution**: Concepts are global; conventions are hierarchically
   scoped. This is the fundamental difference and drives most of the unique
   logic (inheritance, directory-walk, conflict resolution).

2. **Volume**: A typical project might have 10-30 concepts but 50-200
   directory-scoped conventions. Storage and query must handle this.

3. **Source attribution**: Concepts are almost always human-authored.
   Conventions may be LLM-extracted, requiring provenance tracking and a
   review/approval workflow that concepts do not need.

4. **Relationship to `.aindex`**: Concepts are standalone files with no
   connection to `.aindex`. Conventions in the current architecture are
   embedded in `.aindex` via `local_conventions`. Any design must decide
   whether to keep or sever this relationship.

---

## Decisions

### D1: File-based storage (like Concepts)

**Decision**: File-based. Each convention is its own file in
`.lexibrary/conventions/`, mirroring the concepts structure in
`.lexibrary/concepts/`. Conventions are fully separated from `.aindex` files.

**Rationale**: Best editability (human-readable markdown files, any text
editor), best versioning (git-diffable), consistent with the concepts
pattern. The existing `local_conventions` field on `.aindex` and the
downstream pipeline in the builder become consumers of convention files
rather than the source of truth.

**Implication**: The `local_conventions` field on `AIndexFile` should be
deprecated or repurposed as a derived cache. The builder's convention
processing logic (builder.py:849-940) should read from convention files
instead of `.aindex` files. The CLI's parent-directory walk
(lexi_app.py:164-194) should query the `ConventionIndex` or link graph
rather than walking `.aindex` files directly.

### D2: Regeneration is not an issue (resolved by D1)

**Decision**: Moot. Separating conventions from `.aindex` eliminates the
regeneration/overwrite problem entirely. Convention files are never
auto-generated or overwritten by the indexer.

**Implication**: No read-modify-write pattern needed in `generate_aindex()`.
The generator can drop `local_conventions` or set it to `[]` permanently.
Convention files have their own lifecycle, independent of `.aindex`
regeneration.

### D3: Conventions are committed to git

**Decision**: All Lexibrary artifacts — `.aindex` files, design files,
concepts, conventions, and Stack posts — should be committed to version
control.

**Rationale**: Conventions are authoritative project knowledge. They must
survive across machines, be reviewable in PRs, and have visible history.
This applies to both user-declared and LLM-extracted conventions (after
sign-off).

**Implication**: `.lexibrary/conventions/` must not be gitignored. This may
require adjusting the default `.gitignore` patterns that Lexibrary generates
during `lexictl init`. The broader policy (commit all artifacts) may need
its own backlog item if `.lexibrary/` is currently gitignored by default.

### D4: Convention extraction prompt — open, with sign-off config

**Decision**: The extraction prompt design remains an open question. However,
a key requirement is established: **concepts and conventions must have a
config option for auto vs manual sign-off**.

- **Auto sign-off**: LLM-as-judge evaluates and approves extracted
  conventions without user intervention. Suitable for high-trust environments
  or when conventions are advisory.
- **Manual sign-off**: User must review and approve each LLM-extracted
  convention before it becomes active. Conventions are created in `draft`
  status and require explicit promotion to `active`.

This sign-off mechanism should be **extensible to other artifact types**
(concepts, Stack posts, design files) in future. The config shape might be:

```yaml
# .lexibrary/config.yaml
artifact_review:
  conventions: auto    # or "manual"
  concepts: manual     # default for concepts
```

**Open sub-questions** (deferred to implementation):
- What does the extraction BAML prompt look like?
- What inputs does it receive (source code, design files, parent conventions)?
- How do we filter out obvious/unhelpful conventions?
- What does "LLM-as-judge" evaluation look like for auto sign-off?

### D5: Structured markdown, default limit of 5

**Decision**: Conventions should be rendered in structured markdown that is
easy for both agents and users to parse. `lexi lookup` should display a
**default maximum of 5 conventions** per file. This limit is an advanced
config item with a warning if exceeded.

```yaml
# .lexibrary/config.yaml (advanced)
conventions:
  lookup_display_limit: 5    # default; warn if >5 applicable
```

**Rationale**: Conventions add to context window cost on every edit (via
the pre-edit hook). 5 conventions is a reasonable budget — enough to cover
the most important rules without overwhelming the agent. A warning when
exceeded nudges users to consolidate or prioritize their conventions.

**Implication**: The `lexi lookup` renderer and the hook output must
respect this limit. When more conventions apply, the output should
indicate truncation (e.g., "... and 3 more — run `lexi conventions
<path>` to see all").

### D6: Override by specificity + warning

**Decision**: More specific conventions override broader ones. When a
child-scope convention contradicts a parent-scope convention, the child
wins. The system should **detect and flag conflicts as warnings** during
validation.

**Rationale**: Override-by-specificity is the intuitive behavior (a
directory-specific rule beats the project default). Flagging conflicts
ensures users are aware of overrides rather than silently losing parent
conventions.

**Implication**: The validator needs a new `check_convention_conflicts()`
check that compares conventions across scopes. Conflict detection may use
heuristics (same tags, overlapping keywords) or require explicit
`overrides` metadata in the convention frontmatter. The `get_conventions()`
query already returns root-to-leaf order — the renderer can annotate
overridden conventions.

### D7: Pattern-based scopes deferred to v2

**Decision**: v1 supports `project` and directory-path scopes only. The
`scope` field is a string, forward-compatible with glob patterns in v2.
Pattern-based scopes (e.g., `*_test.py`, `src/**/*.ts`) are deferred to
`plans/convention-v2-plan.md`.

**Rationale**: Pattern scopes introduce the hardest algorithmic problem
in the plan — specificity ranking between directories and globs — and we
have zero usage data to design against. Directory + project scopes cover
the most common cases. The data model is forward-compatible: adding
pattern matching later is a non-breaking extension to the resolution
algorithm.

**Implication**: The `scope` field accepts strings. v1 resolution treats
any scope that is not `"project"` as a directory path prefix. No
`pathspec` or `fnmatch` matching in v1. The data model is ready for v2
pattern support without schema changes.

### D8: No migration needed (pre-launch)

**Decision**: These changes will be made before Lexibrary goes live. No
migration path is needed for existing projects.

**Implication**: No `lexictl migrate-conventions` command. No backwards
compatibility concerns with existing `.aindex` convention sections. The
implementation can cleanly replace the current broken pipeline without
worrying about existing data.

### D9: Remove `local_conventions` from `.aindex` (clean cut)

**Decision**: Remove `local_conventions` entirely from the `.aindex`
pipeline. No deprecation period, no backward-compat shim.

- **Remove** the `local_conventions: list[str]` field from `AIndexFile`
- **Remove** the `## Local Conventions` section from the serializer
- **Remove** the convention parsing block from the parser
- **Remove** the `local_conventions=[]` argument from `generate_aindex()`
- **Remove** the parent-directory `.aindex` walk from `lexi_app.py:164-194`

**Rationale**: D8 establishes that no migration is needed. The field was
never populated. The `## Local Conventions\n(none)` section is dead weight
in every `.aindex` file. Clean cut now avoids carrying unused code.

### D10: `ConventionIndex` is the single retrieval path

**Decision**: `ConventionIndex` (loaded from `.lexibrary/conventions/`
files) is the **primary** retrieval path for both CLI and lookup. The link
graph `conventions` table is a **derived index** for FTS search and graph
queries only.

- `lexi lookup` calls `ConventionIndex.find_by_scope(file_path)`
- `lexi conventions` reads from `ConventionIndex` directly
- `lexi search` hits FTS in the link graph (existing search infrastructure)
- `get_conventions()` remains for graph queries ("which conventions
  reference this concept?") but is not used by the CLI hot path

**Rationale**: Mirrors how concepts work — concept files are the source of
truth, the link graph indexes them for search. Single source of truth
eliminates the dual-path confusion identified in the current state analysis
(§8). File-based retrieval is fast (no DB dependency) and works even when
the link graph is stale.

### D11: Slug-based file naming

**Decision**: Convention files use slug-based naming derived from the
title. Example: title "Future annotations import" → file
`future-annotations-import.md`.

**Naming function** `convention_file_path(title, conventions_dir)`:
1. Lowercase the title
2. Replace spaces and special characters with hyphens
3. Collapse consecutive hyphens
4. Truncate to 60 characters (at a word boundary)
5. Append numeric suffix on collision (`-2`, `-3`, etc.)

**Rationale**: Convention titles are sentences/phrases, not noun phrases.
PascalCase produces unwieldy names (`UseFutureAnnotationsImport.md`).
Slugs are standard across the ecosystem, more readable in directory
listings and git diffs, and less likely to collide.

### D12: Convention body format

**Decision**: Convention bodies follow a two-part structure:

1. **First paragraph is the rule.** One to three sentences. Concrete,
   prescriptive, actionable. This is what `lexi lookup` displays. Uses
   "must" / "must not" for mandatory rules, "should" / "should not" for
   advisory guidance.
2. **Everything after is rationale/context.** Optional. Separated from
   the rule by a blank line. May include `**Rationale**:` header,
   code examples, links to concepts via `[[wikilinks]]`. Not shown in
   truncated views (`lexi lookup`), available via `lexi conventions <name>`.

**Example:**
```markdown
---
title: Future annotations import
scope: project
tags: [python, imports]
status: active
source: user
priority: 0
---

Every Python module must include `from __future__ import annotations` as
the first import.

**Rationale**: Enables PEP 604 union syntax (`X | Y`) and forward
references without string quoting. See [[PEP604-Union-Syntax]].
```

**Implication**: The `ConventionFile` parser extracts a `rule` field (first
paragraph) for display in `lexi lookup`. The full `body` is available via
`lexi conventions <name>`. The `lexi convention new --body` flag populates
the rule paragraph; rationale can be added by editing the file.

## Scope Resolution Algorithm

The scope resolution algorithm is the core of convention retrieval. It
must be deterministic, fast, and unambiguous.

### v1 algorithm (directory + project scopes only)

```
find_applicable_conventions(file_path, convention_index, limit=5):

  1. Build ancestry chain from file_path to scope root:
     e.g., [src/auth/handlers/, src/auth/, src/, .]

  2. Collect matching conventions:
     - scope == "project" → matches all files
     - scope is a directory path → matches if file_path starts with scope
       (normalized with trailing /)

  3. Group by scope. Order scopes root-to-leaf:
     [project, ., src/, src/auth/, src/auth/handlers/]

  4. Within same scope, order by:
     a. priority descending (highest priority first)
     b. title alphabetically (stable tiebreaker)

  5. Apply display limit (default 5 from D5 config):
     - When truncating: KEEP the most specific conventions (leaf-ward),
       DROP the most general (root-ward).
     - Rationale: an agent editing src/auth/login.py cares more about
       src/auth/ conventions than project-wide ones it already absorbed
       from START_HERE.
     - Emit truncation notice: "... and N more — run `lexi conventions
       <path>` to see all"

  6. Return ordered list of ConventionResult.
```

### Priority field

The `priority` field in frontmatter (default `0`) controls display
ordering within the same scope:

- User-declared conventions: default `priority: 0`
- Agent-created conventions: default `priority: -1` (lower than user)
- Users can set any integer value to force important conventions to the top

When the display limit truncates, higher-priority conventions survive. User
rules naturally outrank agent-discovered patterns.

### Truncation rationale

Project-wide conventions are background knowledge — agents absorb them via
START_HERE or `lexi conventions`. Directory-scoped conventions are
**actionable edit guidance** for the specific file. The truncation strategy
favors specificity over generality.

## Sign-off Workflow

Conventions created by coding agents use the following workflow:

1. **Agent creates convention** via `lexi convention new --scope <s> --body <b>`
2. Convention file is written with `status: draft`, `source: agent`
3. `lexi lookup` shows draft conventions with a `[draft]` marker — agents
   should still follow them (probable conventions are better than none)
4. **Human reviews** via `lexi conventions --status draft` (list all drafts)
5. **Human approves** via `lexi convention approve <name>` → promotes
   `status: draft` to `status: active`
6. Config-declared conventions bypass this: they are always `status: active`

The `artifact_review.conventions` config controls whether the archivist
(v2) auto-promotes or leaves as draft. For v1 (agent + CLI creation), all
agent-created conventions start as `draft` and require human approval.

## Remaining Open Questions

### OQ1: Convention extraction prompt design (moved to v2)

Deferred to `plans/convention-v2-plan.md`. The BAML prompt for LLM
convention extraction needs design work. Key inputs, output schema,
quality filtering, and the LLM-as-judge auto-sign-off criteria all need
specification. This is a v2 concern — v1 relies on coding agents creating
conventions via `lexi convention new` and user-declared config conventions.

### OQ2: `artifact_review` config extensibility (partially resolved)

v1 implements the basic sign-off workflow: agent-created conventions start
as `draft`, humans approve via `lexi convention approve <name>`. The
broader `artifact_review` config pattern (auto/manual per artifact type,
LLM-as-judge for auto) is deferred to v2 alongside archivist extraction.

---

## Relationship to Other Plans

### `plans/start-here-reamagined.md`

This document is a direct continuation of the "Open Thread: Conventions as a
First-Class Artifact" section (lines 236-273) in `start-here-reamagined.md`.
The decision made there is that conventions should be **removed from
START_HERE** and made into their own artifact type. This document analyzes
what that means in practice.

Once conventions have a real source of truth, the START_HERE changes described
in `start-here-reamagined.md` (removing the Convention Index section,
replacing with a pointer) can proceed.

### `plans/lookup-upgrade.md`

The lookup upgrade plan (extracting `lexi lookup` core logic into
`src/lexibrary/lookup.py`) affects convention delivery. The convention
retrieval logic currently in `lexi_app.py:164-194` should move into the
extracted `LookupResult` dataclass. This means lookup-upgrade should be
sequenced **before or alongside** conventions implementation, so the
convention data flows through the clean lookup architecture.

### `plans/search-upgrade.md`

The search upgrade plan adds post-search context injection via hooks.
Conventions could be part of the injected context -- when a search result
lands in a directory with conventions, those conventions could be included
in the hook output.

### Cross-cutting concern: convention delivery unblocks multiple systems

Conventions are not just a START_HERE problem. Fixing the convention pipeline
unblocks:

1. **`lexi lookup`** -- the "Applicable Conventions" section finally renders content
2. **START_HERE** -- can switch from hallucinated to procedural convention display
3. **Pre-edit hooks** -- convention injection into agent context becomes real
4. **Validation** -- convention-specific health checks become possible
5. **Link graph** -- the `conventions` table and `convention_concept_ref` links
   carry actual data, enabling graph queries like "which conventions reference
   this concept?"
6. **FTS** -- convention text becomes searchable via `lexi search`
