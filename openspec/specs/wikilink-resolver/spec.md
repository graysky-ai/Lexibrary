# wikilink-resolver Specification

## Purpose
TBD - created by archiving change concepts-wiki. Update Purpose after archive.
## Requirements
### Requirement: ResolvedLink dataclass
The system SHALL define a `ResolvedLink` dataclass in `src/lexibrary/wiki/resolver.py` with fields:
- `raw` (str) — original link text including brackets
- `name` (str) — stripped link name
- `kind` (Literal["concept", "stack"]) — type of resolved link
- `path` (Path | None) — file path of the resolved target, None if concept has no file yet

#### Scenario: Create resolved concept link
- **WHEN** a `ResolvedLink` is created with `kind="concept"` and a valid path
- **THEN** all fields SHALL be stored correctly

#### Scenario: Create resolved stack link
- **WHEN** a `ResolvedLink` is created with `kind="stack"` and a valid path
- **THEN** all fields SHALL be stored correctly

### Requirement: UnresolvedLink dataclass
The system SHALL define an `UnresolvedLink` dataclass in `src/lexibrary/wiki/resolver.py` with fields:
- `raw` (str) — original link text including brackets
- `name` (str) — stripped link name
- `suggestions` (list[str]) — suggested concept names from fuzzy matching

#### Scenario: Create unresolved link with suggestions
- **WHEN** an `UnresolvedLink` is created with `suggestions=["JWT Auth", "JWT Tokens"]`
- **THEN** `suggestions` SHALL contain the provided suggestions

### Requirement: WikilinkResolver class
The system SHALL provide a `WikilinkResolver` class in `src/lexibrary/wiki/resolver.py` that:
- Is constructed with `concept_index: ConceptIndex` and `stack_dir: Path | None = None`
- Provides `resolve(link_text: str) -> ResolvedLink | UnresolvedLink`

Resolution order:
1. Strip `[[` and `]]` brackets if present
2. If name matches Stack pattern (`ST-` followed by digits) → scan `stack_dir` for matching `ST-NNN-*.md` file → return `ResolvedLink(kind="stack")` with path if found
3. Exact name/alias match via `concept_index.find()` → return `ResolvedLink(kind="concept")`
4. Fuzzy match via normalized substring against all concept names and aliases → if matches found, return `UnresolvedLink` with suggestions
5. No match → return `UnresolvedLink` with empty suggestions

#### Scenario: Resolve exact concept match
- **WHEN** `resolver.resolve("[[JWT Auth]]")` is called and "JWT Auth" exists in the index
- **THEN** it SHALL return a `ResolvedLink` with `kind="concept"` and `name="JWT Auth"`

#### Scenario: Resolve alias match
- **WHEN** `resolver.resolve("[[json-web-token]]")` is called and a concept has that alias
- **THEN** it SHALL return a `ResolvedLink` with `kind="concept"`

#### Scenario: Resolve stack post link
- **WHEN** `resolver.resolve("[[ST-001]]")` is called and `.lexibrary/stack/ST-001-some-slug.md` exists
- **THEN** it SHALL return a `ResolvedLink` with `kind="stack"`, `name="ST-001"`, and `path` pointing to the file

#### Scenario: Resolve stack post link not found
- **WHEN** `resolver.resolve("[[ST-999]]")` is called and no matching file exists
- **THEN** it SHALL return an `UnresolvedLink`

#### Scenario: Resolve unmatched with suggestions
- **WHEN** `resolver.resolve("[[JWT]]")` is called and "JWT Auth" exists but no exact match
- **THEN** it SHALL return an `UnresolvedLink` with `suggestions` containing `"JWT Auth"`

#### Scenario: Resolve completely unmatched
- **WHEN** `resolver.resolve("[[Nonexistent]]")` is called and no concepts match
- **THEN** it SHALL return an `UnresolvedLink` with empty `suggestions`

#### Scenario: Resolve without brackets
- **WHEN** `resolver.resolve("JWT Auth")` is called (no brackets)
- **THEN** it SHALL still resolve correctly (bracket stripping is optional)

### Requirement: resolve_all batch resolution
The `WikilinkResolver` SHALL provide `resolve_all(links: list[str]) -> tuple[list[ResolvedLink], list[UnresolvedLink]]` that resolves a list of link texts and returns them partitioned into resolved and unresolved.

#### Scenario: Batch resolve mixed links
- **WHEN** `resolver.resolve_all(["[[JWT Auth]]", "[[Nonexistent]]", "[[ST-001]]"])` is called
- **THEN** the resolved list SHALL contain 2 items (concept + stack) and the unresolved list SHALL contain 1 item

