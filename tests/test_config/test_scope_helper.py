"""Tests for the find_owning_root helper and load-time scope guards.

``find_owning_root`` is the single funnel every ownership decision flows
through; a regression here propagates into archivist, validator, conventions,
lookup, bootstrap, and CLI gating. These tests pin:

- First-match-wins precedence.
- Exact-path-match ownership (path equals a declared root).
- Absence when the path is outside every declared root.
- Ownership resolution for roots that do not yet exist on disk (existence
  filtering is a different concern — it lives in ``resolved_scope_roots``).
- The load-time path-traversal, nested-root, and duplicate-entry guards on
  ``LexibraryConfig.resolved_scope_roots``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lexibrary.config.schema import LexibraryConfig, ScopeRoot
from lexibrary.config.scope import find_owning_root


def test_find_owning_root_first_match_wins(tmp_path: Path) -> None:
    """When a path is inside multiple declared roots, the first declared wins."""
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "b").mkdir()
    # Two roots where ``a`` is an ancestor of ``a/b``; declared order chooses
    # the winner. (Note: this scenario only arises because we bypass the
    # nested-root guard by calling find_owning_root directly — the guard
    # prevents such a config from loading in practice.)
    roots = [ScopeRoot(path="a"), ScopeRoot(path="a/b")]
    result = find_owning_root(tmp_path / "a" / "b" / "x.py", roots, tmp_path)
    assert result is not None
    assert result.path == "a"


def test_find_owning_root_path_equals_root(tmp_path: Path) -> None:
    """A path equal to a declared root is owned by that root."""
    (tmp_path / "src").mkdir()
    roots = [ScopeRoot(path="src")]
    result = find_owning_root(tmp_path / "src", roots, tmp_path)
    assert result is not None
    assert result.path == "src"


def test_find_owning_root_path_outside_all_roots(tmp_path: Path) -> None:
    """A path not under any declared root returns None."""
    (tmp_path / "src").mkdir()
    (tmp_path / "docs").mkdir()
    roots = [ScopeRoot(path="src")]
    result = find_owning_root(tmp_path / "docs" / "README.md", roots, tmp_path)
    assert result is None


def test_find_owning_root_nonexistent_root_still_resolves(tmp_path: Path) -> None:
    """Lookups against declared-but-missing roots still compare lexically.

    Existence filtering is ``resolved_scope_roots``' job; ``find_owning_root``
    must answer ownership questions for declared roots regardless of whether
    they exist on disk yet (e.g. sparse-checkout scenarios).
    """
    # ``ghost/`` is not created — the lookup should still succeed for a path
    # that (lexically) sits under it.
    roots = [ScopeRoot(path="ghost")]
    result = find_owning_root(tmp_path / "ghost" / "a.py", roots, tmp_path)
    assert result is not None
    assert result.path == "ghost"


def test_find_owning_root_returns_first_declared_when_two_roots_apply(
    tmp_path: Path,
) -> None:
    """Declared order sets precedence even when a non-nesting match is second."""
    (tmp_path / "src").mkdir()
    (tmp_path / "baml_src").mkdir()
    roots = [ScopeRoot(path="src"), ScopeRoot(path="baml_src")]
    # baml_src branch.
    result = find_owning_root(tmp_path / "baml_src" / "x.baml", roots, tmp_path)
    assert result is not None
    assert result.path == "baml_src"


# --- Load-time guard tests on resolved_scope_roots ---


def test_resolved_scope_roots_rejects_path_traversal_names_entry(
    tmp_path: Path,
) -> None:
    """Path-traversal error names the offending entry."""
    config = LexibraryConfig.model_validate(
        {"scope_roots": [{"path": "../../etc"}]}
    )
    with pytest.raises(ValueError) as exc_info:
        config.resolved_scope_roots(tmp_path)
    assert "../../etc" in str(exc_info.value)


def test_resolved_scope_roots_rejects_nested_roots_names_both(
    tmp_path: Path,
) -> None:
    """Nested-root error names both declared paths so the user can fix either."""
    (tmp_path / "src").mkdir()
    config = LexibraryConfig.model_validate(
        {"scope_roots": [{"path": "."}, {"path": "src/"}]}
    )
    with pytest.raises(ValueError) as exc_info:
        config.resolved_scope_roots(tmp_path)
    message = str(exc_info.value)
    assert "." in message
    assert "src/" in message


def test_resolved_scope_roots_rejects_duplicate_entries(tmp_path: Path) -> None:
    """Duplicate entries (exact same ``path`` string) raise."""
    (tmp_path / "src").mkdir()
    config = LexibraryConfig.model_validate(
        {"scope_roots": [{"path": "src/"}, {"path": "src/"}]}
    )
    with pytest.raises(ValueError, match="Duplicate"):
        config.resolved_scope_roots(tmp_path)
