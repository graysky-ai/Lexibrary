# dependency-extraction Specification

## Purpose
TBD - created by archiving change archivist. Update Purpose after archive.
## Requirements
### Requirement: Extract forward dependencies from source files
The system SHALL provide `extract_dependencies(file_path, project_root) -> list[str]` in `src/lexibrary/archivist/dependency_extractor.py` that uses tree-sitter to find import statements and resolves them to relative file paths within the project.

#### Scenario: Python absolute imports
- **WHEN** `extract_dependencies()` is called on a Python file with `from lexibrary.config.schema import LexibraryConfig`
- **THEN** the result SHALL include `src/lexibrary/config/schema.py` (resolved project-relative path)

#### Scenario: Python relative imports
- **WHEN** `extract_dependencies()` is called on a Python file with `from .module import X`
- **THEN** the result SHALL resolve the relative import to the correct project-relative path

#### Scenario: Third-party imports excluded
- **WHEN** `extract_dependencies()` is called on a Python file with `import requests`
- **THEN** `requests` SHALL NOT appear in the result (third-party package, not in project)

#### Scenario: TypeScript relative imports
- **WHEN** `extract_dependencies()` is called on a TypeScript file with `import { X } from './module'`
- **THEN** the result SHALL resolve to the correct project-relative path (trying `.ts`, `.js`, `/index.ts`, etc.)

#### Scenario: JavaScript imports
- **WHEN** `extract_dependencies()` is called on a JavaScript file with imports
- **THEN** relative imports SHALL be resolved; bare specifiers (npm packages) SHALL be excluded

#### Scenario: Non-code file returns empty
- **WHEN** `extract_dependencies()` is called on a `.yaml`, `.md`, or other non-code file
- **THEN** it SHALL return an empty list

#### Scenario: Unresolvable import gracefully omitted
- **WHEN** `extract_dependencies()` encounters an import that cannot be resolved to a file in the project
- **THEN** that import SHALL be silently omitted from the result

### Requirement: Python import resolution
The system SHALL provide `_resolve_python_import(module_path, project_root) -> str | None` that converts dotted module paths to file paths and verifies they exist under the project root.

#### Scenario: Resolve dotted module path
- **WHEN** `_resolve_python_import("lexibrary.config.schema", project_root)` is called
- **THEN** it SHALL return the relative path if `src/lexibrary/config/schema.py` exists

### Requirement: JavaScript/TypeScript import resolution
The system SHALL provide `_resolve_js_import(import_path, source_dir, project_root) -> str | None` that resolves relative import paths (`./ ../`) trying common extensions (`.ts`, `.js`, `.tsx`, `.jsx`, `/index.ts`, `/index.js`).

#### Scenario: Resolve relative JS import with extension inference
- **WHEN** `_resolve_js_import("./schema", source_dir, project_root)` is called and `schema.ts` exists
- **THEN** it SHALL return the project-relative path to `schema.ts`

