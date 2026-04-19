"""CLI parity tests for ``lexi convention deprecate``.

These tests verify that the CLI wrapper correctly delegates to
:func:`lexibrary.lifecycle.convention_deprecation.deprecate_convention`
without regressing user-facing output.  End-to-end behavioural tests
live in ``test_lexi.py``; this file exercises the helper-call contract.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import yaml
from typer.testing import CliRunner

from lexibrary.cli import lexi_app

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _setup_project(tmp_path: Path) -> Path:
    """Create a minimal initialized project root."""
    (tmp_path / ".lexibrary").mkdir()
    (tmp_path / ".lexibrary" / "config.yaml").write_text("")
    return tmp_path


def _create_convention_file(
    project: Path,
    title: str,
    *,
    status: str = "active",
    scope: str = "project",
    deprecated_at: str | None = None,
) -> Path:
    """Create a convention .md under ``.lexibrary/conventions/``."""
    conventions_dir = project / ".lexibrary" / "conventions"
    conventions_dir.mkdir(parents=True, exist_ok=True)
    slug = title.lower().replace(" ", "-")
    path = conventions_dir / f"{slug}.md"

    fm_data: dict[str, object] = {
        "title": title,
        "id": "CV-001",
        "scope": scope,
        "tags": [],
        "status": status,
        "source": "user",
        "priority": 0,
    }
    if deprecated_at is not None:
        fm_data["deprecated_at"] = deprecated_at

    fm_str = yaml.dump(fm_data, default_flow_style=False, sort_keys=False).rstrip("\n")
    body = f"\n{title} -- body text.\n"
    path.write_text(f"---\n{fm_str}\n---\n{body}", encoding="utf-8")
    return path


def _invoke(tmp_path: Path, args: list[str]) -> object:
    """Invoke the CLI from within *tmp_path*."""
    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        return runner.invoke(lexi_app, args)
    finally:
        os.chdir(old_cwd)


# ---------------------------------------------------------------------------
# Helper-call contract
# ---------------------------------------------------------------------------


class TestConventionDeprecateCallsHelper:
    """``lexi convention deprecate`` delegates to the lifecycle helper."""

    def test_active_calls_helper_with_default_reason(self, tmp_path: Path) -> None:
        """Active conventions invoke ``deprecate_convention`` with the default reason."""
        project = _setup_project(tmp_path)
        path = _create_convention_file(project, "Auth required", status="active")

        with patch("lexibrary.lifecycle.convention_deprecation.deprecate_convention") as mocked:
            result = _invoke(project, ["convention", "deprecate", "auth-required"])

        # The CLI dispatches cleanly.
        assert result.exit_code == 0  # type: ignore[union-attr]
        mocked.assert_called_once()
        call_args, call_kwargs = mocked.call_args
        # Positional convention_path must match.
        assert call_args == (path,)
        # Reason is keyword-only.
        assert call_kwargs == {"reason": "manual"}

    def test_custom_reason_forwarded(self, tmp_path: Path) -> None:
        """``--reason`` is forwarded to the helper as the ``reason`` kwarg."""
        project = _setup_project(tmp_path)
        path = _create_convention_file(project, "Auth required", status="active")

        with patch("lexibrary.lifecycle.convention_deprecation.deprecate_convention") as mocked:
            result = _invoke(
                project,
                [
                    "convention",
                    "deprecate",
                    "auth-required",
                    "--reason",
                    "scope_path_missing",
                ],
            )

        assert result.exit_code == 0  # type: ignore[union-attr]
        mocked.assert_called_once_with(path, reason="scope_path_missing")

    def test_already_deprecated_shortcircuits_helper(self, tmp_path: Path) -> None:
        """Already-deprecated pre-check prints a warning and does NOT call helper."""
        project = _setup_project(tmp_path)
        _create_convention_file(
            project,
            "Auth required",
            status="deprecated",
            deprecated_at="2025-01-01T00:00:00+00:00",
        )

        with patch("lexibrary.lifecycle.convention_deprecation.deprecate_convention") as mocked:
            result = _invoke(project, ["convention", "deprecate", "auth-required"])

        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Already deprecated" in result.output  # type: ignore[union-attr]
        mocked.assert_not_called()

    def test_missing_convention_does_not_call_helper(self, tmp_path: Path) -> None:
        """Nonexistent slug exits 1 without invoking the helper."""
        project = _setup_project(tmp_path)
        (project / ".lexibrary" / "conventions").mkdir(parents=True, exist_ok=True)

        with patch("lexibrary.lifecycle.convention_deprecation.deprecate_convention") as mocked:
            result = _invoke(project, ["convention", "deprecate", "ghost-slug"])

        assert result.exit_code == 1  # type: ignore[union-attr]
        assert "Convention not found" in result.output  # type: ignore[union-attr]
        mocked.assert_not_called()

    def test_output_reports_timestamp_from_disk(self, tmp_path: Path) -> None:
        """After delegation, the CLI re-parses and reports the persisted timestamp."""
        project = _setup_project(tmp_path)
        _create_convention_file(project, "Auth required", status="active")

        # Do NOT mock the helper here -- exercise the real wiring so the
        # CLI reads back a real deprecated_at timestamp.
        result = _invoke(project, ["convention", "deprecate", "auth-required"])

        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Deprecated 'Auth required'" in result.output  # type: ignore[union-attr]
        assert "status set to deprecated at " in result.output  # type: ignore[union-attr]

        conv_path = project / ".lexibrary" / "conventions" / "auth-required.md"
        content = conv_path.read_text(encoding="utf-8")
        assert "status: deprecated" in content
        assert "deprecated_at:" in content
        assert "deprecated_reason: manual" in content
