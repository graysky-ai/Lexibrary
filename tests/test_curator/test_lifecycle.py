"""Tests for curator lifecycle state machine.

Covers all four task items from Group 10 (Lifecycle Unit Tests):
- 10.1 Valid transitions for each artifact type
- 10.2 Invalid transitions raise InvalidTransitionError
- 10.3 can_hard_delete() guard logic
- 10.4 Sidecar cleanup ordering in execute_hard_delete()
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lexibrary.curator.lifecycle import (
    VALID_TRANSITIONS,
    InvalidTransitionError,
    can_hard_delete,
    execute_hard_delete,
    is_terminal,
    validate_transition,
)

# ---------------------------------------------------------------------------
# 10.1 — Valid transitions for each artifact type
# ---------------------------------------------------------------------------


class TestValidTransitionsDesignFile:
    """Design file: active -> deprecated, active -> unlinked, unlinked -> active."""

    def test_active_to_deprecated(self) -> None:
        validate_transition("design_file", "active", "deprecated")

    def test_active_to_unlinked(self) -> None:
        validate_transition("design_file", "active", "unlinked")

    def test_unlinked_to_active(self) -> None:
        validate_transition("design_file", "unlinked", "active")


class TestValidTransitionsConcept:
    """Concept: draft -> active -> deprecated -> hard_deleted."""

    def test_draft_to_active(self) -> None:
        validate_transition("concept", "draft", "active")

    def test_active_to_deprecated(self) -> None:
        validate_transition("concept", "active", "deprecated")

    def test_deprecated_to_hard_deleted(self) -> None:
        validate_transition("concept", "deprecated", "hard_deleted")


class TestValidTransitionsConvention:
    """Convention: draft -> active -> deprecated -> hard_deleted."""

    def test_draft_to_active(self) -> None:
        validate_transition("convention", "draft", "active")

    def test_active_to_deprecated(self) -> None:
        validate_transition("convention", "active", "deprecated")

    def test_deprecated_to_hard_deleted(self) -> None:
        validate_transition("convention", "deprecated", "hard_deleted")


class TestValidTransitionsPlaybook:
    """Playbook: draft -> active -> deprecated -> hard_deleted."""

    def test_draft_to_active(self) -> None:
        validate_transition("playbook", "draft", "active")

    def test_active_to_deprecated(self) -> None:
        validate_transition("playbook", "active", "deprecated")

    def test_deprecated_to_hard_deleted(self) -> None:
        validate_transition("playbook", "deprecated", "hard_deleted")


class TestValidTransitionsStackPost:
    """Stack post: open -> resolved/duplicate/outdated, resolved -> stale, stale -> resolved."""

    def test_open_to_resolved(self) -> None:
        validate_transition("stack_post", "open", "resolved")

    def test_open_to_duplicate(self) -> None:
        validate_transition("stack_post", "open", "duplicate")

    def test_open_to_outdated(self) -> None:
        validate_transition("stack_post", "open", "outdated")

    def test_resolved_to_stale(self) -> None:
        validate_transition("stack_post", "resolved", "stale")

    def test_stale_to_resolved(self) -> None:
        validate_transition("stack_post", "stale", "resolved")


class TestValidTransitionsCompleteness:
    """Verify VALID_TRANSITIONS has the expected number of entries."""

    def test_transition_count(self) -> None:
        assert len(VALID_TRANSITIONS) == 14


# ---------------------------------------------------------------------------
# 10.2 — Invalid transitions raise InvalidTransitionError
# ---------------------------------------------------------------------------


class TestInvalidTransitions:
    """Invalid transitions must raise InvalidTransitionError."""

    def test_concept_draft_to_deprecated_invalid(self) -> None:
        """draft -> deprecated is explicitly INVALID for concepts."""
        with pytest.raises(InvalidTransitionError) as exc_info:
            validate_transition("concept", "draft", "deprecated")
        assert exc_info.value.kind == "concept"
        assert exc_info.value.current == "draft"
        assert exc_info.value.target == "deprecated"

    def test_playbook_draft_to_deprecated_invalid(self) -> None:
        """draft -> deprecated is explicitly INVALID for playbooks."""
        with pytest.raises(InvalidTransitionError) as exc_info:
            validate_transition("playbook", "draft", "deprecated")
        assert exc_info.value.kind == "playbook"
        assert exc_info.value.current == "draft"
        assert exc_info.value.target == "deprecated"

    def test_design_file_deprecated_is_terminal(self) -> None:
        """No transitions allowed from terminal deprecated for design files."""
        with pytest.raises(InvalidTransitionError):
            validate_transition("design_file", "deprecated", "active")

    def test_design_file_deprecated_to_unlinked_invalid(self) -> None:
        """deprecated -> unlinked is also invalid for design files."""
        with pytest.raises(InvalidTransitionError):
            validate_transition("design_file", "deprecated", "unlinked")

    def test_concept_active_to_draft_invalid(self) -> None:
        """Cannot go backwards from active to draft."""
        with pytest.raises(InvalidTransitionError):
            validate_transition("concept", "active", "draft")

    def test_convention_deprecated_to_active_invalid(self) -> None:
        """Conventions cannot go from deprecated back to active."""
        with pytest.raises(InvalidTransitionError):
            validate_transition("convention", "deprecated", "active")

    def test_stack_post_resolved_to_open_invalid(self) -> None:
        """Cannot re-open a resolved stack post."""
        with pytest.raises(InvalidTransitionError):
            validate_transition("stack_post", "resolved", "open")

    def test_stack_post_duplicate_has_no_transitions(self) -> None:
        """duplicate is a dead end for stack posts (not in VALID_TRANSITIONS)."""
        with pytest.raises(InvalidTransitionError):
            validate_transition("stack_post", "duplicate", "open")

    def test_stack_post_outdated_has_no_transitions(self) -> None:
        """outdated is a dead end for stack posts."""
        with pytest.raises(InvalidTransitionError):
            validate_transition("stack_post", "outdated", "open")

    def test_unknown_kind_raises(self) -> None:
        """Unknown artifact kind raises InvalidTransitionError."""
        with pytest.raises(InvalidTransitionError):
            validate_transition("unknown_kind", "active", "deprecated")

    def test_error_message_format(self) -> None:
        """Error message includes kind, current, and target."""
        with pytest.raises(InvalidTransitionError, match="concept.*draft.*deprecated"):
            validate_transition("concept", "draft", "deprecated")


class TestIsTerminal:
    """is_terminal() checks terminal statuses."""

    def test_design_file_deprecated_is_terminal(self) -> None:
        assert is_terminal("design_file", "deprecated") is True

    def test_design_file_active_not_terminal(self) -> None:
        assert is_terminal("design_file", "active") is False

    def test_design_file_unlinked_not_terminal(self) -> None:
        assert is_terminal("design_file", "unlinked") is False

    def test_concept_deprecated_not_terminal(self) -> None:
        """Concepts proceed to hard delete, so deprecated is NOT terminal."""
        assert is_terminal("concept", "deprecated") is False

    def test_convention_deprecated_not_terminal(self) -> None:
        assert is_terminal("convention", "deprecated") is False

    def test_playbook_deprecated_not_terminal(self) -> None:
        assert is_terminal("playbook", "deprecated") is False

    def test_unknown_kind_not_terminal(self) -> None:
        """Unknown kinds have no terminal statuses."""
        assert is_terminal("unknown_kind", "deprecated") is False


# ---------------------------------------------------------------------------
# 10.3 — can_hard_delete() guard logic
# ---------------------------------------------------------------------------


@dataclass
class _FakeLinkResult:
    """Minimal stub for LinkResult with just the source_path attribute."""

    source_id: int
    source_path: str
    link_type: str
    link_context: str | None


class TestCanHardDelete:
    """can_hard_delete() checks TTL and zero-ref guards."""

    def test_allowed_when_ttl_passed_and_zero_refs(self) -> None:
        """Returns (True, '') when TTL passed and link graph returns empty."""
        mock_graph = MagicMock()
        mock_graph.reverse_deps.return_value = []

        allowed, reason = can_hard_delete(
            artifact_path="concepts/old.md",
            ttl_commits=50,
            commits_since_deprecation=60,
            link_graph=mock_graph,
        )

        assert allowed is True
        assert reason == ""
        mock_graph.reverse_deps.assert_called_once_with("concepts/old.md")

    def test_rejected_when_ttl_not_passed(self) -> None:
        """Returns (False, reason) when commits_since_deprecation < ttl_commits."""
        mock_graph = MagicMock()

        allowed, reason = can_hard_delete(
            artifact_path="concepts/recent.md",
            ttl_commits=50,
            commits_since_deprecation=30,
            link_graph=mock_graph,
        )

        assert allowed is False
        assert "TTL not reached" in reason
        assert "30" in reason
        assert "50" in reason
        # reverse_deps should NOT be called if TTL check fails first
        mock_graph.reverse_deps.assert_not_called()

    def test_rejected_when_refs_still_exist(self) -> None:
        """Returns (False, reason) when reverse_deps returns non-empty list."""
        mock_graph = MagicMock()
        mock_graph.reverse_deps.return_value = [
            _FakeLinkResult(
                source_id=1,
                source_path="concepts/dependent.md",
                link_type="wikilink",
                link_context=None,
            ),
            _FakeLinkResult(
                source_id=2,
                source_path="conventions/uses-it.md",
                link_type="wikilink",
                link_context=None,
            ),
        ]

        allowed, reason = can_hard_delete(
            artifact_path="concepts/referenced.md",
            ttl_commits=50,
            commits_since_deprecation=100,
            link_graph=mock_graph,
        )

        assert allowed is False
        assert "2 inbound reference" in reason
        assert "concepts/dependent.md" in reason

    def test_allowed_when_link_graph_is_none(self) -> None:
        """When link_graph is None, skip ref check and allow if TTL passed."""
        allowed, reason = can_hard_delete(
            artifact_path="concepts/orphan.md",
            ttl_commits=50,
            commits_since_deprecation=60,
            link_graph=None,
        )

        assert allowed is True
        assert reason == ""

    def test_rejected_when_ttl_not_passed_and_no_graph(self) -> None:
        """TTL check still applies even when link_graph is None."""
        allowed, reason = can_hard_delete(
            artifact_path="concepts/new.md",
            ttl_commits=50,
            commits_since_deprecation=10,
            link_graph=None,
        )

        assert allowed is False
        assert "TTL not reached" in reason

    def test_exact_ttl_boundary(self) -> None:
        """Exactly meeting TTL (==) should be allowed."""
        mock_graph = MagicMock()
        mock_graph.reverse_deps.return_value = []

        allowed, reason = can_hard_delete(
            artifact_path="concepts/exact.md",
            ttl_commits=50,
            commits_since_deprecation=50,
            link_graph=mock_graph,
        )

        assert allowed is True
        assert reason == ""


# ---------------------------------------------------------------------------
# 10.4 — Sidecar cleanup ordering in execute_hard_delete()
# ---------------------------------------------------------------------------


class TestExecuteHardDeleteSidecarOrdering:
    """Verify .md deleted first, then .comments.yaml sidecar.

    Verify sidecar preserved when .md deletion raises.
    """

    def test_md_deleted_first_then_sidecar(self, tmp_path: Path) -> None:
        """Both .md and .comments.yaml are deleted in correct order."""
        # Create artifact and sidecar files
        md_file = tmp_path / "test-concept.md"
        sidecar_file = tmp_path / "test-concept.comments.yaml"
        md_file.write_text("---\nstatus: deprecated\n---\nContent\n")
        sidecar_file.write_text("comments: []\n")

        # Track deletion order
        deletion_order: list[str] = []
        original_unlink = Path.unlink

        def tracked_unlink(self: Path, *args: object, **kwargs: object) -> None:
            deletion_order.append(self.name)
            original_unlink(self)

        mock_graph = MagicMock()
        mock_graph.reverse_deps.return_value = []

        with (
            patch.object(Path, "unlink", tracked_unlink),
            patch(
                "lexibrary.curator.lifecycle._get_sidecar_path",
                return_value=sidecar_file,
            ),
            patch(
                "lexibrary.curator.lifecycle.can_hard_delete",
                return_value=(True, ""),
            ),
        ):
            execute_hard_delete(
                kind="concept",
                artifact_path=md_file,
                ttl_commits=50,
                commits_since_deprecation=100,
                link_graph=mock_graph,
            )

        assert deletion_order == ["test-concept.md", "test-concept.comments.yaml"]

    def test_sidecar_preserved_when_md_deletion_fails(self, tmp_path: Path) -> None:
        """If .md deletion raises OSError, sidecar must NOT be deleted."""
        md_file = tmp_path / "test-concept.md"
        sidecar_file = tmp_path / "test-concept.comments.yaml"
        md_file.write_text("---\nstatus: deprecated\n---\nContent\n")
        sidecar_file.write_text("comments: []\n")

        mock_graph = MagicMock()
        mock_graph.reverse_deps.return_value = []

        with (
            patch.object(Path, "unlink", side_effect=OSError("Permission denied")),
            patch(
                "lexibrary.curator.lifecycle._get_sidecar_path",
                return_value=sidecar_file,
            ),
            patch(
                "lexibrary.curator.lifecycle.can_hard_delete",
                return_value=(True, ""),
            ),
            pytest.raises(OSError, match="Permission denied"),
        ):
            execute_hard_delete(
                kind="concept",
                artifact_path=md_file,
                ttl_commits=50,
                commits_since_deprecation=100,
                link_graph=mock_graph,
            )

        # Sidecar must still exist on disk (original was not unlinked)
        assert sidecar_file.exists()

    def test_sidecar_missing_is_harmless(self, tmp_path: Path) -> None:
        """If .comments.yaml does not exist, deletion still succeeds."""
        md_file = tmp_path / "test-concept.md"
        md_file.write_text("---\nstatus: deprecated\n---\nContent\n")
        sidecar_file = tmp_path / "test-concept.comments.yaml"
        # Sidecar intentionally NOT created

        mock_graph = MagicMock()
        mock_graph.reverse_deps.return_value = []

        with (
            patch(
                "lexibrary.curator.lifecycle._get_sidecar_path",
                return_value=sidecar_file,
            ),
            patch(
                "lexibrary.curator.lifecycle.can_hard_delete",
                return_value=(True, ""),
            ),
        ):
            execute_hard_delete(
                kind="concept",
                artifact_path=md_file,
                ttl_commits=50,
                commits_since_deprecation=100,
                link_graph=mock_graph,
            )

        assert not md_file.exists()
        assert not sidecar_file.exists()

    def test_hard_delete_rejected_raises_value_error(self) -> None:
        """If can_hard_delete returns False, ValueError is raised."""
        mock_graph = MagicMock()
        mock_graph.reverse_deps.return_value = [
            _FakeLinkResult(
                source_id=1,
                source_path="other.md",
                link_type="wikilink",
                link_context=None,
            ),
        ]

        with pytest.raises(ValueError, match="Cannot hard-delete"):
            execute_hard_delete(
                kind="concept",
                artifact_path=Path("/fake/concept.md"),
                ttl_commits=50,
                commits_since_deprecation=100,
                link_graph=mock_graph,
            )

    def test_convention_sidecar_deleted(self, tmp_path: Path) -> None:
        """Convention .comments.yaml is also deleted after .md."""
        md_file = tmp_path / "test-convention.md"
        sidecar_file = tmp_path / "test-convention.comments.yaml"
        md_file.write_text("---\nstatus: deprecated\n---\nContent\n")
        sidecar_file.write_text("comments: []\n")

        deletion_order: list[str] = []
        original_unlink = Path.unlink

        def tracked_unlink(self: Path, *args: object, **kwargs: object) -> None:
            deletion_order.append(self.name)
            original_unlink(self)

        mock_graph = MagicMock()
        mock_graph.reverse_deps.return_value = []

        with (
            patch.object(Path, "unlink", tracked_unlink),
            patch(
                "lexibrary.curator.lifecycle._get_sidecar_path",
                return_value=sidecar_file,
            ),
            patch(
                "lexibrary.curator.lifecycle.can_hard_delete",
                return_value=(True, ""),
            ),
        ):
            execute_hard_delete(
                kind="convention",
                artifact_path=md_file,
                ttl_commits=50,
                commits_since_deprecation=100,
                link_graph=mock_graph,
            )

        assert deletion_order == ["test-convention.md", "test-convention.comments.yaml"]

    def test_playbook_sidecar_deleted(self, tmp_path: Path) -> None:
        """Playbook .comments.yaml is also deleted after .md."""
        md_file = tmp_path / "test-playbook.md"
        sidecar_file = tmp_path / "test-playbook.comments.yaml"
        md_file.write_text("---\nstatus: deprecated\n---\nContent\n")
        sidecar_file.write_text("comments: []\n")

        deletion_order: list[str] = []
        original_unlink = Path.unlink

        def tracked_unlink(self: Path, *args: object, **kwargs: object) -> None:
            deletion_order.append(self.name)
            original_unlink(self)

        mock_graph = MagicMock()
        mock_graph.reverse_deps.return_value = []

        with (
            patch.object(Path, "unlink", tracked_unlink),
            patch(
                "lexibrary.curator.lifecycle._get_sidecar_path",
                return_value=sidecar_file,
            ),
            patch(
                "lexibrary.curator.lifecycle.can_hard_delete",
                return_value=(True, ""),
            ),
        ):
            execute_hard_delete(
                kind="playbook",
                artifact_path=md_file,
                ttl_commits=50,
                commits_since_deprecation=100,
                link_graph=mock_graph,
            )

        assert deletion_order == ["test-playbook.md", "test-playbook.comments.yaml"]
