"""Unit tests for lexibrary.services.status and lexibrary.services.status_render."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml

from lexibrary.linkgraph.health import IndexHealth
from lexibrary.services.status import StatusResult, collect_status
from lexibrary.services.status_render import render_dashboard, render_quiet

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _setup_project(tmp_path: Path) -> Path:
    """Create a minimal project with .lexibrary directory."""
    (tmp_path / ".lexibrary").mkdir()
    (tmp_path / ".lexibrary" / "config.yaml").write_text("")
    (tmp_path / "src").mkdir()
    return tmp_path


def _create_design_file(tmp_path: Path, source_rel: str, source_content: str) -> Path:
    """Create a design file in .lexibrary mirror tree with correct metadata."""
    content_hash = hashlib.sha256(source_content.encode()).hexdigest()
    design_path = tmp_path / ".lexibrary" / "designs" / f"{source_rel}.md"
    design_path.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.now().isoformat()
    design_content = f"""---
description: Design file for {source_rel}
id: DS-001
updated_by: archivist
status: active
---

# {source_rel}

Test design file content.

## Interface Contract

```python
def hello(): ...
```

## Dependencies

- (none)

## Dependents

- (none)

<!-- lexibrary:meta
source: {source_rel}
source_hash: {content_hash}
design_hash: placeholder
generated: {now}
generator: lexibrary-v2
-->
"""
    design_path.write_text(design_content, encoding="utf-8")
    return design_path


def _create_concept_file(
    tmp_path: Path,
    name: str,
    *,
    tags: list[str] | None = None,
    status: str = "active",
) -> Path:
    """Create a concept markdown file in .lexibrary/concepts/."""
    import re  # noqa: PLC0415

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

    words = re.split(r"[^a-zA-Z0-9]+", name)
    pascal = "".join(w.capitalize() for w in words if w)
    file_path = concepts_dir / f"{pascal}.md"

    body = f"---\n{fm_str}\n---\n\n## Details\n\n## Decision Log\n\n## Related\n"
    file_path.write_text(body, encoding="utf-8")
    return file_path


def _create_stack_post(
    tmp_path: Path,
    post_id: str = "ST-001",
    title: str = "Bug in auth module",
    *,
    tags: list[str] | None = None,
    status: str = "open",
) -> Path:
    """Create a stack post file for testing."""
    import re as _re  # noqa: PLC0415

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
        "votes": 0,
        "duplicate_of": None,
        "refs": {"concepts": [], "files": [], "designs": []},
    }
    fm_str = yaml.dump(fm_data, default_flow_style=False, sort_keys=False).rstrip("\n")
    content = f"---\n{fm_str}\n---\n\n## Problem\n\nSomething is broken\n\n### Evidence\n\n"
    post_path.write_text(content, encoding="utf-8")
    return post_path


# ---------------------------------------------------------------------------
# StatusResult dataclass tests
# ---------------------------------------------------------------------------


class TestStatusResult:
    """Tests for the StatusResult dataclass."""

    def test_default_values(self) -> None:
        """Default StatusResult has sensible zero values."""
        result = StatusResult()
        assert result.total_designs == 0
        assert result.stale_count == 0
        assert result.concept_counts == {"active": 0, "deprecated": 0, "draft": 0}
        assert result.stack_counts == {"open": 0, "resolved": 0}
        assert result.error_count == 0
        assert result.warning_count == 0
        assert result.latest_generated is None
        assert result.exit_code == 0

    def test_total_stack_property(self) -> None:
        """total_stack sums all stack count values."""
        result = StatusResult(stack_counts={"open": 3, "resolved": 2})
        assert result.total_stack == 5

    def test_total_stack_empty(self) -> None:
        """total_stack is zero when counts are empty."""
        result = StatusResult(stack_counts={})
        assert result.total_stack == 0

    def test_no_cli_dependencies(self) -> None:
        """StatusResult is importable without pulling in CLI modules."""
        import importlib  # noqa: PLC0415

        mod = importlib.import_module("lexibrary.services.status")
        source = Path(mod.__file__).read_text(encoding="utf-8")  # type: ignore[arg-type]
        assert "import typer" not in source
        assert "from lexibrary.cli._output" not in source


# ---------------------------------------------------------------------------
# collect_status() tests
# ---------------------------------------------------------------------------


class TestCollectStatus:
    """Tests for the collect_status() service function."""

    def test_empty_library(self, tmp_path: Path) -> None:
        """Empty library returns zero counts and exit_code 0."""
        project = _setup_project(tmp_path)
        result = collect_status(project)

        assert result.total_designs == 0
        assert result.stale_count == 0
        assert result.concept_counts == {"active": 0, "deprecated": 0, "draft": 0}
        assert result.stack_counts == {"open": 0, "resolved": 0}
        assert result.total_stack == 0
        assert result.latest_generated is None
        assert result.exit_code == 0

    def test_counts_design_files(self, tmp_path: Path) -> None:
        """collect_status counts design files correctly."""
        project = _setup_project(tmp_path)
        src_content = "def hello(): pass\n"
        (project / "src" / "main.py").write_text(src_content)
        _create_design_file(project, "src/main.py", src_content)

        result = collect_status(project)
        assert result.total_designs == 1
        assert result.stale_count == 0

    def test_detects_stale_files(self, tmp_path: Path) -> None:
        """collect_status detects stale files when source hash mismatches."""
        project = _setup_project(tmp_path)
        original_content = "y = 2\n"
        (project / "src" / "stale.py").write_text("y = 3\n")  # Different from hash
        _create_design_file(project, "src/stale.py", original_content)

        result = collect_status(project)
        assert result.total_designs == 1
        assert result.stale_count == 1

    def test_counts_concepts_by_status(self, tmp_path: Path) -> None:
        """collect_status counts concepts by status."""
        project = _setup_project(tmp_path)
        _create_concept_file(project, "Alpha", tags=["a"], status="active")
        _create_concept_file(project, "Beta", tags=["b"], status="active")
        _create_concept_file(project, "Gamma", tags=["c"], status="deprecated")
        _create_concept_file(project, "Delta", tags=["d"], status="draft")

        result = collect_status(project)
        assert result.concept_counts["active"] == 2
        assert result.concept_counts["deprecated"] == 1
        assert result.concept_counts["draft"] == 1

    def test_counts_stack_posts_by_status(self, tmp_path: Path) -> None:
        """collect_status counts stack posts by status."""
        project = _setup_project(tmp_path)
        _create_stack_post(project, "ST-001", "Bug one", status="open")
        _create_stack_post(project, "ST-002", "Bug two", status="resolved")
        _create_stack_post(project, "ST-003", "Bug three", status="open")

        result = collect_status(project)
        assert result.stack_counts["open"] == 2
        assert result.stack_counts["resolved"] == 1
        assert result.total_stack == 3

    def test_tracks_latest_generated(self, tmp_path: Path) -> None:
        """collect_status tracks the latest generated timestamp."""
        project = _setup_project(tmp_path)
        src_content = "x = 1\n"
        (project / "src" / "a.py").write_text(src_content)
        _create_design_file(project, "src/a.py", src_content)

        result = collect_status(project)
        assert result.latest_generated is not None

    def test_returns_exit_code_from_validation(self, tmp_path: Path) -> None:
        """collect_status populates exit_code from validation report."""
        project = _setup_project(tmp_path)
        # Clean project -> exit_code 0
        result = collect_status(project)
        assert result.exit_code == 0

    def test_link_graph_health_populated(self, tmp_path: Path) -> None:
        """collect_status populates index_health from read_index_health."""
        project = _setup_project(tmp_path)
        result = collect_status(project)
        # Without an index.db, all fields are None
        assert result.index_health.artifact_count is None
        assert result.index_health.link_count is None
        assert result.index_health.built_at is None

    def test_link_graph_health_with_database(self, tmp_path: Path) -> None:
        """collect_status reads link graph health when index.db exists."""
        import sqlite3  # noqa: PLC0415

        from lexibrary.linkgraph.schema import ensure_schema  # noqa: PLC0415

        project = _setup_project(tmp_path)
        db_path = project / ".lexibrary" / "index.db"
        conn = sqlite3.connect(str(db_path))
        ensure_schema(conn)

        conn.execute(
            "INSERT INTO artifacts (id, path, kind, title, status) "
            "VALUES (1, 'src/main.py', 'source', 'Main', 'active')"
        )
        conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) "
            "VALUES ('built_at', '2026-02-20T10:30:00+00:00')"
        )
        conn.commit()
        conn.close()

        result = collect_status(project)
        assert result.index_health.artifact_count == 1
        assert result.index_health.link_count == 0
        assert result.index_health.built_at == "2026-02-20T10:30:00+00:00"


# ---------------------------------------------------------------------------
# render_dashboard() tests
# ---------------------------------------------------------------------------


class TestRenderDashboard:
    """Tests for the render_dashboard() formatter."""

    def test_includes_header(self) -> None:
        """Dashboard includes the 'Lexibrary Status' header."""
        result = StatusResult()
        output = render_dashboard(result)
        assert "Lexibrary Status" in output

    def test_shows_file_counts(self) -> None:
        """Dashboard shows tracked file count."""
        result = StatusResult(total_designs=5)
        output = render_dashboard(result)
        assert "Files: 5 tracked" in output

    def test_shows_stale_count(self) -> None:
        """Dashboard shows stale count when present."""
        result = StatusResult(total_designs=3, stale_count=1)
        output = render_dashboard(result)
        assert "3 tracked, 1 stale" in output

    def test_shows_concept_counts(self) -> None:
        """Dashboard shows concept breakdown by status."""
        result = StatusResult(concept_counts={"active": 2, "deprecated": 1, "draft": 0})
        output = render_dashboard(result)
        assert "2 active" in output
        assert "1 deprecated" in output
        assert "draft" not in output  # 0 draft not shown

    def test_shows_zero_concepts(self) -> None:
        """Dashboard shows 'Concepts: 0' when no concepts exist."""
        result = StatusResult(concept_counts={"active": 0, "deprecated": 0, "draft": 0})
        output = render_dashboard(result)
        assert "Concepts: 0" in output

    def test_shows_stack_counts(self) -> None:
        """Dashboard shows stack post counts."""
        result = StatusResult(stack_counts={"open": 2, "resolved": 3})
        output = render_dashboard(result)
        assert "5 posts" in output
        assert "3 resolved" in output
        assert "2 open" in output

    def test_shows_zero_stack(self) -> None:
        """Dashboard shows 'Stack: 0 posts' when no posts exist."""
        result = StatusResult(stack_counts={"open": 0, "resolved": 0})
        output = render_dashboard(result)
        assert "Stack: 0 posts" in output

    def test_shows_single_stack_post(self) -> None:
        """Dashboard uses singular 'post' for one post."""
        result = StatusResult(stack_counts={"open": 1, "resolved": 0})
        output = render_dashboard(result)
        assert "1 post " in output  # "1 post (" not "1 posts"

    def test_shows_link_graph_health(self) -> None:
        """Dashboard shows link graph stats when available."""
        result = StatusResult(
            index_health=IndexHealth(artifact_count=5, link_count=3, built_at="2026-01-01T00:00:00")
        )
        output = render_dashboard(result)
        assert "5 artifacts" in output
        assert "3 links" in output
        assert "built 2026-01-01T00:00:00" in output

    def test_shows_link_graph_not_built(self) -> None:
        """Dashboard shows 'not built' when index is absent."""
        result = StatusResult(
            index_health=IndexHealth(artifact_count=None, link_count=None, built_at=None)
        )
        output = render_dashboard(result)
        assert "Link graph: not built" in output

    def test_shows_issues(self) -> None:
        """Dashboard shows error and warning counts."""
        result = StatusResult(error_count=2, warning_count=3)
        output = render_dashboard(result)
        assert "2 errors" in output
        assert "3 warnings" in output

    def test_shows_singular_issue(self) -> None:
        """Dashboard uses singular when counts are 1."""
        result = StatusResult(error_count=1, warning_count=1)
        output = render_dashboard(result)
        assert "1 error," in output
        assert "1 warning" in output

    def test_shows_validate_suggestion_when_issues(self) -> None:
        """Dashboard suggests validate when issues exist."""
        result = StatusResult(error_count=1, warning_count=0)
        output = render_dashboard(result, cli_prefix="lexi")
        assert "Run `lexi validate` for details." in output

    def test_no_validate_suggestion_when_clean(self) -> None:
        """Dashboard omits validate suggestion when no issues."""
        result = StatusResult(error_count=0, warning_count=0)
        output = render_dashboard(result, cli_prefix="lexi")
        assert "validate" not in output

    def test_shows_updated_never(self) -> None:
        """Dashboard shows 'Updated: never' when no generated timestamp."""
        result = StatusResult(latest_generated=None)
        output = render_dashboard(result)
        assert "Updated: never" in output

    def test_shows_updated_recently(self) -> None:
        """Dashboard shows relative time for recent updates."""
        recent = datetime.now(tz=UTC) - timedelta(seconds=30)
        result = StatusResult(latest_generated=recent)
        output = render_dashboard(result)
        assert "Updated:" in output
        assert "second" in output

    def test_shows_updated_minutes_ago(self) -> None:
        """Dashboard shows minutes for updates a few minutes ago."""
        minutes_ago = datetime.now(tz=UTC) - timedelta(minutes=5)
        result = StatusResult(latest_generated=minutes_ago)
        output = render_dashboard(result)
        assert "5 minutes ago" in output

    def test_shows_updated_hours_ago(self) -> None:
        """Dashboard shows hours for updates several hours ago."""
        hours_ago = datetime.now(tz=UTC) - timedelta(hours=3)
        result = StatusResult(latest_generated=hours_ago)
        output = render_dashboard(result)
        assert "3 hours ago" in output

    def test_shows_updated_days_ago(self) -> None:
        """Dashboard shows days for updates more than a day ago."""
        days_ago = datetime.now(tz=UTC) - timedelta(days=2)
        result = StatusResult(latest_generated=days_ago)
        output = render_dashboard(result)
        assert "2 days ago" in output

    def test_cli_prefix_in_validate_suggestion(self) -> None:
        """Dashboard uses the correct cli_prefix in validate suggestion."""
        result = StatusResult(error_count=1)
        output = render_dashboard(result, cli_prefix="lexictl")
        assert "Run `lexictl validate` for details." in output


# ---------------------------------------------------------------------------
# render_quiet() tests
# ---------------------------------------------------------------------------


class TestRenderQuiet:
    """Tests for the render_quiet() formatter."""

    def test_healthy_output(self) -> None:
        """Quiet mode shows 'library healthy' when no issues."""
        result = StatusResult(error_count=0, warning_count=0)
        output = render_quiet(result, cli_prefix="lexi")
        assert output == "lexi: library healthy"

    def test_errors_only(self) -> None:
        """Quiet mode shows error count and validate suggestion."""
        result = StatusResult(error_count=3, warning_count=0)
        output = render_quiet(result, cli_prefix="lexi")
        assert "3 errors" in output
        assert "lexi validate" in output

    def test_warnings_only(self) -> None:
        """Quiet mode shows warning count and validate suggestion."""
        result = StatusResult(error_count=0, warning_count=2)
        output = render_quiet(result, cli_prefix="lexictl")
        assert "2 warnings" in output
        assert "lexictl validate" in output

    def test_errors_and_warnings(self) -> None:
        """Quiet mode shows both error and warning counts."""
        result = StatusResult(error_count=1, warning_count=2)
        output = render_quiet(result, cli_prefix="lexi")
        assert "1 error" in output
        assert "2 warnings" in output
        assert "lexi validate" in output

    def test_singular_error(self) -> None:
        """Quiet mode uses singular 'error' for count of 1."""
        result = StatusResult(error_count=1, warning_count=0)
        output = render_quiet(result, cli_prefix="lexi")
        assert "1 error " in output or output.endswith("1 error")

    def test_singular_warning(self) -> None:
        """Quiet mode uses singular 'warning' for count of 1."""
        result = StatusResult(error_count=0, warning_count=1)
        output = render_quiet(result, cli_prefix="lexi")
        assert "1 warning " in output or "1 warning\n" in output or output.endswith("1 warning")

    def test_cli_prefix_used(self) -> None:
        """Quiet mode starts with the cli_prefix."""
        result = StatusResult()
        output = render_quiet(result, cli_prefix="lexictl")
        assert output.startswith("lexictl:")

    def test_default_cli_prefix(self) -> None:
        """Quiet mode defaults to 'lexictl' prefix."""
        result = StatusResult()
        output = render_quiet(result)
        assert output.startswith("lexictl:")
