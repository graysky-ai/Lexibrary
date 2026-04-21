"""Unit tests for schema frontmatter validation checks.

Tests check_convention_frontmatter, check_design_frontmatter,
check_stack_frontmatter, and check_iwh_frontmatter from
the validator.checks module.
"""

from __future__ import annotations

from pathlib import Path

from lexibrary.validator.checks import (
    check_convention_frontmatter,
    check_design_frontmatter,
    check_iwh_frontmatter,
    check_stack_frontmatter,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_convention(
    conventions_dir: Path,
    name: str,
    *,
    raw_content: str | None = None,
    title: str = "Test Convention",
    status: str = "active",
    source: str = "user",
    scope: str = "project",
    tags: str = "[general]",
    priority: int = 0,
) -> Path:
    """Write a convention file; use raw_content for custom frontmatter."""
    conventions_dir.mkdir(parents=True, exist_ok=True)
    path = conventions_dir / f"{name}.md"
    if raw_content is not None:
        path.write_text(raw_content, encoding="utf-8")
    else:
        path.write_text(
            f"""---
title: {title}
id: CV-001
status: {status}
source: {source}
scope: {scope}
tags: {tags}
priority: {priority}
---

{title} body text.
""",
            encoding="utf-8",
        )
    return path


def _write_design(
    designs_dir: Path,
    name: str,
    *,
    raw_content: str | None = None,
    description: str = "Test design file",
    updated_by: str = "archivist",
    status: str = "active",
) -> Path:
    """Write a design file; use raw_content for custom frontmatter."""
    path = designs_dir / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    if raw_content is not None:
        path.write_text(raw_content, encoding="utf-8")
    else:
        path.write_text(
            f"""---
description: {description}
id: DS-004
updated_by: {updated_by}
status: {status}
---

# {name}

Design body.
""",
            encoding="utf-8",
        )
    return path


def _write_stack_post(
    posts_dir: Path,
    filename: str,
    *,
    raw_content: str | None = None,
    post_id: str = "ST-001",
    title: str = "Test Post",
    tags: str = "[bug]",
    status: str = "open",
    created: str = "2026-01-15",
    author: str = "tester",
    resolution_type: str | None = None,
) -> Path:
    """Write a Stack post file; use raw_content for custom frontmatter."""
    posts_dir.mkdir(parents=True, exist_ok=True)
    path = posts_dir / f"{filename}.md"
    if raw_content is not None:
        path.write_text(raw_content, encoding="utf-8")
    else:
        rt_line = f"\nresolution_type: {resolution_type}" if resolution_type else ""
        path.write_text(
            f"""---
id: {post_id}
title: {title}
tags: {tags}
status: {status}
created: {created}
author: {author}{rt_line}
---

## Problem

Test problem description.
""",
            encoding="utf-8",
        )
    return path


def _write_iwh(
    parent_dir: Path,
    *,
    raw_content: str | None = None,
    author: str = "agent-session-1",
    created: str = "2026-03-10T14:30:00",
    scope: str = "incomplete",
) -> Path:
    """Write an .iwh file; use raw_content for custom YAML."""
    parent_dir.mkdir(parents=True, exist_ok=True)
    path = parent_dir / ".iwh"
    if raw_content is not None:
        path.write_text(raw_content, encoding="utf-8")
    else:
        path.write_text(
            f"""---
author: {author}
created: {created}
scope: {scope}
---

Some handoff body text.
""",
            encoding="utf-8",
        )
    return path


# ---------------------------------------------------------------------------
# check_convention_frontmatter
# ---------------------------------------------------------------------------


class TestCheckConventionFrontmatter:
    """Tests for check_convention_frontmatter."""

    def test_valid_convention_returns_empty(self, tmp_path: Path) -> None:
        """Valid convention with all fields produces no issues."""
        project_root = tmp_path
        ld = tmp_path / ".lexibrary"
        _write_convention(ld / "conventions", "good-convention")

        issues = check_convention_frontmatter(project_root, ld)
        assert issues == []

    def test_missing_directory_returns_empty(self, tmp_path: Path) -> None:
        """No conventions directory returns empty list."""
        project_root = tmp_path
        ld = tmp_path / ".lexibrary"
        ld.mkdir()

        issues = check_convention_frontmatter(project_root, ld)
        assert issues == []

    def test_missing_title_reports_error(self, tmp_path: Path) -> None:
        """Missing title field produces an error."""
        ld = tmp_path / ".lexibrary"
        _write_convention(
            ld / "conventions",
            "no-title",
            raw_content="""---
status: active
source: user
scope: project
tags: [general]
priority: 0
---

Body.
""",
        )

        issues = check_convention_frontmatter(tmp_path, ld)
        title_issues = [i for i in issues if "title" in i.message]
        assert len(title_issues) == 1
        assert title_issues[0].severity == "error"
        assert title_issues[0].check == "convention_frontmatter"
        assert "title" in title_issues[0].suggestion

    def test_invalid_status_reports_error(self, tmp_path: Path) -> None:
        """Invalid status produces an error listing valid values."""
        ld = tmp_path / ".lexibrary"
        _write_convention(
            ld / "conventions",
            "bad-status",
            raw_content="""---
title: Bad Status
id: CV-004
status: archived
source: user
scope: project
tags: [general]
priority: 0
---

Body.
""",
        )

        issues = check_convention_frontmatter(tmp_path, ld)
        status_issues = [i for i in issues if "status" in i.message.lower()]
        assert len(status_issues) == 1
        assert "archived" in status_issues[0].message
        assert "draft" in status_issues[0].suggestion

    def test_invalid_source_reports_error(self, tmp_path: Path) -> None:
        """Invalid source produces an error listing valid values."""
        ld = tmp_path / ".lexibrary"
        _write_convention(
            ld / "conventions",
            "bad-source",
            raw_content="""---
title: Bad Source
id: CV-003
status: active
source: llm
scope: project
tags: [general]
priority: 0
---

Body.
""",
        )

        issues = check_convention_frontmatter(tmp_path, ld)
        source_issues = [i for i in issues if "source" in i.message.lower()]
        assert len(source_issues) == 1
        assert "llm" in source_issues[0].message
        assert "user" in source_issues[0].suggestion

    def test_unparseable_yaml_reports_error(self, tmp_path: Path) -> None:
        """Malformed YAML produces an error with fix suggestion."""
        ld = tmp_path / ".lexibrary"
        _write_convention(
            ld / "conventions",
            "bad-yaml",
            raw_content="""---
title: [unterminated
id: CN-001
status: broken
---

Body.
""",
        )

        issues = check_convention_frontmatter(tmp_path, ld)
        assert len(issues) >= 1
        assert any(i.check == "convention_frontmatter" for i in issues)
        assert any("YAML" in i.message for i in issues)

    def test_missing_frontmatter_delimiters_reports_error(self, tmp_path: Path) -> None:
        """No frontmatter delimiters produces an error."""
        ld = tmp_path / ".lexibrary"
        _write_convention(
            ld / "conventions",
            "no-delimiters",
            raw_content="Just plain text, no frontmatter.\n",
        )

        issues = check_convention_frontmatter(tmp_path, ld)
        assert len(issues) == 1
        assert issues[0].check == "convention_frontmatter"
        assert "Missing YAML frontmatter" in issues[0].message

    def test_multiple_field_errors_per_file(self, tmp_path: Path) -> None:
        """Missing title AND invalid status produce two separate errors."""
        ld = tmp_path / ".lexibrary"
        _write_convention(
            ld / "conventions",
            "multi-error",
            raw_content="""---
status: archived
source: user
scope: project
tags: [general]
priority: 0
---

Body.
""",
        )

        issues = check_convention_frontmatter(tmp_path, ld)
        assert len(issues) >= 2
        checks = {i.message for i in issues}
        assert any("title" in m for m in checks)
        assert any("status" in m.lower() for m in checks)

    def test_missing_tags_reports_error(self, tmp_path: Path) -> None:
        """Missing tags field produces an error."""
        ld = tmp_path / ".lexibrary"
        _write_convention(
            ld / "conventions",
            "no-tags",
            raw_content="""---
title: No Tags
id: CV-002
status: active
source: user
scope: project
priority: 0
---

Body.
""",
        )

        issues = check_convention_frontmatter(tmp_path, ld)
        tag_issues = [i for i in issues if "tags" in i.message]
        assert len(tag_issues) == 1

    def test_missing_priority_reports_error(self, tmp_path: Path) -> None:
        """Missing priority field produces an error."""
        ld = tmp_path / ".lexibrary"
        _write_convention(
            ld / "conventions",
            "no-priority",
            raw_content="""---
title: No Priority
id: CV-001
status: active
source: user
scope: project
tags: [general]
---

Body.
""",
        )

        issues = check_convention_frontmatter(tmp_path, ld)
        prio_issues = [i for i in issues if "priority" in i.message]
        assert len(prio_issues) == 1


# ---------------------------------------------------------------------------
# check_design_frontmatter
# ---------------------------------------------------------------------------


class TestCheckDesignFrontmatter:
    """Tests for check_design_frontmatter."""

    def test_valid_design_returns_empty(self, tmp_path: Path) -> None:
        """Valid design file with all fields produces no issues."""
        ld = tmp_path / ".lexibrary"
        _write_design(ld / "designs" / "src", "auth.py")

        issues = check_design_frontmatter(tmp_path, ld)
        assert issues == []

    def test_missing_directory_returns_empty(self, tmp_path: Path) -> None:
        """No designs directory returns empty list."""
        ld = tmp_path / ".lexibrary"
        ld.mkdir()

        issues = check_design_frontmatter(tmp_path, ld)
        assert issues == []

    def test_missing_description_reports_error(self, tmp_path: Path) -> None:
        """Missing description field produces an error."""
        ld = tmp_path / ".lexibrary"
        _write_design(
            ld / "designs" / "src",
            "bad",
            raw_content="""---
updated_by: archivist
status: active
---

# bad

Body.
""",
        )

        issues = check_design_frontmatter(tmp_path, ld)
        desc_issues = [i for i in issues if "description" in i.message]
        assert len(desc_issues) == 1
        assert desc_issues[0].severity == "error"
        assert desc_issues[0].check == "design_frontmatter"

    def test_invalid_updated_by_reports_error(self, tmp_path: Path) -> None:
        """Invalid updated_by produces an error listing valid values."""
        ld = tmp_path / ".lexibrary"
        _write_design(
            ld / "designs" / "src",
            "bad-updater",
            raw_content="""---
description: Test file
id: DS-003
updated_by: unknown
status: active
---

Body.
""",
        )

        issues = check_design_frontmatter(tmp_path, ld)
        ub_issues = [i for i in issues if "updated_by" in i.message]
        assert len(ub_issues) == 1
        assert "unknown" in ub_issues[0].message
        assert "archivist" in ub_issues[0].suggestion

    def test_invalid_status_reports_error(self, tmp_path: Path) -> None:
        """Invalid status 'draft' (not valid for designs) produces error."""
        ld = tmp_path / ".lexibrary"
        _write_design(
            ld / "designs" / "src",
            "bad-status",
            raw_content="""---
description: Test file
id: DS-002
updated_by: archivist
status: draft
---

Body.
""",
        )

        issues = check_design_frontmatter(tmp_path, ld)
        s_issues = [i for i in issues if "status" in i.message.lower()]
        assert len(s_issues) == 1
        assert "draft" in s_issues[0].message

    def test_omitted_status_returns_empty(self, tmp_path: Path) -> None:
        """A design file with NO ``status`` key SHALL NOT produce a status-related
        issue — the serializer now omits the default value and the check treats
        an absent ``status`` as equivalent to ``active``."""
        ld = tmp_path / ".lexibrary"
        _write_design(
            ld / "designs" / "src",
            "no-status",
            raw_content="""---
description: Design file without explicit status
id: DS-010
updated_by: archivist
---

# no-status

Design body.
""",
        )

        issues = check_design_frontmatter(tmp_path, ld)
        s_issues = [i for i in issues if "status" in i.message.lower()]
        assert s_issues == []

    def test_status_deprecated_returns_empty(self, tmp_path: Path) -> None:
        """A design file with ``status: deprecated`` SHALL NOT produce an issue."""
        ld = tmp_path / ".lexibrary"
        _write_design(
            ld / "designs" / "src",
            "deprecated-file",
            raw_content="""---
description: Deprecated design file
id: DS-011
updated_by: archivist
status: deprecated
---

# deprecated-file

Design body.
""",
        )

        issues = check_design_frontmatter(tmp_path, ld)
        s_issues = [i for i in issues if "status" in i.message.lower()]
        assert s_issues == []

    def test_recursive_scan(self, tmp_path: Path) -> None:
        """Recursively finds design files in subdirectories."""
        ld = tmp_path / ".lexibrary"
        _write_design(ld / "designs" / "src" / "auth", "middleware.py")
        _write_design(ld / "designs" / "src" / "db", "models.py")

        issues = check_design_frontmatter(tmp_path, ld)
        assert issues == []

    def test_non_markdown_files_skipped(self, tmp_path: Path) -> None:
        """Non-.md files in designs directory are not checked."""
        ld = tmp_path / ".lexibrary"
        designs_dir = ld / "designs"
        designs_dir.mkdir(parents=True)
        # Write a .comments.yaml file — should be skipped (not .md)
        (designs_dir / ".comments.yaml").write_text("count: 3\n", encoding="utf-8")
        # Write an .iwh file — should be skipped (not .md)
        (designs_dir / ".iwh").write_text("---\nauthor: test\n---\n", encoding="utf-8")

        issues = check_design_frontmatter(tmp_path, ld)
        assert issues == []

    def test_unparseable_yaml_reports_error(self, tmp_path: Path) -> None:
        """Malformed YAML in design file produces an error."""
        ld = tmp_path / ".lexibrary"
        _write_design(
            ld / "designs" / "src",
            "bad-yaml",
            raw_content="""---
description: [unterminated
id: DS-001
updated_by: broken
---

Body.
""",
        )

        issues = check_design_frontmatter(tmp_path, ld)
        assert len(issues) >= 1
        assert any("YAML" in i.message for i in issues)


# ---------------------------------------------------------------------------
# check_stack_frontmatter
# ---------------------------------------------------------------------------


class TestCheckStackFrontmatter:
    """Tests for check_stack_frontmatter."""

    def test_valid_post_returns_empty(self, tmp_path: Path) -> None:
        """Valid Stack post with all fields produces no issues."""
        ld = tmp_path / ".lexibrary"
        _write_stack_post(ld / "stack" / "posts", "ST-001-test")

        issues = check_stack_frontmatter(tmp_path, ld)
        assert issues == []

    def test_missing_directory_returns_empty(self, tmp_path: Path) -> None:
        """No posts directory returns empty list."""
        ld = tmp_path / ".lexibrary"
        ld.mkdir()

        issues = check_stack_frontmatter(tmp_path, ld)
        assert issues == []

    def test_missing_id_reports_error(self, tmp_path: Path) -> None:
        """Missing id field produces an error."""
        ld = tmp_path / ".lexibrary"
        _write_stack_post(
            ld / "stack" / "posts",
            "no-id",
            raw_content="""---
title: No ID Post
id: CN-001
tags: [bug]
status: open
created: 2026-01-15
author: tester
---

## Problem

Test.
""",
        )

        issues = check_stack_frontmatter(tmp_path, ld)
        id_issues = [i for i in issues if "id" in i.message.lower()]
        assert len(id_issues) == 1
        assert id_issues[0].check == "stack_frontmatter"

    def test_invalid_id_format_reports_error(self, tmp_path: Path) -> None:
        """Wrong id prefix 'STACK-001' produces an error."""
        ld = tmp_path / ".lexibrary"
        _write_stack_post(
            ld / "stack" / "posts",
            "bad-id",
            raw_content="""---
id: STACK-001
title: Bad ID Post
tags: [bug]
status: open
created: 2026-01-15
author: tester
---

## Problem

Test.
""",
        )

        issues = check_stack_frontmatter(tmp_path, ld)
        id_issues = [i for i in issues if "id" in i.message.lower()]
        assert len(id_issues) == 1
        assert "STACK-001" in id_issues[0].message
        assert "ST-NNN" in id_issues[0].suggestion

    def test_empty_tags_reports_error(self, tmp_path: Path) -> None:
        """Empty tags list produces an error."""
        ld = tmp_path / ".lexibrary"
        _write_stack_post(
            ld / "stack" / "posts",
            "empty-tags",
            raw_content="""---
id: ST-002
title: Empty Tags Post
tags: []
status: open
created: 2026-01-15
author: tester
---

## Problem

Test.
""",
        )

        issues = check_stack_frontmatter(tmp_path, ld)
        tag_issues = [i for i in issues if "tags" in i.message]
        assert len(tag_issues) == 1
        assert "at least 1" in tag_issues[0].message

    def test_invalid_status_reports_error(self, tmp_path: Path) -> None:
        """Invalid status value produces an error."""
        ld = tmp_path / ".lexibrary"
        _write_stack_post(
            ld / "stack" / "posts",
            "bad-status",
            raw_content="""---
id: ST-003
title: Bad Status Post
tags: [bug]
status: invalid
created: 2026-01-15
author: tester
---

## Problem

Test.
""",
        )

        issues = check_stack_frontmatter(tmp_path, ld)
        status_issues = [i for i in issues if "status" in i.message.lower()]
        assert len(status_issues) == 1
        assert "invalid" in status_issues[0].message

    def test_invalid_resolution_type_reports_error(self, tmp_path: Path) -> None:
        """Invalid resolution_type produces an error."""
        ld = tmp_path / ".lexibrary"
        _write_stack_post(
            ld / "stack" / "posts",
            "bad-resolution",
            raw_content="""---
id: ST-004
title: Bad Resolution
tags: [bug]
status: resolved
created: 2026-01-15
author: tester
resolution_type: resolved
---

## Problem

Test.
""",
        )

        issues = check_stack_frontmatter(tmp_path, ld)
        rt_issues = [i for i in issues if "resolution_type" in i.message]
        assert len(rt_issues) == 1
        assert "resolved" in rt_issues[0].message

    def test_valid_resolution_types_pass(self, tmp_path: Path) -> None:
        """All valid resolution_type values produce no issues."""
        ld = tmp_path / ".lexibrary"
        valid_types = ["fix", "workaround", "wontfix", "cannot_reproduce", "by_design"]
        for i, rt in enumerate(valid_types):
            _write_stack_post(
                ld / "stack" / "posts",
                f"resolved-{i}",
                post_id=f"ST-{i + 10:03d}",
                status="resolved",
                resolution_type=rt,
            )

        issues = check_stack_frontmatter(tmp_path, ld)
        assert issues == []

    def test_missing_author_reports_error(self, tmp_path: Path) -> None:
        """Missing author field produces an error."""
        ld = tmp_path / ".lexibrary"
        _write_stack_post(
            ld / "stack" / "posts",
            "no-author",
            raw_content="""---
id: ST-005
title: No Author
tags: [bug]
status: open
created: 2026-01-15
---

## Problem

Test.
""",
        )

        issues = check_stack_frontmatter(tmp_path, ld)
        auth_issues = [i for i in issues if "author" in i.message]
        assert len(auth_issues) == 1

    def test_missing_created_reports_error(self, tmp_path: Path) -> None:
        """Missing created field produces an error."""
        ld = tmp_path / ".lexibrary"
        _write_stack_post(
            ld / "stack" / "posts",
            "no-created",
            raw_content="""---
id: ST-006
title: No Created
tags: [bug]
status: open
author: tester
---

## Problem

Test.
""",
        )

        issues = check_stack_frontmatter(tmp_path, ld)
        created_issues = [i for i in issues if "created" in i.message]
        assert len(created_issues) == 1

    def test_unparseable_yaml_reports_error(self, tmp_path: Path) -> None:
        """Malformed YAML in Stack post produces an error."""
        ld = tmp_path / ".lexibrary"
        _write_stack_post(
            ld / "stack" / "posts",
            "bad-yaml",
            raw_content="""---
id: [unterminated
title: broken
---

## Problem

Test.
""",
        )

        issues = check_stack_frontmatter(tmp_path, ld)
        assert len(issues) >= 1
        assert any("YAML" in i.message for i in issues)

    def test_missing_frontmatter_reports_error(self, tmp_path: Path) -> None:
        """No frontmatter delimiters produces an error."""
        ld = tmp_path / ".lexibrary"
        _write_stack_post(
            ld / "stack" / "posts",
            "no-fm",
            raw_content="Just plain text, no frontmatter.\n",
        )

        issues = check_stack_frontmatter(tmp_path, ld)
        assert len(issues) == 1
        assert "Missing YAML frontmatter" in issues[0].message


# ---------------------------------------------------------------------------
# check_iwh_frontmatter
# ---------------------------------------------------------------------------


class TestCheckIwhFrontmatter:
    """Tests for check_iwh_frontmatter."""

    def test_valid_iwh_returns_empty(self, tmp_path: Path) -> None:
        """Valid IWH file with all fields produces no issues."""
        ld = tmp_path / ".lexibrary"
        _write_iwh(ld / "designs" / "src" / "auth")

        issues = check_iwh_frontmatter(tmp_path, ld)
        assert issues == []

    def test_no_iwh_files_returns_empty(self, tmp_path: Path) -> None:
        """No .iwh files under .lexibrary returns empty list."""
        ld = tmp_path / ".lexibrary"
        ld.mkdir()

        issues = check_iwh_frontmatter(tmp_path, ld)
        assert issues == []

    def test_missing_lexibrary_dir_returns_empty(self, tmp_path: Path) -> None:
        """Non-existent .lexibrary dir returns empty list."""
        ld = tmp_path / ".lexibrary"

        issues = check_iwh_frontmatter(tmp_path, ld)
        assert issues == []

    def test_missing_author_reports_error(self, tmp_path: Path) -> None:
        """Missing author field produces an error."""
        ld = tmp_path / ".lexibrary"
        _write_iwh(
            ld / "designs" / "src",
            raw_content="""---
created: 2026-03-10T14:30:00
scope: incomplete
---

Body.
""",
        )

        issues = check_iwh_frontmatter(tmp_path, ld)
        auth_issues = [i for i in issues if "author" in i.message]
        assert len(auth_issues) == 1
        assert auth_issues[0].severity == "error"
        assert auth_issues[0].check == "iwh_frontmatter"

    def test_invalid_scope_reports_error(self, tmp_path: Path) -> None:
        """Invalid scope value produces an error listing valid values."""
        ld = tmp_path / ".lexibrary"
        _write_iwh(
            ld / "designs" / "src",
            raw_content="""---
author: agent-1
created: 2026-03-10T14:30:00
scope: error
---

Body.
""",
        )

        issues = check_iwh_frontmatter(tmp_path, ld)
        scope_issues = [i for i in issues if "scope" in i.message.lower()]
        assert len(scope_issues) == 1
        assert "error" in scope_issues[0].message
        assert "blocked" in scope_issues[0].suggestion

    def test_invalid_datetime_reports_error(self, tmp_path: Path) -> None:
        """Invalid created datetime produces an error."""
        ld = tmp_path / ".lexibrary"
        _write_iwh(
            ld / "designs" / "src",
            raw_content="""---
author: agent-1
created: not-a-date
scope: incomplete
---

Body.
""",
        )

        issues = check_iwh_frontmatter(tmp_path, ld)
        created_issues = [i for i in issues if "created" in i.message.lower()]
        assert len(created_issues) == 1
        assert "ISO 8601" in created_issues[0].suggestion

    def test_valid_scopes_pass(self, tmp_path: Path) -> None:
        """All valid scope values produce no issues."""
        ld = tmp_path / ".lexibrary"
        for i, scope in enumerate(["warning", "incomplete", "blocked"]):
            _write_iwh(ld / "designs" / f"dir{i}", scope=scope)

        issues = check_iwh_frontmatter(tmp_path, ld)
        assert issues == []

    def test_unparseable_yaml_reports_error(self, tmp_path: Path) -> None:
        """Malformed YAML in IWH file produces an error."""
        ld = tmp_path / ".lexibrary"
        _write_iwh(
            ld / "designs" / "src",
            raw_content="""---
author: [unterminated
scope: broken
---

Body.
""",
        )

        issues = check_iwh_frontmatter(tmp_path, ld)
        assert len(issues) >= 1
        assert any("YAML" in i.message for i in issues)

    def test_missing_created_reports_error(self, tmp_path: Path) -> None:
        """Missing created field produces an error."""
        ld = tmp_path / ".lexibrary"
        _write_iwh(
            ld / "designs" / "src",
            raw_content="""---
author: agent-1
scope: incomplete
---

Body.
""",
        )

        issues = check_iwh_frontmatter(tmp_path, ld)
        created_issues = [i for i in issues if "created" in i.message]
        assert len(created_issues) == 1

    def test_missing_scope_reports_error(self, tmp_path: Path) -> None:
        """Missing scope field produces an error."""
        ld = tmp_path / ".lexibrary"
        _write_iwh(
            ld / "designs" / "src",
            raw_content="""---
author: agent-1
created: 2026-03-10T14:30:00
---

Body.
""",
        )

        issues = check_iwh_frontmatter(tmp_path, ld)
        scope_issues = [i for i in issues if "scope" in i.message]
        assert len(scope_issues) == 1

    def test_yaml_date_auto_parsed_passes(self, tmp_path: Path) -> None:
        """YAML auto-parses dates; check passes for valid date values."""
        ld = tmp_path / ".lexibrary"
        # YAML auto-parses 2026-03-10 as a date object
        _write_iwh(
            ld / "designs" / "src",
            raw_content="""---
author: agent-1
created: 2026-03-10
scope: incomplete
---

Body.
""",
        )

        issues = check_iwh_frontmatter(tmp_path, ld)
        created_issues = [i for i in issues if "created" in i.message]
        assert len(created_issues) == 0

    def test_multiple_iwh_files_all_checked(self, tmp_path: Path) -> None:
        """Multiple .iwh files are each independently checked."""
        ld = tmp_path / ".lexibrary"
        # One valid, one invalid
        _write_iwh(ld / "designs" / "src" / "good")
        _write_iwh(
            ld / "designs" / "src" / "bad",
            raw_content="""---
scope: invalid
---

Body.
""",
        )

        issues = check_iwh_frontmatter(tmp_path, ld)
        # The bad one should have issues for author, created, and scope
        assert len(issues) >= 2
