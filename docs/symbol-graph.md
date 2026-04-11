# Symbol Graph

The symbol graph is a SQLite database at `.lexibrary/symbols.db` that indexes
code relationships below the file level: function and method definitions, call
edges, class hierarchy, enum membership, and module-level constants.

It is a companion to the [link graph](link-graph.md). The link graph records
edges between *artifacts and files*; the symbol graph records edges between
*symbols within files*.

## Status of this feature

- **Phase 1:** schema and wiring. `.lexibrary/symbols.db` is created but
  remains empty.
- **Phase 2 (current):** Python function, method, and class definitions
  plus call edges, exposed through `lexi trace`, `lexi search --type symbol`,
  and a new "Key symbols" section in `lexi lookup --full`. TypeScript and
  JavaScript extraction records definitions; call resolution for those
  languages is intra-file fuzzy matching only until Phase 6.
- **Phase 3:** class hierarchy edges.
- **Phase 4:** enum members and module-level constants.
- **Phase 5:** design-file enrichment with call paths, enum roles, and data
  flows.
- **Phase 6:** composition edges and TypeScript/JavaScript cross-file
  resolution.

## Storage

The database lives at `.lexibrary/symbols.db` alongside `index.db`. It is
gitignored by default and rebuilt from source on every `lexictl update`. It is
safe to delete — the next update regenerates it.

## Configuration

```yaml
# .lexibrary/config.yaml
symbols:
  enabled: true
```

Set `enabled: false` to skip symbol extraction entirely (saves a small amount
of time during `lexictl update`; disables all symbol-level queries).

## Relationship to the link graph

| Scope | File | Example edge |
|-------|------|-------------|
| Artifact / file level | `.lexibrary/index.db` | `pipeline.py` imports `builder.py` |
| Symbol level | `.lexibrary/symbols.db` | `update_project()` calls `build_index()` at line 1525 |

Both databases are populated during the same `lexictl update` run. Neither
depends on the other at schema level, but the services layer joins them for
commands like `lexi lookup` and `lexi search`.

## Commands

### `lexi trace <symbol>`

Shows callers, callees, and unresolved external calls for every symbol
matching the given name.

- Pass a **bare name** (`update_project`) to match any symbol with that
  name; multiple matches render one section per hit.
- Pass a **fully-qualified name**
  (`lexibrary.archivist.pipeline.update_project`) — any argument
  containing a `.` is matched exactly against `qualified_name`.
- Use `--file <path>` to narrow a bare-name match to a single file when
  the same symbol name exists in multiple modules.

```
$ lexi trace update_project

## lexibrary.archivist.pipeline.update_project  [function]
`src/lexibrary/archivist/pipeline.py:1412`

### Callers
| Caller                          | Location                              |
|---------------------------------|---------------------------------------|
| lexibrary.cli.lexictl_app.update| src/lexibrary/cli/lexictl_app.py:312  |

### Callees
| Callee                                           | Location                                 |
|--------------------------------------------------|------------------------------------------|
| lexibrary.linkgraph.builder.build_index          | src/lexibrary/archivist/pipeline.py:1525 |
| lexibrary.symbolgraph.builder.build_symbol_graph | src/lexibrary/archivist/pipeline.py:1534 |

### Unresolved callees (external or dynamic)
| Name                | Line |
|---------------------|------|
| logger.info         | 1456 |
| logger.exception    | 1476 |
```

If the symbol's file has a stale `last_hash` in `symbols.db`, `lexi trace`
prints a `Symbol graph may be stale for <file> — run lexi design update
<file> to refresh.` warning on stderr and still renders the (possibly
outdated) results. If no symbol matches, the command exits with code 1
and hints at `lexi design update` and `lexi search --type symbol`.

### `lexi search --type symbol <query>`

LIKE-search on `symbols.name` and `symbols.qualified_name`. Returns a
`file:line` for each hit. Unlike the artifact search path this does not
support `--tag` or any stack-only flags; combining them exits with code 1
and an error explaining the mismatch. `--limit` still applies.

### `lexi lookup <file> --full`

The `Key symbols` section lists the file's public functions, classes, and
methods with caller and callee counts — useful for sizing refactor blast
radius before editing. Methods are grouped under their class. The list is
capped at 10 rows; if the file defines more public symbols, a trailing
`… and N more` line is appended. The section is omitted when
`symbols.enabled` is `false` or `symbols.db` is missing.

## See also

- Concept: [[Symbol Graph]] (`CN-021`)
- Concept: [[Call Edge]] (`CN-022`)
- Concept: [[Symbol Resolution]] (`CN-023`)
- Playbook: [[Tracing a symbol with lexi trace]] (`PB-008`)
- [Link Graph](link-graph.md)
- [How It Works](how-it-works.md)
