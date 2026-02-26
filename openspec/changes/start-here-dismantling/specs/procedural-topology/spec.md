## ADDED Requirements

### Requirement: generate_topology function
The system SHALL provide `generate_topology(project_root: Path) -> Path` in `src/lexibrary/archivist/topology.py` that generates `.lexibrary/TOPOLOGY.md` from `.aindex` billboard summaries.

The function SHALL:
1. Call `_build_procedural_topology(project_root)` to build the annotated tree
2. Wrap the tree in a markdown document with `# Project Topology` heading
3. Write the result to `.lexibrary/TOPOLOGY.md` using `atomic_write()`
4. Return the output path

#### Scenario: Generate TOPOLOGY.md for project with .aindex files
- **WHEN** `generate_topology()` is called on a project with `.aindex` files
- **THEN** `.lexibrary/TOPOLOGY.md` SHALL be written with an annotated directory tree

#### Scenario: Generate TOPOLOGY.md for project without .aindex files
- **WHEN** `generate_topology()` is called on a project with no `.aindex` files
- **THEN** `.lexibrary/TOPOLOGY.md` SHALL be written with a placeholder message

### Requirement: _build_procedural_topology function
The system SHALL provide `_build_procedural_topology(project_root: Path) -> str` that reads all `.aindex` files in the `.lexibrary/` mirror tree and builds an adaptive-depth indented tree with billboard annotations.

The function SHALL:
1. Find all `.aindex` files under `.lexibrary/` using `parse_aindex()`
2. Extract `directory_path`, `billboard`, and child entry count from each
3. Apply adaptive depth filtering based on project scale
4. Render an indented tree with billboard annotations

#### Scenario: Small project shows full tree
- **WHEN** `_build_procedural_topology()` is called on a project with 10 or fewer directories in `.aindex` data
- **THEN** the output SHALL include all directories at all depths

#### Scenario: Medium project uses depth limit with hotspots
- **WHEN** `_build_procedural_topology()` is called on a project with 11-40 directories
- **THEN** the output SHALL show directories at depth ≤2 plus any directory with more than 5 child entries (hotspots)

#### Scenario: Large project uses shallow depth with hotspots
- **WHEN** `_build_procedural_topology()` is called on a project with 41+ directories
- **THEN** the output SHALL show directories at depth ≤1 plus hotspot directories

#### Scenario: Billboard annotations included
- **WHEN** `_build_procedural_topology()` renders a directory entry
- **THEN** the output SHALL include the billboard text from the corresponding `.aindex` file in the format `dir_name/ -- billboard text`

#### Scenario: Hidden children count shown
- **WHEN** a directory has child directories that are filtered out by the depth limit
- **THEN** the output SHALL append `(N subdirs)` to indicate hidden children

#### Scenario: No .lexibrary directory
- **WHEN** `_build_procedural_topology()` is called on a project with no `.lexibrary/` directory
- **THEN** the output SHALL return `(no .lexibrary directory found)`

#### Scenario: No .aindex files found
- **WHEN** `_build_procedural_topology()` is called on a project where `.lexibrary/` exists but contains no `.aindex` files
- **THEN** the output SHALL return `(no .aindex files found -- run 'lexi update' first)`

#### Scenario: Root billboard used as header
- **WHEN** a root-level `.aindex` file exists with a billboard summary
- **THEN** the first line of the tree SHALL be `project_name/ -- billboard_text`

### Requirement: Adaptive depth thresholds
The depth algorithm SHALL use these thresholds:
- Small (≤10 directories): `display_depth = max_depth`, no hotspot filtering
- Medium (11-40 directories): `display_depth = 2`, `hotspot_threshold = 5`
- Large (41+ directories): `display_depth = 1`, `hotspot_threshold = 5`

Directory count is the number of unique `.aindex` files found.

#### Scenario: Threshold boundaries
- **WHEN** a project has exactly 10 directories
- **THEN** it SHALL be classified as "small" (full tree shown)

#### Scenario: Medium threshold boundary
- **WHEN** a project has exactly 11 directories
- **THEN** it SHALL be classified as "medium" (depth ≤2 + hotspots)

#### Scenario: Large threshold boundary
- **WHEN** a project has exactly 41 directories
- **THEN** it SHALL be classified as "large" (depth ≤1 + hotspots)
