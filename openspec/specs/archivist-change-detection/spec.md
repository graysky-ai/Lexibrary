# archivist-change-detection Specification

## Purpose
TBD - created by archiving change archivist. Update Purpose after archive.
## Requirements
### Requirement: ChangeLevel enumeration
The system SHALL define a `ChangeLevel` enum in `src/lexibrary/archivist/change_checker.py` with values:
- `UNCHANGED` — source file has not changed
- `AGENT_UPDATED` — agent already updated the design file (or created it from scratch without footer)
- `CONTENT_ONLY` — source content changed but interface unchanged
- `CONTENT_CHANGED` — non-code file content changed (no interface to compare)
- `INTERFACE_CHANGED` — interface (public API) changed
- `NEW_FILE` — no existing design file

#### Scenario: All change levels defined
- **WHEN** the ChangeLevel enum is imported
- **THEN** it SHALL contain exactly six values: UNCHANGED, AGENT_UPDATED, CONTENT_ONLY, CONTENT_CHANGED, INTERFACE_CHANGED, NEW_FILE

### Requirement: check_change function
The system SHALL provide `check_change(source_path, project_root, content_hash, interface_hash) -> ChangeLevel` that classifies the change state of a source file by comparing current hashes against the existing design file's metadata footer.

#### Scenario: No existing design file
- **WHEN** `check_change()` is called and no design file exists at the mirror path
- **THEN** it SHALL return `NEW_FILE`

#### Scenario: Design file exists without metadata footer
- **WHEN** `check_change()` is called and the design file exists but has no HTML comment footer
- **THEN** it SHALL return `AGENT_UPDATED` (agent authored the file from scratch — trust content, add footer)

#### Scenario: Source file unchanged
- **WHEN** `check_change()` is called and `content_hash` matches the footer's `source_hash`
- **THEN** it SHALL return `UNCHANGED`

#### Scenario: Agent edited design file
- **WHEN** `check_change()` is called, the source file changed, AND the design file content hash differs from the footer's `design_hash`
- **THEN** it SHALL return `AGENT_UPDATED` (agent edited the design file — refresh footer hashes only, no LLM call)

#### Scenario: Non-code file content changed
- **WHEN** `check_change()` is called, the source file changed, the design file was NOT agent-edited, AND `interface_hash` is None
- **THEN** it SHALL return `CONTENT_CHANGED`

#### Scenario: Content changed but interface unchanged
- **WHEN** `check_change()` is called, the source file changed, the design file was NOT agent-edited, AND `interface_hash` matches the footer's `interface_hash`
- **THEN** it SHALL return `CONTENT_ONLY`

#### Scenario: Interface changed
- **WHEN** `check_change()` is called, the source file changed, the design file was NOT agent-edited, AND `interface_hash` differs from the footer's `interface_hash`
- **THEN** it SHALL return `INTERFACE_CHANGED`

### Requirement: Design content hashing excludes footer
When computing the design file content hash for agent-edit detection, the system SHALL hash only the frontmatter + body content, excluding the HTML comment footer. This ensures that footer-only updates (hash refreshes) do not trigger false agent-edit detection.

#### Scenario: Footer update does not change design hash
- **WHEN** only the HTML comment footer of a design file is updated (hashes refreshed)
- **THEN** the design content hash SHALL remain the same as before the update

