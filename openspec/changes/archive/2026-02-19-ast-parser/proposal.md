## Why

Phase 4 (Archivist) needs to detect whether a file's **public interface** changed or only its internals, so it can skip expensive LLM regeneration when signatures are unchanged. Currently, Lexibrary only has content-level SHA-256 hashing — any byte change triggers a full update. Adding AST-based interface extraction and a second "interface hash" enables two-tier change detection: content hash for "did anything change?" and interface hash for "did the public API change?"

## What Changes

- Add a new `ast_parser` library module that extracts public interface skeletons (function signatures, class names, constants, exports) from source files using tree-sitter
- Support Python, TypeScript/TSX, and JavaScript/JSX (6 file extensions total)
- Compute interface hashes from deterministic skeleton renderings for two-tier change detection
- Add `hash_string()` utility and consolidate existing inline hashing
- Add `ASTConfig` to the project configuration schema
- Add optional dependency group `lexibrary[ast]` for tree-sitter grammar packages
- **No new CLI commands** — this is a library module consumed by Phase 4

## Capabilities

### New Capabilities
- `ast-models`: Pydantic data models for interface skeletons (FunctionSig, ClassSig, ConstantSig, InterfaceSkeleton)
- `grammar-registry`: Extension-to-grammar mapping, lazy loading, caching, graceful fallback when grammars are missing
- `python-parser`: Tree-sitter based Python interface extraction (functions, classes, constants, `__all__` exports)
- `typescript-parser`: Tree-sitter based TypeScript/TSX interface extraction (functions, classes, interfaces, type aliases, enums, exports)
- `javascript-parser`: Tree-sitter based JavaScript/JSX interface extraction (functions, classes, exports)
- `skeleton-renderer`: Deterministic canonical text rendering of interface skeletons for hashing
- `interface-hashing`: Two-tier hashing API — content hash + interface hash from a single file path

### Modified Capabilities
- `utilities`: Adding `hash_string()` function and consolidating inline hashing from `indexer/generator.py`
- `config-system`: Adding `ASTConfig` section (enabled flag, language list) to `LexibraryConfig`

## Impact

- **New package**: `src/lexibrary/ast_parser/` (7 modules)
- **Dependencies**: `tree-sitter>=0.25.0,<0.26.0`, `tree-sitter-python>=0.25.0,<0.26.0`, `tree-sitter-javascript>=0.25.0,<0.26.0`, `tree-sitter-typescript>=0.23.0,<0.24.0` — all under optional `[ast]` extras group
- **Config**: New `ast:` section in `.lexibrary/config.yaml` and default template
- **Existing code**: `utils/hashing.py` gains `hash_string()`; `indexer/generator.py` inline hash consolidated
- **Phase**: This is Phase 3. Consumed by Phase 4 (Archivist) — no user-facing changes until then.
