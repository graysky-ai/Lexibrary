## 1. Project Scaffolding

- [x] 1.1 Create directory structure: `src/lexibrary/{config,ignore,utils,crawler,indexer,llm,tokenizer,daemon}/`, `tests/`, `baml_src/`, `tests/fixtures/sample_project/`
- [x] 1.2 Write `pyproject.toml` with project metadata, dependencies, and CLI entry points
- [x] 1.3 Write `.python-version` file with "3.12"
- [x] 1.4 Write `.gitignore` with Python defaults and Lexibrary-specific patterns
- [x] 1.5 Create `src/lexibrary/__init__.py` with `__version__ = "0.1.0"`
- [x] 1.6 Create `src/lexibrary/__main__.py` with CLI entry point
- [x] 1.7 Create empty `__init__.py` in all sub-packages
- [x] 1.8 Run `uv sync` and verify no import errors

## 2. Config System

- [x] 2.1 Create `src/lexibrary/config/schema.py` with Pydantic models (LLMConfig, TokenizerConfig, CrawlConfig, IgnoreConfig, DaemonConfig, OutputConfig, LexibraryConfig)
- [x] 2.2 Create `src/lexibrary/config/loader.py` with `find_config_file()` and `load_config()` functions
- [x] 2.3 Create `src/lexibrary/config/defaults.py` with `DEFAULT_CONFIG_TEMPLATE` string
- [x] 2.4 Create `src/lexibrary/config/__init__.py` re-exporting config functions
- [x] 2.5 Write tests: `tests/test_config/test_schema.py` (validation, defaults, invalid values)
- [x] 2.6 Write tests: `tests/test_config/test_loader.py` (find_config_file upward traversal, load_config with fixture, fallback to defaults)

## 3. Ignore System

- [x] 3.1 Create `src/lexibrary/ignore/gitignore.py` with `load_gitignore_specs()` function
- [x] 3.2 Create `src/lexibrary/ignore/patterns.py` for config pattern loading
- [x] 3.3 Create `src/lexibrary/ignore/matcher.py` with `IgnoreMatcher` class and `is_ignored()`, `should_descend()` methods
- [x] 3.4 Create `src/lexibrary/ignore/__init__.py` with `create_ignore_matcher()` factory and re-exports
- [x] 3.5 Write tests: `tests/test_ignore/test_matcher.py` (sample .gitignore, config patterns, hierarchical overrides, should_descend pruning)

## 4. Utilities

- [x] 4.1 Create `src/lexibrary/utils/hashing.py` with `hash_file()` function
- [x] 4.2 Create `src/lexibrary/utils/logging.py` with `setup_logging()` function
- [x] 4.3 Create `src/lexibrary/utils/paths.py` with `find_project_root()` function
- [x] 4.4 Create `src/lexibrary/utils/__init__.py` re-exporting utilities
- [x] 4.5 Write unit tests for `hash_file()` with known content
- [x] 4.6 Write unit tests for `find_project_root()` with tmp_path fixtures

## 5. CLI Skeleton

- [x] 5.1 Create `src/lexibrary/cli.py` with Typer app
- [x] 5.2 Implement `init` command with path argument and placeholder message
- [x] 5.3 Implement `crawl` command with path argument and placeholder message
- [x] 5.4 Implement `daemon` command with path argument and placeholder message
- [x] 5.5 Implement `status` command with path argument and placeholder message
- [x] 5.6 Implement `clean` command with path argument and placeholder message
- [x] 5.7 Verify `uv run lexi --help` works and shows all 5 commands
- [x] 5.8 Verify `uv run lexibrary --help` works (alias)
- [x] 5.9 Test placeholder commands execute without error

## 6. Verification & Testing

- [x] 6.1 Run full test suite: `uv run pytest tests/test_config tests/test_ignore -v`
- [x] 6.2 Verify all acceptance criteria from spec:
  - `uv sync` installs dependencies
  - `uv run lexi --help` shows help with all 5 subcommands
  - `uv run lexibrary --help` identical output
  - `load_config()` returns valid config with defaults
  - `load_config(path)` loads and validates fixture TOML
  - `IgnoreMatcher.is_ignored()` matches .gitignore patterns
  - `IgnoreMatcher.should_descend()` prunes ignored directories
  - `hash_file()` returns consistent SHA-256
- [x] 6.3 Ensure no type errors with `mypy` (strict mode)
- [x] 6.4 Ensure no linting errors with `ruff check`
