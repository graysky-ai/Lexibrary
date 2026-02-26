## MODIFIED Requirements

### Requirement: Full build indexes local conventions from .aindex files
For each convention file in `.lexibrary/conventions/`, the builder SHALL:
1. Parse the convention file via `parse_convention_file()`
2. Insert a `kind='convention'` artifact with the convention file path, title from frontmatter, and the convention's status
3. Insert a row in the `conventions` table with `directory_path` (derived from scope — `"."` for project scope), `ordinal` (0-based order within that scope), `body` (full convention body), `source` (from frontmatter), `status` (from frontmatter), and `priority` (from frontmatter)
4. Extract `[[wikilinks]]` from the convention body and insert `convention_concept_ref` links
5. Insert an FTS row with body = rule + body text
6. Insert tags from `ConventionFileFrontmatter.tags`

#### Scenario: Convention file with project scope
- **WHEN** `full_build()` processes a convention file with `scope: project`
- **THEN** a convention artifact is inserted, a conventions table row is created with `directory_path="."`, and FTS is populated

#### Scenario: Convention file with directory scope
- **WHEN** `full_build()` processes a convention file with `scope: src/auth`
- **THEN** a convention artifact is inserted, a conventions table row is created with `directory_path="src/auth"`, and FTS is populated

#### Scenario: Convention text contains wikilinks
- **WHEN** a convention body contains `"All endpoints must use [[Authentication]] middleware"`
- **THEN** a `convention_concept_ref` link is created from the convention artifact to the `Authentication` concept artifact

#### Scenario: Convention with tags
- **WHEN** a convention file has `tags: ["python", "imports"]`
- **THEN** two tag rows are inserted linking the convention artifact to each tag

#### Scenario: Multiple conventions with same scope
- **WHEN** `full_build()` processes two convention files both with `scope: src/auth`
- **THEN** both get ordinal values (0 and 1) within the `src/auth` directory path

## ADDED Requirements

### Requirement: Conventions table extended schema
The `conventions` table SHALL include additional columns:
- `source` (TEXT NOT NULL DEFAULT 'user') — provenance: 'user', 'agent', or 'config'
- `status` (TEXT NOT NULL DEFAULT 'active') — lifecycle: 'draft', 'active', or 'deprecated'
- `priority` (INTEGER NOT NULL DEFAULT 0) — display ordering within scope

#### Scenario: Convention row with metadata
- **WHEN** a convention with `source: agent`, `status: draft`, `priority: -1` is indexed
- **THEN** the conventions table row SHALL have `source='agent'`, `status='draft'`, `priority=-1`

#### Scenario: Default column values
- **WHEN** a convention row is inserted without specifying source, status, or priority
- **THEN** defaults SHALL be `source='user'`, `status='active'`, `priority=0`
