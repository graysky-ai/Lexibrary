# linkgraph-blueprints Specification

## Purpose
TBD - created by archiving change phase-10g-linkgraph-cleanup. Update Purpose after archive.
## Requirements
### Requirement: Blueprint for linkgraph schema module

A blueprint design file SHALL exist at `blueprints/src/lexibrary/linkgraph/schema.md` describing the `schema.py` module's purpose, public API (`ensure_schema()`, `check_schema_version()`, `set_pragmas()`, `SCHEMA_VERSION`), DDL constants, and the 8-table + FTS5 schema structure.

#### Scenario: Blueprint exists and describes public API

- **WHEN** an agent reads `blueprints/src/lexibrary/linkgraph/schema.md`
- **THEN** the file SHALL describe all public functions and constants exported by `schema.py`, including `ensure_schema()`, `check_schema_version()`, `set_pragmas()`, and `SCHEMA_VERSION`

#### Scenario: Blueprint describes schema tables

- **WHEN** an agent reads the schema blueprint
- **THEN** the file SHALL list all 8 tables (`meta`, `artifacts`, `links`, `tags`, `aliases`, `conventions`, `build_log`, `artifacts_fts`) and their purposes

### Requirement: Blueprint for linkgraph builder module

A blueprint design file SHALL exist at `blueprints/src/lexibrary/linkgraph/builder.md` describing the `builder.py` module's purpose, the `IndexBuilder` class, `full_build()` and `incremental_update()` methods, link type extraction, and FTS population.

#### Scenario: Blueprint exists and describes builder API

- **WHEN** an agent reads `blueprints/src/lexibrary/linkgraph/builder.md`
- **THEN** the file SHALL describe the `IndexBuilder` class, `full_build()`, `incremental_update()`, and build pipeline steps

### Requirement: Blueprint for linkgraph query module

A blueprint design file SHALL exist at `blueprints/src/lexibrary/linkgraph/query.md` describing the `query.py` module's purpose, the `LinkGraph` read-only query interface, key query methods (reverse deps, tag search, FTS, alias resolution, convention inheritance, `traverse()` multi-hop), and graceful degradation behaviour.

#### Scenario: Blueprint exists and describes query API

- **WHEN** an agent reads `blueprints/src/lexibrary/linkgraph/query.md`
- **THEN** the file SHALL describe the `LinkGraph` class, all key query methods, and the graceful degradation pattern (returning `None` when `index.db` is missing or corrupt)

### Requirement: Blueprint for linkgraph init module

A blueprint design file SHALL exist at `blueprints/src/lexibrary/linkgraph/__init__.md` describing the `__init__.py` module's public API re-exports and the module's role as the entry point for the link graph subsystem.

#### Scenario: Blueprint describes re-exports

- **WHEN** an agent reads `blueprints/src/lexibrary/linkgraph/__init__.md`
- **THEN** the file SHALL list the public API symbols re-exported from `__init__.py`

### Requirement: START_HERE.md includes linkgraph in project topology

The `blueprints/START_HERE.md` file SHALL include the `linkgraph/` package in the project topology tree, showing `__init__.py`, `schema.py`, `builder.py`, and `query.py` with brief descriptions.

#### Scenario: Topology tree includes linkgraph

- **WHEN** an agent reads `blueprints/START_HERE.md`
- **THEN** the project topology tree SHALL contain a `linkgraph/` entry with its submodules listed

### Requirement: START_HERE.md includes linkgraph in package map

The `blueprints/START_HERE.md` Package Map table SHALL include a `linkgraph` row describing the package's role: SQLite link graph index for cross-artifact queries — reverse deps, tag search, FTS, alias resolution, convention inheritance, multi-hop traversal.

#### Scenario: Package map includes linkgraph

- **WHEN** an agent reads the Package Map table in `blueprints/START_HERE.md`
- **THEN** a `linkgraph` row SHALL describe the package's purpose and key capabilities

### Requirement: START_HERE.md includes linkgraph in navigation table

The Navigation by Intent table in `blueprints/START_HERE.md` SHALL include entries for link graph tasks, pointing agents to the appropriate blueprint files.

#### Scenario: Navigation table includes linkgraph tasks

- **WHEN** an agent looks up "Add / modify link graph" or "Change reverse dependency lookups" in the Navigation by Intent table
- **THEN** the table SHALL direct them to `blueprints/src/lexibrary/linkgraph/` files

### Requirement: Blueprints follow existing format conventions

All new blueprint files SHALL follow the existing blueprint format and conventions used in other `blueprints/src/lexibrary/` design files: a heading with the module path, a brief purpose section, interface contract or public API, dependencies, and key design notes.

#### Scenario: Blueprint format consistency

- **WHEN** a new linkgraph blueprint is compared to an existing blueprint (e.g., `blueprints/src/lexibrary/artifacts/design_file_serializer.md`)
- **THEN** the new blueprint SHALL use the same section structure and formatting conventions

