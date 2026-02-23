## Context

Phase 10 (Unified Link Graph) builds a SQLite-backed index at `.lexibrary/index.db` for reverse dependency lookups, tag search, full-text search, and bidirectional validation. Sub-phases 10a through 10f implement the schema, builder, query interface, pipeline integration, CLI integration, and validation checks. Sub-phase 10g is the final cleanup pass.

The current state:
- `design_file_serializer.py` writes a `## Dependents` section that emits either bullet items from `data.dependents` or `(none)`. Per D-070, the pipeline never populates `DesignFile.dependents` -- dependents are served at query time via `lexi lookup`. Agents reading the `(none)` line have no indication of where to find reverse references.
- `blueprints/` has no design files for the `linkgraph/` modules (`schema.py`, `builder.py`, `query.py`).
- `blueprints/START_HERE.md` does not include `linkgraph/` in the project topology or package map.
- The `.gitignore` has no `index.db` pattern, and the `lexictl init` scaffolder does not ensure `index.db` is gitignored.
- `plans/v2-master-plan.md` has sub-phases 10b through 10g marked as "Planned".

## Goals / Non-Goals

**Goals:**
- Annotate the `## Dependents` section in serialized design files so agents know to use `lexi lookup` for reverse references
- Ensure backward compatibility: existing design files with hand-written dependents content are preserved
- Create blueprints for all `linkgraph/` modules and update `START_HERE.md`
- Mark Phase 10 complete in the master plan
- Ensure `index.db` is properly gitignored both at the project level and via the init scaffolder
- Clean up Phase 10 TODOs and verify test coverage

**Non-Goals:**
- Changing the `DesignFile` Pydantic model (the `dependents` field stays for backward compatibility)
- Modifying the `design_file_parser.py` (the annotation format is chosen to be naturally ignored by the existing bullet-list parser)
- Adding new features to the link graph beyond what sub-phases 10a-10f already implement
- Modifying any linkgraph runtime behavior

## Decisions

### D1: Annotation format for `## Dependents`

**Decision:** Emit an italic annotation line `*(see \`lexi lookup\` for live reverse references)*` immediately after the `## Dependents` heading, before any bullet items.

**Rationale:** The annotation must be:
1. **Visible to agents** reading the markdown so they know where to look for dependents
2. **Ignored by the parser** -- the existing `_bullet_list("Dependents")` in `design_file_parser.py` only picks up lines starting with `- `, so an italic line starting with `*` is naturally filtered out
3. **Non-breaking** for existing tooling that parses design files

**Alternatives considered:**
- HTML comment (`<!-- ... -->`): Invisible to agents reading rendered markdown; defeats the purpose
- Replacing the section entirely: Breaks backward compatibility with files that have hand-written dependents
- Adding to the section heading (`## Dependents (query-time)`): Changes section name, breaks parser section detection

### D2: Handling existing hand-written dependents

**Decision:** When `data.dependents` is non-empty, emit both the annotation line AND the bullet items. When empty, emit the annotation line followed by `(none)`.

**Rationale:** Some design files may have been hand-edited by agents to include dependents. The annotation tells agents the canonical source is `lexi lookup`, but the existing content is preserved for backward compatibility. The serializer already handles both cases (empty and non-empty); we just prepend the annotation.

### D3: `index.db` gitignore pattern

**Decision:** Add `.lexibrary/index.db` to the patterns that `_ensure_daemon_files_gitignored` manages (or create a similar helper). Also add it to the project `.gitignore`.

**Rationale:** The master plan explicitly states: "`index.db` must be in `.gitignore` -- `lexictl init` scaffolder must include it." The current `.gitignore` covers `.lexibrary/**/*.md` and `.lexibrary/**/.aindex` but not `.db` files. Since `index.db` is a derived, rebuildable artifact, it must not be version-controlled.

**Alternative:** Rely on users adding it manually. Rejected -- this is a footgun; a large `.db` file committed to git causes repository bloat.

### D4: Blueprint scope

**Decision:** Create blueprint design files for `linkgraph/schema.py`, `linkgraph/builder.py`, `linkgraph/query.py`, and `linkgraph/__init__.py`. Update `START_HERE.md` with the `linkgraph/` entry in the project topology tree and in the package map and navigation tables.

**Rationale:** The blueprints navigation protocol requires that every source module has a corresponding design file. The linkgraph modules were added in Phase 10 without blueprints.

## Risks / Trade-offs

- **[Annotation breaks third-party parsers]** Any external tool that parses the `## Dependents` section by reading all non-blank lines (not just `- ` lines) would pick up the annotation as content. **Mitigation:** The annotation uses markdown italic format (`*...*`) which is visually and syntactically distinct from bullet items. The risk is low since the design file format is Lexibrary-internal.

- **[Stale blueprints if linkgraph modules change]** Blueprints for `builder.py` and `query.py` describe modules that may still be under development (10b, 10c). **Mitigation:** Blueprints are written based on the current implementation state and the master plan specifications. They can be updated as modules evolve.

- **[Missing `index.db` in existing projects]** Projects initialized before this change won't have the `index.db` gitignore pattern. **Mitigation:** `lexictl setup --update` is the mechanism for updating existing projects. Document this in the overview. Users running `lexictl init` on new projects will get it automatically.
