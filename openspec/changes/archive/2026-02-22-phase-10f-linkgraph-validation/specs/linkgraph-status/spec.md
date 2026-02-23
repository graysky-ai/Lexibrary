## ADDED Requirements

### Requirement: Status displays link graph health when index exists
The `lexictl status` command SHALL display a link graph health line when `.lexibrary/index.db` exists and is readable. The line SHALL show the artifact count, link count, and build timestamp in the format: `Link graph: <N> artifacts, <M> links (built <ISO-8601-timestamp>)`.

#### Scenario: Index exists with data
- **WHEN** running `lexictl status` and `index.db` exists with 245 artifacts, 1203 links, and built_at of `2026-02-22T14:30:00Z`
- **THEN** the output includes `Link graph: 245 artifacts, 1,203 links (built 2026-02-22T14:30:00Z)`

#### Scenario: Index exists but is empty
- **WHEN** running `lexictl status` and `index.db` exists with 0 artifacts and 0 links
- **THEN** the output includes `Link graph: 0 artifacts, 0 links (built <timestamp>)`

### Requirement: Status displays not-built message when index is absent
The `lexictl status` command SHALL display `Link graph: not built (run lexictl update to create)` when `.lexibrary/index.db` does not exist.

#### Scenario: Index file does not exist
- **WHEN** running `lexictl status` and `index.db` does not exist
- **THEN** the output includes `Link graph: not built (run lexictl update to create)`

### Requirement: Status handles corrupt or version-mismatched index
The `lexictl status` command SHALL handle a corrupt `index.db` or schema version mismatch gracefully, displaying `Link graph: not built (run lexictl update to create)` rather than crashing.

#### Scenario: Index file is corrupt
- **WHEN** running `lexictl status` and `index.db` exists but is corrupt (not valid SQLite)
- **THEN** the output includes `Link graph: not built (run lexictl update to create)` and no exception is raised

#### Scenario: Index has wrong schema version
- **WHEN** running `lexictl status` and `index.db` has schema_version=1 but current code expects version 2
- **THEN** the output includes `Link graph: not built (run lexictl update to create)`

### Requirement: Status reads index metadata without full LinkGraph instantiation
The `lexictl status` command SHALL read the link graph health data using direct SQL queries against the `meta`, `artifacts`, and `links` tables. It SHALL NOT require instantiating the full `LinkGraph` query object.

#### Scenario: Status performs lightweight index read
- **WHEN** running `lexictl status` with a valid `index.db`
- **THEN** the command reads only `meta` key-value pairs and `COUNT(*)` from `artifacts` and `links` tables

### Requirement: Link graph health line appears in full dashboard mode only
The link graph health line SHALL appear in the full `lexictl status` dashboard output. It SHALL NOT appear in `--quiet` mode, which only reports error and warning counts.

#### Scenario: Quiet mode omits link graph line
- **WHEN** running `lexictl status --quiet`
- **THEN** the output does not contain any link graph health information

#### Scenario: Full mode includes link graph line
- **WHEN** running `lexictl status` (without --quiet)
- **THEN** the output includes the link graph health line
