"""Git pre-commit hook installation for Lexibrary.

Installs a pre-commit hook that runs ``lexictl validate --ci --severity error``
before each commit.  If validation fails the commit is blocked; the user can
bypass with ``git commit --no-verify``.
"""

from __future__ import annotations

import stat
from dataclasses import dataclass
from pathlib import Path

from lexibrary.templates import read_template

# Marker used to detect whether the Lexibrary section is already present
# in an existing hook script.  Must appear on its own line.
HOOK_MARKER = "# lexibrary:pre-commit"

# The hook script appended (or written) to .git/hooks/pre-commit.
# Runs lexictl validate in CI mode and blocks the commit on failure.
HOOK_SCRIPT_TEMPLATE = read_template("hooks/pre-commit.sh").replace(
    "{hook_marker}", HOOK_MARKER
)


@dataclass
class HookInstallResult:
    """Result of a hook installation attempt.

    Attributes:
        installed: ``True`` if the hook was created or updated.
        already_installed: ``True`` if the marker was already present.
        no_git_dir: ``True`` if no ``.git`` directory was found.
        message: Human-readable status message.
    """

    installed: bool = False
    already_installed: bool = False
    no_git_dir: bool = False
    message: str = ""


def install_pre_commit_hook(project_root: Path) -> HookInstallResult:
    """Install or update the Lexibrary pre-commit git hook.

    Behaviour:
    - If ``project_root/.git`` does not exist, returns a result with
      ``no_git_dir=True`` and no file changes.
    - If ``.git/hooks/pre-commit`` does not exist, creates a new hook
      file containing a shebang and the Lexibrary hook script, then
      makes it executable.
    - If the file exists but does **not** contain the Lexibrary
      marker, appends the hook script to the existing file.
    - If the marker is already present (idempotent check), returns a
      result with ``already_installed=True``.

    Args:
        project_root: Absolute path to the project root (where ``.git/``
            lives).

    Returns:
        A :class:`HookInstallResult` describing what happened.
    """
    git_dir = project_root / ".git"
    if not git_dir.is_dir():
        return HookInstallResult(
            no_git_dir=True,
            message="No .git directory found — skipping hook installation.",
        )

    hooks_dir = git_dir / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)

    hook_path = hooks_dir / "pre-commit"

    if hook_path.exists():
        existing_content = hook_path.read_text(encoding="utf-8")

        # Idempotent: already installed
        if HOOK_MARKER in existing_content:
            return HookInstallResult(
                already_installed=True,
                message="Lexibrary pre-commit hook is already installed.",
            )

        # Append to existing hook
        separator = "" if existing_content.endswith("\n") else "\n"
        new_content = existing_content + separator + "\n" + HOOK_SCRIPT_TEMPLATE
        hook_path.write_text(new_content, encoding="utf-8")
        _ensure_executable(hook_path)

        return HookInstallResult(
            installed=True,
            message="Lexibrary pre-commit hook appended to existing hook.",
        )

    # Create new hook file with shebang
    new_content = "#!/bin/sh\n\n" + HOOK_SCRIPT_TEMPLATE
    hook_path.write_text(new_content, encoding="utf-8")
    _ensure_executable(hook_path)

    return HookInstallResult(
        installed=True,
        message="Lexibrary pre-commit hook installed.",
    )


def _ensure_executable(path: Path) -> None:
    """Add owner/group/other execute bits to *path*."""
    current = path.stat().st_mode
    path.chmod(current | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
