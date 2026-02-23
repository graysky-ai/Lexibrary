# linkgraph/health

**Summary:** Lightweight index health helper that reads artifact/link counts and the `built_at` timestamp from `index.db` without instantiating the full `LinkGraph` query interface. Designed for `lexictl status` and validation checks that need quick metadata.

## Interface

| Name | Signature / Fields | Purpose |
| --- | --- | --- |
| `IndexHealth` | dataclass: `artifact_count: int \| None`, `link_count: int \| None`, `built_at: str \| None` | Summary of the link graph index state; all fields `None` when index is absent, corrupt, or has a schema version mismatch |
| `read_index_health` | `(project_root: Path) -> IndexHealth` | Open `.lexibrary/index.db`, set pragmas, verify schema version, read `COUNT(*)` from `artifacts` and `links` tables and `built_at` from `meta` table; returns all-`None` `IndexHealth` for graceful degradation |

## Graceful Degradation

`read_index_health()` returns `IndexHealth(artifact_count=None, link_count=None, built_at=None)` when:

- The database file does not exist
- The database is corrupt (cannot be opened or queried)
- The schema version is missing or does not match `SCHEMA_VERSION`
- Any `sqlite3.Error` or `OSError` is raised during the read

The connection is always closed in a `finally` block with `contextlib.suppress(Exception)`.

## Dependencies

- `lexibrarian.linkgraph.schema` -- `SCHEMA_VERSION`, `check_schema_version`, `set_pragmas`
- `lexibrarian.utils.paths` -- `LEXIBRARY_DIR`

## Dependents

- `lexibrarian.linkgraph.__init__` -- eagerly re-exports `IndexHealth`, `read_index_health`
- `lexibrarian.cli.lexictl_app` -- `status` command imports `read_index_health` for dashboard display
