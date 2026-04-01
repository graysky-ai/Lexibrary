"""Unit tests for lexibrary.services.design_render — rendering functions."""

from __future__ import annotations

from lexibrary.services.design import DesignUpdateDecision
from lexibrary.services.design_render import (
    render_failure,
    render_skeleton_warning,
    render_skip,
    render_success,
)

# ---------------------------------------------------------------------------
# render_skip() tests
# ---------------------------------------------------------------------------


class TestRenderSkip:
    """Tests for the render_skip() function."""

    def test_protected_with_updated_by(self) -> None:
        """Protected skip includes updated_by value and --force hint."""
        decision = DesignUpdateDecision(
            action="skip",
            reason="Design file was last updated by agent. Use --force / -f to override.",
            skip_code="protected",
        )
        output = render_skip(decision, updated_by="agent")

        assert "agent" in output
        assert "--force" in output or "-f" in output

    def test_protected_without_updated_by(self) -> None:
        """Protected skip without updated_by falls back to reason."""
        decision = DesignUpdateDecision(
            action="skip",
            reason="Design file was last updated by maintainer. Use --force / -f to override.",
            skip_code="protected",
        )
        output = render_skip(decision)

        assert "Skipped:" in output

    def test_up_to_date(self) -> None:
        """Up-to-date skip indicates design file is current."""
        decision = DesignUpdateDecision(
            action="skip",
            reason="Design file for src/main.py is up to date",
            skip_code="up_to_date",
        )
        output = render_skip(decision)

        assert "up to date" in output

    def test_iwh_blocked(self) -> None:
        """IWH blocked skip includes directory path and signal body."""
        decision = DesignUpdateDecision(
            action="skip",
            reason=(
                "IWH blocked signal in src/auth/: Concurrent work. "
                "Resolve the IWH signal before updating."
            ),
            skip_code="iwh_blocked",
        )
        output = render_skip(decision)

        assert "src/auth" in output
        assert "Concurrent work" in output

    def test_unknown_skip_code(self) -> None:
        """Unknown skip code falls back to reason."""
        decision = DesignUpdateDecision(
            action="skip",
            reason="Some unexpected reason",
            skip_code="unknown_code",
        )
        output = render_skip(decision)

        assert "Skipped:" in output
        assert "Some unexpected reason" in output


# ---------------------------------------------------------------------------
# render_success() tests
# ---------------------------------------------------------------------------


class TestRenderSuccess:
    """Tests for the render_success() function."""

    def test_includes_change_level(self) -> None:
        """Success message includes the change level."""
        output = render_success("src/auth/login.py", "NEW_FILE")

        assert "src/auth/login.py" in output
        assert "NEW_FILE" in output

    def test_interface_change(self) -> None:
        """Success message shows INTERFACE_CHANGE level."""
        output = render_success("src/utils.py", "INTERFACE_CHANGE")

        assert "INTERFACE_CHANGE" in output

    def test_body_change(self) -> None:
        """Success message shows BODY_CHANGE level."""
        output = render_success("src/core.py", "BODY_CHANGE")

        assert "BODY_CHANGE" in output


# ---------------------------------------------------------------------------
# render_failure() tests
# ---------------------------------------------------------------------------


class TestRenderFailure:
    """Tests for the render_failure() function."""

    def test_includes_reason(self) -> None:
        """Failure message includes the failure reason."""
        output = render_failure("src/broken.py", "LLM API timeout")

        assert "src/broken.py" in output
        assert "LLM API timeout" in output

    def test_includes_file_path(self) -> None:
        """Failure message includes the source file path."""
        output = render_failure("src/deep/nested/mod.py", "Connection refused")

        assert "src/deep/nested/mod.py" in output
        assert "Connection refused" in output


# ---------------------------------------------------------------------------
# render_skeleton_warning() tests
# ---------------------------------------------------------------------------


class TestRenderSkeletonWarning:
    """Tests for the render_skeleton_warning() function."""

    def test_warns_llm_not_used(self) -> None:
        """Warning mentions LLM was not used."""
        output = render_skeleton_warning("src/large.py", "file exceeds token limit")

        assert "skeleton" in output.lower()
        assert "LLM not used" in output
        assert "file exceeds token limit" in output

    def test_suggests_unlimited(self) -> None:
        """Warning suggests --unlimited flag."""
        output = render_skeleton_warning("src/huge.py", "token budget exceeded")

        assert "--unlimited" in output

    def test_includes_source_path(self) -> None:
        """Warning includes the source file path."""
        output = render_skeleton_warning("src/module.py", "too large")

        assert "src/module.py" in output
