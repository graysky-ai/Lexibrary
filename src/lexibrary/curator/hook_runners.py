"""Thin wrapper entry points for Claude Code hook configuration.

Each runner function:
1. Discovers the project root via :func:`find_project_root`.
2. Loads the project configuration.
3. Delegates to the corresponding async hook in :mod:`hooks`.
4. Prints a brief status message to stderr (not stdout) on completion
   or skip.

These are intended as the callable targets for Claude Code's PostToolUse
hook system (post-edit, post-bead-close) or direct programmatic invocation.
"""

from __future__ import annotations

import sys
from pathlib import Path

from lexibrary.config.loader import load_config
from lexibrary.curator.hooks import (
    post_bead_close_hook_sync,
    post_edit_hook_sync,
    validation_failure_hook_sync,
)
from lexibrary.utils.root import find_project_root
from lexibrary.validator.report import ValidationIssue


def _log_stderr(msg: str) -> None:
    """Print a status message to stderr."""
    print(f"[curator-hook] {msg}", file=sys.stderr)


def run_post_edit(file_path: str | Path) -> None:
    """Hook runner for post-edit events.

    Discovers the project root, loads config, and calls
    :func:`~hooks.post_edit_hook_sync`.

    Args:
        file_path: Path to the file that was edited.  Can be relative
            (resolved against cwd) or absolute.
    """
    resolved = Path(file_path).resolve()
    try:
        project_root = find_project_root(resolved.parent)
    except Exception:
        _log_stderr(f"skip: no .lexibrary/ found for {resolved}")
        return

    config = load_config(project_root)

    if not config.curator.reactive.enabled:
        _log_stderr("skip: reactive hooks disabled")
        return

    _log_stderr(f"post-edit: {resolved.name}")
    post_edit_hook_sync(resolved, project_root, config=config)
    _log_stderr("post-edit: done")


def run_post_bead_close(directory: str | Path) -> None:
    """Hook runner for post-bead-close events.

    Discovers the project root, loads config, and calls
    :func:`~hooks.post_bead_close_hook_sync`.

    Args:
        directory: Path to the directory affected by the closed bead.
    """
    resolved = Path(directory).resolve()
    try:
        project_root = find_project_root(resolved)
    except Exception:
        _log_stderr(f"skip: no .lexibrary/ found for {resolved}")
        return

    config = load_config(project_root)

    if not config.curator.reactive.enabled:
        _log_stderr("skip: reactive hooks disabled")
        return

    _log_stderr(f"post-bead-close: {resolved.name}")
    post_bead_close_hook_sync(resolved, project_root, config=config)
    _log_stderr("post-bead-close: done")


def run_validation_failure(errors: list[ValidationIssue]) -> None:
    """Hook runner for validation-failure events.

    Discovers the project root from cwd, loads config, and calls
    :func:`~hooks.validation_failure_hook_sync`.

    Args:
        errors: List of :class:`~lexibrary.validator.report.ValidationIssue`
            instances to evaluate against the severity threshold.
    """
    try:
        project_root = find_project_root()
    except Exception:
        _log_stderr("skip: no .lexibrary/ found from cwd")
        return

    config = load_config(project_root)

    if not config.curator.reactive.enabled:
        _log_stderr("skip: reactive hooks disabled")
        return

    _log_stderr(f"validation-failure: {len(errors)} issue(s)")
    validation_failure_hook_sync(errors, project_root, config=config)
    _log_stderr("validation-failure: done")
