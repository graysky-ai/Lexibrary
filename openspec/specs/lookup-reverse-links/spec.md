# lookup-reverse-links Specification

## Purpose
TBD - created by archiving change phase-10e-linkgraph-cli. Update Purpose after archive.
## Requirements
### Requirement: Lookup displays reverse dependencies from the link graph
The `lexi lookup <file>` command SHALL, after displaying the design file content and inherited conventions, query the link graph index for inbound links to the source file. If inbound `ast_import` links exist, a `## Dependents (imports this file)` section SHALL be displayed listing the source paths of importing files. If other inbound link types exist (wikilinks, Stack file refs, concept file refs), an `## Also Referenced By` section SHALL be displayed with the source name and link type annotation.

#### Scenario: File with import dependents
- **WHEN** running `lexi lookup src/services/auth_service.py` and the link graph contains `ast_import` links from `src/api/auth_controller.py` and `src/middleware/auth.py` targeting this file
- **THEN** the output includes a `## Dependents (imports this file)` section listing both files

#### Scenario: File with cross-artifact references
- **WHEN** running `lexi lookup src/services/auth_service.py` and the link graph contains a `wikilink` from the `Authentication` concept and a `stack_file_ref` from `ST-007`
- **THEN** the output includes an `## Also Referenced By` section listing `[[Authentication]] (concept wikilink)` and `[[ST-007]] (stack post)`

#### Scenario: File with both dependents and references
- **WHEN** running `lexi lookup src/services/auth_service.py` and both `ast_import` links and `wikilink` links reference this file
- **THEN** the output includes both the `## Dependents (imports this file)` section and the `## Also Referenced By` section

#### Scenario: File with no inbound links
- **WHEN** running `lexi lookup src/utils/helpers.py` and no link graph entries reference this file
- **THEN** neither the Dependents nor the Also Referenced By sections are displayed

### Requirement: Reverse links gracefully degrade when index is unavailable
If the link graph index (`index.db`) does not exist, is corrupt, or has a schema version mismatch, the `lexi lookup` command SHALL silently omit the reverse link sections. The design file content and inherited conventions SHALL still be displayed normally.

#### Scenario: Index file missing
- **WHEN** running `lexi lookup src/foo.py` and `.lexibrary/index.db` does not exist
- **THEN** the design file and conventions are displayed normally with no reverse link sections and no error message

#### Scenario: Index file corrupt
- **WHEN** running `lexi lookup src/foo.py` and `.lexibrary/index.db` exists but is corrupt (not a valid SQLite database)
- **THEN** the design file and conventions are displayed normally with no reverse link sections and no error message

#### Scenario: Index schema version mismatch
- **WHEN** running `lexi lookup src/foo.py` and `.lexibrary/index.db` has a schema version that does not match the current `SCHEMA_VERSION`
- **THEN** the design file and conventions are displayed normally with no reverse link sections and no error message

### Requirement: Reverse link display uses Rich console output
All reverse link output SHALL be rendered through the shared `rich.console.Console` instance. No bare `print()` calls SHALL be used.

#### Scenario: Dependents rendered via Rich
- **WHEN** reverse dependency data is available for a looked-up file
- **THEN** the Dependents and Also Referenced By sections are rendered through `console.print()`

### Requirement: Reverse link sections appear after conventions
The reverse link sections SHALL appear after the `## Applicable Conventions` section (if present) in the lookup output. The order SHALL be: design file content, applicable conventions, dependents, also referenced by.

#### Scenario: Output ordering with conventions and reverse links
- **WHEN** running `lexi lookup src/payments/processor.py` and both conventions and reverse links are available
- **THEN** the output order is: design file content, `## Applicable Conventions`, `## Dependents (imports this file)`, `## Also Referenced By`

#### Scenario: Output ordering without conventions
- **WHEN** running `lexi lookup src/utils/helpers.py` with no conventions but with reverse links
- **THEN** the output order is: design file content, `## Dependents (imports this file)`, `## Also Referenced By`

