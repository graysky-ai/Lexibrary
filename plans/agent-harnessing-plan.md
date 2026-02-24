# Agent Harnessing Plan

> **Purpose:** Fix all open issues and implement suggestions from `plans/analysis-hooks-skills-commands-rules.md`
> **Date:** 2026-02-24
> **Scope:** Rules generation enhancements, CLI feature additions, hook infrastructure, environment integration

---

## Overview

This plan addresses every open item from the analysis, organized into 6 phases by dependency order and priority. Each phase is independently shippable.

### What's Already Resolved (No Work Needed)

- C1/C2: `lexi validate` and `lexi status` exist (cli-command-rebalance)
- C3/C4: IWH CLI surface and rule content bugs fixed (iwh-gap-fix)
- H6: Rule content matches actual commands
- Archivist IWH integration, .aindex batching

---

## Phase 1: Claude Code Agent Integration (High Priority)

Enables frictionless agent experience in Claude Code — the highest-impact environment.

### 1.1 Generate `.claude/settings.json` (H1)

**Problem:** Agents must manually approve every `lexi` bash command execution.

**Implementation:**

File: `src/lexibrary/init/rules/claude.py`

Add to `generate_claude_rules()`:

```python
def _generate_settings_json(project_root: Path) -> Path:
    """Generate .claude/settings.json with pre-approved lexi commands."""
    settings_path = project_root / ".claude" / "settings.json"

    settings = {
        "permissions": {
            "allow": [
                "Bash(lexi *)",
                "Bash(lexi lookup *)",
                "Bash(lexi search *)",
                "Bash(lexi concepts *)",
                "Bash(lexi concept *)",
                "Bash(lexi stack *)",
                "Bash(lexi describe *)",
                "Bash(lexi validate *)",
                "Bash(lexi status *)",
                "Bash(lexi help)",
                "Bash(lexi iwh *)",
            ],
            "deny": [
                "Bash(lexictl *)",
            ],
        }
    }

    # Merge with existing settings if present (preserve user additions)
    if settings_path.exists():
        existing = json.loads(settings_path.read_text())
        # Merge allow/deny lists, deduplicating
        existing_perms = existing.get("permissions", {})
        existing_allow = set(existing_perms.get("allow", []))
        existing_deny = set(existing_perms.get("deny", []))
        existing_allow.update(settings["permissions"]["allow"])
        existing_deny.update(settings["permissions"]["deny"])
        existing_perms["allow"] = sorted(existing_allow)
        existing_perms["deny"] = sorted(existing_deny)
        existing["permissions"] = existing_perms
        settings = existing

    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(settings, indent=2) + "\n")
    return settings_path
```

**Merge strategy:** If `.claude/settings.json` already exists, merge `allow`/`deny` lists (add our entries, preserve user entries). Never remove user-added entries.

**Files changed:**
- `src/lexibrary/init/rules/claude.py` — add `_generate_settings_json()`, call from `generate_claude_rules()`
- `tests/test_init/test_rules/test_claude.py` — test generation, merge behavior, idempotency

### 1.2 Generate `.claude/hooks/` (H2)

**Problem:** No automatic context injection before/after file edits.

**Implementation:**

Hooks are configured in `.claude/settings.json` (same file as permissions from 1.1), not as separate files. The `_generate_settings_json()` function from 1.1 will include the hooks section.

The hooks use the Claude Code hooks API: events are keyed by name (`PreToolUse`, `PostToolUse`, etc.), each containing an array of matcher+handlers objects. Matchers use regex against tool names. Handlers can be `command`, `prompt`, or `agent` type. Exit code 2 blocks the action; exit code 0 allows it with optional JSON output on stdout.

#### PreToolUse Hook (auto-lookup before edits)

Inject design file context before any Edit/Write operation. Uses a command hook that runs `lexi lookup` and returns the output as `additionalContext` via JSON stdout.

Hook script: `.claude/hooks/lexi-pre-edit.sh`

```bash
#!/usr/bin/env bash
# Lexibrary: inject design file context before edits
# Input: JSON on stdin with tool_name and tool_input
FILE_PATH=$(echo "$1" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('tool_input',{}).get('file_path',''))" 2>/dev/null)
if [ -z "$FILE_PATH" ]; then
  exit 0
fi
CONTEXT=$(lexi lookup "$FILE_PATH" 2>/dev/null) || exit 0
if [ -n "$CONTEXT" ]; then
  python3 -c "import sys,json; print(json.dumps({'hookSpecificOutput':{'additionalContext': sys.argv[1]}}))" "$CONTEXT"
fi
```

Settings entry:
```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/lexi-pre-edit.sh",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

#### PostToolUse Hook (design file reminder after edits)

Remind agent to update the design file after edits. Uses a command hook that emits a `systemMessage`.

Hook script: `.claude/hooks/lexi-post-edit.sh`

```bash
#!/usr/bin/env bash
# Lexibrary: remind agent to update design file after edits
FILE_PATH=$(echo "$1" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('tool_input',{}).get('file_path',''))" 2>/dev/null)
if [ -z "$FILE_PATH" ]; then
  exit 0
fi
# Only remind for source files, not design files or config
case "$FILE_PATH" in
  *.lexibrary/*|*blueprints/*|*.claude/*|*.cursor/*) exit 0 ;;
esac
echo '{"systemMessage":"Reminder: Update the design file for this source file. Run `lexi design update <file>` or set updated_by: agent in the design file frontmatter."}'
```

Settings entry (added to same `hooks` object):
```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/lexi-post-edit.sh",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

#### Implementation approach

The `_generate_settings_json()` from 1.1 is extended to also merge hook definitions. Hook scripts are generated as separate executable `.sh` files in `.claude/hooks/`. The settings.json merge logic handles the `hooks` key alongside `permissions`.

**Files changed:**
- `src/lexibrary/init/rules/claude.py` — extend `_generate_settings_json()` to include hooks config, add `_generate_hook_scripts()` for the `.sh` files
- `tests/test_init/test_rules/test_claude.py` — test hook script generation, settings merge with hooks, script executability

### 1.3 Additional Claude Commands (M2, M7)

**Problem:** Only `/lexi-orient` and `/lexi-search` exist. Common operations require agents to remember exact CLI syntax.

**Implementation:**

Add to `generate_claude_rules()` — generate these additional command files:

| Command File | Purpose | Content |
|---|---|---|
| `.claude/commands/lexi-lookup.md` | Look up design file for current file | `Run lexi lookup <file> to see the design context for a source file before editing it.` |
| `.claude/commands/lexi-concepts.md` | Browse/search concepts | `Run lexi concepts [topic] to find architectural concepts. Use --tag to filter by tag, --all to show everything.` |
| `.claude/commands/lexi-stack.md` | Stack Q&A operations | Guided prompts for `lexi stack search`, `lexi stack post`, `lexi stack answer` |

**Content source:** Add new functions to `base.py`:
- `get_lookup_skill_content() -> str`
- `get_concepts_skill_content() -> str`
- `get_stack_skill_content() -> str`

**Files changed:**
- `src/lexibrary/init/rules/base.py` — add 3 new skill content functions
- `src/lexibrary/init/rules/claude.py` — generate 3 additional command files
- `src/lexibrary/init/rules/cursor.py` — append to combined skills file
- `src/lexibrary/init/rules/codex.py` — embed in AGENTS.md
- `tests/test_init/test_rules/test_base.py` — validate new skill content
- `tests/test_init/test_rules/test_claude.py` — verify new files generated

---

## Phase 2: CLI Feature Additions (High Priority)

New flags for `lexictl` that improve operator workflow.

### 2.1 `lexictl update --dry-run` (H3, O13)

**Problem:** No way to preview what `update` would change without making LLM calls and writing files.

**Implementation:**

Two levels of dry-run:

1. **Change detection only (no LLM):** Show which files would be processed and their `ChangeLevel`, without calling the LLM or writing anything. This is the default `--dry-run` behavior — fast and free.

2. **Full dry-run (with LLM):** Process everything including LLM calls but skip file writes. Use `--dry-run --full` for this mode. Useful for testing prompt changes.

#### Level 1: Change detection only (default `--dry-run`)

File: `src/lexibrary/cli/lexictl_app.py`

```python
# Add to update() parameters:
dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview changes without writing.")] = False

# In the update flow, before pipeline calls:
if dry_run:
    # Run change detection only, skip LLM and writes
    console.print("[yellow]DRY-RUN MODE — no files will be modified[/yellow]\n")
    # ... call a new dry_run_project() or dry_run_files() function
```

File: `src/lexibrary/archivist/pipeline.py`

```python
async def dry_run_project(
    project_root: Path,
    config: LexibraryConfig,
) -> list[tuple[Path, ChangeLevel]]:
    """Preview what update_project would do without LLM calls or writes."""
    source_files = discover_source_files(project_root, config)
    results = []
    for source_path in source_files:
        change = check_change(source_path, project_root, config)
        if change != ChangeLevel.UNCHANGED:
            results.append((source_path, change))
    return results
```

CLI output format:
```
DRY-RUN MODE — no files will be modified

  NEW        src/lexibrary/new_module.py
  CHANGED    src/lexibrary/crawler/engine.py
  INTERFACE  src/lexibrary/config/models.py
  AGENT_UPD  src/lexibrary/cli/lexi_app.py

4 files would be processed (3 LLM calls, 1 footer refresh)
```

**Files changed:**
- `src/lexibrary/cli/lexictl_app.py` — add `--dry-run` flag, output formatting
- `src/lexibrary/archivist/pipeline.py` — add `dry_run_project()` and `dry_run_files()` functions
- `tests/test_archivist/test_pipeline.py` — test dry-run returns correct predictions
- `tests/test_cli/test_lexictl.py` — test CLI flag handling and output

### 2.2 `lexictl update --start-here` (H3 related, M3, O14)

**Problem:** No way to regenerate `START_HERE.md` independently without running the full update pipeline.

**Implementation:**

File: `src/lexibrary/cli/lexictl_app.py`

```python
# Add to update() parameters:
start_here: Annotated[bool, typer.Option("--start-here", help="Regenerate START_HERE.md only.")] = False

# Mutually exclusive with --changed-only and path:
if start_here:
    if path is not None or changed_only is not None:
        console.print("[red]--start-here cannot be combined with path or --changed-only[/red]")
        raise typer.Exit(1)
    # Call START_HERE generation directly
    archivist = create_archivist(config)
    await generate_start_here(project_root, config, archivist)
    console.print("[green]START_HERE.md regenerated.[/green]")
    return
```

**Files changed:**
- `src/lexibrary/cli/lexictl_app.py` — add `--start-here` flag and early-return path
- `tests/test_cli/test_lexictl.py` — test flag, mutual exclusivity

### 2.3 `lexictl validate --ci` (M6, O16)

**Problem:** No clean exit codes or machine-readable output for CI pipelines.

**Implementation:**

File: `src/lexibrary/cli/_shared.py`

```python
def _run_validate(
    project_root: Path,
    *,
    severity: str | None = None,
    check: str | None = None,
    json_output: bool = False,
    ci_mode: bool = False,
) -> int:
    report = validate_library(project_root, ...)

    if ci_mode:
        # Compact single-line output for CI logs
        counts = report.counts_by_severity()
        line = f"lexibrary-validate: errors={counts['error']} warnings={counts['warning']} info={counts['info']}"
        console.print(line)
        # Exit codes: 0=clean, 1=errors found, 2=internal failure
        return report.exit_code()

    if json_output:
        # ... existing JSON output

    report.render(console)
    return report.exit_code()
```

File: `src/lexibrary/cli/lexictl_app.py`

```python
# Add to validate() parameters:
ci: Annotated[bool, typer.Option("--ci", help="CI mode: compact output, strict exit codes.")] = False
```

**Exit code contract:**
- `0` — no errors (warnings/info may exist)
- `1` — errors found
- `2` — internal failure (config missing, etc.)

**Files changed:**
- `src/lexibrary/cli/_shared.py` — add `ci_mode` parameter to `_run_validate()`
- `src/lexibrary/cli/lexictl_app.py` — add `--ci` flag, pass through
- `src/lexibrary/validator/report.py` — add `counts_by_severity()` if not present
- `tests/test_cli/test_lexictl.py` — test CI output format and exit codes

### 2.4 `lexictl validate --fix` (L4, O15)

**Problem:** Validation reports issues but offers no remediation.

**Implementation:**

Create `src/lexibrary/validator/fixes.py` with per-check fix functions:

| Check | Auto-fixable? | Fix Strategy |
|---|---|---|
| `hash_freshness` | Yes | Re-run `update_file()` for stale files |
| `orphan_artifacts` | Yes (with confirmation) | Delete design files whose source is gone |
| `aindex_coverage` | Yes | Run `reindex_directories()` for uncovered dirs |
| `orphan_concepts` | No | Report only (requires human decision) |
| `wikilink_resolution` | Partial | Suggest closest match, apply if unambiguous |
| `token_budgets` | No | Report only (requires content editing) |

```python
# src/lexibrary/validator/fixes.py

from __future__ import annotations

@dataclass
class FixResult:
    check: str
    path: Path
    fixed: bool
    message: str

def fix_hash_freshness(issue: ValidationIssue, project_root: Path, config: LexibraryConfig) -> FixResult:
    """Re-generate design file for stale source."""
    # Extract source path from issue
    # Call update_file() for that path
    ...

def fix_orphan_artifacts(issue: ValidationIssue, project_root: Path) -> FixResult:
    """Remove design files with no corresponding source."""
    # Delete the orphaned design file
    ...

def fix_aindex_coverage(issue: ValidationIssue, project_root: Path) -> FixResult:
    """Generate missing .aindex files."""
    # Call reindex for the directory
    ...

# Registry
FIXERS: dict[str, Callable] = {
    "hash_freshness": fix_hash_freshness,
    "orphan_artifacts": fix_orphan_artifacts,
    "aindex_coverage": fix_aindex_coverage,
}
```

CLI flow:
```
$ lexictl validate --fix
Found 5 issues (3 fixable):
  [FIXED]  hash_freshness: src/lexibrary/crawler/engine.py — re-generated design file
  [FIXED]  orphan_artifacts: blueprints/src/old_module.md — deleted orphan
  [FIXED]  aindex_coverage: src/lexibrary/utils/ — generated .aindex
  [SKIP]   orphan_concepts: "old-pattern" — requires manual review
  [SKIP]   token_budgets: blueprints/src/lexibrary/llm/service.md — content too large

Fixed 3 of 5 issues. 2 require manual attention.
```

**Files changed:**
- `src/lexibrary/validator/fixes.py` — **new file**, fix functions and registry
- `src/lexibrary/cli/_shared.py` — add `fix` parameter to `_run_validate()`, orchestrate fixes
- `src/lexibrary/cli/lexictl_app.py` — add `--fix` flag (lexictl only, not lexi)
- `tests/test_validator/test_fixes.py` — **new file**, test each fixer

---

## Phase 3: Agent Tooling Improvements (High Priority)

### 3.1 Agent Design File Update Helper (H4)

**Problem:** Agents are told to "update design files" but have no tooling — they must manually find, read, and edit YAML+markdown files.

**Implementation:**

New command: `lexi design update <source-file>`

Behavior:
1. Resolve source file → design file path
2. If design file doesn't exist: scaffold a new one from template
3. If it exists: open/print it with clear instructions on what to update
4. In both cases: automatically set `updated_by: agent` in frontmatter
5. Print the design file path so the agent can edit it

```python
# src/lexibrary/cli/lexi_app.py — new subcommand group

@lexi_app.command("design")
def design_update(
    source_file: Annotated[str, typer.Argument(help="Source file to update design for")],
) -> None:
    """Show or scaffold the design file for a source file."""
    project_root = require_project_root()
    source_path = Path(source_file).resolve()
    design_path = resolve_design_path(source_path, project_root)

    if design_path.exists():
        # Read and display current design file
        content = design_path.read_text()
        console.print(f"[bold]Design file:[/bold] {design_path.relative_to(project_root)}")
        console.print(content)
        console.print("\n[yellow]Edit the sections above, then set updated_by: agent in frontmatter.[/yellow]")
    else:
        # Scaffold from template
        template = generate_design_scaffold(source_path, project_root)
        design_path.parent.mkdir(parents=True, exist_ok=True)
        design_path.write_text(template)
        console.print(f"[green]Created design scaffold:[/green] {design_path.relative_to(project_root)}")
        console.print(template)
```

**Files changed:**
- `src/lexibrary/cli/lexi_app.py` — add `design` command
- `src/lexibrary/archivist/` — add `generate_design_scaffold()` utility (template without LLM)
- `tests/test_cli/test_lexi.py` — test scaffold creation and display

### 3.2 Stack Post Lifecycle Commands (L5, A16, A17)

**Problem:** No way to mark Stack posts as outdated or duplicate.

**Implementation:**

```python
# src/lexibrary/cli/lexi_app.py — add to stack subgroup

@stack_app.command("mark-outdated")
def stack_mark_outdated(
    post_id: Annotated[str, typer.Argument(help="Stack post ID")],
) -> None:
    """Mark a Stack post as outdated."""
    # Update status field in post frontmatter to "outdated"
    ...

@stack_app.command("duplicate")
def stack_duplicate(
    post_id: Annotated[str, typer.Argument(help="Stack post ID to mark as duplicate")],
    of: Annotated[str, typer.Option("--of", help="Original post ID")] = ...,
) -> None:
    """Mark a Stack post as duplicate of another."""
    # Update status to "duplicate", add duplicate_of field
    ...
```

**Files changed:**
- `src/lexibrary/cli/lexi_app.py` — add 2 new stack subcommands
- `src/lexibrary/stack/parser.py` — add status mutation helpers if needed
- `tests/test_cli/test_lexi.py` — test both commands

---

## Phase 4: Git Hook Enhancements (Medium Priority)

### 4.1 Pre-commit Validation Hook (H5)

**Problem:** No validation gate before commits — broken library state can be committed.

**Implementation:**

File: `src/lexibrary/hooks/pre_commit.py` — **new file**

```python
PRE_COMMIT_MARKER = "# lexibrary:pre-commit"

PRE_COMMIT_SCRIPT = """\
# lexibrary:pre-commit
# — Lexibrary validation gate (installed by lexictl setup --hooks) —
if ! lexictl validate --ci --severity error 2>/dev/null; then
    echo "Lexibrary validation failed. Run 'lexictl validate' for details."
    echo "Use 'git commit --no-verify' to bypass."
    exit 1
fi
# — end Lexibrary —
"""

def install_pre_commit_hook(project_root: Path) -> HookInstallResult:
    """Install pre-commit validation hook."""
    # Same pattern as post_commit.py: marker-based, idempotent, append-safe
    ...
```

Update `lexictl setup --hooks` to offer both hooks:

```python
# src/lexibrary/cli/lexictl_app.py — update setup command
if hooks:
    post_result = install_post_commit_hook(project_root)
    pre_result = install_pre_commit_hook(project_root)
    # Report both results
```

**Files changed:**
- `src/lexibrary/hooks/pre_commit.py` — **new file**, pre-commit hook installer
- `src/lexibrary/hooks/__init__.py` — export new installer
- `src/lexibrary/cli/lexictl_app.py` — call both hook installers from `setup --hooks`
- `tests/test_hooks/test_pre_commit.py` — **new file**, test installation

---

## Phase 5: Cursor & Environment Enhancements (Medium Priority)

### 5.1 Cursor Glob-scoped Rules (M1)

**Problem:** Cursor rules are always-apply only. No context-triggered rules for editing source files.

**Implementation:**

File: `src/lexibrary/init/rules/cursor.py`

Generate an additional MDC file scoped to source files:

`.cursor/rules/lexibrary-editing.mdc`:
```yaml
---
description: Lexibrary editing reminders
globs:
  - "src/**"
  - "lib/**"
alwaysApply: false
---

Before editing this file, run: `lexi lookup <this-file>`
After editing, update the corresponding design file in `.lexibrary/blueprints/`.
Set `updated_by: agent` in the design file frontmatter.
Run `lexi validate` to check library health.
```

The glob patterns should come from config's `scope_root`:

```python
def _generate_editing_rule(project_root: Path, config: LexibraryConfig) -> Path:
    scope = config.scope_root or "src"
    globs = [f"{scope}/**"]
    ...
```

**Files changed:**
- `src/lexibrary/init/rules/cursor.py` — add editing-scoped rule generation
- `tests/test_init/test_rules/test_cursor.py` — test new rule file

### 5.2 Generic Agent Rules for Unsupported Environments (Medium)

**Problem:** Projects using Windsurf, Copilot, Aider, or plain editors get nothing.

**Implementation:**

Generate a `LEXIBRARY_RULES.md` at project root for any environment not specifically supported. This is a fallback that any agent can be pointed to.

File: `src/lexibrary/init/rules/generic.py` — **new file**

```python
def generate_generic_rules(project_root: Path) -> list[Path]:
    """Generate LEXIBRARY_RULES.md for environments without specific integration."""
    rules_path = project_root / "LEXIBRARY_RULES.md"
    content = f"# Lexibrary Agent Rules\n\n{get_core_rules()}\n\n## Skills\n\n### Orient\n{get_orient_skill_content()}\n\n### Search\n{get_search_skill_content()}"
    rules_path.write_text(content)
    return [rules_path]
```

Register in `__init__.py` as `"generic"` environment.

**Files changed:**
- `src/lexibrary/init/rules/generic.py` — **new file**
- `src/lexibrary/init/rules/__init__.py` — register `"generic"` generator
- `tests/test_init/test_rules/test_generic.py` — **new file**

---

## Phase 6: Init Wizard Improvements (Medium Priority)

### 6.1 Hook Installation Prompt During Init (W1 gap)

**Problem:** Operator must remember to run `lexictl setup --hooks` separately.

**Implementation:**

File: `src/lexibrary/init/wizard.py`

Add a wizard step after environment selection:

```python
# Step 9: Git hooks
install_hooks = Confirm.ask(
    "Install git hooks for automatic design file updates?",
    default=True,
)
```

If yes, call `install_post_commit_hook()` and `install_pre_commit_hook()` during init.

Add to `WizardAnswers`:
```python
install_hooks: bool = False
```

**Files changed:**
- `src/lexibrary/init/wizard.py` — add hooks step
- `src/lexibrary/init/models.py` — add `install_hooks` to `WizardAnswers`
- `src/lexibrary/cli/lexictl_app.py` — call hook installers in init if `answers.install_hooks`
- `tests/test_init/test_wizard.py` — test new step

### 6.2 Auto-run `lexictl update` After Init (W1 gap)

**Problem:** Operator must manually run `lexictl update` after `lexictl init`.

**Implementation:**

Add a prompt at the end of init:

```python
run_update = Confirm.ask(
    "Run lexictl update now to generate design files?",
    default=False,  # Default no — update can be slow/expensive
)
if run_update:
    # Import and call update logic
    ...
```

Default to `False` because the initial update involves LLM calls and can be expensive. The prompt ensures the operator knows it's the next step.

**Files changed:**
- `src/lexibrary/cli/lexictl_app.py` — add post-init prompt and update call

---

## Phase Summary

| Phase | Items | New Files | Priority |
|---|---|---|---|
| 1: Claude Integration | H1, H2, M2, M7 | 0 new (extend claude.py, base.py) | High |
| 2: CLI Features | H3, M3, M6, L4, O13-O16 | 1 new (fixes.py) | High |
| 3: Agent Tooling | H4, L5, A16, A17 | 0 new (extend lexi_app.py) | High |
| 4: Git Hooks | H5 | 1 new (pre_commit.py) | Medium |
| 5: Cursor & Environments | M1, L2 | 1 new (generic.py) | Medium |
| 6: Init Improvements | W1 gaps | 0 new (extend wizard.py) | Medium |

### Items Deferred to Backlog

The following items from the analysis were deferred and added to `plans/BACKLOG.md`. See that file for status tracking.

- L1: MCP server for lexi commands
- L3: IDE workspace settings generation
- L6: `lexictl metrics` dashboard
- M5: Hook/sweep coordination
- M8: Windows hook support
- Post-merge and post-checkout git hooks (Phase 4.2)

---

## Implementation Order & Dependencies

```
Phase 1.1 (settings.json) ──┐
Phase 1.2 (hooks)          ──┤── can be done in parallel
Phase 1.3 (commands)       ──┘

Phase 2.1 (dry-run)       ──┐
Phase 2.2 (--start-here)  ──┤── can be done in parallel
Phase 2.3 (--ci)           ──┤
Phase 2.4 (--fix)          ──┘── depends on 2.3 for --ci exit codes

Phase 3.1 (design helper)  ──┐── can be done in parallel
Phase 3.2 (stack lifecycle) ──┘

Phase 4.1 (pre-commit)     ──── depends on 2.3 (uses --ci flag)

Phase 5 ──── independent
Phase 6 ──── depends on Phase 4.1 (offers hook install during init)
```

### Estimated Scope per Phase

| Phase | Complexity | Files Changed | New Files |
|---|---|---|---|
| 1 | Medium | 5 | 0 |
| 2 | Medium-High | 7 | 2 |
| 3 | Medium | 3 | 0 |
| 4 | Low-Medium | 4 | 1 |
| 5 | Low | 3 | 2 |
| 6 | Low | 3 | 0 |

---

## Testing Strategy

Each phase should include:

1. **Unit tests** for new functions (fixers, dry-run, scaffold generation)
2. **CLI integration tests** using `typer.testing.CliRunner` (flag parsing, output format, exit codes)
3. **Filesystem tests** using `tmp_path` (file creation, merge behavior, idempotency)
4. **No mocking of filesystem** — use real tmp directories per project convention

### Key Test Scenarios

- **Settings merge:** Existing `.claude/settings.json` with user entries preserved after regeneration
- **Hook idempotency:** Running `setup --hooks` twice doesn't duplicate hook scripts
- **Dry-run purity:** No files written, no side effects, stats are predictions
- **CI exit codes:** 0 for clean, 1 for errors, 2 for internal failures
- **Fix safety:** Orphan deletion only removes confirmed orphans, never source files
