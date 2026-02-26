# lookup-conventions Specification

## Purpose
TBD - created by archiving change validation-status. Update Purpose after archive.
## Requirements
### Requirement: Lookup appends inherited Local Conventions
The `lexi lookup <file>` command SHALL, after displaying the design file content, retrieve applicable conventions via `ConventionIndex.find_by_scope_limited()` using the configured display limit. If any conventions are found, an `## Applicable Conventions` section SHALL be appended to the output. Conventions SHALL be grouped by scope, ordered from most general (project) to most specific (closest directory). Each convention SHALL display its rule text (first paragraph). Draft conventions SHALL be marked with `[draft]`. After conventions, if a link graph index is available, reverse link sections SHALL be appended.

When the total count of applicable conventions exceeds the display limit, a truncation notice SHALL be appended: `"... and N more — run \`lexi conventions <path>\` to see all"`.

#### Scenario: File in directory with conventions
- **WHEN** running `lexi lookup src/payments/processor.py` and a convention with `scope: src/payments` exists with rule "All monetary values use Decimal"
- **THEN** the output includes an "## Applicable Conventions" section with the scope header and the convention rule text

#### Scenario: File inherits conventions from multiple scopes
- **WHEN** running `lexi lookup src/payments/stripe/charge.py` and conventions exist with `scope: project` (rule "Use UTC everywhere") and `scope: src/payments` (rule "Use Decimal for money")
- **THEN** the output shows conventions grouped by scope, project-scoped first, then directory-scoped

#### Scenario: File with no applicable conventions
- **WHEN** running `lexi lookup src/utils/helpers.py` and no conventions have matching scopes
- **THEN** no "## Applicable Conventions" section is appended

#### Scenario: Conventions appear before reverse links
- **WHEN** running `lexi lookup src/payments/processor.py` and both conventions and reverse links are available
- **THEN** the `## Applicable Conventions` section appears before any `## Dependents` or `## Also Referenced By` sections

#### Scenario: Draft conventions marked
- **WHEN** running `lexi lookup src/auth/login.py` and a convention with `status: draft` applies
- **THEN** the convention SHALL be displayed with a `[draft]` marker

#### Scenario: Display limit truncation
- **WHEN** 8 conventions apply to a file and the display limit is 5
- **THEN** only 5 conventions SHALL be shown (most specific kept) and a truncation notice SHALL say "... and 3 more — run `lexi conventions <path>` to see all"

### Requirement: Convention inheritance stops at scope_root
The convention retrieval SHALL NOT include conventions scoped to directories above the configured `scope_root` directory. Project-scoped conventions (`scope: project`) SHALL always be included regardless of scope_root.

#### Scenario: Walk stops at scope_root boundary
- **WHEN** `scope_root` is configured as `src/` and the file is `src/api/auth.py`
- **THEN** conventions with `scope: src/api` and `scope: src` are included, but conventions with `scope: .` are NOT included. Conventions with `scope: project` ARE included.

### Requirement: Convention display format groups by scope
Conventions SHALL be displayed grouped by their scope, with the scope path as a header. Scopes SHALL be ordered from most general (project) to most specific (closest directory).

#### Scenario: Conventions grouped by scope
- **WHEN** conventions are found with scopes `project`, `src/`, and `src/payments/`
- **THEN** output shows project conventions first, then `src/` conventions, then `src/payments/` conventions

