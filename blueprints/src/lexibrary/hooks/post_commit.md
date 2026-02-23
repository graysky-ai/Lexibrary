# hooks/post_commit

**Summary:** Git post-commit hook installation for Lexibrarian -- installs a hook that runs `lexictl update --changed-only` in the background after each commit, so design files stay in sync without blocking the developer.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `install_post_commit_hook` | `(project_root: Path) -> HookInstallResult` | Install or update the Lexibrarian post-commit hook; idempotent |
| `HookInstallResult` | `@dataclass` | Result with flags: `installed`, `already_installed`, `no_git_dir`, `message` |
| `HOOK_MARKER` | `str` | Marker comment (`# lexibrarian:post-commit`) used for idempotent detection |
| `HOOK_SCRIPT_TEMPLATE` | `str` | Shell snippet: `git diff-tree` to list changed files, pipes to `lexictl update --changed-only` in background |

## Dependencies

- None (stdlib only: `stat`, `dataclasses`, `pathlib`)

## Dependents

- `lexibrarian.cli.lexictl_app` -- `setup --hooks` command calls `install_post_commit_hook`

## Key Concepts

- Hook script uses `git diff-tree --no-commit-id --name-only -r HEAD` to list changed files
- Output is redirected to `.lexibrarian.log` and run in the background (`&`) so it never blocks `git commit`
- Three behaviours:
  - No `.git` directory: returns `HookInstallResult(no_git_dir=True)` with no file changes
  - No existing hook: creates new file with `#!/bin/sh` shebang + hook script, makes executable
  - Existing hook without marker: appends hook script to existing file
  - Existing hook with marker: returns `HookInstallResult(already_installed=True)` (idempotent)
- `_ensure_executable` adds owner/group/other execute bits via `stat.S_IXUSR | S_IXGRP | S_IXOTH`
