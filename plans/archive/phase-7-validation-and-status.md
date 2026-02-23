# Phase 7 — Validation & Library Health

**Reference:** `plans/v2-master-plan.md` (Phase 7 section), `lexibrary-overview.md` (sections 7, 8, 9)
**Depends on:** Phase 4 (Archivist), Phase 5 (Concepts Wiki), Phase 6 (The Stack) — all complete
**Consumed by:** Phase 8 (Agent Setup), Phase 9 (Daemon & CI)

---

## Goal

`lexi validate` runs consistency checks across the entire library and reports issues by severity. `lexi status` provides a quick health dashboard agents can read at session start. Both commands are designed for a future where library maintenance is handled by a **dedicated maintenance service** rather than by coding agents mid-task — see §Design Direction below.

---

## Decisions Made

| # | Decision | Resolution |
|---|----------|------------|
| D-045 | Validate severity tiers | Validation issues are grouped into three tiers: **error** (blocks work — broken references, missing files), **warning** (drift — stale hashes, token budget violations, orphan concepts), **info** (hygiene — bidirectional consistency gaps, potentially outdated Stack posts). |
| D-046 | `lexi status` output model | Status returns a compact summary: total artifact counts by type, stale count, issue counts by severity, last update timestamp. Non-zero exit code when errors or warnings exist (enables hooks/CI). |
| D-047 | Validate is read-only | `lexi validate` never modifies files. It reports issues only. Fixes are the responsibility of `lexi update`, agent edits, or a future `lexi validate --fix` flag. |
| D-048 | Bidirectional consistency — deferred scope | Full bidirectional validation (if A depends on B, B's dependents should list A) requires the reverse dependency index, which is not yet implemented. Phase 7 validates the **forward direction only**: every file listed in a `## Dependencies` section must exist. The reverse check is deferred to the Reverse Index phase. |
| D-049 | Local Conventions — future structural upgrade | Local Conventions in `.aindex` files are currently `list[str]` (plain bullet points). A future phase should upgrade them to a structured model with optional title, tags, and concept links — making them first-class searchable artifacts. See Open Question Q-004. This change requires both an `.aindex` format revision and search integration, so it is tracked separately. |
| D-050 | `lexi lookup` convention inheritance | `lexi lookup <file>` should append applicable Local Conventions by walking up parent `.aindex` files. This surfaces scoped conventions at the moment of highest agent attention — when they're about to edit a file. Implemented alongside the lookup enhancement in this phase. |
| D-051 | Maintenance service pattern | `lexi validate` and `lexi status` are designed as inspection tools, not agent workflow steps. Long-term, library maintenance (validation, staleness remediation, index rebuilds) should be handled by a **dedicated maintenance service or scheduled process** rather than interrupting coding agents. Phase 7 builds the inspection primitives; Phase 9 (Daemon & CI) wires them into automated triggers. Agent rules should direct coding agents to `lexi search` and `lexi lookup` (read operations), not to `lexi validate` (maintenance operation). |

---

## Design Direction: Maintenance vs. Workflow

A key architectural insight: **library health is a maintenance concern, not a coding workflow concern.**

Coding agents should interact with the library through **read operations** (`lexi lookup`, `lexi search`, `lexi concepts`, `lexi stack search`) and **write-back operations** (`lexi update`, design file edits, Stack posts, HANDOFF.md). Asking a coding agent to also run `lexi validate` and triage 47 issues is a distraction that pulls them out of their primary task.

The long-term model:
- **Coding agents** → `lexi lookup`, `lexi search`, `lexi update`, direct edits
- **Maintenance service** → `lexi validate`, `lexi status`, staleness remediation, periodic sweeps
- **CI/CD pipeline** → `lexi validate` as a gate (like a linter)
- **Agent hooks** → `lexi status --quiet` at session start to surface a one-line warning if the library needs attention ("Library has 3 warnings — run `lexi validate` or defer to maintenance")

Phase 7 builds the tools. Phase 8 (Agent Setup) and Phase 9 (Daemon & CI) wire them into the right places. Agent environment rules (Phase 8) should **not** tell coding agents to run `lexi validate` routinely — instead, they should surface `lexi status` as a passive health check and direct maintenance concerns to the appropriate channel.

---

## Sub-Phases

| Sub-Phase | Name | Depends On | Can Parallel With | Task Groups |
|-----------|------|------------|-------------------|-------------|
| **7a** | Validator Module | Phases 4, 5, 6 (all parsers) | 7b | TG1 |
| **7b** | `lexi lookup` Convention Inheritance | Phase 2 (`.aindex` parser) | 7a | TG2 |
| **7c** | CLI Commands (`validate`, `status`) | 7a | 7b | TG3 |

**Critical path:** 7a → 7c
**Independent:** 7b (lookup enhancement) can run in parallel with 7a

---

## 7a — Validator Module

### New module: `src/lexibrary/validator/`

```
validator/
  __init__.py        ← Public API: validate_library(), ValidationReport
  checks.py          ← Individual check functions
  report.py          ← ValidationReport model + Rich rendering
```

### ValidationReport model

```python
@dataclass
class ValidationIssue:
    severity: Literal["error", "warning", "info"]
    check: str           # e.g., "wikilink_resolution", "token_budget"
    message: str         # Human/agent-readable description
    artifact: str        # Path to the artifact with the issue
    suggestion: str      # What to do about it (for future --fix)

@dataclass
class ValidationReport:
    issues: list[ValidationIssue]
    summary: ValidationSummary  # Counts by severity + totals

    def has_errors(self) -> bool: ...
    def has_warnings(self) -> bool: ...
    def exit_code(self) -> int: ...   # 0 = clean, 1 = errors, 2 = warnings only
    def render(self, console: Console) -> None: ...
```

### Validation checks (in priority order)

Each check is a function `check_*(project_root, lexibrary_dir) -> list[ValidationIssue]`:

#### Errors (severity: error)

**1. `check_wikilink_resolution`** — All `[[wikilinks]]` in design files and Stack posts resolve to existing concepts or Stack posts.
- Parse all design files → collect `wikilinks` field entries
- Parse all Stack posts → collect `refs.concepts` entries
- Use `WikilinkResolver` to attempt resolution
- Unresolved links → error with suggestion (closest match from resolver)

**2. `check_file_existence`** — All referenced source files still exist.
- Parse all design files → check `source_path` exists relative to project root
- Parse all Stack posts → check `refs.files` entries exist
- Parse all Stack posts → check `refs.designs` entries exist in `.lexibrary/`
- Missing files → error

**3. `check_concept_frontmatter`** — All concept files have valid mandatory frontmatter.
- Parse all concept files → validate `title`, `aliases`, `tags`, `status` present
- Invalid frontmatter → error (concept file is broken)

#### Warnings (severity: warning)

**4. `check_hash_freshness`** — Design file `source_hash` matches current source file content.
- Parse design file metadata (lightweight — footer only via `parse_design_file_metadata`)
- Compute current source file SHA-256
- Mismatch → warning ("design file may be stale")

**5. `check_token_budgets`** — Generated artifacts are within configured token size targets.
- Load `TokenBudgetConfig` from config
- Count tokens in each artifact type using `tokenizer/`
- Over budget → warning with actual vs target counts

**6. `check_orphan_concepts`** — Concepts with zero inbound references.
- Scan all design files for `wikilinks` entries
- Scan all Stack posts for `refs.concepts` entries
- Scan all concept files for wikilinks to other concepts
- Concepts with zero references → warning ("orphan — consider deprecating or linking")

**7. `check_deprecated_concept_usage`** — Active artifacts referencing deprecated concepts.
- Find all concepts with `status: deprecated`
- Check if any design files or Stack posts still reference them
- References to deprecated concepts → warning with `superseded_by` suggestion

#### Info (severity: info)

**8. `check_forward_dependencies`** — Files listed in `## Dependencies` exist.
- Parse design files → check each dependency path exists
- Missing dependency targets → info (may be external package, not always actionable)

**9. `check_stack_staleness`** — Stack posts whose referenced source files have changed.
- For each Stack post with `refs.files`, compute current source hashes
- Compare against... (note: Stack posts don't store source hashes — this check uses a heuristic: if any referenced file's design file has a stale `source_hash`, the Stack post may be outdated)
- Potentially outdated → info ("referenced files have changed since this post was written")

**10. `check_aindex_coverage`** — Directories within `scope_root` that lack `.aindex` files.
- Walk `scope_root` directory tree
- Check each directory has a corresponding `.lexibrary/<path>/.aindex`
- Missing `.aindex` → info ("directory not indexed")

### What this phase does NOT validate

- **Bidirectional consistency** (dependents ↔ dependencies) — requires the reverse dependency index, deferred
- **Design file content quality** — no LLM-based checks
- **Stack post answer quality** — voting handles this

---

## 7b — `lexi lookup` Convention Inheritance

### Current behavior

`lexi lookup <file>` returns the design file content for a source file.

### Enhanced behavior

`lexi lookup <file>` returns the design file **plus** an `## Applicable Conventions` section listing Local Conventions inherited from all parent `.aindex` files between the file's directory and `scope_root`.

### Implementation

In `cli.py`, after loading the design file content, walk upward from the file's parent directory to `scope_root`, parsing each `.aindex` for `local_conventions`. Collect all conventions with their source directory. Append to output:

```markdown
## Applicable Conventions

**From `src/`:**
- All monetary values use `Decimal`, never `float` — see [[MoneyHandling]]

**From `src/payments/`:**
- Tests in this directory require the `payments` fixture — `conftest.py` has details
```

Only appended if any conventions exist. This keeps the output clean for directories without conventions.

### Why in lookup, not in the design file itself

Conventions are directory-scoped, not file-scoped. Baking them into the design file would duplicate them across every file in the directory and create a maintenance burden. Surfacing them at read time via `lexi lookup` is cheap and always current.

---

## 7c — CLI Commands

### `lexi validate`

```
lexi validate [--severity error|warning|info] [--check <name>] [--json]
```

- Runs all checks by default
- `--severity` filters to only show issues at or above the given severity
- `--check` runs a single named check (useful for CI)
- `--json` outputs structured JSON (for programmatic consumption / future maintenance service)
- Exit codes: 0 (clean), 1 (errors found), 2 (warnings but no errors)

**Output format (Rich):**

```
Validation Report
═════════════════

Errors (2)
  ✗ wikilink_resolution: [[AuthFlow]] in src/api/auth.py.md does not resolve
    → Did you mean [[Authentication]]?
  ✗ file_existence: src/old_module.py referenced by design file but does not exist
    → Remove the design file or restore the source file

Warnings (3)
  ⚠ hash_freshness: src/services/user.py has changed since design file was generated
    → Run `lexi update src/services/user.py`
  ⚠ token_budget: src/services/auth.py.md is 620 tokens (budget: 400)
    → Source file may be over-scoped
  ⚠ orphan_concept: [[OldPattern]] has zero inbound references
    → Consider deprecating or linking from a design file

Info (1)
  ℹ stack_staleness: ST-003 references src/api/events.py which has changed
    → Verify the solution still applies

Summary: 2 errors, 3 warnings, 1 info
```

### `lexi status`

```
lexi status [--quiet]
```

**Default output:**

```
Library Status
══════════════
Files:    47 tracked, 3 stale
Concepts: 12 active, 1 deprecated, 2 draft
Stack:    8 posts (5 resolved, 3 open)
Issues:   0 errors, 3 warnings
Updated:  2 minutes ago

Run `lexi validate` for details.
```

**`--quiet` output** (single line, for hooks):

```
lexi: 3 warnings — run `lexi validate`
```

Or if clean:

```
lexi: library healthy
```

**Exit codes:** Same as validate (0/1/2) — enables `lexi status --quiet` as a hook/CI check.

### How `lexi status` gets its data

Status collects counts without running full validation:
- **File counts:** Count `.md` files in `.lexibrary/` (excluding concepts/, stack/, START_HERE, HANDOFF)
- **Stale count:** Quick scan of design file footers vs current source hashes (same as `check_hash_freshness` but count-only)
- **Concept counts:** Count files in `concepts/`, parse frontmatter for status breakdown
- **Stack counts:** Count files in `stack/`, parse frontmatter for status breakdown
- **Issue counts:** Run a lightweight subset of validation (errors + warnings only, skip info)
- **Last updated:** Most recent `generated` timestamp from any design file footer

This keeps `lexi status` fast (< 2 seconds for typical projects) while `lexi validate` does the thorough analysis.

---

## Files to Create

| File | Purpose |
|------|---------|
| `src/lexibrary/validator/__init__.py` | Public API: `validate_library()`, re-export `ValidationReport` |
| `src/lexibrary/validator/checks.py` | Individual check functions |
| `src/lexibrary/validator/report.py` | `ValidationReport`, `ValidationIssue`, `ValidationSummary` models + Rich rendering |
| `tests/test_validator.py` | Unit tests for each check function |
| `tests/test_validator_integration.py` | Integration tests with `tmp_path` project fixtures |
| `tests/test_cli_validate_status.py` | CLI command tests for validate and status |

## Files to Modify

| File | Change |
|------|--------|
| `src/lexibrary/cli.py` | Replace `validate` and `status` stubs with real implementations; enhance `lexi lookup` with convention inheritance |
| `blueprints/START_HERE.md` | Add `validator` to Package Map and Navigation by Intent |
| `blueprints/src/lexibrary/cli.md` | Update with new validate/status/lookup behavior |

---

## Test Strategy

### Unit tests (`test_validator.py`)

Each check function tested in isolation with minimal fixtures:

- `test_check_wikilink_resolution_valid` — all links resolve → no issues
- `test_check_wikilink_resolution_broken` — unresolved link → error with suggestion
- `test_check_file_existence_valid` — source files exist → no issues
- `test_check_file_existence_missing` — source file deleted → error
- `test_check_hash_freshness_current` — hashes match → no issues
- `test_check_hash_freshness_stale` — hash mismatch → warning
- `test_check_token_budgets_within` — under budget → no issues
- `test_check_token_budgets_exceeded` — over budget → warning with counts
- `test_check_orphan_concepts_linked` — concept has references → no issues
- `test_check_orphan_concepts_orphan` — zero references → warning
- `test_check_deprecated_usage` — deprecated concept referenced → warning with superseded_by
- `test_check_forward_dependencies_exist` — deps exist → no issues
- `test_check_forward_dependencies_missing` — dep missing → info
- `test_check_stack_staleness_current` — referenced files unchanged → no issues
- `test_check_stack_staleness_changed` — referenced files changed → info
- `test_check_aindex_coverage_complete` — all dirs indexed → no issues
- `test_check_aindex_coverage_missing` — dir not indexed → info

### Integration tests (`test_validator_integration.py`)

Full `validate_library()` with realistic project fixtures:

- `test_validate_healthy_project` — no issues
- `test_validate_mixed_issues` — combination of errors + warnings + info
- `test_validate_empty_library` — no artifacts → graceful handling
- `test_validate_severity_filter` — `--severity warning` hides info

### CLI tests (`test_cli_validate_status.py`)

- `test_validate_clean_exit_code_0` — healthy project → exit 0
- `test_validate_errors_exit_code_1` — errors → exit 1
- `test_validate_warnings_exit_code_2` — warnings only → exit 2
- `test_validate_json_output` — `--json` produces valid JSON
- `test_status_output_format` — status shows expected sections
- `test_status_quiet_one_line` — `--quiet` gives single line
- `test_status_exit_codes` — matches validate exit codes
- `test_lookup_with_conventions` — `lexi lookup` shows inherited conventions
- `test_lookup_without_conventions` — no conventions → no extra section

---

## Open Questions

| # | Phase | Question | Status |
|---|-------|----------|--------|
| Q-004 | 7+ | Local Conventions need a structural upgrade to become first-class searchable artifacts. Current `list[str]` model doesn't support titles, tags, concept links, or search integration. The upgrade must also make it easy for agents to add new conventions (e.g., `lexi convention add <dir> "..."` or similar). This requires: (a) a structured model for conventions, (b) `.aindex` format revision, (c) search integration, (d) an agent-friendly creation workflow, (e) preservation during `.aindex` regeneration (relates to Q-001). Additionally, `lexi lookup` needs to surface inherited conventions from parent directories — agents who jump directly to a file miss conventions they didn't traverse through. | Open |

---

## What to Watch Out For

- **Performance:** `lexi validate` parses every artifact in the library. For large projects this could be slow. Parse metadata-only where possible (e.g., `parse_design_file_metadata` for hash checks, `parse_design_file_frontmatter` for description checks). Reserve full parsing for checks that need it (wikilink resolution).
- **Token counting cost:** `check_token_budgets` needs to count tokens for every artifact. Use the approximate counter (character-ratio) for validation speed, not the full tiktoken/anthropic backend.
- **Exit codes in CI:** The 0/1/2 exit code scheme must be reliable — CI pipelines will gate on it. Test this explicitly.
- **`lexi status` speed:** Status must complete in < 2 seconds. If it's slow, agents won't use it at session start. Profile early.
- **Convention inheritance in lookup:** Walking up `.aindex` files adds I/O. For deep directory trees, this could mean 5-10 file reads. Cache or limit depth if needed.
- **Stack staleness heuristic:** Stack posts don't store source file hashes (unlike design files). The staleness check is indirect (check if referenced files' design files are stale). This is imperfect — document the limitation.
