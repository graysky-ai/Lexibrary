# hooks/pre_commit

**Summary:** Git pre-commit hook installation for Lexibrary -- installs a hook that runs `lexictl validate --ci --severity error` before each commit, blocking the commit if validation fails. Users can bypass with `git commit --no-verify`.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `install_pre_commit_hook` | `(project_root: Path) -> HookInstallResult` | Install or update the Lexibrary pre-commit hook; idempotent |
| `HookInstallResult` | `@dataclass` | Result with flags: `installed`, `already_installed`, `no_git_dir`, `message` |
| `HOOK_MARKER` | `str` | Marker comment (`# lexibrary:pre-commit`) used for idempotent detection |
| `HOOK_SCRIPT_TEMPLATE` | `str` | Shell snippet: runs `lexictl validate --ci --severity error`, exits 1 on failure with bypass instructions |

## Dependencies

- None (stdlib only: `stat`, `dataclasses`, `pathlib`)

## Dependents

- `lexibrary.cli.lexictl_app` -- `setup --hooks` command calls `install_pre_commit_hook`
- `lexibrary.hooks.__init__` -- re-exports `install_pre_commit_hook`

## Key Concepts

- Hook script runs `lexictl validate --ci --severity error` synchronously (blocking, unlike the post-commit hook)
- On validation failure: prints "Lexibrary validation failed" with bypass instructions (`git commit --no-verify`) and exits 1
- On validation success: exits 0 (commit proceeds)
- Three behaviours:
  - No `.git` directory: returns `HookInstallResult(no_git_dir=True)` with no file changes
  - No existing hook: creates new file with `#!/bin/sh` shebang + hook script, makes executable
  - Existing hook without marker: appends hook script to existing file
  - Existing hook with marker: returns `HookInstallResult(already_installed=True)` (idempotent)
- `_ensure_executable` adds owner/group/other execute bits via `stat.S_IXUSR | S_IXGRP | S_IXOTH`
