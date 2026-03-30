"""Tests for the global ``--format`` flag (markdown / json / plain).

Covers: ``lexi search --type concept``, ``lexi search --type convention``,
``lexi search --type stack``, and ``lexi validate`` in all three output modes.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from lexibrary.cli import lexi_app
from lexibrary.cli._format import OutputFormat, get_format, set_format

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_format() -> None:  # noqa: PT004
    """Reset the global format state to markdown before each test."""
    set_format(OutputFormat.markdown)


def _setup_project(tmp_path: Path) -> Path:
    (tmp_path / ".lexibrary").mkdir()
    (tmp_path / ".lexibrary" / "config.yaml").write_text("")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("x = 1\n")
    return tmp_path


def _create_concept_file(
    tmp_path: Path,
    name: str,
    *,
    tags: list[str] | None = None,
    status: str = "active",
    summary: str = "A concept about something.",
) -> Path:
    import re as _re

    concepts_dir = tmp_path / ".lexibrary" / "concepts"
    concepts_dir.mkdir(parents=True, exist_ok=True)
    resolved_tags = tags or []
    fm_data: dict[str, object] = {
        "title": name,
        "id": "CN-001",
        "aliases": [],
        "tags": resolved_tags,
        "status": status,
    }
    fm_str = yaml.dump(fm_data, default_flow_style=False, sort_keys=False).rstrip("\n")
    words = _re.split(r"[^a-zA-Z0-9]+", name)
    pascal = "".join(w.capitalize() for w in words if w)
    file_path = concepts_dir / f"{pascal}.md"
    body = f"---\n{fm_str}\n---\n\n{summary}\n\n## Details\n\n## Decision Log\n\n## Related\n"
    file_path.write_text(body, encoding="utf-8")
    return file_path


def _create_convention_file(
    tmp_path: Path,
    title: str,
    *,
    scope: str = "project",
    rule: str = "Follow this rule.",
    tags: list[str] | None = None,
    status: str = "active",
) -> Path:
    conventions_dir = tmp_path / ".lexibrary" / "conventions"
    conventions_dir.mkdir(parents=True, exist_ok=True)
    slug = title.lower().replace(" ", "-")
    path = conventions_dir / f"{slug}.md"
    fm_data = {
        "title": title,
        "id": "CV-001",
        "scope": scope,
        "tags": tags or [],
        "status": status,
        "source": "user",
        "priority": 0,
    }
    fm_str = yaml.dump(fm_data, default_flow_style=False, sort_keys=False).rstrip("\n")
    body = f"\n{rule}\n"
    content = f"---\n{fm_str}\n---\n{body}\n"
    path.write_text(content, encoding="utf-8")
    return path


def _create_stack_post(
    tmp_path: Path,
    post_id: str = "ST-001",
    title: str = "Bug in auth",
    tags: list[str] | None = None,
    status: str = "open",
    votes: int = 0,
) -> Path:
    import re as _re

    resolved_tags = tags or ["auth"]
    title_slug = _re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:50]
    filename = f"{post_id}-{title_slug}.md"
    stack_dir = tmp_path / ".lexibrary" / "stack"
    stack_dir.mkdir(parents=True, exist_ok=True)
    post_path = stack_dir / filename
    fm_data: dict[str, object] = {
        "id": post_id,
        "title": title,
        "tags": resolved_tags,
        "status": status,
        "created": "2026-01-15",
        "author": "tester",
        "bead": None,
        "votes": votes,
        "duplicate_of": None,
        "refs": {"concepts": [], "files": [], "designs": []},
    }
    fm_str = yaml.dump(fm_data, default_flow_style=False, sort_keys=False).rstrip("\n")
    post_path.write_text(f"---\n{fm_str}\n---\n\n## Problem\n\nSomething broke\n", encoding="utf-8")
    return post_path


def _invoke(tmp_path: Path, args: list[str]) -> object:
    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        return runner.invoke(lexi_app, args)
    finally:
        os.chdir(old_cwd)


# ---------------------------------------------------------------------------
# Format state unit tests
# ---------------------------------------------------------------------------


class TestFormatState:
    def test_default_is_markdown(self) -> None:
        assert get_format() == OutputFormat.markdown

    def test_set_and_get(self) -> None:
        set_format(OutputFormat.json)
        assert get_format() == OutputFormat.json

    def test_enum_values(self) -> None:
        assert OutputFormat.markdown.value == "markdown"
        assert OutputFormat.json.value == "json"
        assert OutputFormat.plain.value == "plain"


# ---------------------------------------------------------------------------
# Concepts --format tests
# ---------------------------------------------------------------------------


class TestConceptsFormat:
    def test_default_markdown(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _create_concept_file(tmp_path, "Auth Flow", tags=["security"])
        result = _invoke(tmp_path, ["search", "--type", "concept"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "| Auth Flow" in result.output  # type: ignore[union-attr]

    def test_format_json(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _create_concept_file(tmp_path, "Auth Flow", tags=["security"])
        result = _invoke(tmp_path, ["--format", "json", "search", "--type", "concept"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        data = json.loads(result.output)  # type: ignore[union-attr]
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["name"] == "Auth Flow"
        assert data[0]["tags"] == ["security"]
        assert data[0]["status"] == "active"

    def test_format_plain(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _create_concept_file(tmp_path, "Auth Flow", tags=["security"])
        result = _invoke(tmp_path, ["--format", "plain", "search", "--type", "concept"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        # Plain: tab-separated, one per line
        assert "Auth Flow\t" in output
        assert "security" in output
        # Should NOT have markdown table pipes
        assert "|" not in output


# ---------------------------------------------------------------------------
# Conventions --format tests
# ---------------------------------------------------------------------------


class TestConventionsFormat:
    def test_default_markdown(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _create_convention_file(tmp_path, "Use Pytest", rule="Always use pytest")
        result = _invoke(tmp_path, ["search", "--type", "convention"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "| Use Pytest" in result.output  # type: ignore[union-attr]

    def test_format_json(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _create_convention_file(tmp_path, "Use Pytest", rule="Always use pytest", tags=["testing"])
        result = _invoke(tmp_path, ["--format", "json", "search", "--type", "convention"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        data = json.loads(result.output)  # type: ignore[union-attr]
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["title"] == "Use Pytest"
        assert data[0]["scope"] == "project"
        assert data[0]["tags"] == ["testing"]

    def test_format_plain(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _create_convention_file(tmp_path, "Use Pytest", rule="Always use pytest")
        result = _invoke(tmp_path, ["--format", "plain", "search", "--type", "convention"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "Use Pytest\t" in output
        assert "|" not in output


# ---------------------------------------------------------------------------
# Stack search --format tests
# ---------------------------------------------------------------------------


class TestStackSearchFormat:
    def test_default_markdown(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _create_stack_post(tmp_path, "ST-001", "Auth Bug", tags=["auth"])
        result = _invoke(tmp_path, ["search", "--type", "stack"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        assert "| ST-001" in result.output  # type: ignore[union-attr]

    def test_format_json(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _create_stack_post(tmp_path, "ST-001", "Auth Bug", tags=["auth"], votes=3)
        result = _invoke(tmp_path, ["--format", "json", "search", "--type", "stack"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        data = json.loads(result.output)  # type: ignore[union-attr]
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["id"] == "ST-001"
        assert data[0]["title"] == "Auth Bug"
        assert data[0]["votes"] == 3
        assert data[0]["tags"] == ["auth"]

    def test_format_plain(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        _create_stack_post(tmp_path, "ST-001", "Auth Bug", tags=["auth"])
        result = _invoke(tmp_path, ["--format", "plain", "search", "--type", "stack"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        output = result.output  # type: ignore[union-attr]
        assert "ST-001\t" in output
        assert "|" not in output


# ---------------------------------------------------------------------------
# Validate --format tests
# ---------------------------------------------------------------------------


class TestValidateFormat:
    def test_format_json_passes_json_flag(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        result = _invoke(tmp_path, ["--format", "json", "validate"])
        assert result.exit_code == 0  # type: ignore[union-attr]
        # JSON output should be valid JSON
        data = json.loads(result.output)  # type: ignore[union-attr]
        assert "issues" in data
        assert "summary" in data

    def test_format_plain_validate(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        result = _invoke(tmp_path, ["--format", "plain", "validate"])
        # May have exit code 0 (no issues) or non-zero (some info/warning issues)
        output = result.output  # type: ignore[union-attr]
        # Plain format should use tab-separated fields, no markdown pipes
        if "No validation issues found" not in output:
            # Should be tab-separated lines
            assert "\t" in output
            assert "|" not in output

    def test_default_markdown_validate(self, tmp_path: Path) -> None:
        _setup_project(tmp_path)
        result = _invoke(tmp_path, ["validate"])
        output = result.output  # type: ignore[union-attr]
        # Default markdown uses tables or "No validation issues found"
        assert "No validation issues found" in output or "|" in output


# ---------------------------------------------------------------------------
# Unsupported commands default to markdown
# ---------------------------------------------------------------------------


class TestUnsupportedFallback:
    def test_help_ignores_format_flag(self, tmp_path: Path) -> None:
        """Commands without --format support should still work."""
        result = _invoke(tmp_path, ["--format", "json", "--help"])
        assert result.exit_code == 0  # type: ignore[union-attr]
