## 1. Convention Data Model & File Operations

- [x] 1.1 Create `src/lexibrary/artifacts/convention.py` with `ConventionFileFrontmatter` and `ConventionFile` Pydantic 2 models, plus `convention_slug()` and `convention_file_path()` functions
- [x] 1.2 Add `ConventionFile` and `ConventionFileFrontmatter` exports to `src/lexibrary/artifacts/__init__.py`
- [x] 1.3 Create `src/lexibrary/conventions/` package with `__init__.py`
- [x] 1.4 Create `src/lexibrary/conventions/parser.py` with `parse_convention_file()` — YAML frontmatter + markdown body parsing, rule extraction from first paragraph
- [x] 1.5 Create `src/lexibrary/conventions/serializer.py` with `serialize_convention_file()` — write ConventionFile to markdown string
- [x] 1.6 Write tests for convention model, slug generation, parser, and serializer

## 2. Convention Index

- [x] 2.1 Create `src/lexibrary/conventions/index.py` with `ConventionIndex` class — load from directory, `find_by_scope()`, `find_by_scope_limited()`, `search()`, `by_tag()`, `by_status()`, `names()`
- [x] 2.2 Export `ConventionIndex` from `src/lexibrary/conventions/__init__.py`
- [x] 2.3 Write tests for ConventionIndex — load, scope resolution, display limit truncation, search, filters

## 3. Config Extensions

- [x] 3.1 Add `ConventionConfig` model (with `lookup_display_limit`) and `ConventionDeclaration` model to `src/lexibrary/config/schema.py`
- [x] 3.2 Add `conventions: ConventionConfig` and `convention_declarations: list[ConventionDeclaration]` fields to `LexibraryConfig`
- [x] 3.3 Add `convention_file_tokens: int = 500` to `TokenBudgetConfig`
- [x] 3.4 Export `ConventionConfig` and `ConventionDeclaration` from `src/lexibrary/config/__init__.py`
- [x] 3.5 Write tests for config changes

## 4. Remove `local_conventions` from `.aindex` Pipeline

- [x] 4.1 Remove `local_conventions: list[str]` field from `AIndexFile` model in `src/lexibrary/artifacts/aindex.py`
- [x] 4.2 Remove `## Local Conventions` section from `src/lexibrary/artifacts/aindex_serializer.py`
- [x] 4.3 Remove convention parsing block from `src/lexibrary/artifacts/aindex_parser.py` (keep tolerance for legacy files)
- [x] 4.4 Remove `local_conventions=[]` from `generate_aindex()` in `src/lexibrary/indexer/generator.py`
- [x] 4.5 Update existing aindex tests to remove convention-related assertions

## 5. Convention CLI Commands

- [x] 5.1 Add `lexi convention new` command — create convention files with `--scope`, `--body`, `--tag`, `--title`, `--source` flags
- [x] 5.2 Add `lexi convention approve` command — promote draft to active
- [x] 5.3 Add `lexi convention deprecate` command — set status to deprecated
- [x] 5.4 Add `lexi conventions` list command — table display with `--tag`, `--status`, `--scope`, `--all` filters and optional path argument
- [x] 5.5 Register `convention` and `conventions` commands on the `lexi` app, update help text
- [x] 5.6 Write tests for all convention CLI commands

## 6. Lookup Convention Delivery Rewrite

- [x] 6.1 Replace `.aindex` parent-directory convention walk in `lexi lookup` (lexi_app.py) with `ConventionIndex.find_by_scope_limited()` call
- [x] 6.2 Render conventions grouped by scope with `[draft]` markers and truncation notice
- [x] 6.3 Write tests for lookup convention rendering — scope grouping, draft markers, truncation

## 7. Link Graph Convention Processing

- [x] 7.1 Extend `conventions` table schema in `src/lexibrary/linkgraph/schema.py` — add `source`, `status`, `priority` columns
- [x] 7.2 Rewrite convention processing in `src/lexibrary/linkgraph/builder.py` to read from `.lexibrary/conventions/` files instead of `.aindex` `local_conventions`
- [x] 7.3 Update `ConventionResult` and `get_conventions()` in `src/lexibrary/linkgraph/query.py` with extended metadata
- [x] 7.4 Update incremental update handler for convention changes
- [x] 7.5 Write tests for link graph convention indexing

## 8. Scaffolding & START_HERE Cleanup

- [x] 8.1 Add `.lexibrary/conventions/` with `.gitkeep` to `create_lexibrary_skeleton()` and `create_lexibrary_from_wizard()` in scaffolder
- [x] 8.2 Remove `convention_index` from BAML prompt (`baml_src/archivist_start_here.baml`) and output type (`baml_src/types.baml`)
- [x] 8.3 Update `_assemble_start_here()` in `src/lexibrary/archivist/start_here.py` — remove convention_index, add conventions pointer
- [x] 8.4 Write tests for scaffolding changes and START_HERE assembly
