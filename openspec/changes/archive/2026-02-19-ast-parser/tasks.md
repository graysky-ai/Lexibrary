## 1. Data Models & Skeleton Renderer

- [x] 1.1 Create `src/lexibrary/ast_parser/__init__.py` with public API stubs (`parse_interface`, `hash_interface`, `compute_hashes`)
- [x] 1.2 Create `src/lexibrary/ast_parser/models.py` with Pydantic models: ParameterSig, ConstantSig, FunctionSig, ClassSig, InterfaceSkeleton
- [x] 1.3 Create `src/lexibrary/ast_parser/skeleton_render.py` with deterministic canonical renderer (version prefix, alphabetical sorting, compact line format)
- [x] 1.4 Add `hash_string()` to `src/lexibrary/utils/hashing.py`
- [x] 1.5 Write tests: `tests/test_ast_parser/test_models.py` and `tests/test_ast_parser/test_skeleton_render.py`

## 2. Grammar Registry & tree-sitter Spike

- [x] 2.1 Run tree-sitter-typescript spike: verify Python import patterns for TS/TSX sub-grammars, JS/JSX support, and version compatibility
- [x] 2.2 Add `[project.optional-dependencies] ast = [...]` to `pyproject.toml` with tree-sitter grammar packages
- [x] 2.3 Create `src/lexibrary/ast_parser/registry.py` with extension-to-grammar mapping, lazy loading, caching, and graceful fallback
- [x] 2.4 Write tests: `tests/test_ast_parser/test_registry.py` including grammar loading verification for all supported extensions

## 3. Python Parser

- [x] 3.1 Create `src/lexibrary/ast_parser/python_parser.py` with `extract_interface()` using tree-sitter queries
- [x] 3.2 Create test fixtures: `tests/test_ast_parser/fixtures/simple_module.py`, `classes_and_functions.py`, `empty_module.py`, `no_public_api.py`
- [x] 3.3 Write tests: `tests/test_ast_parser/test_python_parser.py` covering functions, classes, constants, `__all__`, private exclusion, async, staticmethod/classmethod/property, syntax errors

## 4. TypeScript Parser

- [x] 4.1 Create `src/lexibrary/ast_parser/typescript_parser.py` with `extract_interface()` for TS/TSX
- [x] 4.2 Create test fixtures: `tests/test_ast_parser/fixtures/simple_module.ts`, `classes_and_functions.ts`, `jsx_component.tsx`
- [x] 4.3 Write tests: `tests/test_ast_parser/test_typescript_parser.py` covering functions, classes, interfaces, type aliases, enums, exports, generics, TSX

## 5. JavaScript Parser

- [x] 5.1 Create `src/lexibrary/ast_parser/javascript_parser.py` with `extract_interface()` for JS/JSX
- [x] 5.2 Create test fixtures: `tests/test_ast_parser/fixtures/simple_module.js`, `jsx_component.jsx`
- [x] 5.3 Write tests: `tests/test_ast_parser/test_javascript_parser.py` covering functions, arrow functions, classes, exports (ES modules + CommonJS), JSX

## 6. Public API, Config Integration & Integration Tests

- [x] 6.1 Wire up `parse_interface()`, `hash_interface()`, `compute_hashes()` in `ast_parser/__init__.py`
- [x] 6.2 Add `ASTConfig` model to `src/lexibrary/config/schema.py` and add `ast` field to `LexibraryConfig`
- [x] 6.3 Add `[ast]` section to config template in `src/lexibrary/config/defaults.py`
- [x] 6.4 Consolidate inline `_compute_dir_hash()` in `indexer/generator.py` to use `hash_string()`
- [x] 6.5 Write integration tests: `tests/test_ast_parser/test_hash_interface.py` covering end-to-end hashing, hash stability, hash sensitivity to signature changes, hash insensitivity to body/order changes
- [x] 6.6 Run full test suite, linting, and type checking
