## 1. Link Graph Index Health Helper

- [x] 1.1 Create `read_index_health()` helper function in `src/lexibrarian/linkgraph/` that opens `index.db`, reads `meta` table for `built_at`, and runs `COUNT(*)` on `artifacts` and `links` tables. Returns a dataclass with `artifact_count`, `link_count`, `built_at` (or `None` if index is absent/corrupt/version-mismatch). Uses `set_pragmas()` and `check_schema_version()` from `schema.py`.
- [x] 1.2 Write unit tests for `read_index_health()`: index exists with data, index exists but empty, index does not exist, index is corrupt, schema version mismatch.

## 2. Bidirectional Dependency Check

- [x] 2.1 Implement `check_bidirectional_deps()` in `src/lexibrarian/validator/checks.py`. Opens `index.db` via `read_index_health()` pattern (open connection, check schema version). Parses each design file's `## Dependencies` section and queries `ast_import` links from the graph. Reports mismatches in both directions at info severity. Returns empty list if index is absent.
- [x] 2.2 Write unit tests for `check_bidirectional_deps()`: all consistent (no issues), design file lists dep not in graph, graph has link not in design file, index missing (returns empty), index corrupt (returns empty).

## 3. Dangling Links Check

- [x] 3.1 Implement `check_dangling_links()` in `src/lexibrarian/validator/checks.py`. Opens `index.db`, queries all artifacts with `kind` in (`source`, `design`, `concept`, `stack`), verifies backing file exists at `project_root / artifact.path`. Skips `convention` artifacts. Reports missing files at info severity.
- [x] 3.2 Write unit tests for `check_dangling_links()`: all files exist (no issues), source file deleted but in index, convention artifacts skipped, index missing (returns empty).

## 4. Orphan Artifacts Check

- [x] 4.1 Implement `check_orphan_artifacts()` in `src/lexibrarian/validator/checks.py`. Opens `index.db`, queries all non-convention artifacts, verifies backing file exists. Reports artifacts for deleted files at info severity with suggestion to rebuild index.
- [x] 4.2 Write unit tests for `check_orphan_artifacts()`: no orphans (no issues), source file deleted, design file deleted, index missing (returns empty).

## 5. Register New Checks

- [x] 5.1 Add `check_bidirectional_deps`, `check_dangling_links`, and `check_orphan_artifacts` to imports in `src/lexibrarian/validator/__init__.py`.
- [x] 5.2 Add all three to `AVAILABLE_CHECKS` registry with `"info"` default severity.
- [x] 5.3 Write integration test verifying `validate_library()` includes all 13 checks with no filters, and that link-graph checks return empty lists gracefully when index is absent.

## 6. Status Command: Link Graph Health

- [x] 6.1 Add link graph health section to the full dashboard in `lexictl status` in `src/lexibrarian/cli/lexictl_app.py`. Use `read_index_health()` to get counts and timestamp. Display `Link graph: N artifacts, M links (built <timestamp>)` or `Link graph: not built (run lexictl update to create)`. Place after the Stack section and before the Issues section.
- [x] 6.2 Ensure `--quiet` mode does not include the link graph line.
- [x] 6.3 Write CLI tests for `lexictl status`: index exists shows health line, index missing shows not-built message, quiet mode omits link graph line.

## 7. Blueprint and Design File Updates

- [x] 7.1 Update the blueprint/design file for `src/lexibrarian/validator/checks.py` to document the three new check functions.
- [x] 7.2 Update the blueprint/design file for `src/lexibrarian/cli/lexictl_app.py` to document the link graph health section in status.
- [x] 7.3 Update the blueprint/design file for `src/lexibrarian/linkgraph/` to document the `read_index_health()` helper.

## 8. Final Verification

- [x] 8.1 Run full test suite (`uv run pytest --cov=lexibrarian`) and confirm all tests pass with no regressions.
- [x] 8.2 Run linting and type checking (`uv run ruff check src/ tests/` and `uv run mypy src/`) and fix any issues.
- [x] 8.3 Manually test `lexictl validate` with and without an `index.db` to confirm graceful degradation.
- [x] 8.4 Manually test `lexictl status` with and without an `index.db` to confirm the health line appears correctly.
