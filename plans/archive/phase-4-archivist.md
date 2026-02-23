# Phase 4 — Archivist: LLM-Powered Design Files

**Reference:** `plans/v2-master-plan.md` (Phase 4 section), `lexibrary-overview.md` (sections 2, 7, 9)
**Depends on:** Phase 1 (Foundation), Phase 2 (Directory Indexes), Phase 3 (AST Parser) — all complete
**Consumed by:** Phase 5 (Knowledge Graph), Phase 6 (Guardrails), Phase 7 (Validation), Phase 9 (Daemon)

---

## Goal

`lexi update [<path>]` generates or refreshes design files as a **fallback** when agents haven't updated them directly. `lexi lookup <file>` returns the design file for a source file. START_HERE.md generation from project topology.

The primary authoring model: **agents write design files while they have context** (during code changes). The Archivist LLM pipeline is the safety net — it catches files that agents forgot to document.

---

## Decisions Made

| # | Decision | Resolution |
|---|----------|------------|
| D-011 | File scope | All files within `scope_root` get design files. Non-code files use content hash only (no interface hash). Files outside `scope_root` appear in `.aindex` but don't get design files. |
| D-012 | LLM client routing | Config-driven. BAML defines multiple named clients; archivist selects client based on `LLMConfig.provider` at runtime. |
| D-013 | LLM input strategy | Always send interface skeleton + full source file content. Consistent approach regardless of change type. |
| D-014 | Dependency tracking | Forward dependencies only in Phase 4 (extracted from AST imports). Reverse dependency index (dependents) deferred to Phase 5. |
| D-015 | Change detection source | Read `StalenessMetadata` from existing design file HTML comment footer — no separate cache file. Design file metadata *is* the cache. |
| D-016 | Archivist service placement | New `archivist/` module, separate from `llm/service.py`. Clean separation of v1 summarization from v2 design file generation. |
| D-017 | Old BAML functions | Retire `SummarizeFile`, `SummarizeFilesBatch`, `SummarizeDirectory` — replaced by Archivist functions. Old `LLMService` methods remain but are unused. |
| D-018 | Design file format | YAML frontmatter (agent-facing: description, updated_by) + markdown body + HTML comment footer (machine-facing: hashes, timestamps). Split responsibility. |
| D-019 | Authoring model | Agent-first. Agents write/update design files during coding sessions. `lexi update` is backup — detects stale files where agent forgot and runs Archivist LLM. |
| D-020 | `.lexignore` file | New `.lexignore` file (gitignore format) layered on top of `.gitignore` + `config.ignore.additional_patterns`. Three sources merged. |
| D-021 | Scope root | `scope_root` config (default: project root). Files within scope get design files; files outside appear in `.aindex` only. |
| D-022 | `.aindex` descriptions | File descriptions in `.aindex` Child Map are programmatically extracted from design file YAML frontmatter `description` field. Directory descriptions are written once and not auto-updated (manual `lexi describe` command available). |
| D-023 | `.aindex` update on file change | `lexi update` on a single file also refreshes the parent directory's `.aindex` Child Map entry (pulls description from the design file's frontmatter). |
| D-024 | Content-only changes | Call LLM with a focused prompt: "update summary and description, interface contract unchanged." Still counts as an Archivist update. |
| D-025 | Concurrency | Sequential processing for MVP. Async architecture designed for concurrency from the start (async functions, `ArchivistService` as stateless). Concurrent execution added as future performance optimisation. |
| D-026 | Footer-less design files | If a design file exists but has no metadata footer, treat as `AGENT_UPDATED` (agent authored from scratch). Trust existing content, add footer with current hashes. Do not overwrite via LLM. |
| D-027 | Non-code change level | Non-code files (no interface hash) use `CONTENT_CHANGED` state, not `INTERFACE_CHANGED`. Both trigger full Archivist LLM, but the distinct label avoids implying a non-code file has an "interface." |

---

## Agent-First Authoring Model

The fundamental shift in Phase 4: **the agent writing code is the best author of the design file**, because it has full context of *why* the change was made. The Archivist LLM is a fallback for files agents missed.

### How it works

1. **Agent edits `src/foo.py`** — agent environment rules (Phase 8) instruct it to also update `.lexibrary/src/foo.py.md`
2. **Agent updates the design file directly** — edits the YAML frontmatter `description` and markdown body. Sets `updated_by: agent` in frontmatter.
3. **`lexi update` runs later** (manually, via daemon, or CI) — detects that:
   - Source file hash changed (content_hash differs from footer)
   - Design file *also* changed (its own content differs from what the Archivist last wrote)
   - **Conclusion:** Agent already updated this → trust the agent's version. Only refresh the tracking hashes in the footer.
4. **If the agent forgot** — source changed but design file is stale (footer hashes don't match source, and design file content hasn't changed) → run the Archivist LLM to regenerate.

### Change detection with agent awareness

```
compute_hashes(source_file) → (content_hash, interface_hash)
design_file_path = mirror_path(project_root, source_file)

if design file does not exist:
    → NEW_FILE (run full Archivist LLM)

if design file exists but has no footer (no StalenessMetadata):
    → AGENT_UPDATED (agent authored the file from scratch — trust it, add footer)

read design file footer → StalenessMetadata

if content_hash == footer.source_hash:
    → UNCHANGED (skip)

if design_file_content has changed since last Archivist run:
    → AGENT_UPDATED (refresh hashes only, don't run LLM)

if interface_hash is None:
    → CONTENT_CHANGED (non-code file; run full Archivist LLM — no interface to compare)

if interface_hash == footer.interface_hash:
    → CONTENT_ONLY (run LLM with lightweight prompt)

else:
    → INTERFACE_CHANGED (run full Archivist LLM)
```

To detect "design file content has changed since last Archivist run," the footer includes a `design_hash` field — the hash of the design file content at the time the Archivist (or hash refresh) last wrote it. If the current file content hashes differently, an agent (or human) has edited it.

**Footer-less design files:** If a design file exists but has no metadata footer, an agent (or human) created it directly — before the Archivist ever ran. Rather than treating this as `NEW_FILE` (which would overwrite the agent's work via LLM regeneration), the system treats it as `AGENT_UPDATED`: trust the existing content, add the footer with current hashes, and move on. The Archivist's `existing_design_file` parameter is only used for `NEW_FILE` / `CONTENT_ONLY` / `CONTENT_CHANGED` / `INTERFACE_CHANGED` states where the LLM is called.

---

## `.lexignore` — Dedicated Ignore File

A new `.lexignore` file at the project root, following `.gitignore` format and rules (parsed via `pathspec` with `"gitignore"` pattern name — same as existing ignore infrastructure).

### Three-layer ignore system

| Layer | File | Purpose |
|-------|------|---------|
| 1 | `.gitignore` | Standard git ignores (build output, deps, etc.) |
| 2 | `.lexignore` | Lexibrary-specific ignores (files that exist in git but shouldn't get design files) |
| 3 | `config.ignore.additional_patterns` | Programmatic patterns from `.lexibrary/config.yaml` |

All three are merged by `IgnoreMatcher`. A file ignored by any layer is excluded.

### Typical `.lexignore` content

```gitignore
# Generated code
**/migrations/
**/*_generated.*
**/*.pb.go

# Large data files
data/
*.csv
*.parquet

# Vendored dependencies
vendor/
third_party/
```

### Implementation

Extend `ignore/matcher.py` to load `.lexignore` alongside `.gitignore`. The `IgnoreMatcher` constructor gains a `lexignore_path` parameter. `lexi init` creates an empty `.lexignore` file with a comment header.

---

## Scope Root Configuration

A new `scope_root` field in project config controls which files get design files:

```yaml
# .lexibrary/config.yaml
scope_root: "."  # default: project root (everything gets design files)
# scope_root: "src/"  # only files under src/ get design files
```

### Behaviour

| Location | `.aindex` | Design file |
|----------|-----------|-------------|
| Within `scope_root` | Yes | Yes |
| Outside `scope_root` | Yes (directory listing) | No |

Files outside `scope_root` still appear in `.aindex` Child Map entries (agents can see they exist) but `lexi update` does not generate design files for them, and `lexi lookup` returns "file is outside scope_root."

### Config model addition

```python
class LexibraryConfig(BaseModel):
    # ... existing fields ...
    scope_root: str = "."  # relative to project root
```

---

## Design File Markdown Format

Design files have three sections: YAML frontmatter (agent-editable), markdown body (agent-editable), and HTML comment footer (machine-managed).

### Example output

```markdown
---
description: "Authentication service handling login, logout, and token refresh."
updated_by: archivist  # or "agent"
---

# src/services/auth_service.py

## Interface Contract

` ``python
class AuthService(BaseService):
    def __init__(self, config: AuthConfig) -> None
    def login(self, credentials: Credentials) -> Session
    def logout(self, session_id: str) -> None
    @classmethod
    def from_env(cls) -> AuthService

def authenticate(username: str, password: str) -> bool
def refresh_token(token: str) -> str | None
` ``

## Dependencies

- `src/config/auth_config.py` — AuthConfig model
- `src/models/session.py` — Session dataclass
- `src/db/users.py` — user lookup queries

## Tests

`tests/services/test_auth_service.py`

## Complexity Warning

Legacy token validation uses a hand-rolled JWT parser instead of the
standard library. Do not extend — plan is to migrate to `pyjwt`.

## Wikilinks

- [[Authentication]]
- [[SessionManagement]]

## Tags

auth, security, jwt, login

## Guardrails

- [[GR-001]] Timezone-naive datetimes — use `utils/time.py:now()`

<!-- lexibrary:meta
source: src/services/auth_service.py
source_hash: a3f2b8c1d5e6f7a8
interface_hash: 7e2d4f90b1c3a5d7
design_hash: c4d5e6f7a8b9c0d1
generated: 2026-02-20T10:30:00Z
generator: lexibrary v0.2.0
-->
```

### YAML Frontmatter

```yaml
---
description: "Single sentence summary of what this file does."
updated_by: archivist  # "archivist" or "agent"
---
```

- **`description`** — single sentence, used by `.aindex` Child Map. This is the canonical short description. When `lexi update` refreshes an `.aindex`, it reads this field from each child file's design file.
- **`updated_by`** — who last meaningfully updated the design file body. `"archivist"` when the LLM generated it, `"agent"` when an agent edited it directly. Informational — the hash-based change detection is the actual mechanism, not this field.

Agents are free to edit any part of the markdown body (add notes, update descriptions, fix errors). The frontmatter `description` field is the primary thing agents should keep current — it propagates to `.aindex`.

### HTML Comment Footer (machine-managed)

```html
<!-- lexibrary:meta
source: src/services/auth_service.py
source_hash: a3f2b8c1d5e6f7a8
interface_hash: 7e2d4f90b1c3a5d7
design_hash: c4d5e6f7a8b9c0d1
generated: 2026-02-20T10:30:00Z
generator: lexibrary v0.2.0
-->
```

- **`source_hash`** — SHA-256 of the source file at last update
- **`interface_hash`** — SHA-256 of the interface skeleton (None for non-code files)
- **`design_hash`** — SHA-256 of the design file content (frontmatter + body, excluding the footer itself) at the time the Archivist last wrote or refreshed it. Used to detect agent edits.
- **`generated`** — ISO timestamp of last Archivist write
- **`generator`** — Lexibrary version string

Agents should not edit the footer. The parser reads from the bottom of the file. If the footer is missing (e.g., an agent created the design file from scratch), `lexi update` treats the file as `AGENT_UPDATED` — trusting the existing content and adding the footer with current hashes. If the footer is corrupt (present but unparseable), `lexi update` treats the file as needing full regeneration.

### Format rules

1. YAML frontmatter delimited by `---` at top of file
2. H1 = source file path relative to project root
3. `## Interface Contract` — fenced code block with language tag. For non-code files, prose description.
4. `## Dependencies` — bullet list of dependency paths with brief description. Empty = `(none)`
5. `## Dependents` — bullet list. Empty = `(none)` (populated in Phase 5)
6. `## Tests` — test file path or description. Omitted if `None`.
7. `## Complexity Warning` — prose warning. Omitted if `None`.
8. `## Wikilinks` — bullet list of `[[ConceptName]]` references. Omitted if empty.
9. `## Tags` — comma-separated tags on a single line. Omitted if empty.
10. `## Guardrails` — bullet list of `[[GR-NNN]]` references. Omitted if empty.
11. HTML comment metadata footer at end of file
12. File ends with a trailing newline
13. Optional sections (Tests, Complexity Warning, Wikilinks, Tags, Guardrails) omitted when empty/None.
14. Required sections (Interface Contract, Dependencies, Dependents) always present.

---

## `.aindex` Integration — Description Extraction

`.aindex` Child Map descriptions are no longer generated mechanically (language + line count). Instead:

### For files

The description is pulled from the design file's YAML frontmatter `description` field.

```
.aindex generation for directory:
  for each file in directory:
    if design file exists at mirror_path(file):
      description = parse frontmatter "description" field
    else:
      description = structural fallback: "{Language} source ({N} lines)"
```

This means `.aindex` accuracy improves as design files are created. Before any design files exist, the structural fallback from Phase 2 still works.

### For directories

Directory descriptions (the billboard in `.aindex`) are **written once** — typically when the directory is first indexed or created. They are not auto-regenerated on `lexi update` because a directory's purpose shouldn't change frequently.

If an agent needs to update a directory description, a manual command is available:

```
lexi describe <directory> "New description of this directory's purpose"
```

This updates the billboard in the `.aindex` for that directory.

### `.aindex` refresh during `lexi update`

When `lexi update` processes a file, it also refreshes the parent directory's `.aindex`:
1. Re-read the parent `.aindex` (parse it)
2. Update the Child Map entry for the changed file with the new `description` from the design file frontmatter
3. If a new file was added (not in Child Map), add it
4. Re-serialize and write the `.aindex`

This keeps `.aindex` descriptions in sync with design files without requiring a separate `lexi index` run.

---

## Pipeline Overview

```
lexi update [<path>]
  │
  ├─ Single file path ─────────────────────────────────────┐
  │                                                         │
  └─ No path (or directory) ──→ discover source files       │
     within scope_root ──→ for each file: ──────────────────┤
                                                            ▼
                                                 ┌──────────────────┐
                                                 │ compute_hashes() │
                                                 │ (Phase 3)        │
                                                 └────────┬─────────┘
                                                          ▼
                                               ┌────────────────────┐
                                               │ Check design file  │
                                               │ existence + footer │
                                               └────────┬───────────┘
                                                        ▼
                                            ┌───────────────────────┐
                                            │ no design file ───────┼─→ NEW_FILE
                                            │                       │   (full Archivist)
                                            │ file exists, no ──────┼─→ AGENT_UPDATED
                                            │ footer (agent-        │   (trust content,
                                            │ authored)             │    add footer)
                                            └────────┬──────────────┘
                                                     ▼ (has footer)
                                            ┌───────────────────────┐
                                            │ Compare hashes:       │
                                            │                       │
                                            │ content unchanged ────┼─→ skip (up to date)
                                            │                       │
                                            │ design file edited ───┼─→ AGENT_UPDATED
                                            │ (design_hash differs) │   (refresh footer
                                            │                       │    hashes only)
                                            │                       │
                                            │ non-code file ────────┼─→ CONTENT_CHANGED
                                            │ (no interface hash)   │   (full Archivist)
                                            │                       │
                                            │ interface unchanged ──┼─→ CONTENT_ONLY
                                            │ (content changed)     │   (LLM lightweight)
                                            │                       │
                                            │ interface changed ────┼─→ INTERFACE_CHANGED
                                            │ (or new file)         │   (full Archivist)
                                            └───────────────────────┘
                                                        ▼
                                              ┌───────────────────┐
                                              │ parse_interface()  │
                                              │ + read source      │
                                              └────────┬──────────┘
                                                       ▼
                                             ┌──────────────────┐
                                             │ BAML Archivist   │
                                             │ LLM call         │
                                             └────────┬─────────┘
                                                      ▼
                                            ┌───────────────────┐
                                            │ Validate token    │
                                            │ budget            │
                                            └────────┬──────────┘
                                                     ▼
                                           ┌──────────────────────┐
                                           │ serialize_design_file│
                                           │ + write_artifact     │
                                           └────────┬─────────────┘
                                                    ▼
                                           ┌──────────────────────┐
                                           │ Refresh parent       │
                                           │ .aindex Child Map    │
                                           └──────────────────────┘
```

For non-code files (no tree-sitter grammar): `interface_hash` is always `None`. Any content change where the agent hasn't updated the design file is classified as `CONTENT_CHANGED` (not `INTERFACE_CHANGED`) and triggers full Archivist generation. Both states result in the same LLM call, but the distinct label avoids the misleading implication that a YAML or markdown file has an "interface" that changed.

---

## BAML Changes

### New types (`baml_src/types.baml`)

```
class DesignFileOutput {
  summary string
  interface_contract string
  dependencies DesignFileDependency[]
  tests string?
  complexity_warning string?
  wikilinks string[]
  tags string[]
}

class DesignFileDependency {
  path string
  description string
}

class StartHereOutput {
  topology string
  ontology string
  navigation_by_intent string
  convention_index string
  navigation_protocol string
}
```

### New functions

**`baml_src/archivist_design_file.baml`:**

```
function ArchivistGenerateDesignFile(
  source_path: string,
  source_content: string,
  interface_skeleton: string?,
  language: string?,
  existing_design_file: string?
) -> DesignFileOutput
```

Prompt guidance (key points for the system prompt):
- Describe *why*, not *what* — the code itself shows what it does
- The `summary` field becomes the frontmatter `description` — keep it to a single sentence
- Flag edge cases, dragons, and non-obvious behaviour
- Respect the token budget — if the source file is very large, summarise rather than enumerate
- When updating an existing design file, preserve relevant human/agent-added context
- Dependencies should be actual import paths observed in the source, not inferred
- Wikilinks should reference concepts that would help an agent understand this file's role in the broader system
- Tags should be 3-7 short lowercase labels useful for searching

**`baml_src/archivist_start_here.baml`:**

```
function ArchivistGenerateStartHere(
  project_name: string,
  directory_tree: string,
  aindex_summaries: string,
  existing_start_here: string?
) -> StartHereOutput
```

Prompt guidance:
- Keep total output under 500-800 tokens
- Topology: Mermaid diagram or ASCII tree of the top-level structure
- Ontology: 5-15 key domain terms with one-line definitions
- Navigation by Intent: task-oriented routing table mapping agent goals to library entry points
- Convention Index: compact list of convention names with one-line descriptions
- Navigation Protocol: 3-5 bullet instructions on how to use the library

### Client configuration

**`baml_src/clients.baml` updates:**

Replace the single `PrimaryClient` with named clients per provider, and increase `max_tokens` for Archivist functions (design files need more output than v1's 1-2 sentence summaries):

```
client<llm> AnthropicArchivist {
  provider anthropic
  retry_policy DefaultRetry
  options {
    model "claude-sonnet-4-6"
    api_key env.ANTHROPIC_API_KEY
    max_tokens 1500
  }
}

client<llm> OpenAIArchivist {
  provider openai
  retry_policy DefaultRetry
  options {
    model "gpt-5-nano"
    api_key env.OPENAI_API_KEY
    max_completion_tokens 1500
  }
}
```

The archivist service will use BAML's client override mechanism (`ClientRegistry`) at runtime to route to the correct provider based on `LLMConfig.provider`. This avoids hardcoding the client in the BAML function definition.

**Spike needed (Task 4.2):** Verify BAML's `ClientRegistry` Python API supports runtime client override for individual function calls. If not, fall back to defining the function with a default client and accepting that the provider is set at BAML definition time (configured via env vars).

---

## Import/Dependency Extraction

Phase 4 extracts forward dependencies from source files to populate the `dependencies` field of design files. This is separate from Phase 3's interface extraction — imports are not part of the "public API" skeleton.

### Approach

Use tree-sitter to extract import statements:

| Language | Node types |
|----------|------------|
| Python | `import_statement`, `import_from_statement` |
| TypeScript/JavaScript | `import_statement`, `import_clause` |

For non-code files (no grammar): dependencies are empty. The LLM may suggest dependencies in its output, but these are treated as advisory — only AST-extracted imports are authoritative.

### Resolution

Raw import paths (e.g., `from lexibrary.config.schema import LexibraryConfig`) are resolved to relative file paths within the project (e.g., `src/lexibrary/config/schema.py`). Third-party imports (packages not in the project) are excluded from the dependency list.

Resolution strategy:
1. For Python: convert dotted module path to file path, check if it exists under project root
2. For TypeScript/JavaScript: resolve relative imports (`./ ../`), skip bare specifiers (npm packages)
3. If resolution fails, omit the import (don't include unresolvable paths)

This is a best-effort extraction. The LLM's dependency section may include additional context the AST can't capture.

---

## START_HERE.md Generation

START_HERE.md is a special artifact — it's not a per-file design file but a project-level synthesis.

### Pipeline

```
lexi update (no path, or explicit --start-here flag)
  → collect all .aindex summaries from .lexibrary/ mirror tree
  → build directory tree string from project structure
  → call ArchivistGenerateStartHere(project_name, directory_tree, aindex_summaries, existing?)
  → validate against token budget (start_here_tokens: 800)
  → write to .lexibrary/START_HERE.md
```

### When to regenerate

START_HERE.md is regenerated when:
- `lexi update` runs without a specific path (full project update)
- Explicitly requested (future: `lexi update --start-here`)
- The set of top-level directories has changed since last generation

It is NOT regenerated on every single file update — it's a project-level summary that changes infrequently.

### HANDOFF.md

HANDOFF.md is NOT generated by the Archivist. It is written by agents during their sessions. `lexi init` creates a placeholder, and that's it. `lexi validate` (Phase 7) checks its token budget.

---

## Module Structure

```
src/lexibrary/archivist/
├── __init__.py              # Public API: update_file(), update_project(), lookup()
├── change_checker.py        # Compare hashes against existing design file metadata
├── dependency_extractor.py  # AST-based import extraction → resolved file paths
├── pipeline.py              # Orchestrate: hash check → AST → LLM → serialize → write → refresh .aindex
├── service.py               # ArchivistService — wraps BAML calls with rate limiting
└── start_here.py            # START_HERE.md generation pipeline

src/lexibrary/artifacts/
├── design_file.py             # Updated: DesignFile model + DesignFileFrontmatter model
├── design_file_serializer.py  # serialize_design_file(DesignFile) -> str (with YAML frontmatter)
└── design_file_parser.py      # parse_design_file(), parse_design_file_metadata(), parse_design_file_frontmatter()

src/lexibrary/ignore/
└── matcher.py                 # Updated: load .lexignore alongside .gitignore

baml_src/
├── archivist_design_file.baml  # ArchivistGenerateDesignFile function + prompt
├── archivist_start_here.baml   # ArchivistGenerateStartHere function + prompt
├── types.baml                  # Updated with DesignFileOutput, StartHereOutput, etc.
└── clients.baml                # Updated with per-provider Archivist clients

tests/test_archivist/
├── __init__.py
├── test_change_checker.py
├── test_dependency_extractor.py
├── test_pipeline.py
├── test_service.py              # Mocked BAML calls
├── test_start_here.py
└── fixtures/
    ├── sample_source.py
    ├── sample_source.ts
    ├── sample_config.yaml        # non-code file
    └── expected_design_file.md

tests/test_artifacts/
├── test_design_file_serializer.py
├── test_design_file_parser.py
└── test_design_file_roundtrip.py
```

---

## Implementation Tasks

### 4.1 Design file model update, serializer, and parser

**Files:**
- `src/lexibrary/artifacts/design_file.py` — add `DesignFileFrontmatter` model, add `design_hash` to `StalenessMetadata`
- `src/lexibrary/artifacts/design_file_serializer.py` — new
- `src/lexibrary/artifacts/design_file_parser.py` — new

**Model updates:**

```python
class DesignFileFrontmatter(BaseModel):
    """YAML frontmatter for a design file — agent-editable fields."""
    description: str
    updated_by: Literal["archivist", "agent"] = "archivist"

class StalenessMetadata(BaseModel):
    """Metadata in HTML comment footer — machine-managed."""
    source: str
    source_hash: str
    interface_hash: str | None = None
    design_hash: str  # hash of design file content (frontmatter + body, excluding footer)
    generated: datetime
    generator: str

class DesignFile(BaseModel):
    """Represents a design file artifact for a single source file."""
    source_path: str
    frontmatter: DesignFileFrontmatter
    # ... rest of existing fields ...
    metadata: StalenessMetadata
```

**`design_file_serializer.py`:**

```python
def serialize_design_file(data: DesignFile) -> str:
    """Serialize a DesignFile model to markdown with YAML frontmatter and metadata footer."""
```

Emits: `---\n{yaml frontmatter}\n---\n\n{markdown body}\n\n{html comment footer}\n`

**`design_file_parser.py`:**

```python
def parse_design_file(path: Path) -> DesignFile | None:
    """Parse an existing design file into a DesignFile model.
    Returns None if file doesn't exist or is malformed.
    """

def parse_design_file_metadata(path: Path) -> StalenessMetadata | None:
    """Parse only the metadata footer from a design file.
    Reads from end of file — cheap, used for change detection.
    """

def parse_design_file_frontmatter(path: Path) -> DesignFileFrontmatter | None:
    """Parse only the YAML frontmatter from a design file.
    Used by .aindex generation to extract descriptions.
    """
```

**Tests:** `tests/test_artifacts/test_design_file_serializer.py`, `test_design_file_parser.py`, `test_design_file_roundtrip.py`

| Test | Verifies |
|------|----------|
| `test_serialize_full` | YAML frontmatter + all sections + footer for fully populated DesignFile |
| `test_serialize_minimal` | Optional sections omitted when empty/None |
| `test_serialize_frontmatter` | YAML frontmatter correctly formatted with description and updated_by |
| `test_serialize_metadata_footer` | HTML comment footer includes design_hash |
| `test_parse_full` | Parses well-formed design file into correct DesignFile model |
| `test_parse_frontmatter_only` | `parse_design_file_frontmatter` extracts description |
| `test_parse_metadata_only` | `parse_design_file_metadata` extracts footer without full parse |
| `test_parse_nonexistent` | Returns None for missing file |
| `test_roundtrip` | serialize → write → parse produces identical DesignFile |
| `test_roundtrip_with_optional_sections` | All optional sections survive round-trip |
| `test_agent_edited_body_detected` | design_hash mismatch detected after body edit |

---

### 4.2 BAML function definitions and client configuration spike

**Files:**
- `baml_src/types.baml` — add `DesignFileOutput`, `DesignFileDependency`, `StartHereOutput`
- `baml_src/archivist_design_file.baml` — `ArchivistGenerateDesignFile` function + prompt
- `baml_src/archivist_start_here.baml` — `ArchivistGenerateStartHere` function + prompt
- `baml_src/clients.baml` — add per-provider Archivist clients, increase max_tokens

**Spike: BAML ClientRegistry runtime override**

Before writing the BAML functions, verify:
1. Can BAML's Python `ClientRegistry` API override which client a function uses at call time?
2. If yes, what's the API? (`b.ArchivistGenerateDesignFile(..., baml_options={"client_registry": ...})`?)
3. If not, what's the fallback? (env var switching, or defining separate functions per provider)

**Outcome determines:** How `archivist/service.py` selects the LLM provider at runtime.

After the spike, write the BAML functions and run `baml-cli generate` to regenerate `baml_client/`.

**Tests:** BAML functions are tested indirectly via `test_service.py` (mocked) and integration tests.

---

### 4.3 `.lexignore` support and scope root config

**Files:**
- `src/lexibrary/ignore/matcher.py` — load `.lexignore`
- `src/lexibrary/config/schema.py` — add `scope_root` to `LexibraryConfig`, add `max_file_size_kb` to `CrawlConfig` (planned in D-005 but not yet implemented)
- `src/lexibrary/config/defaults.py` — update default config template
- `src/lexibrary/init/scaffolder.py` — create empty `.lexignore` on `lexi init`

**IgnoreMatcher update:**

```python
class IgnoreMatcher:
    def __init__(
        self,
        project_root: Path,
        gitignore_patterns: list[str],
        lexignore_patterns: list[str],  # NEW
        additional_patterns: list[str],
    ) -> None
```

New factory helper:

```python
def create_ignore_matcher(config: LexibraryConfig, project_root: Path) -> IgnoreMatcher:
    """Create matcher from .gitignore + .lexignore + config patterns."""
```

**Tests:** `tests/test_ignore/test_matcher.py`

| Test | Verifies |
|------|----------|
| `test_lexignore_loaded` | Patterns from `.lexignore` are applied |
| `test_lexignore_missing_ok` | No error if `.lexignore` doesn't exist |
| `test_three_layer_merge` | All three ignore sources combined correctly |
| `test_scope_root_config` | `scope_root` correctly parsed from config |

---

### 4.4 Change checker (with agent-awareness)

**File:** `src/lexibrary/archivist/change_checker.py`

```python
from enum import Enum

class ChangeLevel(Enum):
    UNCHANGED = "unchanged"
    AGENT_UPDATED = "agent_updated"
    CONTENT_ONLY = "content_only"
    CONTENT_CHANGED = "content_changed"  # non-code files (no interface to compare)
    INTERFACE_CHANGED = "interface_changed"
    NEW_FILE = "new_file"

def check_change(
    source_path: Path,
    project_root: Path,
    content_hash: str,
    interface_hash: str | None,
) -> ChangeLevel:
    """Compare current hashes against existing design file metadata.

    Detects whether an agent has already updated the design file,
    avoiding unnecessary LLM regeneration.
    """
```

Logic:
1. Compute `mirror_path(project_root, source_path)` to find existing design file
2. If design file does not exist → `NEW_FILE`
3. If design file exists but has no footer (no `StalenessMetadata`) → `AGENT_UPDATED` (agent authored the file from scratch — trust it, add footer with current hashes)
4. Call `parse_design_file_metadata(design_file_path)` → `StalenessMetadata`
5. If `content_hash == existing.source_hash` → `UNCHANGED`
6. Hash the current design file content (frontmatter + body, excluding footer)
7. If current design content hash != `existing.design_hash` → `AGENT_UPDATED` (agent edited it)
8. If `interface_hash is None` → `CONTENT_CHANGED` (non-code file, no interface to compare)
9. If `interface_hash == existing.interface_hash` → `CONTENT_ONLY`
10. Otherwise → `INTERFACE_CHANGED`

`CONTENT_CHANGED` and `INTERFACE_CHANGED` both trigger full Archivist LLM generation — the distinct label avoids the misleading implication that a non-code file has an "interface."

**Footer-less design files (step 3):** This handles the case where an agent creates a design file directly before any Archivist run. Without this check, the file would be treated as `NEW_FILE` and overwritten by LLM regeneration — destroying the agent's work. Instead, the system trusts the agent's content and adds the footer.

**Tests:** `tests/test_archivist/test_change_checker.py`

| Test | Verifies |
|------|----------|
| `test_new_file` | No existing design file → `NEW_FILE` |
| `test_footerless_design_file` | Design file exists but has no metadata footer → `AGENT_UPDATED` (trust agent, add footer) |
| `test_unchanged` | Same content hash → `UNCHANGED` |
| `test_agent_updated` | Source changed, design file also edited → `AGENT_UPDATED` |
| `test_content_only_change` | Content hash differs, interface hash same, design file not edited → `CONTENT_ONLY` |
| `test_interface_changed` | Both hashes differ, design file not edited → `INTERFACE_CHANGED` |
| `test_content_changed_non_code` | Non-code file with content change, design not edited → `CONTENT_CHANGED` |

---

### 4.5 Dependency extractor

**File:** `src/lexibrary/archivist/dependency_extractor.py`

```python
def extract_dependencies(
    file_path: Path,
    project_root: Path,
) -> list[str]:
    """Extract forward dependencies from a source file.

    Uses tree-sitter to find import statements and resolves them
    to relative file paths within the project. Third-party imports
    are excluded.

    Returns list of relative paths (e.g., ["src/config/schema.py"]).
    """
```

For non-code files (no grammar): returns empty list.

**Resolution helpers:**

```python
def _resolve_python_import(module_path: str, project_root: Path) -> str | None:
    """Resolve 'lexibrary.config.schema' → 'src/lexibrary/config/schema.py'."""

def _resolve_js_import(import_path: str, source_dir: Path, project_root: Path) -> str | None:
    """Resolve './schema' → 'src/config/schema.ts' (tries .ts, .js, /index.ts, etc.)."""
```

**Tests:** `tests/test_archivist/test_dependency_extractor.py`

| Test | Verifies |
|------|----------|
| `test_python_imports` | Extracts and resolves Python imports |
| `test_python_relative_import` | Resolves `from .module import X` |
| `test_python_third_party_excluded` | `import requests` not in results |
| `test_typescript_imports` | Resolves `import { X } from './module'` |
| `test_javascript_imports` | Resolves JS imports |
| `test_non_code_file` | Returns empty list for `.yaml`, `.md`, etc. |
| `test_unresolvable_import` | Gracefully omits imports that can't be resolved |

---

### 4.6 Archivist service

**Depends on:** Task 4.2 (BAML spike determines client routing pattern used here)

**File:** `src/lexibrary/archivist/service.py`

```python
@dataclass
class DesignFileRequest:
    source_path: str
    source_content: str
    interface_skeleton: str | None
    language: str | None
    existing_design_file: str | None

@dataclass
class DesignFileResult:
    source_path: str
    design_file_output: DesignFileOutput | None
    error: bool = False
    error_message: str | None = None

class ArchivistService:
    def __init__(self, rate_limiter: RateLimiter, config: LLMConfig) -> None

    async def generate_design_file(self, request: DesignFileRequest) -> DesignFileResult:
        """Call BAML ArchivistGenerateDesignFile with rate limiting."""

    async def generate_start_here(self, request: StartHereRequest) -> StartHereResult:
        """Call BAML ArchivistGenerateStartHere with rate limiting."""
```

The service handles:
- Rate limiting via existing `RateLimiter`
- BAML client selection based on `LLMConfig.provider` (using the pattern determined by the Task 4.2 spike)
- Error handling and fallback (returns `error=True` on LLM failure)
- Logging

**Tests:** `tests/test_archivist/test_service.py` — mock the BAML client, test rate limiting, error handling.

---

### 4.7 Archivist pipeline (orchestrator)

**Depends on:** Tasks 4.1 (models/serializer/parser), 4.3 (.lexignore/scope_root), 4.4 (change checker), 4.5 (dependency extractor), 4.6 (Archivist service)

**File:** `src/lexibrary/archivist/pipeline.py`

```python
@dataclass
class UpdateStats:
    files_scanned: int = 0
    files_unchanged: int = 0
    files_agent_updated: int = 0
    files_updated: int = 0
    files_created: int = 0
    files_failed: int = 0
    aindex_refreshed: int = 0
    token_budget_warnings: int = 0

async def update_file(
    source_path: Path,
    project_root: Path,
    config: LexibraryConfig,
    archivist: ArchivistService,
) -> ChangeLevel:
    """Generate or update the design file for a single source file.
    Also refreshes the parent directory's .aindex Child Map entry.
    """

async def update_project(
    project_root: Path,
    config: LexibraryConfig,
    archivist: ArchivistService,
    *,
    progress_callback: Callable[[str, int, int], None] | None = None,
) -> UpdateStats:
    """Update all design files for the project.

    Discovers all source files within scope_root, checks each for changes,
    generates/updates design files as needed.
    Also regenerates START_HERE.md.
    """
```

**`update_file` pipeline:**
1. Check `scope_root` — if file is outside scope, skip
2. `compute_hashes(source_path)` → `(content_hash, interface_hash)`
3. `check_change(source_path, project_root, content_hash, interface_hash)` → `ChangeLevel`
4. If `UNCHANGED` → return early
5. If `AGENT_UPDATED` → refresh footer hashes only (no LLM call), go to step 12. This includes both "agent edited an existing design file" and "agent created a footer-less design file from scratch."
6. `parse_interface(source_path)` → `InterfaceSkeleton | None`
7. Read source file content
8. Read existing design file content (if exists, for continuity)
9. `render_skeleton(skeleton)` → readable interface text (if skeleton exists)
10. `extract_dependencies(source_path, project_root)` → `list[str]`
11. `archivist.generate_design_file(request)` → `DesignFileResult`
12. Build `DesignFile` model from result + dependencies + metadata (including `design_hash`)
13. Validate token budget (`config.token_budgets.design_file_tokens`)
14. `serialize_design_file(design_file)` → markdown string
15. `write_artifact(mirror_path(project_root, source_path), markdown)`
16. **Refresh parent `.aindex`:** parse parent's `.aindex`, update Child Map entry for this file with frontmatter `description`, re-serialize and write

**`update_project` pipeline:**
1. Create `IgnoreMatcher` from config (includes `.lexignore`)
2. Discover all source files within `scope_root` using `discover_directories_bottom_up()` + `list_directory_files()`
3. Filter: skip files in `.lexibrary/`, skip binary files, skip files outside `scope_root`
4. For each file: call `update_file()` (sequential)
5. After all files: call `generate_start_here()` (Task 4.8)
6. Return `UpdateStats`

**Token budget validation:**

After the LLM generates a design file, count tokens using the configured tokenizer backend. If the design file exceeds `config.token_budgets.design_file_tokens`:
- Log a warning: "Design file for {path} exceeds token budget ({actual} > {target}) — source file may be over-scoped"
- Still write the file (don't discard work)
- Increment `token_budget_warnings` counter in stats

**Tests:** `tests/test_archivist/test_pipeline.py`

| Test | Verifies |
|------|----------|
| `test_update_file_new` | Creates design file for file with no existing one |
| `test_update_file_unchanged` | Skips file when content hash matches |
| `test_update_file_agent_updated` | Refreshes footer hashes only, no LLM call |
| `test_update_file_footerless_agent_authored` | Agent-created design file without footer → adds footer, no LLM call |
| `test_update_file_content_only` | Calls LLM with lightweight prompt |
| `test_update_file_content_changed_non_code` | Full regeneration for non-code file content change |
| `test_update_file_interface_changed` | Full regeneration on interface change |
| `test_update_file_outside_scope` | Skips file outside scope_root |
| `test_update_file_refreshes_aindex` | Parent .aindex Child Map updated with new description |
| `test_update_project_discovers_files` | Scans files within scope_root |
| `test_update_project_skips_binary` | Binary files not processed |
| `test_update_project_skips_lexibrary` | `.lexibrary/` contents not indexed |
| `test_update_project_stats` | Stats correctly track counts including agent_updated |
| `test_token_budget_warning` | Warning logged for oversized design file |

---

### 4.8 START_HERE.md generation

**File:** `src/lexibrary/archivist/start_here.py`

```python
async def generate_start_here(
    project_root: Path,
    config: LexibraryConfig,
    archivist: ArchivistService,
) -> Path:
    """Generate or update .lexibrary/START_HERE.md from project topology."""
```

Pipeline:
1. Build directory tree string from project structure (exclude `.lexibrary/`, ignored dirs)
2. Collect all `.aindex` billboard summaries from `.lexibrary/` mirror tree
3. Read existing `START_HERE.md` (if exists, for continuity)
4. Call `archivist.generate_start_here()`
5. Assemble final markdown from `StartHereOutput` sections
6. Validate token budget (`config.token_budgets.start_here_tokens`)
7. `write_artifact(.lexibrary/START_HERE.md, content)`

**Tests:** `tests/test_archivist/test_start_here.py`

| Test | Verifies |
|------|----------|
| `test_generate_start_here` | Produces well-formed START_HERE.md |
| `test_collects_aindex_summaries` | Reads billboard from each .aindex |
| `test_excludes_lexibrary_dir` | .lexibrary/ not in directory tree |
| `test_token_budget` | Warns if output exceeds budget |

---

### 4.9 Wire `lexi update` and `lexi lookup` CLI commands

**File:** `src/lexibrary/cli.py`

**`lexi update`:**

```python
@app.command()
def update(
    path: Annotated[
        Path | None,
        typer.Argument(help="File or directory to update (default: entire project)"),
    ] = None,
) -> None:
    """Generate or refresh design files for changed source files."""
```

Behaviour:
- `_require_project_root()`
- If `path` is a file → `asyncio.run(update_file(path, ...))`
- If `path` is a directory → discover files in that subtree within scope_root, update each
- If no path → `asyncio.run(update_project(project_root, ...))`
- Rich progress bar for multi-file updates
- Print summary stats on completion (including agent-updated count)
- Exit code 0 on success, 1 on any failures

**`lexi lookup`:**

```python
@app.command()
def lookup(
    file: Annotated[Path, typer.Argument(help="Source file to look up")],
) -> None:
    """Return the design file for a source file."""
```

Behaviour:
- `_require_project_root()`
- Check scope: if file is outside `scope_root`, print message and exit
- Compute `mirror_path(project_root, file)`
- If design file exists → read and print its content via `Console`
- If design file doesn't exist → print message suggesting `lexi update <file>` to generate it
- Check staleness: compare `source_hash` in metadata footer with current file hash. If stale, print a warning before the content.

**`lexi describe` (new command):**

```python
@app.command()
def describe(
    directory: Annotated[Path, typer.Argument(help="Directory to describe")],
    description: Annotated[str, typer.Argument(help="New description for the directory")],
) -> None:
    """Update the billboard description in a directory's .aindex file."""
```

Behaviour:
- `_require_project_root()`
- Parse existing `.aindex` for the directory
- Update the billboard text
- Re-serialize and write

**Tests:** `tests/test_cli.py`

| Test | Verifies |
|------|----------|
| `test_update_single_file` | `lexi update src/foo.py` updates one file |
| `test_update_directory` | `lexi update src/` updates files in subtree |
| `test_update_project` | `lexi update` (no arg) updates all files |
| `test_update_no_project` | Error when no `.lexibrary/` found |
| `test_lookup_exists` | Prints design file content |
| `test_lookup_missing` | Suggests running `lexi update` |
| `test_lookup_stale` | Shows staleness warning |
| `test_lookup_outside_scope` | Message when file is outside scope_root |
| `test_describe_directory` | Updates .aindex billboard |

---

### 4.10 Update `.aindex` generation to use frontmatter descriptions

**File:** `src/lexibrary/indexer/generator.py`

Update `generate_aindex()` so that when building the Child Map description for a file:
1. Check if a design file exists at `mirror_path(project_root, file)`
2. If yes → call `parse_design_file_frontmatter(design_file_path)` → use `description` field
3. If no → fall back to structural description: `"{Language} source ({N} lines)"`

This makes `.aindex` descriptions richer as design files are created, while maintaining backwards compatibility when they don't exist yet.

**Tests:** `tests/test_indexer/test_generator.py`

| Test | Verifies |
|------|----------|
| `test_generate_uses_frontmatter_description` | File with design file → description from frontmatter |
| `test_generate_falls_back_to_structural` | File without design file → structural description |

---

### 4.11 Update blueprints

Create design files in `blueprints/src/lexibrary/archivist/` for all new modules, and update existing blueprints for modified files (`cli.py`, `artifacts/`, `ignore/`, `indexer/`, `config/`).

---

## Config Changes

### `LexibraryConfig` additions

```python
class CrawlConfig(BaseModel):
    binary_extensions: list[str] = [...]
    max_file_size_kb: int = 512  # skip files larger than this

class LexibraryConfig(BaseModel):
    # ... existing fields ...
    scope_root: str = "."  # relative to project root; files within this path get design files
```

Update `defaults.py` config template:

```yaml
# Scope root — files within this path get design files.
# Files outside appear in .aindex but don't get design files.
scope_root: "."

# Crawl settings
crawl:
  max_file_size_kb: 512
```

Files exceeding `max_file_size_kb` are skipped during `update_project` with a log warning.

---

## Task Ordering

```
4.1  Design file model/serializer/parser ───────┐
                                                 │
4.2  BAML functions + client spike ──────────────┤
                                                 ├─→ 4.6 Archivist service ──→ 4.7 Pipeline ──→ 4.9 CLI
4.3  .lexignore + scope_root config ─────────────┤                                  │              │
                                                 │                                  │              ├─→ 4.10 .aindex integration
4.4  Change checker ─────────────────────────────┤                                  │
                                                 │                                  └─→ 4.8 START_HERE.md
4.5  Dependency extractor ───────────────────────┘
                                                                                    4.11 Blueprints (last)
```

Tasks 4.1–4.5 are independent and can be implemented in parallel. Task 4.6 depends on 4.2 (BAML). Task 4.7 depends on 4.1, 4.3, 4.4, 4.5, 4.6. Tasks 4.9 and 4.10 depend on 4.7. Task 4.8 depends on 4.6. Task 4.11 runs after everything else.

---

## Acceptance Criteria

- [ ] `DesignFile` model includes `DesignFileFrontmatter` with `description` and `updated_by`
- [ ] `StalenessMetadata` includes `design_hash` field
- [ ] `serialize_design_file()` produces YAML frontmatter + markdown body + HTML comment footer
- [ ] `parse_design_file()` correctly extracts frontmatter, body, and footer
- [ ] `parse_design_file_frontmatter()` extracts description efficiently
- [ ] `parse_design_file_metadata()` extracts footer without full file parse
- [ ] Round-trip test: serialize → write → parse → compare passes
- [ ] `.lexignore` file loaded by `IgnoreMatcher` alongside `.gitignore` and config patterns
- [ ] `lexi init` creates empty `.lexignore` with comment header
- [ ] `scope_root` config respected — files outside scope don't get design files
- [ ] Files outside `scope_root` still appear in `.aindex` Child Map
- [ ] BAML `ArchivistGenerateDesignFile` function defined with working prompt
- [ ] BAML `ArchivistGenerateStartHere` function defined with working prompt
- [ ] BAML client routing works based on `LLMConfig.provider` config
- [ ] `check_change()` correctly classifies UNCHANGED / AGENT_UPDATED / CONTENT_ONLY / CONTENT_CHANGED / INTERFACE_CHANGED / NEW_FILE
- [ ] Agent-edited design files detected via `design_hash` — footer hashes refreshed without LLM call
- [ ] Footer-less design files (agent-authored from scratch) detected and treated as `AGENT_UPDATED`, not `NEW_FILE`
- [ ] `extract_dependencies()` resolves Python imports to project-relative paths
- [ ] `extract_dependencies()` resolves TypeScript/JavaScript relative imports
- [ ] Third-party imports excluded from dependency list
- [ ] `ArchivistService.generate_design_file()` calls BAML with rate limiting
- [ ] `update_file()` skips unchanged files, trusts agent updates, regenerates on interface change
- [ ] `update_file()` refreshes parent `.aindex` Child Map entry with frontmatter description
- [ ] `update_project()` discovers and processes all source files within scope_root
- [ ] Token budget validation warns on oversized design files
- [ ] Binary files and `.lexibrary/` contents are skipped
- [ ] `lexi update src/foo.py` generates a design file at `.lexibrary/src/foo.py.md`
- [ ] `lexi update` (no args) updates all changed files and regenerates START_HERE.md
- [ ] `lexi lookup src/foo.py` prints the design file content
- [ ] `lexi lookup` shows staleness warning when source has changed
- [ ] `lexi lookup` indicates when file is outside scope_root
- [ ] `lexi describe <dir> "description"` updates `.aindex` billboard
- [ ] `.aindex` Child Map descriptions pulled from design file frontmatter when available
- [ ] `.aindex` falls back to structural description when no design file exists
- [ ] Non-code files (YAML, markdown, etc.) get design files with content-only change detection
- [ ] START_HERE.md generated from project topology and .aindex summaries
- [ ] All tests pass: `uv run pytest tests/ -v`
- [ ] Linting passes: `uv run ruff check src/ tests/`
- [ ] Type checking passes: `uv run mypy src/`
- [ ] Blueprints updated for all new and modified modules

---

## What This Phase Does NOT Do

- **No reverse dependency index** — `dependents` field is always empty. Phase 5 builds the reverse index.
- **No wikilink resolution** — wikilinks are suggested by the LLM but not validated. Phase 5 handles resolution.
- **No guardrail cross-references** — `guardrail_refs` is always empty. Phase 6 populates this.
- **No validation** — `lexi validate` remains a stub. Phase 7 implements consistency checks.
- **No daemon integration** — `lexi daemon` remains a stub. Phase 9 wires file watching to `update_file()`.
- **No HANDOFF.md generation** — HANDOFF.md is agent-written, not Archivist-generated.
- **No grouped/abridged mapping strategies** — all in-scope files get 1:1 design files. Mapping strategy config is a future enhancement.
- **No concurrent processing** — sequential file updates for MVP. Async architecture is designed for concurrency from the start (async functions, stateless service), but concurrent execution is a future optimisation. **First-run `lexi update` on a large project may take 10–30 minutes** due to sequential LLM calls; subsequent runs are fast (most files `UNCHANGED`).

---

## Concerns and Risks

### Concern: Agent-first model depends on Phase 8 rule ordering

**Severity:** High — if Phase 8 rules are ambiguous, agents default to `lexi update` as the primary path.

The agent-first authoring model only works if agents update design files *directly* before `lexi update` runs. If Phase 8 agent environment rules say "run `lexi update` after making changes" without clearly emphasising "update the design file first," agents will reach for `lexi update` as the primary path — defeating the agent-first model and incurring unnecessary LLM costs.

**Phase 8 rules must be explicit about the workflow order:**
1. Agent edits source file
2. Agent updates the corresponding design file directly (frontmatter `description` + body)
3. `lexi update` runs later as a safety net — not as a replacement for step 2

Before Phase 8 is implemented, `lexi update` is the primary (and only) path. The agent-first model is latent in Phase 4 and activated by Phase 8.

### Concern: BAML ClientRegistry API uncertainty

**Severity:** Potentially blocking Task 4.6.

The plan assumes BAML supports runtime client override via `ClientRegistry`. If this doesn't work as expected, the fallback is:
- Define the BAML function with a default client (e.g., `AnthropicArchivist`)
- Use environment variables to switch providers
- Accept that provider switching requires env var changes rather than pure config

The Task 4.2 spike resolves this before implementation proceeds.

### Concern: Agent edit detection via design_hash

**Severity:** Low — the mechanism is straightforward.

The `design_hash` in the footer is the hash of the design file content (frontmatter + body, excluding the footer itself) at the time the Archivist last wrote it. If an agent edits the body or frontmatter, the hash of the current content will differ from `design_hash`, signalling `AGENT_UPDATED`.

Edge case: an agent edits the design file AND the Archivist runs before the source file changes. The Archivist would see `UNCHANGED` (source hash matches) and skip — correct behaviour, the agent's edits are preserved.

Edge case: an agent makes a trivial whitespace edit. This would still be detected as `AGENT_UPDATED` because the hash changed. Acceptable — the cost is just a footer hash refresh, not an LLM call.

Edge case: an agent creates a design file from scratch (no footer). The change checker detects the file exists but has no `StalenessMetadata`, and classifies it as `AGENT_UPDATED` — trusting the agent's content and adding the footer with current hashes. Without this check, the file would be classified as `NEW_FILE` and overwritten by LLM regeneration.

### Concern: `.aindex` refresh on single file update

**Severity:** Low — parsing and re-serializing `.aindex` is cheap.

When `lexi update src/foo.py` runs, it also needs to re-read, update, and re-write `src/.aindex`. This is a read-parse-modify-write cycle on a small file. The risk is concurrent writes if multiple update processes run simultaneously, but Phase 4 is sequential.

### Concern: LLM output quality and consistency

**Severity:** Medium — addressable via prompt iteration.

The Archivist prompt must produce consistent, well-structured output. BAML's structured output (typed return values) mitigates this — the LLM returns a `DesignFileOutput` object, not free-form markdown. The serializer converts structured output to markdown.

### Concern: Token cost for large projects

**Severity:** Medium — the agent-first model reduces LLM calls significantly.

If agents update design files during their coding sessions, `lexi update` only needs to run the LLM for files agents missed. This could reduce LLM calls by 50-80% in practice.

Additional mitigations:
- Two-tier hashing skips unchanged files and avoids full regeneration for implementation-only changes
- Rate limiter prevents API throttling
- `max_file_size_kb` skips very large files
- `scope_root` limits which files get design files

### Risk: Design file format is a serialization contract

**Severity:** High if changed after adoption.

The YAML frontmatter + markdown body + HTML footer format must be stable. Mitigations:
- Defined carefully in this plan
- Parser is tolerant of minor variations (extra whitespace, missing optional sections)
- Frontmatter is a standard convention (Jekyll, Hugo, Obsidian) — well-understood by agents

### Concern: First-run performance with sequential processing

**Severity:** Medium — affects user experience on initial adoption.

On a project with 300 files, the first `lexi update` run touches every file (all are `NEW_FILE`). Sequential processing + LLM calls + rate limiter = potentially 10–30 minutes depending on provider and rate limits. Subsequent runs are fast (most files are `UNCHANGED`).

Mitigations already in place:
- Rich progress bar (Task 4.9) shows real-time progress
- `scope_root` limits the number of files processed
- `max_file_size_kb` skips very large files
- The two-tier hashing ensures subsequent runs are cheap

Recommendations:
- Documentation and CLI output should set expectations: "First run processes all files — this may take several minutes for large projects."
- The progress bar should show estimated remaining time (files remaining × average time per file)
- Consider a `--dry-run` flag for `lexi update` that reports what would be processed without making LLM calls
- The async architecture (pipeline, service) should be designed with concurrency in mind from the start, even though concurrency is not enabled in MVP (D-025). This avoids a rewrite when concurrency is added later.

### Risk: Import resolution is best-effort

**Severity:** Low — dependencies are informational, not load-bearing.

The dependency extractor handles common cases (literal imports with resolvable paths). Unresolvable imports are silently omitted. Acceptable for Phase 4 — the dependency list is informational, not used for graph traversal yet.
