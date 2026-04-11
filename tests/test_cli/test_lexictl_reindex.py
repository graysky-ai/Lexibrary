"""Tests for the ``lexictl update --reindex`` flag."""

from __future__ import annotations

from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from lexibrary.cli import lexictl_app
from lexibrary.linkgraph.builder import BuildResult

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_project_root(tmp_path: Path) -> AbstractContextManager[Any]:
    """Return a patch that makes ``require_project_root`` return *tmp_path*."""
    return patch(
        "lexibrary.cli.lexictl_app.require_project_root",
        return_value=tmp_path,
    )


def _mock_load_config() -> AbstractContextManager[Any]:
    """Return a patch that makes ``load_config`` return a default config mock.

    ``load_config`` is lazily imported inside the ``update()`` function body,
    so we must patch it at its definition site.
    """
    return patch(
        "lexibrary.config.loader.load_config",
        return_value=MagicMock(),
    )


def _successful_build_result(
    artifact_count: int = 100,
    link_count: int = 500,
    duration_ms: int = 1300,
    errors: list[str] | None = None,
) -> BuildResult:
    """Create a ``BuildResult`` with sensible defaults."""
    return BuildResult(
        artifact_count=artifact_count,
        link_count=link_count,
        duration_ms=duration_ms,
        errors=errors or [],
    )


# ---------------------------------------------------------------------------
# 4.1 — reindex succeeds with normal output
# ---------------------------------------------------------------------------


class TestReindexSuccess:
    """Task 4.1: reindex succeeds with normal output."""

    def test_reindex_succeeds_with_normal_output(self, tmp_path: Path) -> None:
        mock_build = MagicMock(
            return_value=_successful_build_result(
                artifact_count=100,
                link_count=500,
                duration_ms=1300,
                errors=[],
            ),
        )

        with (
            _mock_project_root(tmp_path),
            _mock_load_config(),
            patch("lexibrary.linkgraph.builder.build_index", mock_build),
        ):
            result = runner.invoke(lexictl_app, ["update", "--reindex"])

        assert result.exit_code == 0, f"Output: {result.output}"
        assert "Rebuilding link graph index..." in result.output
        assert "100 artifacts" in result.output
        assert "500 links" in result.output
        assert "1.3s" in result.output
        mock_build.assert_called_once_with(tmp_path)


# ---------------------------------------------------------------------------
# 4.2 — reindex reports parse errors as warnings
# ---------------------------------------------------------------------------


class TestReindexParseErrors:
    """Task 4.2: reindex reports parse errors as warnings."""

    def test_reindex_reports_parse_errors(self, tmp_path: Path) -> None:
        mock_build = MagicMock(
            return_value=_successful_build_result(
                errors=["bad.yaml", "corrupt.md"],
            ),
        )

        with (
            _mock_project_root(tmp_path),
            _mock_load_config(),
            patch("lexibrary.linkgraph.builder.build_index", mock_build),
        ):
            result = runner.invoke(lexictl_app, ["update", "--reindex"])

        assert result.exit_code == 0, f"Output: {result.output}"
        assert "2 artifact(s) had parse errors" in result.output


# ---------------------------------------------------------------------------
# 4.3 — reindex handles build_index exception
# ---------------------------------------------------------------------------


class TestReindexException:
    """Task 4.3: reindex handles build_index exception."""

    def test_reindex_handles_exception(self, tmp_path: Path) -> None:
        mock_build = MagicMock(side_effect=RuntimeError("disk full"))

        with (
            _mock_project_root(tmp_path),
            _mock_load_config(),
            patch("lexibrary.linkgraph.builder.build_index", mock_build),
        ):
            result = runner.invoke(lexictl_app, ["update", "--reindex"])

        assert result.exit_code == 1
        assert "Failed to rebuild link graph: disk full" in result.output


# ---------------------------------------------------------------------------
# 4.4 — mutual exclusivity with each conflicting flag
# ---------------------------------------------------------------------------


class TestReindexMutualExclusivity:
    """Task 4.4: mutual exclusivity with each conflicting flag."""

    @pytest.mark.parametrize(
        "args",
        [
            ["update", "--reindex", "--force"],
            ["update", "--reindex", "--dry-run"],
            ["update", "--reindex", "--topology"],
            ["update", "--reindex", "--unlimited"],
            ["update", "--reindex", "--changed-only", "src/foo.py"],
            ["update", "--reindex", "src/"],
        ],
        ids=[
            "force",
            "dry-run",
            "topology",
            "unlimited",
            "changed-only",
            "path",
        ],
    )
    def test_reindex_rejects_conflicting_flags(self, tmp_path: Path, args: list[str]) -> None:
        with (
            _mock_project_root(tmp_path),
            _mock_load_config(),
        ):
            result = runner.invoke(lexictl_app, args)

        assert result.exit_code == 1
        assert "--reindex cannot be combined with any other update flags" in result.output

    def test_reindex_rejects_skeleton(self, tmp_path: Path) -> None:
        """--skeleton --reindex is rejected by the skeleton exclusivity check.

        The skeleton guard (which also covers reindex) fires first, producing
        its own error message.  The important invariant is that the combination
        is rejected with exit code 1.
        """
        with (
            _mock_project_root(tmp_path),
            _mock_load_config(),
        ):
            result = runner.invoke(lexictl_app, ["update", "--reindex", "--skeleton", "src/foo.py"])

        assert result.exit_code == 1
        assert "--skeleton cannot be combined with" in result.output


# ---------------------------------------------------------------------------
# 4.5 — no LLM infrastructure instantiated
# ---------------------------------------------------------------------------


class TestReindexNoLlmInfrastructure:
    """Task 4.5: no LLM infrastructure instantiated during --reindex."""

    def test_no_llm_infrastructure(self, tmp_path: Path) -> None:
        mock_build = MagicMock(return_value=_successful_build_result())

        with (
            _mock_project_root(tmp_path),
            _mock_load_config(),
            patch("lexibrary.linkgraph.builder.build_index", mock_build),
            patch(
                "lexibrary.llm.rate_limiter.RateLimiter.__init__",
                side_effect=AssertionError("RateLimiter should not be called"),
            ),
        ):
            result = runner.invoke(lexictl_app, ["update", "--reindex"])

        assert result.exit_code == 0, f"Output: {result.output}"
        mock_build.assert_called_once()


# ---------------------------------------------------------------------------
# 4.6 — help text includes --reindex
# ---------------------------------------------------------------------------


class TestReindexHelpText:
    """Task 4.6: help text includes --reindex."""

    def test_help_text_includes_reindex(self) -> None:
        # maintainer_help() prints via info(); capture by invoking the help command
        result = runner.invoke(lexictl_app, ["help"])

        assert result.exit_code == 0
        assert "lexictl update --reindex" in result.output
        assert "Rebuild link graph from existing artifacts" in result.output
