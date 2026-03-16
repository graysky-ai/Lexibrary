# Validate Schema/Template Gaps

## Current State

`lexi validate` runs ~27 checks covering link resolution, staleness, orphans, conventions, and lifecycle concerns. However, only **one** check validates artifact schema: `check_concept_frontmatter`. All other artifact types rely on parse-time validation (Pydantic models or parsers returning `None` on malformed input), which means malformed artifacts are silently skipped rather than surfaced as issues.

## What Exists

### Concepts — `check_concept_frontmatter` (error severity)

- Validates YAML frontmatter is present and parseable
- Checks mandatory fields: `title`, `aliases`, `tags`, `status`
- Validates `status` is one of: `draft`, `active`, `deprecated`
- Does **not** validate body sections

### Parse-Time Validation (not surfaced by `lexi validate`)

| Artifact | Parser | What it checks | Failure mode |
|----------|--------|---------------|--------------|
| Conventions | `conventions/parser.py` → `ConventionFileFrontmatter` | `title` (required), `scope`, `tags`, `status`, `source`, `priority`, `aliases` | Returns `None` — silently skipped |
| Design files | `artifacts/design_file_parser.py` → `DesignFileFrontmatter` | `description` (required), `updated_by`, `status`, `deprecated_at` | Returns `None` — silently skipped |
| Design files | `artifacts/design_file_parser.py` → full parser | H1 heading, section boundaries, metadata footer (source, source_hash, design_hash, generated, generator) | Returns `None` — silently skipped |
| Stack posts | `stack/parser.py` → `StackPostFrontmatter` | `id`, `title`, `tags` (min 1), `status`, `created`, `author`, plus optional fields | Raises `ConfigError` — crashes the check |
| IWH signals | `iwh/parser.py` | Frontmatter fields for IWH signals | Returns `None` — silently skipped |

## What Is Missing

### Schema / Frontmatter Gaps

### 1. Convention Frontmatter Check

No `check_convention_frontmatter` exists. A convention file with missing `title`, invalid `status`, or unparseable YAML is silently ignored by all convention checks (`convention_orphaned_scope`, `convention_stale`, `convention_gap`, `convention_consistent_violation`).

**Impact:** A typo in convention frontmatter makes the convention invisible to the entire system with no warning.

**Pydantic model fields to validate:**
- `title` (required)
- `scope` (default: `"project"`)
- `status` (must be `draft` | `active` | `deprecated`)
- `source` (must be `user` | `agent` | `config`)
- `tags` (list)
- `priority` (int)

### 2. Design File Frontmatter Check

No `check_design_frontmatter` exists. Design files with missing `description` or invalid frontmatter are returned as `None` by the parser. Checks like `check_orphaned_designs` parse frontmatter separately but don't report parse failures — they just skip the file.

**Impact:** A corrupted design file is invisible to staleness, dependency, and orphan checks.

**Pydantic model fields to validate:**
- `description` (required)
- `updated_by` (default: `"archivist"`)
- `status` (default: `"active"`)
- `deprecated_at` (optional datetime)

### 3. Design File Structure Check

No check validates that design files have the expected sections. The full parser (`parse_design_file`) expects:
- H1 heading (source path)
- `## Interface Contract`
- `## Dependencies`
- `## Dependents`
- Metadata footer (`<!-- lexibrary:meta ... -->`)

A design file missing any of these returns `None` from the parser but is never reported as malformed.

**Impact:** Partially generated or manually edited design files that lost sections go undetected.

### 4. Stack Post Frontmatter Check

No `check_stack_frontmatter` exists. Stack parsers raise `ConfigError` on invalid frontmatter, which the validator catches as an exception and logs to `ErrorSummary` — but this appears as a generic check failure, not a structured validation issue with artifact path and suggestion.

**Impact:** A malformed Stack post produces a vague error log rather than an actionable validation issue.

**Pydantic model fields to validate:**
- `id` (required)
- `title` (required)
- `tags` (required, min length 1)
- `status` (must be one of: `open`, `resolved`, `outdated`, `duplicate`, `stale`)
- `created` (required date)
- `author` (required)
- `resolution_type` (if present, must be: `fix`, `workaround`, `wontfix`, `cannot_reproduce`, `by_design`)

### 5. Stack Post Body Sections Check

No check validates that Stack posts have expected body sections. The parser extracts Problem, Context, Evidence, and Attempts sections but does not flag missing ones. A Stack post with no `## Problem` section is technically valid to the parser (problem will be an empty string).

**Impact:** Stack posts without a Problem section are not useful for search but are never flagged.

### 6. Concept Body Sections Check

`check_concept_frontmatter` validates frontmatter only. There is no check for expected body content — e.g., whether a concept has any summary text, related concepts via wikilinks, or linked files.

**Impact:** A concept file with valid frontmatter but an empty body is never flagged.

### 7. IWH Frontmatter Check

No `check_iwh_frontmatter` exists. IWH signals use the same silent-`None` return pattern as conventions and design files. A corrupt `.iwh` file is invisible to `check_orphaned_iwh_signals` (the TTL check) because it can't parse the file — it simply skips it.

**Impact:** An IWH signal left by a previous agent session could be silently lost if the file is malformed, defeating the purpose of the handoff mechanism.

**Pydantic model fields to validate:**
- `author` (required, non-empty string)
- `created` (required, ISO 8601 datetime)
- `scope` (must be `warning` | `incomplete` | `blocked`)
- `body` (optional, default empty)

### Infrastructure / Environment Gaps

### 8. Config File Validation

`.lexibrary/config.yaml` is validated by Pydantic at load time, but `lexi validate` does not re-check it. A corrupted or manually edited config could cause confusing failures across all checks without a clear root-cause message.

**Impact:** A bad config produces cascading failures in unrelated checks with no indication that the config itself is the problem.

**What to check:**
- YAML is parseable
- All fields pass `LexibraryConfig.model_validate()`
- Report the specific Pydantic `ValidationError` details as the issue message

### 9. `.lexignore` Syntax Validation

`.lexignore` uses gitignore-style patterns via `pathspec`. Invalid patterns are silently accepted, potentially causing unexpected file inclusion or exclusion from crawling and indexing.

**Impact:** A malformed ignore pattern could cause files to be indexed that shouldn't be, or vice versa, with no warning.

**What to check:**
- Each line is a valid gitignore pattern (attempt to compile via `pathspec`)
- Report line number of any invalid pattern

### 10. Linkgraph Schema Version Check

The linkgraph DB has `SCHEMA_VERSION = 3`. If the DB was created by an older version, `lexi validate` doesn't flag the mismatch — it may silently get wrong results or fail in confusing ways.

**Impact:** After an upgrade, a stale linkgraph DB could produce incorrect validation results for all link-related checks.

**What to check:**
- Read stored schema version via `check_schema_version(conn)`
- Compare to current `SCHEMA_VERSION`
- If mismatched, report as error with suggestion to run `lexictl update`

### Cross-Artifact Consistency Gaps

### 11. Duplicate Concept Aliases

Two concepts with the same alias would cause ambiguous wikilink resolution. Currently not checked by any validation.

**Impact:** Ambiguous wikilinks resolve to an unpredictable concept, causing incorrect cross-references.

**What to check:**
- Collect all aliases from all concept frontmatter
- Report any alias that appears in more than one concept file

### 12. Design File Status Enum Validation

Design file `status` has a default of `"active"` but no enum constraint — any string is accepted. Unlike concepts and conventions (which constrain to `draft`|`active`|`deprecated`), design files have no status validation.

**Impact:** A design file with `status: "daft"` (typo) is silently accepted.

**Decision needed:** Define the valid status values for design files, then add enum validation to the Pydantic model and the new `design_frontmatter` check.

### 13. Stack Post Resilience

Stack post parsing raises `ConfigError` on invalid frontmatter. Any existing check that iterates over stack posts and encounters a malformed post will abort with a generic exception rather than gracefully skipping it and continuing. The new `stack_frontmatter` check should run first, but existing checks also need try/except wrapping around individual post parsing to be resilient.

**Impact:** One bad stack post can prevent all stack-related checks from completing.

### 14. Stack Post Refs Validation

Stack posts have a structured `refs` object with `concepts`, `files`, and `designs` lists. The `wikilink_resolution` check validates `[[concept]]` links in body text, but the `refs.files` and `refs.designs` fields are **never validated** to point to artifacts that actually exist.

**Impact:** A Stack post can reference a deleted design file or renamed source file in its `refs` without any warning. Agents relying on `refs` for context get broken links.

**What to check:**
- Each entry in `refs.files` exists on disk (relative to project root)
- Each entry in `refs.designs` resolves to an existing design file in `.lexibrary/designs/`
- Report each broken ref as a separate `ValidationIssue` with the Stack post path and the invalid ref

### 15. Design File Dependencies Existence

Design files list `dependencies` and `dependents` as string lists extracted from `## Dependencies` / `## Dependents` sections. The `forward_dependencies` check only validates temporal ordering (whether a dependency is newer than the dependent). It does **not** verify that the referenced design files exist.

**Impact:** A design file can reference a non-existent dependency (e.g., after a rename or deletion), producing incorrect dependency graphs.

**What to check:**
- Each entry in `dependencies` resolves to an existing design file
- Each entry in `dependents` resolves to an existing design file
- Report each broken reference with the design file path and the missing target

### 16. AIndex Entry Validation

AIndex files contain a `## Child Map` table listing child files and directories. No check validates that these entries actually exist on disk. An AIndex generated for a directory that was later reorganized will have stale entries.

**Impact:** Stale AIndex entries mislead agents about directory contents, causing lookups for files that no longer exist.

**What to check:**
- Each `AIndexEntry` with `entry_type == "file"` exists relative to the AIndex's `directory_path`
- Each `AIndexEntry` with `entry_type == "dir"` exists as a subdirectory
- Report each missing entry with the AIndex path and the stale entry name

### 17. Duplicate Concept/Convention Slugs

Beyond duplicate aliases (#11), ConceptIndex and ConventionIndex could contain duplicate slugs if two files produce the same slug. No validation detects this.

**Impact:** Duplicate slugs cause unpredictable index lookups and wikilink resolution.

**What to check:**
- Collect all slugs from ConceptIndex and ConventionIndex
- Report any slug that maps to more than one file

### Parser / Model Consistency Gaps

### 18. Inconsistent Datetime Handling

Convention `deprecated_at` and Stack `stale_at`/`last_vote_at` are stored as raw strings (`str | None`), while Design and Concept `deprecated_at` are parsed to `datetime` objects. This means Convention and Stack parsers silently accept invalid ISO datetime strings (e.g., `"not-a-date"`).

**Impact:** Invalid datetime strings pass validation silently in Convention/Stack, but would fail in Design/Concept. Cross-artifact datetime comparisons require mixed handling.

**What to fix:**
- Standardize all datetime fields to `datetime | None` in Pydantic models
- Convention: change `deprecated_at: str | None` → `deprecated_at: datetime | None`
- Stack: change `stale_at: str | None` → `stale_at: datetime | None`, same for `last_vote_at`
- Pydantic will then validate ISO format at parse time

### 19. Parser Exception Strategy Standardization

Five parsers return `None` on failure, Stack raises `ConfigError`, Config raises `ValidationError`. Callers must implement mixed error-handling logic. This is a systemic inconsistency beyond the Stack-specific resilience fix (#13).

**Impact:** Every caller of any parser must know which error pattern to expect. New checks are likely to get this wrong, causing either silent skips or unhandled exceptions.

**Recommendation:** Standardize all parsers on a uniform pattern — either:
- **(a)** All return `None` (current majority pattern), with the new per-artifact frontmatter checks (#1–7) catching and reporting parse failures
- **(b)** Introduce a `ParseResult[T]` wrapper that carries either the parsed artifact or structured error context, enabling callers to handle both cases uniformly

Option (a) is lower effort and aligns with the existing codebase. Option (b) is cleaner long-term but requires parser refactoring.

### 20. Frontmatter Schema Version

No artifact frontmatter includes a `version` or `schema_version` field. If the frontmatter schema changes in a future release, there is no mechanism to detect or migrate old artifacts.

**Impact:** Schema evolution requires manual migration with no automated detection of stale artifacts.

**What to add:**
- Add optional `schema_version: int = 1` field to all frontmatter Pydantic models
- Add a `frontmatter_schema_version` check that flags artifacts with a version older than current
- Include a migration suggestion in the issue message

### 21. AST Interface vs. Documented Interface Contract

Design files contain an `## Interface Contract` section documenting a file's public API. The AST parser extracts the actual interface from source code. No check compares these two — `hash_freshness` detects content changes via hash, but does not validate that the documented interface still matches reality.

**Impact:** An interface contract can drift from the actual code without being flagged, even when the source hash matches (e.g., if only non-interface code changed, then the interface was later edited manually).

**What to check:**
- Re-extract the interface via the AST parser for the design file's `source_path`
- Compare to the stored `## Interface Contract` section (semantic or hash comparison)
- Flag mismatches as warning-level issues

## Summary of Gaps

| # | Missing Check | Artifact | Severity | Effort |
|---|--------------|----------|----------|--------|
| 1 | `convention_frontmatter` | Conventions | error | Low — mirrors `check_concept_frontmatter` |
| 2 | `design_frontmatter` | Design files | error | Low — frontmatter-only parse |
| 3 | `design_structure` | Design files | warning | Medium — need to define required sections |
| 4 | `stack_frontmatter` | Stack posts | error | Low — already has Pydantic model |
| 5 | `stack_body_sections` | Stack posts | warning | Low — check for non-empty `problem` |
| 6 | `concept_body` | Concepts | info | Low — check for non-empty body/summary |
| 7 | `iwh_frontmatter` | IWH signals | error | Low — mirrors convention pattern |
| 8 | `config_valid` | Config | error | Low — re-run Pydantic validation |
| 9 | `lexignore_syntax` | .lexignore | warning | Low — compile patterns, report failures |
| 10 | `linkgraph_version` | Linkgraph DB | error | Low — compare stored vs current version |
| 11 | `duplicate_aliases` | Concepts | warning | Low — collect and compare alias sets |
| 12 | `design_status_enum` | Design files | warning | Low — add enum constraint |
| 13 | Stack post resilience | Stack posts | — | Low — add try/except in existing checks |
| 14 | `stack_refs_validity` | Stack posts | warning | Low — check `refs.files`/`refs.designs` exist |
| 15 | `design_deps_existence` | Design files | warning | Low — check dependencies/dependents exist |
| 16 | `aindex_entries` | AIndex files | warning | Low — check child map entries exist on disk |
| 17 | `duplicate_slugs` | Concepts, Conventions | warning | Low — collect and compare slug sets |
| 18 | Datetime standardization | Convention, Stack | — | Low — change `str` → `datetime` in models |
| 19 | Parser exception standardization | All parsers | — | Medium — choose pattern, refactor parsers |
| 20 | `frontmatter_schema_version` | All artifacts | info | Medium — add field to all models + check |
| 21 | `interface_contract_drift` | Design files | warning | Medium — AST re-extract + comparison |

## Implementation Approach

Individual per-artifact checks, each with field-specific error messages. This gives users actionable feedback (e.g., "missing required field: title" rather than "failed to parse").

Each new check should:
- Attempt to parse YAML frontmatter independently (not rely on the artifact parser)
- Validate each required field and report a separate `ValidationIssue` per missing/invalid field
- Include the artifact file path and a suggestion for how to fix it
- Be registered in `AVAILABLE_CHECKS` with appropriate severity

## Notes

- The parsers already do most of the heavy lifting via Pydantic models. The missing piece is surfacing parse failures as `ValidationIssue` objects instead of returning `None` or swallowing exceptions.
- **Priority tiers:**
  - **P0 — Schema gaps (#1–7):** Implement first. These catch silent data loss from malformed artifacts.
  - **P1 — Infrastructure (#8–10) + Cross-artifact refs (#14–17):** Prevent cascading failures and catch broken cross-references.
  - **P2 — Model consistency (#18–19):** Datetime and exception standardization. Lower urgency but reduces maintenance burden.
  - **P3 — Future-proofing (#20–21):** Schema versioning and interface drift. Implement when schema evolution becomes likely.
- Stack post resilience (#13) is not a new check but a hardening pass on existing stack-iterating checks.
- Datetime standardization (#18) and parser exception standardization (#19) are model/parser refactors, not new validator checks. They should be coordinated with the frontmatter check implementations to avoid double-refactoring.
- Interface contract drift (#21) depends on the AST parser being available for the source file's language. Initially scope to Python files only.
