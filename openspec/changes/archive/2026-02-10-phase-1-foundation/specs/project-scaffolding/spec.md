## ADDED Requirements

### Requirement: Project directory structure
The system SHALL have a Python package structure with source code under `src/lexibrary/` and test code under `tests/`. Supporting directories for BAML, fixtures, and configuration SHALL exist.

#### Scenario: Directory structure exists after initialization
- **WHEN** running `uv sync` in the project root
- **THEN** the following directories are created: `src/lexibrary/`, `src/lexibrary/config/`, `src/lexibrary/ignore/`, `src/lexibrary/utils/`, `src/lexibrary/crawler/`, `src/lexibrary/indexer/`, `src/lexibrary/llm/`, `src/lexibrary/tokenizer/`, `src/lexibrary/daemon/`, `tests/`, `baml_src/`

### Requirement: Project metadata in pyproject.toml
The system SHALL declare the project name as "lexibrary", version "0.1.0", and include all required dependencies for config management, CLI, ignore patterns, tokenization, BAML, and HTTP operations.

#### Scenario: Dependencies are declared
- **WHEN** reading `pyproject.toml`
- **THEN** it contains Typer (>=0.15.0), Pydantic (>=2.0.0), Pathspec (>=0.12.0), Watchdog (>=4.0.0), Tiktoken (>=0.8.0), BAML-py (>=0.75.0), and HTTPx (>=0.27.0)

#### Scenario: Optional dependencies are declared
- **WHEN** reading `pyproject.toml` optional-dependencies
- **THEN** "dev" extras include Pytest, Pytest-asyncio, Pytest-cov, Ruff, Mypy, and Respx; "ollama" extra includes Ollama library

#### Scenario: CLI entry points are configured
- **WHEN** reading `pyproject.toml` project.scripts
- **THEN** both "lexi" and "lexibrary" commands map to "lexibrary.cli:app"

### Requirement: Python version is pinned
The system SHALL require Python 3.11+ and pin to Python 3.12 via `.python-version` file.

#### Scenario: Python version file exists
- **WHEN** reading `.python-version`
- **THEN** it contains exactly "3.12"

### Requirement: .gitignore is configured
The system SHALL exclude Python artifacts, virtual environments, Lexibrary caches, and generated BAML code.

#### Scenario: .gitignore contains project-specific patterns
- **WHEN** reading `.gitignore`
- **THEN** it includes patterns for `.aindex`, `.lexibrary_cache.json`, `.lexibrary.log`, `baml_client/`, and standard Python patterns (`__pycache__/`, `*.pyc`, `.venv/`, `venv/`)

### Requirement: Module initialization
The system SHALL have proper `__init__.py` files in all packages with version declaration.

#### Scenario: Root module declares version
- **WHEN** importing `lexibrary.__version__`
- **THEN** it returns "0.1.0"

#### Scenario: Root module can be run as a script
- **WHEN** running `python -m lexibrary`
- **THEN** it imports the CLI app without errors
