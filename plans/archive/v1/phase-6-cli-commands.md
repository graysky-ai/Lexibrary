# Phase 6: CLI Commands

**Goal:** Wire up all 5 CLI commands with real implementations, rich output, and progress bars.
**Milestone:** All commands work end-to-end (`lexi init`, `lexi crawl`, `lexi status`, `lexi clean`, `lexi daemon`).
**Depends on:** Phase 1 (CLI skeleton, config), Phase 5 (crawler engine). Daemon command depends on Phase 7.

---

## 6.1 CLI Structure

### File: `src/lexibrary/cli.py`

Replace the Phase 1 placeholder commands with full implementations. The Typer app stays the same; the command bodies change.

Imports needed:
```python
import asyncio
from pathlib import Path
import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table
from rich.panel import Panel
```

---

## 6.2 `lexi init`

Creates `lexibrary.toml` and optionally updates `.gitignore`.

```python
@app.command()
def init(
    path: Path = typer.Argument(Path("."), help="Project root directory"),
    provider: str = typer.Option("anthropic", help="LLM provider: anthropic, openai, ollama"),
):
    """Initialize Lexibrary in a project. Creates lexibrary.toml config file."""
    root = path.resolve()
    config_path = root / "lexibrary.toml"

    if config_path.exists():
        console.print(f"[yellow]lexibrary.toml already exists at {config_path}[/yellow]")
        raise typer.Exit(1)

    # Write config from template
    from .config.defaults import render_default_config
    content = render_default_config(provider=provider)
    config_path.write_text(content, encoding="utf-8")
    console.print(f"[green]Created {config_path}[/green]")

    # Update .gitignore
    gitignore_path = root / ".gitignore"
    entries_to_add = [".aindex", ".lexibrary_cache.json", ".lexibrary.log", ".lexibrary.pid"]
    if gitignore_path.exists():
        existing = gitignore_path.read_text()
        additions = [e for e in entries_to_add if e not in existing]
        if additions:
            with open(gitignore_path, "a") as f:
                f.write("\n# Lexibrary\n")
                for entry in additions:
                    f.write(entry + "\n")
            console.print(f"[green]Updated .gitignore with Lexibrary entries[/green]")
    else:
        with open(gitignore_path, "w") as f:
            f.write("# Lexibrary\n")
            for entry in entries_to_add:
                f.write(entry + "\n")
        console.print(f"[green]Created .gitignore with Lexibrary entries[/green]")

    console.print("\n[bold]Next steps:[/bold]")
    console.print("  1. Edit lexibrary.toml to configure your LLM provider and API key")
    console.print("  2. Run [bold]lexi crawl[/bold] to index your project")
```

### `config/defaults.py` — Template Renderer

```python
import tomli_w

def render_default_config(provider: str = "anthropic") -> str:
    """Render lexibrary.toml with comments."""
    # Build a commented TOML template string
    # (tomli_w doesn't support comments, so we use a string template)
    template = '''# Lexibrary Configuration
# Documentation: https://github.com/...

[llm]
provider = "{provider}"
model = "{model}"
api_key_env = "{api_key_env}"
max_retries = 3
timeout = 60

[tokenizer]
backend = "tiktoken"
model = "cl100k_base"

[crawl]
root = "."
max_file_size_kb = 512
max_files_per_llm_batch = 10
summary_max_tokens = 80
dir_summary_max_tokens = 150

[ignore]
use_gitignore = true
additional_patterns = [
    ".aindex",
    "lexibrary.toml",
    ".env",
    ".env.*",
    "*.lock",
    "node_modules/",
    "__pycache__/",
    ".git/",
    ".venv/",
    "venv/",
]

[daemon]
debounce_seconds = 2.0
full_sweep_interval_minutes = 30
log_file = ".lexibrary.log"

[output]
filename = ".aindex"
include_token_counts = true
'''
    provider_defaults = {
        "anthropic": ("claude-sonnet-4-5-20250514", "ANTHROPIC_API_KEY"),
        "openai": ("gpt-4o-mini", "OPENAI_API_KEY"),
        "ollama": ("llama3.2", ""),
    }
    model, api_key_env = provider_defaults.get(provider, provider_defaults["anthropic"])
    return template.format(provider=provider, model=model, api_key_env=api_key_env)
```

---

## 6.3 `lexi crawl`

The main command. Runs the crawler with progress output.

```python
@app.command()
def crawl(
    path: Path = typer.Argument(Path("."), help="Project root directory"),
    full: bool = typer.Option(False, "--full", "-f", help="Force full re-crawl (ignore cache)"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Show what would be indexed"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """Run the Lexibrary crawler. Generates .aindex files for all directories."""
    root = path.resolve()

    # Load config
    from .config.loader import load_config
    config = load_config()

    # Setup logging
    from .utils.logging import setup_logging
    setup_logging(verbose=verbose, log_file=config.daemon.log_file if verbose else None)

    # Create components
    from .ignore import create_ignore_matcher
    from .tokenizer import create_tokenizer
    from .llm import create_llm_service
    from .crawler.change_detector import ChangeDetector

    matcher = create_ignore_matcher(config, root)
    tokenizer = create_tokenizer(config.tokenizer)
    llm_service = create_llm_service(config.llm)

    cache_path = root / ".lexibrary_cache.json"
    change_detector = ChangeDetector(cache_path)
    change_detector.load()
    if full:
        change_detector.clear()

    # Run crawl with progress bar
    from .crawler.engine import full_crawl

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Indexing directories...", total=None)

        def on_progress(current: int, total: int, dir_name: str):
            progress.update(task, total=total, completed=current, description=f"Indexing {dir_name}/")

        stats = asyncio.run(full_crawl(
            root=root,
            config=config,
            llm_service=llm_service,
            tokenizer=tokenizer,
            matcher=matcher,
            change_detector=change_detector,
            dry_run=dry_run,
            progress_callback=on_progress,
        ))

    # Print summary
    console.print()
    prefix = "[yellow]Dry run complete[/yellow]" if dry_run else "[green]Crawl complete[/green]"
    console.print(prefix)
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_row("Directories indexed:", str(stats.directories_indexed))
    table.add_row("Files summarized:", str(stats.files_summarized))
    table.add_row("Files cached:", str(stats.files_cached))
    table.add_row("Files skipped:", str(stats.files_skipped))
    table.add_row("LLM calls:", str(stats.llm_calls))
    if stats.errors:
        table.add_row("[red]Errors:[/red]", str(stats.errors))
    console.print(table)
```

---

## 6.4 `lexi status`

Shows current indexing state.

```python
@app.command()
def status(
    path: Path = typer.Argument(Path("."), help="Project root directory"),
):
    """Show indexing status: files indexed, stale files, daemon status."""
    root = path.resolve()

    from .config.loader import load_config, find_config_file
    config_file = find_config_file(root)
    config = load_config(config_file)

    # Count directories with .aindex files
    iandex_count = sum(1 for _ in root.rglob(config.output.filename))

    # Load cache
    from .crawler.change_detector import ChangeDetector
    cache_path = root / ".lexibrary_cache.json"
    change_detector = ChangeDetector(cache_path)
    change_detector.load()
    cached_files = len(change_detector._cache.files)

    # Count stale files (changed since last index)
    stale = 0
    for file_key in list(change_detector._cache.files.keys()):
        file_path = Path(file_key)
        if file_path.exists() and change_detector.has_changed(file_path):
            stale += 1

    # Check daemon
    pid_file = root / ".lexibrary.pid"
    daemon_status = "not running"
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            import os, signal
            os.kill(pid, 0)  # check if process exists
            daemon_status = f"running (PID {pid})"
        except (ValueError, ProcessLookupError, PermissionError):
            daemon_status = "not running (stale PID file)"

    # Display
    panel_content = f"""[bold]Config file:[/bold]  {config_file or 'not found (using defaults)'}
[bold]LLM provider:[/bold] {config.llm.provider} ({config.llm.model})
[bold]Tokenizer:[/bold]    {config.tokenizer.backend} ({config.tokenizer.model})

[bold]Directories indexed:[/bold] {iandex_count}
[bold]Files cached:[/bold]        {cached_files}
[bold]Stale files:[/bold]         {stale}

[bold]Daemon:[/bold]       {daemon_status}"""

    console.print(Panel(panel_content, title="Lexibrary Status", border_style="blue"))

    if stale > 0:
        console.print(f"\n[yellow]Run 'lexi crawl' to update {stale} stale files.[/yellow]")
```

---

## 6.5 `lexi clean`

Removes all `.aindex` files and the cache.

```python
@app.command()
def clean(
    path: Path = typer.Argument(Path("."), help="Project root directory"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Remove all .aindex files and the cache from the project."""
    root = path.resolve()

    from .config.loader import load_config
    config = load_config()

    # Find all .aindex files
    iandex_files = list(root.rglob(config.output.filename))
    cache_file = root / ".lexibrary_cache.json"
    log_file = root / config.daemon.log_file

    targets = iandex_files[:]
    if cache_file.exists():
        targets.append(cache_file)
    if log_file.exists():
        targets.append(log_file)

    if not targets:
        console.print("Nothing to clean.")
        return

    console.print(f"Found {len(iandex_files)} .aindex files and {len(targets) - len(iandex_files)} other Lexibrary files.")

    if not yes:
        confirm = typer.confirm("Delete all?")
        if not confirm:
            raise typer.Abort()

    for f in targets:
        f.unlink()
    console.print(f"[green]Removed {len(targets)} files.[/green]")
```

---

## 6.6 `lexi daemon`

Thin wrapper that starts the daemon service (implemented in Phase 7). In Phase 6 we add the CLI command with a "not yet implemented" guard that gets replaced in Phase 7.

```python
@app.command()
def daemon(
    path: Path = typer.Argument(Path("."), help="Project root directory"),
    foreground: bool = typer.Option(False, "--foreground", "-f", help="Run in foreground"),
):
    """Start the Lexibrary background daemon for live re-indexing."""
    root = path.resolve()

    from .config.loader import load_config
    config = load_config()

    from .daemon.service import DaemonService
    svc = DaemonService(root, config)
    svc.start(foreground=foreground)
```

---

## 6.7 Tests

### File: `tests/test_cli.py`

Use Typer's `CliRunner` for testing.

```python
from typer.testing import CliRunner
from lexibrary.cli import app

runner = CliRunner()
```

| Test | What it verifies |
|------|-----------------|
| `test_help` | `lexi --help` exits 0 and shows all 5 commands |
| `test_init_creates_config` | `lexi init` in tmp dir creates `lexibrary.toml` |
| `test_init_updates_gitignore` | `.gitignore` contains `.aindex` after init |
| `test_init_already_exists` | Running init twice exits with error |
| `test_init_provider_openai` | `--provider openai` sets correct model in config |
| `test_crawl_dry_run` | `lexi crawl --dry-run` with mock LLM returns stats, writes no files |
| `test_status_no_config` | `lexi status` works with defaults when no config exists |
| `test_status_with_cache` | Shows correct counts after a crawl |
| `test_clean_removes_files` | After crawl, `lexi clean --yes` removes all `.aindex` files |
| `test_clean_nothing_to_clean` | Clean in empty dir prints "Nothing to clean" |

---

## Acceptance Criteria

- [ ] `lexi --help` shows all 5 commands with descriptions
- [ ] `lexi init` creates a valid `lexibrary.toml` with comments
- [ ] `lexi init` adds Lexibrary entries to `.gitignore`
- [ ] `lexi init` fails gracefully if config already exists
- [ ] `lexi crawl` shows a progress bar and prints summary stats
- [ ] `lexi crawl --dry-run` reports stats but writes no files
- [ ] `lexi crawl --full` ignores cache and re-indexes everything
- [ ] `lexi status` shows config, counts, and daemon status
- [ ] `lexi clean --yes` removes all `.aindex` files and cache
- [ ] `lexi clean` prompts for confirmation without `--yes`
- [ ] Both `lexi` and `lexibrary` aliases work identically
- [ ] All tests pass: `uv run pytest tests/test_cli.py -v`
