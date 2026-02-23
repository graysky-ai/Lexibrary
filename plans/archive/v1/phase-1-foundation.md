# Phase 1: Foundation

**Goal:** Project scaffolding, config system, ignore matching, utilities, and a working CLI skeleton.
**Milestone:** `uv run lexi --help` prints help text.
**Depends on:** Nothing (this is the root phase).

---

## 1.1 Project Scaffolding

### Files to create

| File | Purpose |
|------|---------|
| `pyproject.toml` | Project metadata, dependencies, build config, CLI entry points |
| `.python-version` | Pin to `3.12` |
| `.gitignore` | Python defaults + `.aindex`, `.lexibrary_cache.json`, `.lexibrary.log`, `baml_client/` |
| `src/lexibrary/__init__.py` | `__version__ = "0.1.0"` |
| `src/lexibrary/__main__.py` | `from lexibrary.cli import app; app()` |

### `pyproject.toml` specification

```toml
[project]
name = "lexibrary"
version = "0.1.0"
description = "AI-friendly codebase indexer — creates .aindex files for LLM context navigation"
readme = "README.md"
license = "MIT"
requires-python = ">=3.11"
authors = [{ name = "Shann Gray" }]

dependencies = [
    "typer>=0.15.0",
    "rich>=13.0.0",
    "pydantic>=2.0.0",
    "pathspec>=0.12.0",
    "watchdog>=4.0.0",
    "tiktoken>=0.8.0",
    "baml-py>=0.75.0",
    "httpx>=0.27.0",
    "tomli-w>=1.0.0",
]

[project.optional-dependencies]
ollama = ["ollama>=0.4.0"]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.24.0",
    "pytest-cov>=5.0.0",
    "ruff>=0.8.0",
    "mypy>=1.13.0",
    "respx>=0.22.0",
]

[project.scripts]
lexibrary = "lexibrary.cli:app"
lexi = "lexibrary.cli:app"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/lexibrary"]

[tool.ruff]
target-version = "py311"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP", "B", "A", "SIM"]

[tool.mypy]
python_version = "3.11"
strict = true

[tool.pytest.ini_options]
testpaths = ["tests"]
```

### Steps
1. Create all directories: `src/lexibrary/`, `src/lexibrary/config/`, `src/lexibrary/crawler/`, `src/lexibrary/indexer/`, `src/lexibrary/llm/`, `src/lexibrary/tokenizer/`, `src/lexibrary/daemon/`, `src/lexibrary/ignore/`, `src/lexibrary/utils/`, `tests/`, `tests/fixtures/sample_project/`, `baml_src/`
2. Write `pyproject.toml`
3. Write `.python-version` containing `3.12`
4. Write `.gitignore`
5. Write `src/lexibrary/__init__.py` and `__main__.py`
6. Place empty `__init__.py` in every sub-package
7. Run `uv sync` to install dependencies and create `uv.lock`
8. Verify: `uv run python -m lexibrary` runs without import errors

---

## 1.2 Config System

### Files

| File | Purpose |
|------|---------|
| `src/lexibrary/config/__init__.py` | Re-export `LexibraryConfig`, `load_config` |
| `src/lexibrary/config/schema.py` | Pydantic models |
| `src/lexibrary/config/loader.py` | Find config file, load + validate |
| `src/lexibrary/config/defaults.py` | Default `lexibrary.toml` template string for `init` command |

### `schema.py` — Pydantic Models

```python
from __future__ import annotations
from pathlib import Path
from pydantic import BaseModel, Field

class LLMConfig(BaseModel):
    provider: str = "anthropic"
    model: str = "claude-sonnet-4-5-20250514"
    api_key_env: str = "ANTHROPIC_API_KEY"
    api_key: str | None = None
    base_url: str = ""
    max_retries: int = 3
    timeout: int = 60

class TokenizerConfig(BaseModel):
    backend: str = "tiktoken"
    model: str = "cl100k_base"

class CrawlConfig(BaseModel):
    root: str = "."
    max_file_size_kb: int = 512
    max_files_per_llm_batch: int = 10
    binary_extensions: list[str] = Field(default_factory=lambda: [
        ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg",
        ".woff", ".woff2", ".ttf", ".eot",
        ".zip", ".tar", ".gz", ".bz2",
        ".exe", ".dll", ".so", ".dylib",
        ".pdf", ".doc", ".docx",
        ".mp3", ".mp4", ".wav", ".avi",
        ".pyc", ".pyo", ".class",
        ".sqlite", ".db",
    ])
    summary_max_tokens: int = 80
    dir_summary_max_tokens: int = 150

class IgnoreConfig(BaseModel):
    use_gitignore: bool = True
    additional_patterns: list[str] = Field(default_factory=lambda: [
        ".aindex", "lexibrary.toml", ".env", ".env.*",
        "*.lock", "node_modules/", "__pycache__/", ".git/", ".venv/", "venv/",
    ])

class DaemonConfig(BaseModel):
    debounce_seconds: float = 2.0
    full_sweep_interval_minutes: int = 30
    log_file: str = ".lexibrary.log"

class OutputConfig(BaseModel):
    filename: str = ".aindex"
    include_token_counts: bool = True

class LexibraryConfig(BaseModel):
    llm: LLMConfig = Field(default_factory=LLMConfig)
    tokenizer: TokenizerConfig = Field(default_factory=TokenizerConfig)
    crawl: CrawlConfig = Field(default_factory=CrawlConfig)
    ignore: IgnoreConfig = Field(default_factory=IgnoreConfig)
    daemon: DaemonConfig = Field(default_factory=DaemonConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
```

### `loader.py` — Key Logic

```python
import tomllib
from pathlib import Path
from .schema import LexibraryConfig

def find_config_file(start: Path | None = None) -> Path | None:
    """Walk upward from start (default CWD) to find lexibrary.toml."""
    current = (start or Path.cwd()).resolve()
    while True:
        candidate = current / "lexibrary.toml"
        if candidate.is_file():
            return candidate
        if current == current.parent:
            return None
        current = current.parent

def load_config(config_path: Path | None = None) -> LexibraryConfig:
    """Load and validate configuration. Returns all-defaults if no file found."""
    if config_path is None:
        config_path = find_config_file()
    if config_path is None:
        return LexibraryConfig()
    with open(config_path, "rb") as f:
        raw = tomllib.load(f)
    return LexibraryConfig.model_validate(raw)
```

### `defaults.py` — Template for `init` command

Contains a `DEFAULT_CONFIG_TEMPLATE: str` — the full `lexibrary.toml` content with comments, used by the `lexi init` command to write a starter config.

### Tests
- `tests/test_config/test_schema.py`: Validate defaults, validate overrides, test invalid values raise `ValidationError`
- `tests/test_config/test_loader.py`: Test `find_config_file` walks upward correctly, test `load_config` with fixture TOML file, test fallback to all-defaults when no file

---

## 1.3 Ignore System

### Files

| File | Purpose |
|------|---------|
| `src/lexibrary/ignore/__init__.py` | Re-export `IgnoreMatcher`, `create_ignore_matcher` |
| `src/lexibrary/ignore/gitignore.py` | Parse `.gitignore` files using `pathspec` |
| `src/lexibrary/ignore/patterns.py` | Load additional patterns from config |
| `src/lexibrary/ignore/matcher.py` | Combined matcher with a single `is_ignored(path) -> bool` |

### `gitignore.py` — Key Logic

```python
import pathspec
from pathlib import Path

def load_gitignore_specs(root: Path) -> list[tuple[Path, pathspec.PathSpec]]:
    """Find all .gitignore files under root and parse each one.

    Returns list of (directory, spec) tuples sorted root-first.
    Handles hierarchical .gitignore: a .gitignore in a subdirectory
    only applies to paths under that subdirectory.
    """
    specs = []
    for gitignore_path in root.rglob(".gitignore"):
        lines = gitignore_path.read_text().splitlines()
        spec = pathspec.PathSpec.from_lines("gitwildmatch", lines)
        specs.append((gitignore_path.parent, spec))
    return sorted(specs, key=lambda t: len(t[0].parts))
```

### `matcher.py` — Combined Matcher

```python
from pathlib import Path
import pathspec

class IgnoreMatcher:
    """Combines .gitignore specs, config patterns, and built-in patterns."""

    def __init__(
        self,
        gitignore_specs: list[tuple[Path, pathspec.PathSpec]],
        config_spec: pathspec.PathSpec,
        root: Path,
    ):
        self._gitignore_specs = gitignore_specs
        self._config_spec = config_spec
        self._root = root

    def is_ignored(self, path: Path) -> bool:
        """Check if a path should be ignored.

        Tests against config patterns first (cheap), then .gitignore specs.
        Path is relative to root for matching.
        """
        rel = path.relative_to(self._root)
        rel_str = str(rel)

        # Config patterns
        if self._config_spec.match_file(rel_str):
            return True

        # Gitignore specs (most specific directory first)
        for git_dir, spec in reversed(self._gitignore_specs):
            if path == git_dir or git_dir in path.parents:
                git_rel = str(path.relative_to(git_dir))
                if spec.match_file(git_rel):
                    return True

        return False

    def should_descend(self, directory: Path) -> bool:
        """Check if crawler should enter this directory.

        Pruning entire directories early saves traversal time.
        """
        return not self.is_ignored(directory)
```

### Factory function

```python
def create_ignore_matcher(config: LexibraryConfig, root: Path) -> IgnoreMatcher:
    """Build an IgnoreMatcher from config and .gitignore files."""
    gitignore_specs = []
    if config.ignore.use_gitignore:
        gitignore_specs = load_gitignore_specs(root)

    config_spec = pathspec.PathSpec.from_lines(
        "gitwildmatch", config.ignore.additional_patterns
    )

    return IgnoreMatcher(gitignore_specs, config_spec, root)
```

### Tests
- `tests/test_ignore/test_matcher.py`: Test with sample `.gitignore`, test config patterns, test hierarchical `.gitignore` overrides, test `should_descend` prunes directories
- Use `tmp_path` fixtures to create test directory trees

---

## 1.4 Utilities

### Files

| File | Purpose |
|------|---------|
| `src/lexibrary/utils/__init__.py` | Re-exports |
| `src/lexibrary/utils/hashing.py` | `hash_file(path) -> str` — SHA-256 hex digest |
| `src/lexibrary/utils/logging.py` | `setup_logging(verbose, log_file)` — configure stdlib logging + rich handler |
| `src/lexibrary/utils/paths.py` | `find_project_root(start) -> Path` — find root by looking for `.git` or `lexibrary.toml` |

### `hashing.py`

```python
import hashlib
from pathlib import Path

def hash_file(path: Path, chunk_size: int = 8192) -> str:
    """Return SHA-256 hex digest of file contents. Reads in chunks for memory efficiency."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()
```

### `logging.py`

```python
import logging
from rich.logging import RichHandler

def setup_logging(verbose: bool = False, log_file: str | None = None) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    handlers: list[logging.Handler] = [RichHandler(rich_tracebacks=True, show_time=False)]
    if log_file:
        handlers.append(logging.FileHandler(log_file))
    logging.basicConfig(level=level, handlers=handlers, format="%(message)s")
```

### `paths.py`

```python
from pathlib import Path

def find_project_root(start: Path | None = None) -> Path:
    """Walk upward to find project root (directory with .git or lexibrary.toml).
    Falls back to CWD if nothing found."""
    current = (start or Path.cwd()).resolve()
    while True:
        if (current / ".git").exists() or (current / "lexibrary.toml").exists():
            return current
        if current == current.parent:
            return Path.cwd().resolve()
        current = current.parent
```

### Tests
- `tests/test_config/test_loader.py` already covers config path finding
- Quick unit test for `hash_file` with known content
- Quick unit test for `find_project_root` with tmp_path fixture

---

## 1.5 CLI Skeleton

### File: `src/lexibrary/cli.py`

Minimal Typer app with placeholder commands. Full implementations come in Phase 6.

```python
import typer
from rich.console import Console

app = typer.Typer(
    name="lexibrary",
    help="AI-friendly codebase indexer. Creates .aindex files to help LLMs navigate your project.",
    no_args_is_help=True,
)
console = Console()

@app.command()
def init(path: str = typer.Argument(".", help="Project root directory")):
    """Initialize Lexibrary in a project. Creates lexibrary.toml."""
    console.print("[yellow]init command — not yet implemented[/yellow]")

@app.command()
def crawl(path: str = typer.Argument(".", help="Project root directory")):
    """Run the Lexibrary crawler."""
    console.print("[yellow]crawl command — not yet implemented[/yellow]")

@app.command()
def daemon(path: str = typer.Argument(".", help="Project root directory")):
    """Start the background daemon."""
    console.print("[yellow]daemon command — not yet implemented[/yellow]")

@app.command()
def status(path: str = typer.Argument(".", help="Project root directory")):
    """Show indexing status."""
    console.print("[yellow]status command — not yet implemented[/yellow]")

@app.command()
def clean(path: str = typer.Argument(".", help="Project root directory")):
    """Remove all .aindex files and cache."""
    console.print("[yellow]clean command — not yet implemented[/yellow]")
```

### Verification
```bash
uv sync
uv run lexi --help        # Shows help with all 5 commands
uv run lexibrary --help  # Same output (alias works)
uv run lexi crawl          # Prints "not yet implemented"
```

---

## Acceptance Criteria

- [ ] `uv sync` installs all dependencies without errors
- [ ] `uv run lexi --help` shows help text with all 5 subcommands
- [ ] `uv run lexibrary --help` produces identical output
- [ ] `load_config()` returns valid `LexibraryConfig` with defaults when no file exists
- [ ] `load_config(path)` correctly loads and validates a `lexibrary.toml` fixture
- [ ] `IgnoreMatcher.is_ignored()` correctly matches `.gitignore` patterns
- [ ] `IgnoreMatcher.should_descend()` prunes ignored directories
- [ ] `hash_file()` returns consistent SHA-256 for same content
- [ ] All tests pass: `uv run pytest tests/test_config tests/test_ignore -v`
