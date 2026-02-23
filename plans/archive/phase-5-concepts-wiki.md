# Phase 5 — Concepts Wiki

**Reference:** `plans/v2-master-plan.md` (Phase 5 section), `lexibrary-overview.md` (sections 4, 5)
**Depends on:** Phase 1 (Foundation), Phase 4 (Archivist) — both complete
**Consumed by:** Phase 6 (The Stack), Phase 7 (Validation & Search), Phase 8 (Agent Setup)

---

## Goal

A living wiki of cross-cutting concepts that agents maintain alongside code. `lexi concepts` lists or searches concept files. `lexi concept new` creates a concept from a template. Wikilinks in design files and Stack posts resolve to concept files. Agents create, update, and link concepts during normal development — the wiki grows organically with the codebase.

---

## Decisions Made

| # | Decision | Resolution |
|---|----------|------------|
| D-028 | Concept index location | `lexi concepts` command, NOT embedded in START_HERE.md. The convention index in START_HERE stays as a lightweight routing aid; the full concept catalog is CLI-accessed. This keeps START_HERE within its token budget as concept count grows. |
| D-029 | YAML frontmatter fields | `title`, `aliases`, `tags`, and `status` are mandatory in concept file frontmatter. `aliases` enables fuzzy discovery (agents think in different terms). `tags` enables `lexi search --tag`. |
| D-030 | Directory structure | Flat `concepts/` directory — no subdirectories. Nesting/hierarchy is expressed through wikilinks between concepts, not filesystem structure. Resolution stays simple: `[[ConceptName]]` → `concepts/ConceptName.md`. |
| D-031 | Concept lifecycle | Concepts have a `status` field: `active`, `deprecated`, `draft`. Deprecated concepts still resolve but display a notice and `superseded_by` pointer. `lexi validate` flags concepts with zero inbound references as candidates for review. |
| D-032 | Agent-first authoring | Agents are the primary authors of concepts (they have context). No LLM generation of concept content — concepts are too nuanced for automated generation. The Archivist's role is limited to suggesting wikilinks to existing concepts in design files. |
| D-033 | Wikilink format in design files | Wikilinks in design file `## Wikilinks` sections are stored as `[[ConceptName]]` (double-bracket wrapped). The resolver strips brackets for lookup. This matches established wikilink conventions agents know from training data. |
| D-034 | Concept deletion | Soft delete via `status: deprecated`. Hard deletion is a manual operation (agents/users delete the file). `lexi validate` flags orphan concepts (zero references) for review. No auto-delete. |

---

## Concept File Format

### YAML Frontmatter (mandatory fields)

```yaml
---
title: Money Handling
aliases: [currency, monetary values, pricing]
tags: [domain, finance, data-integrity]
status: active
---
```

All four fields are mandatory. Validation rejects concept files missing any of them.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `title` | string | yes | Human-readable concept name (matches filename without `.md`) |
| `aliases` | list[string] | yes | Alternative names agents might search for. Minimum 1 entry. |
| `tags` | list[string] | yes | Lowercase labels for search/filtering. Minimum 1 entry. |
| `status` | enum | yes | `active`, `deprecated`, or `draft` |
| `superseded_by` | string | no | Concept name that replaces this one (when `status: deprecated`) |

### Markdown Body (agent-authored)

```markdown
# Money Handling

## Summary
All monetary values in this codebase use `Decimal`, never `float`.
Rounding is always explicit via `quantize()`.

## Why This Matters
Float arithmetic causes silent precision loss. $10.10 + $10.20 = $20.299999...
This corrupted invoice totals in production (see [[ST-007]]).

## Rules
- Use `Decimal` for all money fields (models, API responses, calculations)
- Rounding: `value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)`
- Storage: stored as integer cents in the DB, converted at the boundary

## Where It Applies
- `src/models/` — all price/amount fields
- `src/services/billing/` — calculation logic
- `src/api/` — serialization/deserialization

## Related
- [[DataValidation]] — input validation for monetary amounts
- [[DatabaseConventions]] — integer storage pattern
- [[ST-007]] — the float bug that prompted this convention

## Decision Log
- 2026-01-15: Adopted Decimal over float after production incident
- 2026-02-01: Added quantize() convention after inconsistent rounding found
```

### Section Guide

| Section | Required | Purpose |
|---------|----------|---------|
| `# Title` | yes | H1 heading matching the `title` frontmatter field |
| `## Summary` | yes | 1-3 sentences. What this concept is and why it matters. |
| `## Why This Matters` | no | Context for why this convention/pattern exists. Evidence-driven. |
| `## Rules` | no | Prescriptive guidelines. "Do X, not Y, because Z." This is the highest-value section. |
| `## Where It Applies` | no | File/directory scopes where this concept is relevant. |
| `## Related` | no | Wikilinks to other concepts, Stack posts, or file paths. |
| `## Decision Log` | no | Append-only record of key decisions. Date + one-line entry. |

**Design principle:** Concepts should be **prescriptive, not descriptive**. "Do X, not Y, because Z" is worth 10x more than "X is a pattern where..." Agents need actionable rules, not encyclopedia entries.

### No Metadata Footer

Unlike design files, concept files have **no HTML comment footer**. Concepts are fully agent/human authored — there is no LLM generation to track staleness against. The `status` field and `lexi validate` handle lifecycle management instead.

---

## ConceptFile Model (Update from Stub)

The existing stub in `artifacts/concept.py` is replaced with the full model:

```python
class ConceptFileFrontmatter(BaseModel):
    title: str
    aliases: list[str] = Field(min_length=1)
    tags: list[str] = Field(min_length=1)
    status: Literal["active", "deprecated", "draft"] = "active"
    superseded_by: str | None = None

class ConceptFile(BaseModel):
    name: str                              # filename stem (e.g., "MoneyHandling")
    frontmatter: ConceptFileFrontmatter
    body: str                              # full markdown body below frontmatter
    # Parsed from body for programmatic access:
    summary: str                           # extracted from ## Summary section
    related_concepts: list[str] = []       # [[wikilinks]] found in body
    related_files: list[str] = []          # file paths found in body
    decision_log: list[str] = []           # entries from ## Decision Log
```

**Key change from stub:** The model now separates frontmatter (structured, validated) from body (freeform markdown). The parser extracts `summary`, `related_concepts`, and `related_files` from the body for programmatic access, but the body itself is the source of truth — we never reconstruct the body from parsed fields.

---

## New Module: `src/lexibrary/wiki/`

The master plan calls this `knowledge_graph/` but `wiki/` better reflects the evolved design. This is the core module for Phase 5.

```
src/lexibrary/wiki/
├── __init__.py          ← Public API re-exports
├── resolver.py          ← Wikilink resolution (exact + fuzzy match)
├── parser.py            ← Parse concept files from disk
├── serializer.py        ← Serialize ConceptFile to markdown
├── index.py             ← Build concept index (names + aliases + summaries)
└── template.py          ← Concept file template for `lexi concept new`
```

### Module Responsibilities

**`resolver.py`** — Shared wikilink resolution utility (used by design files, Stack posts, and concepts themselves).

```python
@dataclass
class ResolvedLink:
    target: str           # concept name or Stack post ID
    target_path: Path     # resolved file path
    link_type: Literal["concept", "stack"]

@dataclass
class UnresolvedLink:
    raw: str              # original link text
    source_file: Path     # file containing the link
    suggestions: list[str]  # fuzzy match candidates

def resolve_wikilink(
    link_text: str,
    project_root: Path,
    concept_index: ConceptIndex,
) -> ResolvedLink | UnresolvedLink
```

Resolution order:
1. Strip `[[` and `]]` brackets
2. Check for Stack pattern (`ST-NNN`) → resolve to `stack/ST-NNN-*.md`
3. Exact match against concept filenames (case-sensitive)
4. Exact match against concept aliases (case-insensitive)
5. Fuzzy match against concept titles + aliases (case-insensitive, normalised)
6. Return `UnresolvedLink` with suggestions if no match

**`parser.py`** — Parse concept files from disk.

```python
def parse_concept_file(path: Path) -> ConceptFile | None
def parse_concept_frontmatter(path: Path) -> ConceptFileFrontmatter | None
```

Parsing strategy:
- YAML frontmatter extracted between `---` delimiters (same approach as design file parser)
- Body is everything after the closing `---`
- `## Summary` section extracted via heading scan
- `[[wikilinks]]` extracted via regex `\[\[([^\]]+)\]\]` from full body
- File paths extracted via backtick-wrapped path patterns from `## Where It Applies`
- `## Decision Log` entries extracted as bullet list items

**`serializer.py`** — Serialize `ConceptFile` to markdown.

Only used by `lexi concept new` (template generation). After creation, concepts are hand-edited — the serializer is never used to overwrite an existing concept file.

**`index.py`** — Build the concept index for CLI display and resolver use.

```python
@dataclass
class ConceptIndexEntry:
    name: str
    title: str
    aliases: list[str]
    tags: list[str]
    summary: str
    status: str
    path: Path

class ConceptIndex:
    entries: list[ConceptIndexEntry]

    @classmethod
    def build(cls, project_root: Path) -> ConceptIndex
        """Scan concepts/ directory, parse frontmatter + summary from each file."""

    def search(self, query: str) -> list[ConceptIndexEntry]
        """Fuzzy search across names, titles, aliases, and tags."""

    def find(self, name: str) -> ConceptIndexEntry | None
        """Exact match by name or alias."""

    def by_tag(self, tag: str) -> list[ConceptIndexEntry]
        """Filter entries by tag."""
```

The index is built on-demand by scanning the `concepts/` directory. No caching for MVP (file count will be small — < 50 concepts in most projects). If performance becomes an issue, Phase 10 (Query Index) handles it.

**`template.py`** — Template for `lexi concept new`.

```python
def render_concept_template(name: str) -> str
    """Return a concept file template with mandatory frontmatter pre-filled."""
```

---

## CLI Commands

### `lexi concepts [<topic>]` — List or search concepts

**No arguments:** List all active concepts in compact format (name + summary, one line each). This is the concept index.

```
$ lexi concepts
Authentication     — JWT-based auth with refresh token rotation
MoneyHandling      — All monetary values use Decimal, never float
RepositoryPattern  — Data access via repository classes, not direct ORM
AsyncMigration     — In-progress migration from sync to async handlers
EventBus           — Pub/sub event system for cross-module communication

5 concepts (5 active)
```

**With topic argument:** Fuzzy search across names, aliases, tags, and summary text. Display full concept file content for matches.

```
$ lexi concepts auth
# Authentication

## Summary
JWT-based authentication with refresh token rotation...
[full concept file content]
```

If multiple matches, show the compact list and let the agent pick:

```
$ lexi concepts data
Multiple matches:
  DataValidation  — Input validation rules for API boundaries
  MoneyHandling   — All monetary values use Decimal, never float

Use `lexi concepts <exact-name>` to view a specific concept.
```

**Flags:**
- `--tag <tag>` — filter by tag
- `--status <status>` — filter by status (default: show only `active`)
- `--all` — include deprecated and draft concepts

### `lexi concept new <name>` — Create a concept from template

Creates `.lexibrary/concepts/<Name>.md` with mandatory frontmatter pre-filled and body sections as placeholders. Opens the file content to stdout so agents can see what was created.

```
$ lexi concept new MoneyHandling
Created .lexibrary/concepts/MoneyHandling.md
```

The template includes all mandatory frontmatter fields with placeholder values and the recommended body sections as empty scaffolds:

```markdown
---
title: MoneyHandling
aliases: []
tags: []
status: draft
---

# MoneyHandling

## Summary

[What is this concept and why does it matter?]

## Rules

[Prescriptive guidelines: "Do X, not Y, because Z"]

## Where It Applies

[File paths and directories where this concept is relevant]

## Related

[Links to other concepts, Stack posts, or key files]
```

**Validation:** Exits with error if the concept file already exists. Name is normalised to PascalCase for the filename.

### `lexi concept link <file> <concept>` — Add wikilink to a design file

Convenience command: adds `[[ConceptName]]` to the `## Wikilinks` section of the specified file's design file.

```
$ lexi concept link src/models/payment.py MoneyHandling
Added [[MoneyHandling]] to .lexibrary/src/models/payment.py.md
```

**Validation:**
- Concept must exist (resolved via index)
- Design file must exist (suggest `lexi update` if not)
- Skip if link already present

---

## Wikilink Integration with Existing Artifacts

### Design Files

Design files already have a `## Wikilinks` section and `wikilinks: list[str]` in the model. Phase 5 changes:

1. **Wikilinks stored with brackets:** The serializer already writes them as bullet items. Standardise on `[[ConceptName]]` format in the serialized output. The parser strips brackets for model storage.

2. **Archivist awareness of concepts:** Update the `ArchivistGenerateDesignFile` BAML prompt to accept an optional `available_concepts` parameter — a compact list of concept names + aliases. The Archivist can then suggest relevant wikilinks from the known concept set rather than inventing concept names that don't exist.

3. **Pipeline integration:** `update_file()` in `archivist/pipeline.py` passes the concept index (names only) to the Archivist prompt. This is a lightweight addition — just the list of names, not full concept content.

### Stack Posts (Phase 6 prep)

The wikilink resolver in `wiki/resolver.py` is designed as a shared utility. Phase 6 will use the same resolver for Stack post `[[ST-NNN]]` wikilinks. No prep work needed beyond building a clean resolver API.

### `.aindex` Files

No change. `.aindex` files don't contain wikilinks.

---

## Wikilink Resolution: Detail

### The Resolver Algorithm

```
Input: raw link text (e.g., "[[Authentication]]" or "[[ST-001]]")

1. Strip [[ and ]] → "Authentication" or "ST-001"

2. Stack pattern check:
   - If matches /^ST-\d{3}/  →  scan stack/ directory
   - Return resolved path or unresolved

3. Exact name match:
   - Check concepts/{name}.md exists
   - Case-sensitive
   - Return if found

4. Alias match:
   - Load frontmatter from all concept files (cached in ConceptIndex)
   - Check aliases (case-insensitive)
   - Return if exactly one match
   - If multiple matches → return unresolved with candidates

5. Fuzzy match:
   - Normalise: lowercase, strip hyphens/underscores/spaces
   - Compare against normalised names + aliases
   - Return unresolved with suggestions (top 3 by similarity)

6. No match → UnresolvedLink with empty suggestions
```

### Cycle Detection

Concepts can link to each other via wikilinks. Cycles are allowed (e.g., `Authentication ↔ SessionManagement`) — they represent genuine bidirectional relationships. However, `lexi validate` (Phase 7) will detect and report cycles for informational purposes, not as errors.

The resolver itself does not need cycle detection — it resolves individual links, not graphs. Graph traversal (if ever needed) is a Phase 10 concern.

---

## What Changes in Existing Code

### `artifacts/concept.py` — Model update

Replace the stub model with the full `ConceptFileFrontmatter` + `ConceptFile` model described above. This is a non-breaking change — no existing code calls the stub model.

### `artifacts/design_file_serializer.py` — Wikilink format

Update wikilink serialization to wrap concept names in `[[brackets]]`:

```python
# Current:
parts.append(f"- {link}")

# Updated:
parts.append(f"- [[{link}]]")
```

**Impact:** Design files regenerated after this change will use `[[ConceptName]]` format. Existing design files with plain names will work — the parser should handle both formats (strip brackets if present).

### `artifacts/design_file_parser.py` — Parse both formats

Update the wikilinks parser to strip `[[` and `]]` brackets if present, so the model stores clean names regardless of serialized format.

### `baml_src/archivist_design_file.baml` — Concept awareness

Add `available_concepts` optional parameter to the prompt. This is a backward-compatible addition — the existing prompt works without it, but produces better wikilink suggestions when it's provided.

### `archivist/pipeline.py` — Pass concept index

In `update_file()`, build a lightweight concept name list and pass it to the Archivist service. This is a small addition to the existing pipeline.

### `cli.py` — Implement `concepts` command, add `concept` sub-app

Replace the `concepts` stub. Add a `concept` sub-app with `new` and `link` commands.

---

## Implementation Tasks

### Task Group 1: ConceptFile Model & Parser/Serializer

1. Update `artifacts/concept.py` with full `ConceptFileFrontmatter` + `ConceptFile` model
2. Create `wiki/__init__.py` with public API re-exports
3. Create `wiki/parser.py` — parse concept files from disk (frontmatter + body extraction)
4. Create `wiki/serializer.py` — serialize ConceptFile to markdown (used by template)
5. Create `wiki/template.py` — concept file template rendering
6. Write unit tests for model validation (mandatory fields, status enum, alias/tag minimums)
7. Write unit tests for parser (valid files, missing frontmatter, missing fields)
8. Write unit tests for serializer round-trip

### Task Group 2: Concept Index

1. Create `wiki/index.py` — `ConceptIndex` class with `build()`, `search()`, `find()`, `by_tag()`
2. Implement fuzzy search (case-insensitive name/alias/tag/summary matching)
3. Write unit tests for index building and search

### Task Group 3: Wikilink Resolver

1. Create `wiki/resolver.py` — `resolve_wikilink()` function
2. Implement resolution chain: bracket stripping → Stack pattern → exact name → alias → fuzzy
3. Define `ResolvedLink` and `UnresolvedLink` result types
4. Write unit tests for each resolution step
5. Write integration tests with `tmp_path` concept files

### Task Group 4: CLI Commands

1. Implement `lexi concepts` — list all concepts (compact format)
2. Implement `lexi concepts <topic>` — fuzzy search + display
3. Implement `lexi concepts --tag <tag>` — filter by tag
4. Implement `lexi concepts --all` — include deprecated/draft
5. Add `concept` sub-app to CLI
6. Implement `lexi concept new <name>` — create from template
7. Implement `lexi concept link <file> <concept>` — add wikilink to design file
8. Write CLI tests with `typer.testing.CliRunner`

### Task Group 5: Design File Integration

1. Update `design_file_serializer.py` — wrap wikilinks in `[[brackets]]`
2. Update `design_file_parser.py` — strip brackets on parse (handle both formats)
3. Update `archivist_design_file.baml` — add `available_concepts` parameter
4. Update `archivist/service.py` — accept and pass concept names to BAML
5. Update `archivist/pipeline.py` — build concept name list, pass to Archivist
6. Write tests for updated serializer/parser
7. Write integration test: design file generation with concept awareness

### Task Group 6: Documentation & Blueprints

1. Update `blueprints/START_HERE.md` with wiki module entry
2. Create design files for new wiki module files
3. Update `lexibrary-overview.md` with Phase 5 decisions
4. Update `v2-master-plan.md` decision log

---

## Acceptance Criteria

1. `lexi concept new MoneyHandling` creates a valid concept file with mandatory frontmatter
2. `lexi concepts` lists all active concepts with name + summary
3. `lexi concepts auth` fuzzy-matches concepts by name, alias, and tag
4. `lexi concepts --tag security` filters by tag
5. `lexi concept link src/foo.py Authentication` adds `[[Authentication]]` to the design file's wikilinks section
6. Design files generated by `lexi update` include `[[wikilinks]]` that reference existing concepts (when available)
7. Concept files with missing mandatory frontmatter fields are rejected with clear error messages
8. The wikilink resolver correctly handles: exact match, alias match, fuzzy match, unresolved links, Stack pattern
9. All new code has `from __future__ import annotations`
10. All output uses `rich.console.Console` — no bare `print()`
11. Test coverage for all new modules

---

## What to Watch Out For

- **Concept file names are PascalCase by convention** — `MoneyHandling.md`, not `money-handling.md` or `money_handling.md`. The resolver normalises for matching but filenames should be consistent.
- **The parser must handle concept files with extra sections** — agents will add sections beyond the template. Parse known sections, preserve everything else as part of `body`.
- **Fuzzy matching must not be too aggressive** — returning false positives is worse than returning no match. Keep the threshold conservative and surface suggestions rather than auto-resolving uncertain matches.
- **Concept count will be small for MVP** — O(n) scanning of `concepts/` directory is fine. Don't over-optimise. Phase 10 adds SQLite if needed.
- **The Archivist concept-awareness is best-effort** — if no concepts exist yet, the prompt works without them. The `available_concepts` parameter is optional.
- **`lexi concept link` must read-modify-write the design file** — use the existing parser to read, modify the wikilinks list, and re-serialize. Don't do string manipulation on the raw file.
- **Bracket format transition** — existing design files may have wikilinks without brackets (from Phase 4 LLM output). The parser handles both; the serializer always writes brackets going forward. No migration needed.

---

## Not In Scope (Deferred)

- **LLM-generated concept content** — concepts are agent-authored. The Archivist suggests wikilinks to existing concepts but never generates concept file content.
- **Reverse dependency index** — design file `dependents` field population is deferred to a future enhancement. Phase 5 focuses on concept graph, not import graph.
- **Graph traversal queries** — "What's 2 hops from Authentication?" is a Phase 10 concern (if ever needed). Phase 5 resolves individual links.
- **Concept merge/split tooling** — manual process for now. Agents deprecate the old concept and create new ones.
- **START_HERE.md concept embedding** — the convention index in START_HERE.md remains as-is (lightweight, LLM-generated). The full concept catalog is accessed via `lexi concepts`.
