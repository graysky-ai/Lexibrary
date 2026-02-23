# Phase 8c — Agent Rules + I Was Here (IWH)

**Reference:** `plans/v2-master-plan.md` (Phase 8c section), `lexibrary-overview.md` (sections 1, 8)
**Depends on:** Phase 8b (Init Wizard + Setup) — `lexictl init` wizard persists `agent_environment` in config, `lexictl setup --update` exists as a stub
**Consumed by:** Phase 9 (Daemon & CI), ongoing agent workflows

---

## Goal

Implement two systems and wire them together:

1. **I Was Here (IWH)** — ephemeral, directory-scoped inter-agent signalling that replaces the project-wide HANDOFF.md
2. **Agent environment rules** — generate environment-specific rule files, skills, and commands for Claude Code, Cursor, and Codex
3. **HANDOFF.md removal** — remove all HANDOFF.md scaffolding per D-053

After Phase 8c, running `lexictl init` (or `lexictl setup --update`) produces complete agent environment rules that instruct agents to use the library, check for `.iwh` signals, and follow the full Lexibrary workflow.

---

## Decisions Referenced

| # | Decision | Summary |
|---|----------|---------|
| D-053 | Replace HANDOFF.md with IWH | Directory-scoped, ephemeral, pull-based inter-agent signals |
| D-057 | IWH scope field | `warning`, `incomplete`, `blocked` |
| D-058 | Persist agent environment in config | `agent_environment` list in config |
| Q-014 | Same-directory race condition | Accepted as known limitation; IWH is advisory |

---

## Sub-Phases

| Sub-Phase | Name | Depends On | Can Parallel With |
|-----------|------|------------|-------------------|
| **8c-1** | IWH Module | Phase 1 (foundation) | 8c-2 (once model stable) |
| **8c-2** | Agent Rule Templates | 8b (config persistence) | 8c-3 |
| **8c-3** | Skills & Commands | 8c-2 (rule templates) | 8c-4 |
| **8c-4** | Hooks | 8c-2 | 8c-3 |
| **8c-5** | HANDOFF.md Removal | 8c-1 (IWH replaces it) | 8c-2 |
| **8c-6** | Gitignore Integration | 8c-1 | 8c-2 |
| **8c-7** | `lexictl setup --update` Implementation | 8c-2, 8c-3, 8c-4 | — |

**Critical path:** 8c-1 → 8c-5 (IWH before HANDOFF removal); 8c-2 → 8c-3 → 8c-7 (rules before skills before update wiring)

---

## 8c-1 — IWH Module

### New module: `src/lexibrary/iwh/`

```
iwh/
  __init__.py        # Public API re-exports
  model.py           # Pydantic model for .iwh files
  parser.py          # Parse .iwh file from disk → IWHFile
  serializer.py      # IWHFile → markdown string
  reader.py          # Read + consume (delete) .iwh from a directory
  writer.py          # Create .iwh in a directory
  gitignore.py       # Ensure **/.iwh pattern exists in .gitignore
```

### `iwh/model.py`

```python
"""Pydantic 2 model for I Was Here (.iwh) files."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

IWHScope = Literal["warning", "incomplete", "blocked"]


class IWHFile(BaseModel):
    """Represents an .iwh inter-agent signal file."""

    author: str
    created: datetime
    scope: IWHScope
    body: str
```

Design notes:
- `author` is free-form (e.g., `agent-session-abc123`). No validation beyond non-empty.
- `created` is timezone-aware `datetime`. Serializer writes ISO 8601.
- `scope` is a strict `Literal` — parser rejects unknown values.
- `body` is freeform markdown below the frontmatter.

### `iwh/parser.py`

Follow the same pattern as `stack/parser.py` — YAML frontmatter regex, `yaml.safe_load`, model construction:

```python
def parse_iwh(path: Path) -> IWHFile | None:
    """Parse an .iwh file. Returns None if missing, invalid, or unparseable."""
```

### `iwh/serializer.py`

```python
def serialize_iwh(iwh: IWHFile) -> str:
    """Serialize an IWHFile to markdown with YAML frontmatter."""
```

### `iwh/reader.py`

```python
def read_iwh(directory: Path) -> IWHFile | None:
    """Read .iwh from directory. Does NOT delete it."""

def consume_iwh(directory: Path) -> IWHFile | None:
    """Read .iwh from directory and delete it (consume on read).

    Always deletes even if parsing fails — corrupt files are consumed too.
    """
```

### `iwh/writer.py`

```python
def write_iwh(
    directory: Path,
    *,
    author: str,
    scope: IWHScope,
    body: str,
) -> Path:
    """Create an .iwh file. Overwrites existing (latest signal wins).

    Creates parent directories if needed.
    """
```

### `iwh/gitignore.py`

```python
def ensure_iwh_gitignored(project_root: Path) -> bool:
    """Ensure .gitignore contains **/.iwh pattern.

    Appends if not present. Creates .gitignore if missing.
    Returns True if pattern was added, False if already present.
    """
```

Recognizes both `**/.iwh` and `.lexibrary/**/.iwh` as equivalent.

### `iwh/__init__.py`

Re-exports: `IWHFile`, `IWHScope`, `parse_iwh`, `serialize_iwh`, `read_iwh`, `consume_iwh`, `write_iwh`, `ensure_iwh_gitignored`.

### IWH path helper

Add to `src/lexibrary/utils/paths.py`:

```python
def iwh_path(project_root: Path, source_directory: Path) -> Path:
    """Compute .iwh path: src/auth/ → .lexibrary/src/auth/.iwh
    Project root → .lexibrary/.iwh
    """
```

---

## 8c-2 — Agent Rule Templates

### New module: `src/lexibrary/init/rules/`

```
init/rules/
  __init__.py        # Public API: generate_rules(), supported_environments()
  base.py            # Shared rule content (instructions all environments use)
  claude.py          # Claude Code: CLAUDE.md section + .claude/commands/
  cursor.py          # Cursor: .cursor/rules/lexibrary.mdc + .cursor/skills/
  codex.py           # Codex: AGENTS.md section
  markers.py         # Marker detection + section replacement
```

### `markers.py` — Section marker utilities

Handles `<!-- lexibrary:start -->` / `<!-- lexibrary:end -->` markers for files where Lexibrary appends a section (CLAUDE.md, AGENTS.md).

```python
MARKER_START = "<!-- lexibrary:start -->"
MARKER_END = "<!-- lexibrary:end -->"

def has_lexibrary_section(content: str) -> bool: ...
def replace_lexibrary_section(content: str, new_section: str) -> str: ...
def append_lexibrary_section(content: str, new_section: str) -> str: ...
```

### `base.py` — Shared rule content

```python
def get_core_rules() -> str:
    """Core Lexibrary rules for all environments."""
```

The rules instruct agents to:
- Read `.lexibrary/START_HERE.md` at session start
- Check for `.iwh` signals when entering directories — read, act, delete
- Run `lexi lookup <file>` before editing
- Update design files directly after editing (set `updated_by: agent`)
- Run `lexi concepts <topic>` before architectural decisions
- Run `lexi stack search` before debugging; `lexi stack post` after solving non-trivial bugs
- Create `.iwh` if leaving work incomplete; don't create if work is clean
- **Never run `lexictl` commands** — maintenance operations only

```python
def get_orient_skill_content() -> str:
    """Content for /lexi-orient skill — reads START_HERE + checks .iwh + status."""

def get_search_skill_content() -> str:
    """Content for /lexi-search skill — wraps lexi search with richer context."""
```

### `claude.py` — Claude Code environment

```python
def generate_claude_rules(project_root: Path) -> list[Path]:
    """Generate Claude Code environment files.

    Produces:
    - CLAUDE.md — append/update Lexibrary section (marker-delimited)
    - .claude/commands/lexi-orient.md — orient command
    - .claude/commands/lexi-search.md — search command
    """
```

Key behavior:
- If CLAUDE.md exists with markers: replace delimited section
- If CLAUDE.md exists without markers: append section
- If CLAUDE.md doesn't exist: create with markers
- `.claude/commands/` files are created fresh (overwritten on update)

### `cursor.py` — Cursor environment

```python
def generate_cursor_rules(project_root: Path) -> list[Path]:
    """Generate Cursor environment files.

    Produces:
    - .cursor/rules/lexibrary.mdc — MDC rules file
    - .cursor/skills/lexi.md — combined skills file
    """
```

MDC format has YAML frontmatter:
```yaml
---
description: Lexibrary codebase knowledge library rules
globs:
alwaysApply: true
---
```

### `codex.py` — Codex environment

```python
def generate_codex_rules(project_root: Path) -> list[Path]:
    """Generate Codex environment files.

    Produces:
    - AGENTS.md — append/update Lexibrary section (marker-delimited)
    """
```

Same marker-based append/replace pattern as CLAUDE.md.

### `__init__.py` — Public API

```python
_GENERATORS = {
    "claude": generate_claude_rules,
    "cursor": generate_cursor_rules,
    "codex": generate_codex_rules,
}

def generate_rules(project_root: Path, environments: list[str]) -> dict[str, list[Path]]:
    """Generate rules for specified environments. Returns env → created paths."""

def supported_environments() -> list[str]:
    """Return list of supported environment names."""
```

---

## 8c-3 — Skills & Commands

Skills are generated as part of rule templates (8c-2). Content defined in `base.py`, placed by environment modules:

| Environment | Orient Skill | Search Skill |
|-------------|-------------|--------------|
| Claude Code | `.claude/commands/lexi-orient.md` | `.claude/commands/lexi-search.md` |
| Cursor | `.cursor/skills/lexi.md` (combined) | `.cursor/skills/lexi.md` (combined) |
| Codex | Embedded in AGENTS.md rules | Embedded in AGENTS.md rules |

No additional implementation beyond 8c-2.

---

## 8c-4 — Hooks

### Session Start Hook

**Decision: Instructions-based, not automated in MVP.**

Claude Code, Cursor, and Codex do not provide reliable pre-session hook infrastructure. Instead:
- Rules instruct agents to read `START_HERE.md` and check `.iwh` at session start
- The `/lexi-orient` skill automates this for Claude Code and Cursor
- `CLAUDE.md` and `.cursor/rules/lexibrary.mdc` with `alwaysApply: true` ensure rules are always loaded

### Pre-Edit Hook

**Not implemented in MVP.** Rules instruct agents to run `lexi lookup <file>` before editing. No automated trigger — may be too aggressive for fast workflows. A future phase can add this if environments develop better support.

---

## 8c-5 — HANDOFF.md Removal

### Changes to `src/lexibrary/init/scaffolder.py`

1. Remove `HANDOFF_PLACEHOLDER` constant
2. Remove `base / "HANDOFF.md": HANDOFF_PLACEHOLDER` from `files` dict in `create_lexibrary_skeleton()`
3. Update `START_HERE_PLACEHOLDER`:

```python
START_HERE_PLACEHOLDER = """\
# START HERE

This library has not been generated yet.

Run `lexictl update` to crawl the project and generate the full Lexibrary library.

Check `.lexibrary/.iwh` for any I Was Here signals from previous agents.
"""
```

### Changes to `src/lexibrary/config/schema.py`

Remove `handoff_tokens` from `TokenBudgetConfig` (or keep for backward compat — `extra="ignore"` handles stale config files either way).

### Changes to `src/lexibrary/config/defaults.py`

Remove `handoff_tokens` line from template.

### Changes to `src/lexibrary/ignore/` patterns

Remove `.lexibrary/HANDOFF.md` from `IgnoreConfig.additional_patterns` default.

---

## 8c-6 — Gitignore Integration

Call `ensure_iwh_gitignored()` at two points:

1. `create_lexibrary_skeleton()` in `init/scaffolder.py` — ensures pattern on fresh init
2. `generate_rules()` in `init/rules/__init__.py` — ensures pattern on rule update

---

## 8c-7 — `lexictl setup --update` Implementation

Replace the Phase 8b stub with real implementation:

```python
@app.command()
def setup(
    environment: Annotated[str | None, typer.Argument(help="Agent environment.")] = None,
    *,
    update_flag: Annotated[bool, typer.Option("--update", help="Update rules.")] = False,
) -> None:
    """Install or update agent environment rules."""
    project_root = require_project_root()
    config = load_config(project_root)

    # Determine environments
    if environment is not None:
        envs = [environment]
    elif config.agent_environment:
        envs = config.agent_environment
    else:
        console.print("[yellow]No agent environment configured.[/yellow]")
        raise typer.Exit(1)

    # Validate
    supported = supported_environments()
    for env in envs:
        if env not in supported:
            console.print(f"[red]Unsupported: {env}[/red]. Supported: {', '.join(supported)}")
            raise typer.Exit(1)

    # Generate
    results = generate_rules(project_root, envs)
    ensure_iwh_gitignored(project_root)

    # Report
    total = sum(len(paths) for paths in results.values())
    for env, paths in results.items():
        console.print(f"[green]{env}[/green]: {len(paths)} files written")
        for p in paths:
            console.print(f"  {p.relative_to(project_root)}")

    action = "Updated" if update_flag else "Installed"
    console.print(f"\n[green]{action}[/green] rules for {', '.join(envs)} ({total} files)")
```

---

## Files to Create

| File | Purpose |
|------|---------|
| `src/lexibrary/iwh/__init__.py` | Public API re-exports |
| `src/lexibrary/iwh/model.py` | `IWHFile` Pydantic model |
| `src/lexibrary/iwh/parser.py` | Parse `.iwh` files |
| `src/lexibrary/iwh/serializer.py` | Serialize `IWHFile` to markdown |
| `src/lexibrary/iwh/reader.py` | Read + consume `.iwh` files |
| `src/lexibrary/iwh/writer.py` | Create `.iwh` files |
| `src/lexibrary/iwh/gitignore.py` | Gitignore integration |
| `src/lexibrary/init/rules/__init__.py` | `generate_rules()`, `supported_environments()` |
| `src/lexibrary/init/rules/base.py` | Shared rule content |
| `src/lexibrary/init/rules/claude.py` | Claude Code rules |
| `src/lexibrary/init/rules/cursor.py` | Cursor rules |
| `src/lexibrary/init/rules/codex.py` | Codex rules |
| `src/lexibrary/init/rules/markers.py` | Marker utilities |
| `tests/test_iwh/__init__.py` | Test package |
| `tests/test_iwh/test_model.py` | IWH model tests |
| `tests/test_iwh/test_parser.py` | Parser tests |
| `tests/test_iwh/test_serializer.py` | Serializer tests |
| `tests/test_iwh/test_reader.py` | Reader + consume tests |
| `tests/test_iwh/test_writer.py` | Writer tests |
| `tests/test_iwh/test_gitignore.py` | Gitignore tests |
| `tests/test_iwh/test_roundtrip.py` | Roundtrip tests |
| `tests/test_init/test_rules/__init__.py` | Test package |
| `tests/test_init/test_rules/test_base.py` | Base rule tests |
| `tests/test_init/test_rules/test_claude.py` | Claude rule tests |
| `tests/test_init/test_rules/test_cursor.py` | Cursor rule tests |
| `tests/test_init/test_rules/test_codex.py` | Codex rule tests |
| `tests/test_init/test_rules/test_markers.py` | Marker tests |
| `tests/test_init/test_rules/test_integration.py` | Full flow tests |

## Files to Modify

| File | Change |
|------|--------|
| `src/lexibrary/init/scaffolder.py` | Remove HANDOFF.md; update START_HERE placeholder; add gitignore integration |
| `src/lexibrary/config/schema.py` | Remove `handoff_tokens` from `TokenBudgetConfig` |
| `src/lexibrary/config/defaults.py` | Remove `handoff_tokens`; add IWH section |
| `src/lexibrary/utils/paths.py` | Add `iwh_path()` helper |
| `src/lexibrary/cli/lexictl_app.py` | Replace `setup` stub with real implementation |
| `tests/test_init/test_scaffolder.py` | Update: no HANDOFF.md; verify gitignore |
| `tests/test_config/test_schema.py` | Update for removed `handoff_tokens` |
| `tests/test_cli/test_lexictl.py` | Add `setup` command tests |
| `blueprints/START_HERE.md` | Add `iwh` and `init/rules` to Package Map |

---

## Test Strategy

### IWH Tests

**`test_model.py`:** Valid construction, all scope values, invalid scope, empty body.

**`test_parser.py`:** Valid parse, missing file, no frontmatter, invalid frontmatter, missing scope, unknown scope, empty body.

**`test_serializer.py`:** Complete serialization, markdown body preserved, ISO datetime.

**`test_roundtrip.py`:** All scopes roundtrip, body preserved, multiline body.

**`test_reader.py`:** Read exists, read missing, consume reads and deletes, consume missing, consume corrupt still deletes.

**`test_writer.py`:** Creates file, content parseable, overwrites existing, creates directories.

**`test_gitignore.py`:** Adds to existing, creates if missing, idempotent, recognizes alternative pattern, preserves existing content.

### Rule Template Tests

**`test_markers.py`:** Section detection, replacement, surrounding content preserved, append, append to empty.

**`test_base.py`:** Core rules contain key instructions, no lexictl references, orient/search skill content.

**`test_claude.py`:** Creates CLAUDE.md from scratch, appends to existing, updates existing section, creates command files, command content correct.

**`test_cursor.py`:** Creates MDC file, MDC format correct, creates skills file, combined content.

**`test_codex.py`:** Creates AGENTS.md from scratch, appends to existing, updates existing section.

**`test_integration.py`:** Full flow per environment, multi-environment, setup --update refreshes, preserves user content, unsupported env errors, gitignore updated.

---

## Implementation Order

### Step 1: IWH Module (8c-1)
Create `iwh/` module. Self-contained, fully testable independently.

### Step 2: Config Changes (8c-5 partial)
Remove `handoff_tokens`, update defaults template.

### Step 3: HANDOFF.md Removal (8c-5)
Remove from scaffolder, update START_HERE placeholder.

### Step 4: Path Helper (8c-1 addendum)
Add `iwh_path()` to `utils/paths.py`.

### Step 5: Marker Utilities (8c-2)
Create `init/rules/markers.py`.

### Step 6: Rule Templates (8c-2, 8c-3)
Create `base.py`, `claude.py`, `cursor.py`, `codex.py`, `__init__.py`.

### Step 7: CLI Integration (8c-7)
Replace `setup` stub with real implementation.

### Step 8: Scaffolder + Gitignore Integration (8c-6)
Wire `ensure_iwh_gitignored()` into scaffolder.

### Step 9: Integration Tests
Full flow tests.

### Step 10: Blueprint Updates
Update `blueprints/START_HERE.md`.

---

## Risks and Edge Cases

| Risk | Mitigation |
|------|------------|
| `.cursor/rules/*.mdc` format | Test with special characters in project names |
| Appending to CLAUDE.md with existing section | Thorough marker tests including edge cases |
| Git worktrees | `.iwh` is gitignored → worktree-local. Correct by design |
| Same-directory race condition (Q-014) | Accepted limitation. IWH is advisory. Document in docstrings |
| Empty `.iwh` body | Valid — scope field alone is meaningful. Model handles it |
| `handoff_tokens` backward compat | `extra="ignore"` on models silently ignores stale keys |
| Phase 8a dependency | `setup` command is portable — only registration changes after CLI split |

---

## What to Watch Out For

1. **`from __future__ import annotations`** in every new module
2. **No bare `print()`** — use `rich.console.Console` for CLI output; library code should not print
3. **pathspec pattern name is `"gitignore"`** — relevant if `iwh/gitignore.py` ever needs to parse patterns
4. **Config YAML via PyYAML** — IWH serializer uses `yaml.dump()` consistent with other serializers
5. **Pydantic 2** — `IWHFile` and `IWHConfig` use Pydantic 2 `BaseModel`
6. **Testing with `tmp_path`** — all filesystem tests use pytest `tmp_path`, never real project directories
7. **Marker robustness** — markers must survive manual editing (extra whitespace, trailing newlines)
