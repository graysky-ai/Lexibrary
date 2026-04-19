"""CLI parity tests for ``lexi concept deprecate``.

Assert that the CLI delegates frontmatter mutation to the lifecycle helper
``lexibrary.lifecycle.concept_deprecation.deprecate_concept`` rather than
mutating the concept file directly.

The existing end-to-end output / exit-code tests in ``test_lexi.py`` remain
the byte-identical-output ground truth; these tests are spy-based and focus
on the CLI -> helper contract.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import yaml
from typer.testing import CliRunner

from lexibrary.cli import lexi_app

runner = CliRunner()


def _setup_project(tmp_path: Path) -> Path:
    """Create a minimal initialized project at tmp_path."""
    (tmp_path / ".lexibrary").mkdir()
    (tmp_path / ".lexibrary" / "config.yaml").write_text("")
    return tmp_path


def _create_concept_file(
    tmp_path: Path,
    name: str,
    *,
    status: str = "active",
) -> Path:
    """Create a concept markdown file at .lexibrary/concepts/<PascalCase>.md."""
    import re  # noqa: PLC0415

    concepts_dir = tmp_path / ".lexibrary" / "concepts"
    concepts_dir.mkdir(parents=True, exist_ok=True)

    fm_data: dict[str, object] = {
        "title": name,
        "id": "CN-001",
        "aliases": [],
        "tags": [],
        "status": status,
    }
    fm_str = yaml.dump(fm_data, default_flow_style=False, sort_keys=False).rstrip("\n")

    words = re.split(r"[^a-zA-Z0-9]+", name)
    pascal = "".join(w.capitalize() for w in words if w)
    file_path = concepts_dir / f"{pascal}.md"

    body = f"---\n{fm_str}\n---\n\n{name} summary.\n"
    file_path.write_text(body, encoding="utf-8")
    return file_path


def _invoke(tmp_path: Path, args: list[str]) -> object:
    """Invoke the lexi CLI with cwd=tmp_path so require_project_root resolves."""
    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        return runner.invoke(lexi_app, args)
    finally:
        os.chdir(old_cwd)


class TestConceptDeprecateCliDelegatesToHelper:
    """CLI -> helper delegation parity tests."""

    def test_cli_calls_helper_with_path_and_reason(self, tmp_path: Path) -> None:
        """`lexi concept deprecate <slug> --reason foo` calls the helper with
        the resolved absolute path and the reason kwarg."""
        _setup_project(tmp_path)
        concept_path = _create_concept_file(tmp_path, "Scope Root", status="active")

        with patch("lexibrary.lifecycle.concept_deprecation.deprecate_concept") as mock_helper:
            result = _invoke(
                tmp_path,
                ["concept", "deprecate", "ScopeRoot", "--reason", "no_inbound_links"],
            )

        assert result.exit_code == 0  # type: ignore[union-attr]
        mock_helper.assert_called_once()
        # Positional arg: path
        args, kwargs = mock_helper.call_args
        assert args == (concept_path,)
        # kwargs must include reason and superseded_by
        assert kwargs["reason"] == "no_inbound_links"
        assert kwargs["superseded_by"] is None

    def test_cli_calls_helper_with_superseded_by(self, tmp_path: Path) -> None:
        """`--superseded-by` is forwarded to the helper."""
        _setup_project(tmp_path)
        _create_concept_file(tmp_path, "Project Scope", status="active")

        with patch("lexibrary.lifecycle.concept_deprecation.deprecate_concept") as mock_helper:
            result = _invoke(
                tmp_path,
                [
                    "concept",
                    "deprecate",
                    "ProjectScope",
                    "--reason",
                    "merged",
                    "--superseded-by",
                    "Scope Root",
                ],
            )

        assert result.exit_code == 0  # type: ignore[union-attr]
        mock_helper.assert_called_once()
        _, kwargs = mock_helper.call_args
        assert kwargs["reason"] == "merged"
        assert kwargs["superseded_by"] == "Scope Root"

    def test_cli_does_not_call_helper_when_already_deprecated(self, tmp_path: Path) -> None:
        """CLI pre-check short-circuits before helper invocation for already-
        deprecated concepts (user-facing ``Already deprecated`` message)."""
        _setup_project(tmp_path)
        _create_concept_file(tmp_path, "Old Concept", status="deprecated")

        with patch("lexibrary.lifecycle.concept_deprecation.deprecate_concept") as mock_helper:
            result = _invoke(
                tmp_path,
                ["concept", "deprecate", "OldConcept", "--reason", "anything"],
            )

        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "Already deprecated" in result.output  # type: ignore[union-attr]
        # Helper MUST NOT be called; CLI pre-check short-circuits.
        mock_helper.assert_not_called()

    def test_cli_does_not_call_helper_when_file_missing(self, tmp_path: Path) -> None:
        """Missing concept file -> exit 1, helper not invoked."""
        _setup_project(tmp_path)

        with patch("lexibrary.lifecycle.concept_deprecation.deprecate_concept") as mock_helper:
            result = _invoke(
                tmp_path,
                ["concept", "deprecate", "nonexistent", "--reason", "x"],
            )

        assert result.exit_code == 1  # type: ignore[union-attr]
        mock_helper.assert_not_called()
