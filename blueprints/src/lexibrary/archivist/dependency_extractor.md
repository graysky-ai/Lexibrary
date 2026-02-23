# archivist/dependency_extractor

**Summary:** Extracts forward import dependencies from Python, TypeScript, and JavaScript source files using tree-sitter, resolving them to project-relative paths.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `extract_dependencies` | `(file_path, project_root) -> list[str]` | Parse imports via tree-sitter and resolve to sorted, deduplicated project-relative paths |

## Dependencies

- `lexibrarian.ast_parser.registry` -- `get_parser` for tree-sitter grammar lookup

## Dependents

- `lexibrarian.archivist.pipeline` -- populates `dependencies` field in generated design files

## Key Concepts

- Third-party and unresolvable imports are silently omitted
- Python resolution: tries `src/` layout then flat layout for both module files and packages (`__init__.py`)
- JS/TS resolution: only relative imports (`./`, `../`); tries literal path, common extensions (`.ts`, `.tsx`, `.js`, `.jsx`), then index files
- Returns empty list for unsupported file types (no tree-sitter grammar available)
