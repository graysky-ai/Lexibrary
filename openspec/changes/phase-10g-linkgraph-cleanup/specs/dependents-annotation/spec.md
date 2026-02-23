## ADDED Requirements

### Requirement: Serializer annotates Dependents section with lookup pointer

The design file serializer (`serialize_design_file()`) SHALL emit an italic annotation line immediately after the `## Dependents` heading that reads:

```
*(see `lexi lookup` for live reverse references)*
```

This annotation SHALL appear in every serialized design file, regardless of whether `data.dependents` is empty or populated.

#### Scenario: Empty dependents list

- **WHEN** `serialize_design_file()` is called with `data.dependents = []`
- **THEN** the `## Dependents` section SHALL contain the annotation line followed by `(none)` on the next non-blank line

#### Scenario: Non-empty dependents list

- **WHEN** `serialize_design_file()` is called with `data.dependents = ["src/api/auth.py", "src/middleware/session.py"]`
- **THEN** the `## Dependents` section SHALL contain the annotation line followed by bullet items `- src/api/auth.py` and `- src/middleware/session.py`

#### Scenario: Annotation is ignored by parser

- **WHEN** `parse_design_file()` is called on a design file containing the annotation line in the `## Dependents` section
- **THEN** the parsed `DesignFile.dependents` list SHALL NOT contain the annotation text (only actual bullet items are parsed)

### Requirement: Backward compatibility with existing design files

The serializer change SHALL NOT alter the behaviour of `parse_design_file()` or `parse_design_file_metadata()`. The annotation line uses markdown italic syntax (`*...*`) which is naturally filtered out by the parser's `_bullet_list()` function that only matches lines starting with `- `.

#### Scenario: Parse file with annotation and dependents

- **WHEN** `parse_design_file()` is called on a design file that contains both the annotation line and bullet-list dependents
- **THEN** the returned `DesignFile.dependents` SHALL contain only the bullet-list items, not the annotation

#### Scenario: Parse file without annotation (legacy format)

- **WHEN** `parse_design_file()` is called on a design file that was written before this change (no annotation line)
- **THEN** the parser SHALL succeed and return the dependents list as before

### Requirement: Gitignore includes index.db pattern

The project `.gitignore` and the `lexictl init` scaffolder SHALL ensure that `.lexibrary/index.db` is gitignored.

#### Scenario: New project initialization includes index.db pattern

- **WHEN** `lexictl init` runs `create_lexibrary_skeleton()` or `create_lexibrary_from_wizard()`
- **THEN** the project `.gitignore` SHALL contain a pattern matching `.lexibrary/index.db`

#### Scenario: Existing project gitignore already has pattern

- **WHEN** `lexictl init` runs and `.gitignore` already contains `.lexibrary/index.db`
- **THEN** the scaffolder SHALL NOT duplicate the pattern

### Requirement: Master plan sub-phase status updated

All Phase 10 sub-phases (10a through 10g) in `plans/v2-master-plan.md` SHALL be marked with **Done** status.

#### Scenario: Sub-phases marked done

- **WHEN** an agent reads `plans/v2-master-plan.md` after this change
- **THEN** all rows in the Phase 10 sub-phases table SHALL show status **Done**

### Requirement: Overview document consistency

The `lexibrary-overview.md` document SHALL accurately describe the link graph's behaviour: dependents are served at query time via `lexi lookup`, `index.db` is a gitignored rebuildable artifact, and the link graph degrades gracefully when the index is missing or corrupt.

#### Scenario: Overview describes query-time dependents

- **WHEN** an agent reads `lexibrary-overview.md`
- **THEN** the document SHALL state that reverse dependencies are available via `lexi lookup` queries against the link graph index, not written into design files

### Requirement: Phase 10 TODO comments resolved

All TODO comments added during Phase 10 implementation in the `linkgraph/` module and related integration points SHALL be resolved — either implemented, converted to tracked issues, or removed with justification.

#### Scenario: No unresolved Phase 10 TODOs in linkgraph

- **WHEN** a search for `TODO` is run across `src/lexibrary/linkgraph/`
- **THEN** no unresolved TODO comments related to Phase 10 implementation SHALL remain

### Requirement: Phase 10 tests pass with adequate coverage

All tests covering Phase 10 functionality (linkgraph schema, builder, query, pipeline integration, CLI integration, validation) SHALL pass. Test coverage for the `linkgraph/` module SHALL be verified.

#### Scenario: Test suite passes

- **WHEN** `uv run pytest --cov=lexibrary` is run
- **THEN** all Phase 10-related tests SHALL pass and the `linkgraph/` module SHALL have coverage reported
