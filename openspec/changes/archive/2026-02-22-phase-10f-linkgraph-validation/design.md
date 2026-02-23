## Context

Lexibrary's `lexictl validate` command (Phase 7) runs library consistency checks via a registry of check functions in `src/lexibrary/validator/`. Currently, all checks operate by scanning the filesystem -- reading design files, concept files, and Stack posts directly. This is fine for checks like wikilink resolution and hash freshness, but makes certain graph-level checks impractical.

Bidirectional dependency consistency (D-048) was explicitly deferred from Phase 7 because it required scanning every design file to correlate dependency lists. Phase 10a introduced the SQLite link graph schema (`.lexibrary/index.db`) and Phase 10c provides a read-only query interface (`LinkGraph`). These checks are now cheap SQL queries.

The `lexictl status` dashboard currently reports artifact counts (design files, concepts, Stack posts), staleness, and validation errors/warnings. It has no visibility into the link graph index -- operators cannot tell if the index exists, when it was last built, or how many artifacts and links it contains.

**Current validator architecture:**
- Check functions follow `(project_root: Path, lexibrary_dir: Path) -> list[ValidationIssue]`
- Registered in `AVAILABLE_CHECKS` dict with `(check_fn, default_severity)` tuples
- `validate_library()` orchestrator handles severity/check filtering
- Report model supports `error`, `warning`, and `info` severity tiers (D-045)

**Current status command:**
- Full dashboard mode and `--quiet` single-line mode
- Runs `validate_library()` with `severity_filter="warning"` for error/warning counts
- Exit code: 0=clean, 1=errors, 2=warnings-only (D-046)

## Goals / Non-Goals

**Goals:**
- Add bidirectional dependency consistency check (info severity) to close D-048
- Add dangling link resolution check (verify all graph links resolve to existing files)
- Add orphan artifact detection (artifacts in index whose files have been deleted)
- Add link graph health line to `lexictl status` (artifact count, link count, build timestamp)
- Graceful degradation when `index.db` is absent, corrupt, or has a schema version mismatch
- Maintain read-only semantics for all validation (D-047)

**Non-Goals:**
- Auto-fixing index inconsistencies (that is the builder's job in Phase 10b/10d)
- Adding link graph checks to `--quiet` mode (quiet mode only reports error/warning counts)
- Building or rebuilding the index from within validate/status (read-only)
- Modifying the LinkGraph query interface (use what Phase 10c provides)
- Adding new severity tiers beyond the existing error/warning/info (D-045)

## Decisions

### D1: Check function signature stays unchanged

The existing check signature `(project_root, lexibrary_dir) -> list[ValidationIssue]` does not accept a database connection. Rather than changing the signature (which would require updating all existing checks), the new link-graph checks will open the database themselves using the known path `lexibrary_dir / "index.db"`.

**Rationale:** Minimises changes to existing code. The `LinkGraph.open()` factory method handles all connection setup (pragmas, schema version check). If the index is missing, `open()` returns `None` and the check returns an empty list.

**Alternative considered:** Passing an optional `LinkGraph` instance to all checks via a context object. Rejected because it adds complexity to 10 existing checks that do not need it, and the database open is cheap (SQLite, local file).

### D2: All link-graph checks are info severity

Bidirectional gaps, dangling links, and orphan artifacts are all reported at **info** severity, not error or warning.

**Rationale:** The link graph is a derived, potentially stale index. It may not reflect the current state of the filesystem if `lexictl update` has not been run recently. Reporting these as errors or warnings would create false alarms. The checks provide useful signals when the index is fresh, but they should not affect the exit code (which is driven by errors and warnings per D-046).

**Alternative considered:** Making dangling links a warning. Rejected because the root cause is a stale index, not a broken library.

### D3: Status reads the `meta` table directly

The `lexictl status` command will open `index.db` and read the `meta` table for `built_at`, plus `SELECT COUNT(*)` on `artifacts` and `links` tables.

**Rationale:** This is simpler and faster than instantiating the full `LinkGraph` query object. The status command only needs three values. Direct SQL on a known schema is appropriate here.

**Alternative considered:** Using `LinkGraph` query methods. Acceptable but unnecessary -- `LinkGraph` is designed for graph traversal queries, not metadata reads. A lightweight helper function (`read_index_health`) keeps the concerns separate.

### D4: Index-absent is reported as info, not silently skipped

When `index.db` does not exist, the status command prints `Link graph: not built (run lexictl update to create)` rather than omitting the line entirely.

**Rationale:** Operators need to know the index does not exist so they can build it. Silent omission would make the feature invisible.

### D5: Bidirectional check compares design file dependencies against graph links

The check queries all `ast_import` links from the graph and correlates them with `DesignFile.dependencies` lists parsed from the filesystem. Mismatches in either direction (dep listed but no graph link; graph link exists but not listed in deps) are reported.

**Rationale:** This catches two classes of issues: (1) design files with stale dependency lists, and (2) index entries that do not match the design file claims. Both are useful signals for library maintainers.

## Risks / Trade-offs

**[Risk] Index.db is stale or outdated** -- The link graph may not reflect recent code changes if `lexictl update` has not been run.
  - Mitigation: All link-graph checks use info severity. The status command shows the build timestamp so operators can judge freshness.

**[Risk] Opening index.db in each check function is slightly redundant** -- If multiple link-graph checks run in the same validation pass, each opens the database separately.
  - Mitigation: SQLite opens are very fast (< 1ms for a local file). WAL mode allows concurrent readers. The overhead is negligible compared to the file-scanning checks.

**[Risk] Bidirectional check requires both file parsing AND graph queries** -- It reads design files from disk (to get dependency lists) and queries the graph (to get actual links). If the graph is stale, mismatches are expected.
  - Mitigation: Info severity. The check message explicitly notes that the index may be stale.

**[Trade-off] No exit code impact from info-severity issues** -- The exit code remains 0 when only info issues exist. CI pipelines that want to enforce link graph consistency must explicitly check for info issues in JSON output.
  - Accepted: This matches the existing D-046 design. Info is advisory, not gating.
