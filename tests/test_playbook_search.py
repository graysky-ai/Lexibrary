"""Tests for playbook support in unified search (Group 8).

Covers:
- _PlaybookResult dataclass and SearchResults.playbooks field
- has_results() returns True when only playbooks are present
- Playbook rendering in SearchResults.render() (all three formats)
- _search_playbooks() file-scanning search (query, tag, status, deprecated)
- unified_search() integration with artifact_type="playbook" filter
- VALID_ARTIFACT_TYPES includes "playbook"
"""

from __future__ import annotations

from io import StringIO
from pathlib import Path
from unittest.mock import patch

import yaml

from lexibrary.search import VALID_ARTIFACT_TYPES, SearchResults, unified_search

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_project(tmp_path: Path) -> Path:
    """Create a minimal initialized project."""
    (tmp_path / ".lexibrary").mkdir()
    (tmp_path / ".lexibrary" / "config.yaml").write_text("")
    return tmp_path


_playbook_id_counter = 0


def _next_playbook_id() -> str:
    global _playbook_id_counter
    _playbook_id_counter += 1
    return f"PB-{_playbook_id_counter:03d}"


def _create_playbook_file(
    project: Path,
    title: str,
    *,
    status: str = "active",
    tags: list[str] | None = None,
    aliases: list[str] | None = None,
    trigger_files: list[str] | None = None,
    estimated_minutes: int | None = None,
    overview: str = "",
    body: str = "",
) -> Path:
    """Create a playbook file in .lexibrary/playbooks/."""
    playbooks_dir = project / ".lexibrary" / "playbooks"
    playbooks_dir.mkdir(parents=True, exist_ok=True)

    slug = title.lower().replace(" ", "-")
    path = playbooks_dir / f"{slug}.md"

    fm_data: dict[str, object] = {
        "title": title,
        "id": _next_playbook_id(),
        "status": status,
        "tags": tags or [],
        "source": "user",
    }
    if aliases:
        fm_data["aliases"] = aliases
    if trigger_files:
        fm_data["trigger_files"] = trigger_files
    if estimated_minutes is not None:
        fm_data["estimated_minutes"] = estimated_minutes

    fm_str = yaml.dump(fm_data, default_flow_style=False, sort_keys=False).rstrip("\n")

    if not body and overview:
        body = f"\n{overview}\n"
    elif not body:
        body = f"\n{title} overview.\n"

    content = f"---\n{fm_str}\n---\n{body}"
    if not content.endswith("\n"):
        content += "\n"
    path.write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# VALID_ARTIFACT_TYPES
# ---------------------------------------------------------------------------


def test_valid_artifact_types_includes_playbook() -> None:
    """The 'playbook' string should be in VALID_ARTIFACT_TYPES."""
    assert "playbook" in VALID_ARTIFACT_TYPES


# ---------------------------------------------------------------------------
# _PlaybookResult and SearchResults
# ---------------------------------------------------------------------------


def test_has_results_with_only_playbooks() -> None:
    """has_results() returns True when only playbooks are populated."""
    from lexibrary.search import _PlaybookResult

    results = SearchResults(
        playbooks=[
            _PlaybookResult(
                title="Deploy",
                status="active",
                tags=["ops"],
                overview="Deploy steps.",
            )
        ]
    )
    assert results.has_results() is True


def test_has_results_empty() -> None:
    """has_results() returns False when all groups are empty."""
    results = SearchResults()
    assert results.has_results() is False


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def test_render_markdown_playbooks() -> None:
    """Markdown renderer includes a Playbooks section."""
    from lexibrary.search import _PlaybookResult

    results = SearchResults(
        playbooks=[
            _PlaybookResult(
                title="Version Bump",
                status="active",
                tags=["release"],
                overview="Bump the version number.",
            )
        ]
    )

    buf = StringIO()
    with (
        patch("lexibrary.search.get_format") as mock_fmt,
        patch("lexibrary.search.info", side_effect=lambda msg: buf.write(msg + "\n")),
    ):
        from lexibrary.cli._format import OutputFormat

        mock_fmt.return_value = OutputFormat.markdown
        results.render()

    output = buf.getvalue()
    assert "## Playbooks" in output
    assert "Version Bump" in output
    assert "active" in output


def test_render_json_playbooks() -> None:
    """JSON renderer includes playbook fields."""
    import json

    from lexibrary.search import _PlaybookResult

    results = SearchResults(
        playbooks=[
            _PlaybookResult(
                title="Deploy",
                status="active",
                tags=["ops"],
                overview="Deploy steps.",
            )
        ]
    )

    buf = StringIO()
    with (
        patch("lexibrary.search.get_format") as mock_fmt,
        patch("lexibrary.search.info", side_effect=lambda msg: buf.write(msg + "\n")),
    ):
        from lexibrary.cli._format import OutputFormat

        mock_fmt.return_value = OutputFormat.json
        results.render()

    output = buf.getvalue()
    records = json.loads(output)
    assert len(records) == 1
    assert records[0]["title"] == "Deploy"
    assert records[0]["status"] == "active"
    assert records[0]["overview"] == "Deploy steps."


def test_render_plain_playbooks() -> None:
    """Plain renderer includes playbook tab-separated fields."""
    from lexibrary.search import _PlaybookResult

    results = SearchResults(
        playbooks=[
            _PlaybookResult(
                title="Deploy",
                status="active",
                tags=["ops"],
                overview="Deploy steps.",
            )
        ]
    )

    buf = StringIO()
    with (
        patch("lexibrary.search.get_format") as mock_fmt,
        patch("lexibrary.search.info", side_effect=lambda msg: buf.write(msg + "\n")),
    ):
        from lexibrary.cli._format import OutputFormat

        mock_fmt.return_value = OutputFormat.plain
        results.render()

    output = buf.getvalue()
    assert "Deploy\tactive\tops\tDeploy steps." in output


# ---------------------------------------------------------------------------
# File-scanning search
# ---------------------------------------------------------------------------


def test_search_playbooks_by_query(tmp_path: Path) -> None:
    """File-scanning search finds playbooks by query substring."""
    project = _setup_project(tmp_path)
    _create_playbook_file(project, "Version Bump", tags=["release"])
    _create_playbook_file(project, "Deploy App", tags=["ops"])

    results = unified_search(project, query="version")
    assert len(results.playbooks) == 1
    assert results.playbooks[0].title == "Version Bump"


def test_search_playbooks_by_tag(tmp_path: Path) -> None:
    """File-scanning search finds playbooks by tag."""
    project = _setup_project(tmp_path)
    _create_playbook_file(project, "Version Bump", tags=["release"])
    _create_playbook_file(project, "Deploy App", tags=["ops"])

    results = unified_search(project, tag="ops")
    assert any(pb.title == "Deploy App" for pb in results.playbooks)
    assert not any(pb.title == "Version Bump" for pb in results.playbooks)


def test_search_playbooks_by_status(tmp_path: Path) -> None:
    """File-scanning search filters playbooks by status."""
    project = _setup_project(tmp_path)
    _create_playbook_file(project, "Active Playbook", status="active")
    _create_playbook_file(project, "Draft Playbook", status="draft")

    results = unified_search(project, status="draft")
    playbook_titles = [pb.title for pb in results.playbooks]
    assert "Draft Playbook" in playbook_titles
    assert "Active Playbook" not in playbook_titles


def test_search_playbooks_hides_deprecated_by_default(tmp_path: Path) -> None:
    """Deprecated playbooks are hidden unless explicitly requested."""
    project = _setup_project(tmp_path)
    _create_playbook_file(project, "Old Playbook", status="deprecated")
    _create_playbook_file(project, "Good Playbook", status="active")

    results = unified_search(project, query="playbook")
    playbook_titles = [pb.title for pb in results.playbooks]
    assert "Good Playbook" in playbook_titles
    assert "Old Playbook" not in playbook_titles

    # Explicitly requesting deprecated status should return them
    results2 = unified_search(project, status="deprecated", include_deprecated=True)
    playbook_titles2 = [pb.title for pb in results2.playbooks]
    assert "Old Playbook" in playbook_titles2


def test_search_playbooks_artifact_type_filter(tmp_path: Path) -> None:
    """artifact_type='playbook' returns only playbook results."""
    project = _setup_project(tmp_path)
    _create_playbook_file(project, "Version Bump", tags=["release"])

    results = unified_search(project, query="version", artifact_type="playbook")
    assert len(results.playbooks) == 1
    assert results.playbooks[0].title == "Version Bump"
    # Other artifact types should be empty
    assert len(results.concepts) == 0
    assert len(results.conventions) == 0
    assert len(results.design_files) == 0
    assert len(results.stack_posts) == 0


def test_search_playbooks_list_all(tmp_path: Path) -> None:
    """When no query or tag is given, all playbooks are returned (except deprecated)."""
    project = _setup_project(tmp_path)
    _create_playbook_file(project, "Alpha", status="active")
    _create_playbook_file(project, "Beta", status="active")
    _create_playbook_file(project, "Gamma", status="deprecated")

    results = unified_search(project, artifact_type="playbook")
    playbook_titles = [pb.title for pb in results.playbooks]
    assert "Alpha" in playbook_titles
    assert "Beta" in playbook_titles
    assert "Gamma" not in playbook_titles


def test_search_playbooks_multi_tag_and(tmp_path: Path) -> None:
    """Multi-tag search uses AND logic."""
    project = _setup_project(tmp_path)
    _create_playbook_file(project, "Both Tags", tags=["release", "ops"])
    _create_playbook_file(project, "One Tag", tags=["release"])

    results = unified_search(project, tags=["release", "ops"], artifact_type="playbook")
    playbook_titles = [pb.title for pb in results.playbooks]
    assert "Both Tags" in playbook_titles
    assert "One Tag" not in playbook_titles


def test_search_playbooks_no_dir(tmp_path: Path) -> None:
    """Search returns empty when playbooks directory doesn't exist."""
    project = _setup_project(tmp_path)
    results = unified_search(project, query="anything", artifact_type="playbook")
    assert len(results.playbooks) == 0


def test_search_playbooks_overview_in_result(tmp_path: Path) -> None:
    """Playbook results include the overview field."""
    project = _setup_project(tmp_path)
    _create_playbook_file(
        project,
        "Version Bump",
        overview="Follow these steps to bump the version.",
    )

    results = unified_search(project, query="version", artifact_type="playbook")
    assert len(results.playbooks) == 1
    assert "Follow these steps" in results.playbooks[0].overview
