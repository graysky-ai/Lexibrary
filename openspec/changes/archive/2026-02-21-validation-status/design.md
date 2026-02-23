## Context

Lexibrary has completed Phases 4–6: design files (Archivist), concepts wiki, and the Stack are all functional. However, there is no automated way to detect inconsistencies — broken wikilinks, missing source files, stale design files, orphan concepts. The `validate` and `status` CLI commands are currently stubs. Additionally, `lexi lookup` doesn't surface Local Conventions from parent directories, meaning agents who jump directly to a file miss scoped conventions they didn't traverse through.

The existing codebase provides all the parsing infrastructure needed:
- `parse_design_file_metadata()` — lightweight footer-only parser for hash checks
- `parse_design_file()` — full parser for wikilinks, dependencies, tags
- `parse_aindex()` — `.aindex` parser with `local_conventions: list[str]`
- `WikilinkResolver` — resolves `[[links]]` with fuzzy matching and suggestions
- `parse_stack_post()` — Stack post parser with refs (concepts, files, designs)
- `ConceptIndex.load()` — concept catalog with frontmatter parsing
- `TokenCounter` via `create_tokenizer()` — token counting with approximate mode
- `load_config()` — config with `TokenBudgetConfig`

## Goals / Non-Goals

**Goals:**
- Provide a `validate_library()` function that runs 10 named checks and returns a structured `ValidationReport`
- Implement `lexi validate` with severity filtering, single-check mode, JSON output, and reliable exit codes (0/1/2)
- Implement `lexi status` as a fast (< 2 seconds) health dashboard with `--quiet` mode for hooks
- Enhance `lexi lookup` to surface inherited Local Conventions from parent `.aindex` files
- All inspection commands are strictly read-only — no file modifications

**Non-Goals:**
- Auto-fixing issues (`--fix` flag deferred to a future phase)
- Bidirectional dependency validation (requires reverse dependency index — D-048)
- LLM-based content quality checks
- Structured Local Conventions model upgrade (D-049, Q-004 — deferred)
- Performance optimization beyond the < 2 second target for `lexi status`

## Decisions

### D1: Validator module structure — flat package with three files

The validator lives at `src/lexibrary/validator/` with:
- `report.py` — `ValidationIssue`, `ValidationSummary`, `ValidationReport` dataclasses
- `checks.py` — 10 individual check functions, each `check_*(project_root, lexibrary_dir) -> list[ValidationIssue]`
- `__init__.py` — public API: `validate_library()` orchestrator, re-exports

**Why:** Each check is independently testable. The report model is reusable by both `validate` and `status` commands. The orchestrator composes checks without coupling them.

### D2: Check functions receive `project_root` and `lexibrary_dir` as Path arguments

Rather than injecting parsed artifacts, each check function is responsible for parsing what it needs. This keeps the check interface uniform and avoids a complex dependency injection setup.

**Why not pre-parse everything?** Some checks only need metadata (footer-only parse), others need full parse. Letting each check decide avoids unnecessary work. The tradeoff is some redundant parsing across checks, but for typical project sizes this is negligible.

### D3: `lexi status` uses a lightweight subset, not full validation

Status collects counts directly (file counts, concept frontmatter, stack frontmatter) and runs only error + warning checks (skipping info). This keeps it under the 2-second target.

**Alternative considered:** Running full `validate_library()` and summarizing — rejected because info checks (aindex coverage, stack staleness) add latency with low value for a quick dashboard.

### D4: Exit code scheme — 0/1/2

- 0 = clean (no errors or warnings; info-only is clean)
- 1 = errors found
- 2 = warnings but no errors

Both `validate` and `status` use the same scheme. This enables `lexi status --quiet` as a CI/hook gate.

**Why not 1 for both errors and warnings?** Distinguishing them lets CI pipelines choose: fail on errors only (exit 1) or fail on warnings too (exit != 0). This matches common linter conventions (e.g., pylint).

### D5: Convention inheritance walks from file directory up to scope_root

`lexi lookup` enhancement: after printing the design file, walk from the file's parent directory up to `scope_root` (inclusive), parsing each `.aindex` for `local_conventions`. Conventions are collected in bottom-up order (closest directory first) and rendered with source directory headers.

**Why scope_root as the boundary?** Files outside scope_root don't get design files and their `.aindex` conventions aren't relevant to scoped development work. This also naturally limits the walk depth.

### D6: Token counting uses approximate mode for validation

`check_token_budgets` uses `create_tokenizer(TokenizerConfig(backend="approximate"))` — the character-ratio estimator. This avoids requiring tiktoken/anthropic dependencies for validation and keeps the check fast.

### D7: Stack staleness is heuristic-based

Stack posts don't store source hashes. The staleness check is indirect: for each Stack post with `refs.files`, check if any referenced file's design file has a stale `source_hash`. This is imperfect (a file could change without affecting the Stack post's relevance), but it's the best signal available without adding hash storage to Stack posts.

## Risks / Trade-offs

**[Performance for large projects]** → `lexi validate` parses every artifact. Mitigated by using metadata-only parsing where possible and approximate token counting. If this becomes a bottleneck, individual checks can be parallelized (the uniform interface makes this straightforward).

**[Redundant parsing across checks]** → Multiple checks may parse the same files. Mitigated by the fact that `parse_design_file_metadata` is very fast (reads only the footer). For full parses, the OS file cache handles repeated reads efficiently. A shared parse cache could be added later without changing the check interface.

**[Stack staleness false positives]** → The heuristic (design file staleness as proxy for Stack post relevance) will flag posts even when the referenced file change doesn't affect the post's content. This is acceptable — info severity means it's advisory, not blocking.

**[Convention inheritance I/O for deep trees]** → Walking 5–10 parent directories means 5–10 `.aindex` file reads. For typical projects this is < 50ms total. If it becomes an issue, a depth limit can be added without changing the interface.
