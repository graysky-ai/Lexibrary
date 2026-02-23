## Why

The link graph (Phase 10a schema, 10c query interface) enables validation checks that were previously impractical due to O(N) file scanning. Bidirectional dependency consistency (D-048) was deferred from Phase 7 for exactly this reason. With the SQLite index available, these checks become cheap SQL queries. Additionally, `lexictl status` currently has no visibility into the link graph index, so operators cannot tell whether the index exists, is stale, or is healthy.

## What Changes

- Add three new validation checks to `lexictl validate`:
  - **Bidirectional dependency consistency** (info severity): verify that if file A lists B as a dependency in its design file, the link graph confirms B has an inbound link from A. Report mismatches. Resolves D-048 via D-072.
  - **Dangling link resolution**: verify all links in the graph point to artifacts that still exist on disk.
  - **Orphan artifact detection**: find artifacts recorded in the index whose backing files have been deleted.
- Add a **link graph health line** to `lexictl status` output showing artifact count, link count, and build timestamp (or "not built" if the index does not exist).
- All new checks gracefully degrade: if `index.db` is missing or corrupt, index-dependent checks are skipped and the status line reports the index as missing (info severity).

## Capabilities

### New Capabilities
- `linkgraph-validation`: Bidirectional dependency consistency check, dangling link resolution check, and orphan artifact detection check powered by the link graph SQL index.
- `linkgraph-status`: Link graph health reporting in `lexictl status` (artifact count, link count, build timestamp).

### Modified Capabilities
- `library-validation`: Adds three new link-graph-powered checks to the existing validation registry (bidirectional-deps, dangling-links, orphan-artifacts).
- `library-status`: Adds a link graph health summary line to the existing status dashboard.

## Impact

- **Code:** `src/lexibrarian/validator/checks.py` gains three new check functions. `src/lexibrarian/validator/__init__.py` registers them in `AVAILABLE_CHECKS`. `src/lexibrarian/cli/lexictl_app.py` status command gains a link graph health section. New dependency on `src/lexibrarian/linkgraph/query.py` (Phase 10c).
- **Dependencies:** No new external packages (sqlite3 is stdlib). Internal dependency on the Phase 10c `LinkGraph` query interface.
- **APIs:** No breaking changes. New checks are additive to the existing `AVAILABLE_CHECKS` registry. Status output gains one additional line.
- **Phase:** This is Phase 10f of the master plan, within the Phase 10 (Unified Link Graph) sub-phase structure.
