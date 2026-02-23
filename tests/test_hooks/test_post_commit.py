"""Tests for hooks/post_commit.py — git post-commit hook installation."""

from __future__ import annotations

import stat
from pathlib import Path

from lexibrary.hooks.post_commit import (
    HOOK_MARKER,
    HOOK_SCRIPT_TEMPLATE,
    install_post_commit_hook,
)

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_git_repo(tmp_path: Path) -> Path:
    """Create a minimal .git directory structure and return project root."""
    (tmp_path / ".git" / "hooks").mkdir(parents=True)
    return tmp_path


# ---------------------------------------------------------------------------
# Create hook (no existing hook)
# ---------------------------------------------------------------------------


def test_creates_hook_in_new_repo(tmp_path: Path) -> None:
    """install_post_commit_hook creates a new hook file when none exists."""
    root = _make_git_repo(tmp_path)
    result = install_post_commit_hook(root)

    hook_path = root / ".git" / "hooks" / "post-commit"
    assert result.installed is True
    assert result.already_installed is False
    assert result.no_git_dir is False
    assert hook_path.is_file()


def test_new_hook_has_shebang(tmp_path: Path) -> None:
    """A newly created hook starts with #!/bin/sh."""
    root = _make_git_repo(tmp_path)
    install_post_commit_hook(root)

    content = (root / ".git" / "hooks" / "post-commit").read_text()
    assert content.startswith("#!/bin/sh\n")


# ---------------------------------------------------------------------------
# Executable permissions
# ---------------------------------------------------------------------------


def test_hook_is_executable(tmp_path: Path) -> None:
    """The hook file is made executable after installation."""
    root = _make_git_repo(tmp_path)
    install_post_commit_hook(root)

    hook_path = root / ".git" / "hooks" / "post-commit"
    mode = hook_path.stat().st_mode
    assert mode & stat.S_IXUSR, "Owner execute bit should be set"
    assert mode & stat.S_IXGRP, "Group execute bit should be set"
    assert mode & stat.S_IXOTH, "Other execute bit should be set"


def test_existing_hook_remains_executable(tmp_path: Path) -> None:
    """Appending to an existing hook preserves/adds execute permissions."""
    root = _make_git_repo(tmp_path)
    hook_path = root / ".git" / "hooks" / "post-commit"
    hook_path.write_text("#!/bin/sh\necho 'existing'\n")
    # Remove execute bits first
    hook_path.chmod(0o644)

    install_post_commit_hook(root)

    mode = hook_path.stat().st_mode
    assert mode & stat.S_IXUSR, "Execute bit should be added"


# ---------------------------------------------------------------------------
# Append to existing hook
# ---------------------------------------------------------------------------


def test_appends_to_existing_hook(tmp_path: Path) -> None:
    """Hook script is appended to an existing post-commit hook."""
    root = _make_git_repo(tmp_path)
    hook_path = root / ".git" / "hooks" / "post-commit"
    original = "#!/bin/sh\necho 'pre-existing hook'\n"
    hook_path.write_text(original)
    hook_path.chmod(0o755)

    result = install_post_commit_hook(root)

    assert result.installed is True
    content = hook_path.read_text()
    assert "pre-existing hook" in content, "Original content preserved"
    assert HOOK_MARKER in content, "Lexibrary marker added"


def test_existing_content_preserved_on_append(tmp_path: Path) -> None:
    """All lines of the original hook are preserved after append."""
    root = _make_git_repo(tmp_path)
    hook_path = root / ".git" / "hooks" / "post-commit"
    original_lines = [
        "#!/bin/sh",
        "# My custom hook",
        "npm test",
        "echo 'done'",
    ]
    hook_path.write_text("\n".join(original_lines) + "\n")
    hook_path.chmod(0o755)

    install_post_commit_hook(root)

    content = hook_path.read_text()
    for line in original_lines:
        assert line in content, f"Line '{line}' should be preserved"


# ---------------------------------------------------------------------------
# Idempotent installation
# ---------------------------------------------------------------------------


def test_idempotent_second_call(tmp_path: Path) -> None:
    """Second call with marker already present returns already_installed."""
    root = _make_git_repo(tmp_path)
    first = install_post_commit_hook(root)
    second = install_post_commit_hook(root)

    assert first.installed is True
    assert second.already_installed is True
    assert second.installed is False


def test_idempotent_no_duplicate(tmp_path: Path) -> None:
    """Calling install twice does not duplicate the hook script."""
    root = _make_git_repo(tmp_path)
    install_post_commit_hook(root)
    install_post_commit_hook(root)

    content = (root / ".git" / "hooks" / "post-commit").read_text()
    assert content.count(HOOK_MARKER) == 1


# ---------------------------------------------------------------------------
# No .git directory
# ---------------------------------------------------------------------------


def test_no_git_dir(tmp_path: Path) -> None:
    """Returns no_git_dir=True when .git does not exist."""
    result = install_post_commit_hook(tmp_path)

    assert result.no_git_dir is True
    assert result.installed is False
    assert result.already_installed is False


def test_no_git_dir_message(tmp_path: Path) -> None:
    """Message indicates no git repository was found."""
    result = install_post_commit_hook(tmp_path)

    assert "no .git directory" in result.message.lower() or "no .git" in result.message.lower()


def test_no_crash_without_git(tmp_path: Path) -> None:
    """No exception is raised when .git is absent."""
    # This test verifies the function handles the missing directory gracefully.
    # If it raised, the test would fail automatically.
    result = install_post_commit_hook(tmp_path)
    assert result.no_git_dir is True


# ---------------------------------------------------------------------------
# Script content
# ---------------------------------------------------------------------------


def test_script_uses_git_diff_tree(tmp_path: Path) -> None:
    """Hook script uses git diff-tree to list changed files."""
    root = _make_git_repo(tmp_path)
    install_post_commit_hook(root)

    content = (root / ".git" / "hooks" / "post-commit").read_text()
    assert "git diff-tree --no-commit-id --name-only -r HEAD" in content


def test_script_uses_changed_only_flag(tmp_path: Path) -> None:
    """Hook script passes --changed-only to lexictl update."""
    root = _make_git_repo(tmp_path)
    install_post_commit_hook(root)

    content = (root / ".git" / "hooks" / "post-commit").read_text()
    assert "--changed-only" in content


def test_script_runs_in_background(tmp_path: Path) -> None:
    """Hook script runs lexictl update in the background (&)."""
    root = _make_git_repo(tmp_path)
    install_post_commit_hook(root)

    content = (root / ".git" / "hooks" / "post-commit").read_text()
    # The & should appear on the lexictl update line
    assert "lexictl update --changed-only" in content
    # Check for background execution (&) and log redirection
    for line in content.splitlines():
        if "lexictl update" in line:
            assert "&" in line, "lexictl update should run in background"
            break


def test_script_redirects_to_log(tmp_path: Path) -> None:
    """Hook script redirects output to .lexibrary/daemon.log."""
    root = _make_git_repo(tmp_path)
    install_post_commit_hook(root)

    content = (root / ".git" / "hooks" / "post-commit").read_text()
    assert ".lexibrary/daemon.log" in content


def test_hook_marker_present(tmp_path: Path) -> None:
    """The hook script contains the Lexibrary marker comment."""
    root = _make_git_repo(tmp_path)
    install_post_commit_hook(root)

    content = (root / ".git" / "hooks" / "post-commit").read_text()
    assert HOOK_MARKER in content


# ---------------------------------------------------------------------------
# hooks_dir creation
# ---------------------------------------------------------------------------


def test_creates_hooks_dir_if_missing(tmp_path: Path) -> None:
    """If .git exists but .git/hooks does not, hooks dir is created."""
    (tmp_path / ".git").mkdir()
    # No hooks subdir

    result = install_post_commit_hook(tmp_path)

    assert result.installed is True
    assert (tmp_path / ".git" / "hooks" / "post-commit").is_file()


# ---------------------------------------------------------------------------
# Template constant
# ---------------------------------------------------------------------------


def test_hook_script_template_contains_marker() -> None:
    """HOOK_SCRIPT_TEMPLATE includes the marker for idempotent detection."""
    assert HOOK_MARKER in HOOK_SCRIPT_TEMPLATE


def test_hook_script_template_contains_diff_tree() -> None:
    """HOOK_SCRIPT_TEMPLATE uses git diff-tree."""
    assert "git diff-tree" in HOOK_SCRIPT_TEMPLATE
