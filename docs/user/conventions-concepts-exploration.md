# Comprehensive Exploration: Conventions and Concepts in Lexibrary

## Executive Summary

Conventions and Concepts are two distinct, parallel artifact types in Lexibrary:
- **Concepts** (`.lexibrary/concepts/`) — cross-cutting design ideas, domain vocabulary, and architectural decisions
- **Conventions** (`.lexibrary/conventions/`) — prescriptive project rules, coding patterns, and scope-aware guidelines

Both support YAML frontmatter + markdown format, status lifecycles (draft/active/deprecated), and full-text indexing. However, they differ significantly in:
1. **Scope model**: Conventions are directory-scoped with inheritance; concepts are global
2. **Lifecycle**: Conventions flow from agents discovering patterns during coding; concepts represent established design knowledge
3. **Links**: Conventions can reference concepts; concepts can reference each other
4. **Validation**: Concepts have dedicated frontmatter checks; conventions have no dedicated checks

---

## 1. File Format & Structure

### Conventions

**Location**: `.lexibrary/conventions/*.md`

**Format**: YAML frontmatter + markdown body

```yaml
---
title: Future annotations import
scope: project
tags: [python, imports]
status: active
source: user
priority: 0
---

Every Python module must include `from __future__ import annotations` as the
first import. This enables PEP 604 union syntax (`X | Y`) and forward
references without string quoting.

**Rationale**: Consistency across the codebase enables...
```

**Frontmatter Fields** (all validated by Pydantic 2):

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `title` | `str` | required | Convention name (max 60 chars in slug) |
| `scope` | `str` | `"project"` | `"project"` for global, or directory path like `"src/auth"` |
| `tags` | `list[str]` | `[]` | Arbitrary tags for search/filtering |
| `status` | `Literal` | `"draft"` | One of: `"draft"`, `"active"`, `"deprecated"` |
| `source` | `Literal` | `"user"` | One of: `"user"`, `"agent"`, `"config"` |
| `priority` | `int` | `0` | Higher = sorts earlier within same scope (descending) |

**Body Structure**:
- First paragraph (up to first blank line) is extracted as `rule` — the prescriptive statement
- Remaining text is full body; may include rationale, examples, and exceptions
- Supports wikilinks `[[ConceptName]]` to reference concepts

**Model** (in `src/lexibrary/artifacts/convention.py`):
```python
class ConventionFileFrontmatter(BaseModel):
    title: str
    scope: str = "project"
    tags: list[str] = []
    status: Literal["draft", "active", "deprecated"] = "draft"
    source: Literal["user", "agent", "config"] = "user"
    priority: int = 0

class ConventionFile(BaseModel):
    frontmatter: ConventionFileFrontmatter
    body: str = ""
    rule: str = ""  # First paragraph, extracted from body
    file_path: Path | None = None
    
    @property
    def name(self) -> str:
        return self.frontmatter.title
    
    @property
    def scope(self) -> str:
        return self.frontmatter.scope
```

---

### Concepts

**Location**: `.lexibrary/concepts/*.md`

**Format**: YAML frontmatter + markdown body + optional sections

```yaml
---
title: Authorization
aliases: [auth, authz]
tags: [security, patterns]
status: active
superseded_by: null
---

Authorization is the process of determining what authenticated users are
allowed to do within the system.

... body content with optional wikilinks [[RelatedConcept]] ...

## Decision Log

- D1: Chose role-based access control (RBAC) over attribute-based (ABAC) for simplicity
- D2: Implement auth checks as decorators on handlers, not middleware
```

**Frontmatter Fields**:

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `title` | `str` | required | Concept name/term |
| `aliases` | `list[str]` | `[]` | Alternative names for resolution |
| `tags` | `list[str]` | `[]` | Categorization |
| `status` | `Literal` | `"draft"` | One of: `"draft"`, `"active"`, `"deprecated"` |
| `superseded_by` | `str \| None` | `None` | If deprecated, links to replacement concept |

**Body Sections** (extracted during parsing):
- `summary`: First non-empty paragraph before any `## ` heading
- `related_concepts`: All `[[wikilinks]]` found in body (for cross-referencing)
- `linked_files`: File references in backticks, e.g. `` `src/auth/models.py` ``
- `decision_log`: Bullet items from `## Decision Log` section

**Model** (in `src/lexibrary/artifacts/concept.py`):
```python
class ConceptFileFrontmatter(BaseModel):
    title: str
    aliases: list[str] = []
    tags: list[str] = []
    status: Literal["draft", "active", "deprecated"] = "draft"
    superseded_by: str | None = None

class ConceptFile(BaseModel):
    frontmatter: ConceptFileFrontmatter
    body: str = ""
    summary: str = ""  # First paragraph
    related_concepts: list[str] = []  # Extracted wikilinks
    linked_files: list[str] = []  # Extracted file references
    decision_log: list[str] = []  # Bullet items from Decision Log section
    
    @property
    def name(self) -> str:
        return self.frontmatter.title
```

---

## 2. Creation & Population

### Conventions

**Primary mechanisms** (v1):

#### Source 1: Agent creation via CLI (`lexi convention new`)
```bash
lexi convention new --scope src/auth \
  --body "All endpoints require auth decorator" \
  --tag security --tag patterns
```

**Behavior**:
- Creates markdown file in `.lexibrary/conventions/`
- Sets `status: draft` and `source: agent` if `--source agent`
- Sets `status: active` and `source: user` if `--source user` (default)
- File path derived from title slug: `"All endpoints..."` → `"all-endpoints.md"`
- If collision, appends `-2`, `-3`, etc.
- Agent-created conventions appear with `[draft]` tag in `lexi lookup` output
- Require human approval via `lexi convention approve <name>`

**CLI Implementation** (in `src/lexibrary/cli/lexi_app.py:631-703`):
- Validates `--scope` and `--body` (required)
- Optionally accepts `--tag` (repeatable), `--title`, `--source`
- Derives title from first 60 chars of body if not provided
- Writes via `serialize_convention_file()` → `target.write_text()`

#### Source 2: Config-declared conventions (deferred, partially plumbed)
```yaml
# .lexibrary/config.yaml
convention_declarations:
  - body: "Use `from __future__ import annotations` in every module"
    scope: project
    tags: [python, imports]
  - body: "pathspec pattern name must be 'gitignore'"
    scope: src/lexibrary/ignore
    tags: [pathspec]
```

**Status**: Declared in config schema (`ConventionDeclaration` model in `schema.py:162-173`) but **NOT YET MATERIALIZED** into convention files by the build pipeline.

**Expected materialization**:
- During `lexictl init` or `lexictl bootstrap`
- Write `.lexibrary/conventions/` files with `source: config` and `status: active`
- Survive across regenerations (unlike LLM extraction)

#### Source 3: LLM extraction (v2, deferred)
- During design file generation, secondary extraction step
- New BAML prompt or addition to existing design file prompt
- Risk of hallucinated conventions; requires review workflow

**No existing code path yet.**

---

### Concepts

**Creation mechanisms**:

#### Manual creation (most common)
```bash
lexi concept new --title "Authorization" \
  --aliases auth,authz \
  --tag security
```

**or** directly edit/create `.lexibrary/concepts/authorization.md` in a text editor.

#### Via `lexi lookup` / design file integration
- When agents encounter a cross-cutting design concern, they document it as a concept
- Design files can link concepts via wikilinks
- Concepts serve as the canonical definition of domain vocabulary

**CLI Implementation** (in `src/lexibrary/cli/lexi_app.py`):
- `lexi concept new` command (similar structure to `lexi convention new`)
- `lexi concept approve`, `lexi concept deprecate` commands
- Full CRUD operations supported

**No LLM extraction pipeline yet for concepts.**

---

## 3. Reading & Querying

### Conventions

#### Path: `lexi lookup <file>` (primary delivery)
**Location**: `src/lexibrary/cli/lexi_app.py:164-235`

**Algorithm**:
1. Walk parent directories from file's location up to scope root
2. Collect conventions from `.lexibrary/conventions/` where:
   - `scope == "project"`, OR
   - Normalized file path starts with convention's scope directory
3. Sort by scope depth (project first, then root-to-leaf), then priority descending, then title
4. Render "Applicable Conventions" section, limit to 5 by default (config: `conventions.lookup_display_limit`)

**Code flow**:
```python
# Read conventions directly from .lexibrary/conventions/ files
conventions_dir = project_root / ".lexibrary" / "conventions"
convention_index = ConventionIndex(conventions_dir)
convention_index.load()

# Find conventions applicable to file_path
conventions, total_count = convention_index.find_by_scope_limited(
    file_path=rel_target,
    scope_root=config.scope_root,
    limit=display_limit
)

_render_conventions(conventions, total_count, display_limit, rel_target)
```

**Output** (in `lexi lookup <file>` output):
```
## Applicable Conventions

(project) All endpoints require auth decorator
  Rule: All endpoints require auth decorator
  
(src/auth) Future annotations import
  [draft] Rule: Use from __future__ import annotations first
```

#### Path: Link graph queries (secondary, currently unused by CLI)
**Location**: `src/lexibrary/linkgraph/query.py:435-484` — `get_conventions(directory_paths)`

**Design**: Hierarchical inheritance query accepting ordered directory list (root→leaf), returns conventions sorted by path order then ordinal.

**Note**: Parallel query path exists but CLI reads directly from `.lexibrary/conventions/` files to avoid index dependency.

#### Path: `lexi conventions` (list/filter command)
**Location**: `src/lexibrary/cli/lexi_app.py:501-623`

**Features**:
- List all conventions or filter by path
- Filter by `--tag`, `--status`, `--scope`
- Exclude deprecated by default unless `--all`
- Table output showing title, scope, status, tags, rule

```bash
lexi conventions                          # All conventions
lexi conventions src/auth                 # Apply to src/auth
lexi conventions --status draft           # Draft only
lexi conventions --tag python             # Python-related
```

---

### Concepts

#### Path: Concept index (`ConceptIndex` in `src/lexibrary/wiki/index.py`)
**Features**:
- Load from `.lexibrary/concepts/` directory
- Search by title, alias, tag, or substring
- Retrieve by name
- Build in-memory from markdown files

```python
from lexibrary.wiki import ConceptIndex
index = ConceptIndex.load(concepts_dir)
concept = index.get("Authorization")
matches = index.search("auth")
by_tag = index.by_tag("security")
```

#### Path: Wikilink resolution (`WikilinkResolver` in `src/lexibrary/wiki/resolver.py`)
- Resolves `[[ConceptName]]` to concept files
- Supports aliases (case-insensitive matching)
- Used in:
  - Validator for wikilink_resolution check
  - Design file parser for extracting wikilink targets
  - Stack post body analysis

#### Path: `lexi concepts` (list/search command)
**Location**: `src/lexibrary/cli/lexi_app.py` (via `concept_app` subcommand group)

**Features**:
- Search concepts by keyword
- Filter by tag, status, alias
- Show concept details

---

## 4. Storage & Indexing

### Conventions

**On-disk storage**:
```
.lexibrary/conventions/
├── future-annotations-import.md
├── pathspec-gitignore.md
├── all-endpoints-require-auth.md
└── use-rich-console.md
```

**Parser** (`src/lexibrary/conventions/parser.py`):
- Regex-based YAML frontmatter extraction
- `_extract_rule()` pulls first paragraph as prescriptive statement
- Silent skip on parse failures (returns `None`)

**Serializer** (`src/lexibrary/conventions/serializer.py`):
- Writes YAML frontmatter block
- Preserves full body text
- Ensures trailing newline

**Index** (`src/lexibrary/conventions/index.py` — `ConventionIndex`):
- In-memory list-based index (parallel to `ConceptIndex`)
- Scope-aware queries with inheritance ordering
- Search by substring, tag, status
- Methods:
  - `find_by_scope(file_path, scope_root)` — returns conventions for a file (ordered)
  - `find_by_scope_limited(file_path, scope_root, limit)` — truncates to most-specific
  - `search(query)` — substring search
  - `by_tag(tag)` — filter by tag
  - `by_status(status)` — filter by status
  - `names()` — all titles

### Concepts

**On-disk storage**:
```
.lexibrary/concepts/
├── authorization.md
├── authentication.md
├── design-decision.md
└── dependency-injection.md
```

**Parser** (`src/lexibrary/wiki/parser.py`):
- Regex-based YAML frontmatter extraction
- Extracts summary, wikilinks, file references, decision log during parsing
- Silent skip on failures

**Serializer** (`src/lexibrary/wiki/serializer.py`):
- Writes YAML frontmatter + markdown body

**Index** (`src/lexibrary/wiki/index.py` — `ConceptIndex`):
- In-memory list-based index
- Methods:
  - `get(title)` — lookup by title
  - `search(query)` — substring search
  - `by_alias(alias)` — case-insensitive alias resolution
  - `by_tag(tag)` — filter by tag
  - `by_status(status)` — filter by status
  - `names()` — all titles

### Link Graph Integration

**Conventions table** (`src/lexibrary/linkgraph/schema.py:99-110`):
```sql
CREATE TABLE IF NOT EXISTS conventions (
    artifact_id    INTEGER NOT NULL REFERENCES artifacts(id) ON DELETE CASCADE,
    directory_path TEXT    NOT NULL,
    ordinal        INTEGER NOT NULL DEFAULT 0,
    body           TEXT    NOT NULL,
    source         TEXT    NOT NULL DEFAULT 'user',
    status         TEXT    NOT NULL DEFAULT 'active',
    priority       INTEGER NOT NULL DEFAULT 0,
    UNIQUE(directory_path, ordinal)
);
```

**Conventions artifacts** in `artifacts` table:
- `kind = 'convention'`
- `path = "{directory_path}::convention::{ordinal}"` (synthetic)
- No backing file on disk

**Builder logic** (`src/lexibrary/linkgraph/builder.py:849-940`):
- `_process_aindex_conventions()` — scan `.aindex` files for `local_conventions` field
- For each convention, create artifact + conventions table row
- Extract wikilinks from convention text → `convention_concept_ref` links
- FTS indexing for full-text search

**Note**: Currently unused because `.aindex` files always have `local_conventions = []` (hard-coded in generator).

**Concepts in link graph**:
- `kind = 'concept'`
- `path = <relative path to .lexibrary/concepts/xyz.md>`
- Wikilinks create edges: `concept --[wikilink]--> concept`
- Aliases stored in `aliases` table

---

## 5. Validation & Health Checks

### Conventions

**Current validation**:
- No dedicated convention-specific checks
- Syntactically validated during parser (YAML frontmatter)
- No orphan detection, freshness checks, or conflict detection between scopes

**Why excluded**:
- Convention artifacts use synthetic paths (`{dir}::convention::{ordinal}`) with no backing files
- File-existence checks would always fail
- Historical reason: conventions pipeline was plumbed but never populated (all `.aindex` files have `local_conventions = []`)

**Recommended additions** (for future):
- Orphan convention detection (conventions declared but never matched to files)
- Scope hierarchy conflict detection (broader scope overridden by narrower scope)
- Freshness check on agent-created conventions (draft → active approval workflow)
- Staleness detection on deprecated conventions (still referenced by design files)

### Concepts

**Existing validation** (`src/lexibrary/validator/checks.py`):

#### `check_concept_frontmatter()` (error severity)
- Every `.md` file in `.lexibrary/concepts/` must have valid YAML frontmatter
- Validates all required fields: `title`, `status`
- Checks field types and value constraints

#### `check_token_budgets()` (warning severity)
- Concept files have per-file token limit (config: `token_budgets.concept_file_tokens`, default 400)
- Warns if over budget

#### `check_orphan_concepts()` (warning severity)
- Concepts with zero inbound wikilink references
- Suggests deletion or documentation

#### `check_deprecated_concept_usage()` (warning severity)
- Deprecated concepts still referenced by design files or other concepts
- Suggests updating references to `superseded_by` target

#### Wikilink resolution (`check_wikilink_resolution()`, error severity)
- Every `[[link]]` in design files must resolve to an existing concept or Stack post
- Provides fuzzy-match suggestions

---

## 6. Relationships & Cross-References

### Convention → Concept Links

**In convention body**:
```markdown
Every Python module must include `from __future__ import annotations` as the
first import. This enables [[Forward References]] and [[PEP 604 Union Syntax]]
in our codebase.
```

**Parsing**: `_extract_rule()` + regex `_WIKILINK_RE = r"\[\[(.+?)\]\]"` extracts concept names.

**Link graph**: `convention --[convention_concept_ref]--> concept` edges created during builder processing.

**Status**: Designed but **currently unused** because conventions pipeline is not populated.

### Concept → Concept Links

**In concept body**:
```markdown
Authorization checks are performed after [[Authentication]] establishes the user's identity.
```

**Parsing**: Wikilinks extracted automatically during parsing.

**Link graph**: `concept --[wikilink]--> concept` edges.

**Validation**: Unresolved wikilinks produce error-severity issues.

### Concept → File Links

**In concept body**:
```markdown
The main implementation is in `src/auth/models.py`, specifically the `User` class.
```

**Parsing**: File references extracted via `_FILE_REF_RE` (backtick-delimited paths with known extensions).

**Link graph**: Potential for future `concept --[concept_file_ref]--> source` edges.

**Status**: Extracted but not yet linked in graph.

### Design File → Convention References

**Via `lexi lookup <design-file>`**:
- Lookup command walks parent directories from design file's location
- Collects conventions with matching scope
- Renders in "Applicable Conventions" section

**Example**:
```
.lexibrary/designs/src/auth/models.md
  Applicable scopes:
  - src/auth
  - src
  - . (project root)
  
  Matched conventions:
  - (project) Future annotations import
  - (src/auth) All endpoints require auth decorator
```

### Design File → Concept References

**Via wikilinks in design files**:
- Design files can include `[[ConceptName]]` in body
- Validator resolves each to concept artifact
- Link graph tracks: `design --[wikilink]--> concept`

---

## 7. Configuration

**Config schema** (`src/lexibrary/config/schema.py`):

```python
class ConventionConfig(BaseModel):
    """Convention system configuration."""
    lookup_display_limit: int = 5  # How many to show in lexi lookup

class ConventionDeclaration(BaseModel):
    """A user-declared convention seeded from config."""
    body: str
    scope: str = "project"
    tags: list[str] = []

class LexibraryConfig(BaseModel):
    conventions: ConventionConfig = Field(default_factory=ConventionConfig)
    convention_declarations: list[ConventionDeclaration] = Field(default_factory=list)
    
    # Token budgets for validation
    token_budgets: TokenBudgetConfig
        # convention_file_tokens: int = 500
        # concept_file_tokens: int = 400
```

**Example config**:
```yaml
scope_root: "."
project_name: "Lexibrary"

conventions:
  lookup_display_limit: 5

convention_declarations:
  - body: "Use `from __future__ import annotations` in every module"
    scope: project
    tags: [python, imports]

token_budgets:
  convention_file_tokens: 500
  concept_file_tokens: 400
```

---

## 8. Existing Lifecycle Features

### Concepts

**Status lifecycle** (YAML frontmatter):
- `draft` — proposal, under consideration
- `active` — established, in use
- `deprecated` — obsolete, avoid using (linked via `superseded_by`)

**Aliases** (case-insensitive, unique):
- Support multiple names for the same concept
- Resolver automatically tries aliases when resolving wikilinks

**Decorator API**:
- `lexi concept approve <name>` — promote draft → active
- `lexi concept deprecate <name>` — mark as deprecated
- `lexi concept supersede <name> --by <replacement>` — (future)

### Conventions

**Status lifecycle** (YAML frontmatter):
- `draft` — proposed by agent, requires human approval
- `active` — approved, in force
- `deprecated` — obsolete, avoid using

**Source tracking** (YAML frontmatter):
- `user` — manually created by human
- `agent` — created by coding agent (requires approval)
- `config` — declared in `.lexibrary/config.yaml` (always active)

**Priority ordering**:
- Within same scope, higher priority sorts earlier
- Agent-created: priority = -1 (lower)
- User-created: priority = 0 (default)

**Lifecycle transitions**:
- `lexi convention approve <name>` — draft → active
- `lexi convention deprecate <name>` — any → deprecated

---

## 9. Current Gaps & Deficiencies

### Conventions

1. **No population mechanism**: `.aindex` files always have `local_conventions = []` (hard-coded in generator)
   - Link graph convention artifacts never created
   - CLI reads directly from `.lexibrary/conventions/` files (bypass index)
   - Parallel data flow paths

2. **No config materialization**: `convention_declarations` in config are parsed but never written to disk

3. **No LLM extraction**: v2 feature deferred

4. **No validation checks**:
   - No orphan convention detection
   - No scope hierarchy conflict detection
   - Convention artifacts skipped in `check_orphan_artifacts()`
   - Convention artifacts skipped in `check_dangling_links()`

5. **Design file scope resolution**: Design file at `src/auth/models.md` should inherit conventions from `src/auth`, `src`, project root. Currently works (via CLI walk) but not reflected in link graph.

### Concepts

1. **Limited lifecycle**: No built-in deprecation workflow (no auto-migration of references)

2. **No linked_files indexing**: File references extracted but not linked in graph (designed but not implemented)

3. **No Stack integration**: Concepts and Stack posts are separate; potential for cross-linking

4. **No search unification**: `lexi concepts` and `lexi search` handle different indices

---

## 10. Design Decisions (from conventions-artifact.md)

**D1-D12** (settled, v1):

1. **File-based storage** (like concepts) vs database-only vs hybrid
   - **Decision**: File-based in `.lexibrary/conventions/*.md` for editability and versioning
   - Hybrid approach: `.aindex` files as source of truth, link graph as index (currently broken)

2. **Scope model**: Inheritance vs flat vs pattern-based
   - **Decision**: Directory-scoped with root-to-leaf inheritance (project root → file's directory)

3. **Provenance tracking**: `source` field distinguishes user vs agent vs config origins

4. **Status lifecycle**: draft/active/deprecated (consistent with concepts)

5. **Priority ordering**: Within same scope, higher priority sorts first (tiebreaker: title alphabetic)

6. **Population mechanisms**:
   - v1: CLI creation + config declarations
   - v2: LLM extraction + pattern-based scopes

7. **Delivery point**: `lexi lookup <file>` as primary (auto-runs via hook, file-specific, scope-aware)

8. **Agent harnessing**: Rules/skills instruct agents to create conventions when they discover repeating patterns

9. **Draft/approval workflow**: Agent-created conventions are draft by default, require `lexi convention approve` to activate

10. **No breaking changes**: Legacy `.aindex` local_conventions field preserved for future migration

---

## 11. Key Implementation Files

| File | Role | Key Classes/Functions |
|------|------|----------------------|
| `src/lexibrary/artifacts/convention.py` | Models | `ConventionFile`, `ConventionFileFrontmatter`, `convention_slug()`, `convention_file_path()` |
| `src/lexibrary/artifacts/concept.py` | Models | `ConceptFile`, `ConceptFileFrontmatter` |
| `src/lexibrary/conventions/parser.py` | I/O | `parse_convention_file()`, `_extract_rule()` |
| `src/lexibrary/conventions/serializer.py` | I/O | `serialize_convention_file()` |
| `src/lexibrary/conventions/index.py` | Query | `ConventionIndex.find_by_scope()`, `.find_by_scope_limited()`, `.search()` |
| `src/lexibrary/wiki/parser.py` | I/O | `parse_concept_file()`, `_extract_summary()`, `_extract_decision_log()` |
| `src/lexibrary/wiki/serializer.py` | I/O | `serialize_concept_file()` |
| `src/lexibrary/wiki/index.py` | Query | `ConceptIndex.get()`, `.search()`, `.by_alias()`, `.by_tag()` |
| `src/lexibrary/wiki/resolver.py` | Resolution | `WikilinkResolver`, `ResolvedLink`, `UnresolvedLink` |
| `src/lexibrary/cli/lexi_app.py` | CLI | `conventions()`, `convention_new()`, `convention_approve()`, `convention_deprecate()` |
| `src/lexibrary/cli/lexi_app.py` | CLI | `concept_*` sub-commands (parallel structure) |
| `src/lexibrary/config/schema.py` | Config | `ConventionConfig`, `ConventionDeclaration` |
| `src/lexibrary/linkgraph/schema.py` | DB | Conventions table + FTS indexing |
| `src/lexibrary/linkgraph/builder.py` | Indexing | `_process_aindex_conventions()`, `_handle_changed_aindex()` |
| `src/lexibrary/linkgraph/query.py` | Query | `get_conventions()` (hierarchical inheritance) |
| `src/lexibrary/validator/checks.py` | Validation | `check_concept_frontmatter()`, `check_orphan_concepts()`, `check_deprecated_concept_usage()` |

---

## 12. Testing

**Conventions**:
- `tests/test_artifacts/test_convention_models.py` — Pydantic model validation, slug generation, path helpers
- `tests/test_conventions/` (inferred but not exhaustively explored) — parser, serializer, index

**Concepts**:
- Tests scattered across validators, wiki module, parser/serializer

---

## Summary Table

| Aspect | Conventions | Concepts |
|--------|-------------|----------|
| **Location** | `.lexibrary/conventions/*.md` | `.lexibrary/concepts/*.md` |
| **Scope** | Directory-scoped with inheritance | Global |
| **Frontmatter** | title, scope, tags, status, source, priority | title, aliases, tags, status, superseded_by |
| **Body sections** | rule (first paragraph) + body | summary, related_concepts, linked_files, decision_log |
| **Primary creation** | `lexi convention new` | Manual or `lexi concept new` |
| **Primary consumption** | `lexi lookup <file>` (scope-aware) | Wikilinks in design files + `lexi search` |
| **Status lifecycle** | draft/active/deprecated | draft/active/deprecated |
| **Provenance tracking** | Yes (source field) | No |
| **Aliasing** | No | Yes (aliases field) |
| **Link graph presence** | Artifacts table (synthetic paths), conventions table, FTS | Artifacts table, links table, aliases table, FTS |
| **Validation checks** | None yet | Frontmatter, token budget, orphan, deprecated usage, wikilink resolution |
| **Config integration** | ConventionDeclaration (not yet materialized) | No config integration |
| **v2 features** | LLM extraction, pattern-based scopes | Limited lifecycle, linked_files indexing |

