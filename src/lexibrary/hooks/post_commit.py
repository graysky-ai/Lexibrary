"""Git post-commit hook installation for Lexibrary.

Installs a post-commit hook that automatically updates the Lexibrary
library for files changed in the most recent commit.  The hook runs
``lexictl update --changed-only`` in the background so it never blocks
the developer's workflow.
"""

from __future__ import annotations

import stat
from dataclasses import dataclass
from pathlib import Path

# Marker used to detect whether the Lexibrary section is already present
# in an existing hook script.  Must appear on its own line.
HOOK_MARKER = "# lexibrary:post-commit"

# The hook script appended (or written) to .git/hooks/post-commit.
# Uses git diff-tree to list changed files and passes them to lexictl
# in the background, redirecting output to .lexibrary.log.
HOOK_SCRIPT_TEMPLATE = f"""\
{HOOK_MARKER}
# — Lexibrary auto-update (installed by lexictl setup --hooks) —
CHANGED_FILES=$(git diff-tree --no-commit-id --name-only -r HEAD)
if [ -n "$CHANGED_FILES" ]; then
    lexictl update --changed-only $CHANGED_FILES >> .lexibrary/daemon.log 2>&1 &
fi
# — end Lexibrary —
"""


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


def install_post_commit_hook(project_root: Path) -> HookInstallResult:
    """Install or update the Lexibrary post-commit git hook.

    Behaviour:
    - If ``project_root/.git`` does not exist, returns a result with
      ``no_git_dir=True`` and no file changes.
    - If ``.git/hooks/post-commit`` does not exist, creates a new hook
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

    hook_path = hooks_dir / "post-commit"

    if hook_path.exists():
        existing_content = hook_path.read_text(encoding="utf-8")

        # Idempotent: already installed
        if HOOK_MARKER in existing_content:
            return HookInstallResult(
                already_installed=True,
                message="Lexibrary post-commit hook is already installed.",
            )

        # Append to existing hook
        separator = "" if existing_content.endswith("\n") else "\n"
        new_content = existing_content + separator + "\n" + HOOK_SCRIPT_TEMPLATE
        hook_path.write_text(new_content, encoding="utf-8")
        _ensure_executable(hook_path)

        return HookInstallResult(
            installed=True,
            message="Lexibrary post-commit hook appended to existing hook.",
        )

    # Create new hook file with shebang
    new_content = "#!/bin/sh\n\n" + HOOK_SCRIPT_TEMPLATE
    hook_path.write_text(new_content, encoding="utf-8")
    _ensure_executable(hook_path)

    return HookInstallResult(
        installed=True,
        message="Lexibrary post-commit hook installed.",
    )


def _ensure_executable(path: Path) -> None:
    """Add owner/group/other execute bits to *path*."""
    current = path.stat().st_mode
    path.chmod(current | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
