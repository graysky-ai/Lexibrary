## MODIFIED Requirements

### Requirement: Generate Markdown from IandexData
`generate_iandex(data: IandexData) -> str` function in `src/lexibrary/indexer/generator.py`. When building file descriptions for the Child Map, the generator SHALL:
1. Check if a design file exists at `mirror_path(project_root, file)`
2. If yes → call `parse_design_file_frontmatter(design_file_path)` and use the `description` field
3. If no → fall back to the structural description: `"{Language} source ({N} lines)"`

This makes `.aindex` descriptions richer as design files are created, while maintaining backwards compatibility.

#### Scenario: File with design file gets frontmatter description
- **WHEN** `generate_iandex()` processes a file that has a corresponding design file
- **THEN** the Child Map description SHALL use the `description` from the design file's YAML frontmatter

#### Scenario: File without design file gets structural description
- **WHEN** `generate_iandex()` processes a file that has no corresponding design file
- **THEN** the Child Map description SHALL use the structural fallback format: `"{Language} source ({N} lines)"`

#### Scenario: Design file with empty description
- **WHEN** `generate_iandex()` processes a file whose design file has an empty description
- **THEN** the Child Map description SHALL fall back to the structural description
