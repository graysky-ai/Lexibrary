"""Tests for convention file parser."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from lexibrary.conventions.parser import parse_convention_file

VALID_CONVENTION = """\
---
title: Future annotations import
scope: project
tags:
  - python
  - style
status: active
source: config
priority: 10
---
Every Python module must include `from __future__ import annotations`.

**Rationale**: This enables PEP 604 union syntax and avoids runtime evaluation
of type hints, improving both consistency and performance.
"""

MINIMAL_CONVENTION = """\
---
title: Use UTC everywhere
---
All timestamps must use UTC.
"""

CONVENTION_WITH_ALIASES = """\
---
title: Auth decorator required
scope: src/auth
tags:
  - security
aliases:
  - auth-decorator
  - auth-conv
status: active
source: user
priority: 5
---
All endpoints must use the auth decorator.
"""

DEPRECATED_CONVENTION = """\
---
title: Old logging rule
scope: project
tags:
  - logging
status: deprecated
source: user
priority: 0
deprecated_at: '2026-03-04T10:00:00'
---
Use print for logging.
"""


class TestParseConventionFileValid:
    def test_returns_convention_file(self, tmp_path: Path) -> None:
        path = tmp_path / "future-annotations.md"
        path.write_text(VALID_CONVENTION)
        result = parse_convention_file(path)
        assert result is not None

    def test_frontmatter_fields(self, tmp_path: Path) -> None:
        path = tmp_path / "future-annotations.md"
        path.write_text(VALID_CONVENTION)
        result = parse_convention_file(path)
        assert result is not None
        assert result.frontmatter.title == "Future annotations import"
        assert result.frontmatter.scope == "project"
        assert result.frontmatter.tags == ["python", "style"]
        assert result.frontmatter.status == "active"
        assert result.frontmatter.source == "config"
        assert result.frontmatter.priority == 10

    def test_rule_extraction(self, tmp_path: Path) -> None:
        path = tmp_path / "future-annotations.md"
        path.write_text(VALID_CONVENTION)
        result = parse_convention_file(path)
        assert result is not None
        expected_rule = "Every Python module must include `from __future__ import annotations`."
        assert result.rule == expected_rule

    def test_body_preserved(self, tmp_path: Path) -> None:
        path = tmp_path / "future-annotations.md"
        path.write_text(VALID_CONVENTION)
        result = parse_convention_file(path)
        assert result is not None
        assert "**Rationale**" in result.body
        assert "from __future__ import annotations" in result.body

    def test_file_path_set(self, tmp_path: Path) -> None:
        path = tmp_path / "future-annotations.md"
        path.write_text(VALID_CONVENTION)
        result = parse_convention_file(path)
        assert result is not None
        assert result.file_path == path

    def test_name_property(self, tmp_path: Path) -> None:
        path = tmp_path / "future-annotations.md"
        path.write_text(VALID_CONVENTION)
        result = parse_convention_file(path)
        assert result is not None
        assert result.name == "Future annotations import"

    def test_scope_property(self, tmp_path: Path) -> None:
        path = tmp_path / "future-annotations.md"
        path.write_text(VALID_CONVENTION)
        result = parse_convention_file(path)
        assert result is not None
        assert result.scope == "project"


class TestParseConventionFileMinimal:
    def test_minimal_frontmatter_defaults(self, tmp_path: Path) -> None:
        path = tmp_path / "use-utc.md"
        path.write_text(MINIMAL_CONVENTION)
        result = parse_convention_file(path)
        assert result is not None
        assert result.frontmatter.title == "Use UTC everywhere"
        assert result.frontmatter.scope == "project"
        assert result.frontmatter.tags == []
        assert result.frontmatter.status == "draft"
        assert result.frontmatter.source == "user"
        assert result.frontmatter.priority == 0
        assert result.frontmatter.aliases == []
        assert result.frontmatter.deprecated_at is None

    def test_minimal_rule(self, tmp_path: Path) -> None:
        path = tmp_path / "use-utc.md"
        path.write_text(MINIMAL_CONVENTION)
        result = parse_convention_file(path)
        assert result is not None
        assert result.rule == "All timestamps must use UTC."


class TestParseConventionFileRuleExtraction:
    def test_rule_from_multiline_first_paragraph(self, tmp_path: Path) -> None:
        text = (
            "---\ntitle: Test\n---\nFirst line of rule.\nSecond line of rule.\n\nRationale below.\n"
        )
        path = tmp_path / "test.md"
        path.write_text(text)
        result = parse_convention_file(path)
        assert result is not None
        assert result.rule == "First line of rule.\nSecond line of rule."

    def test_empty_body_produces_empty_rule(self, tmp_path: Path) -> None:
        text = "---\ntitle: Empty\n---\n"
        path = tmp_path / "empty.md"
        path.write_text(text)
        result = parse_convention_file(path)
        assert result is not None
        assert result.rule == ""

    def test_body_with_only_whitespace(self, tmp_path: Path) -> None:
        text = "---\ntitle: Whitespace\n---\n\n  \n\n"
        path = tmp_path / "ws.md"
        path.write_text(text)
        result = parse_convention_file(path)
        assert result is not None
        assert result.rule == ""


class TestParseConventionFileEdgeCases:
    def test_nonexistent_file(self, tmp_path: Path) -> None:
        path = tmp_path / "missing.md"
        assert parse_convention_file(path) is None

    def test_no_frontmatter(self, tmp_path: Path) -> None:
        path = tmp_path / "nofm.md"
        path.write_text("# Just a heading\n\nSome text.\n")
        assert parse_convention_file(path) is None

    def test_invalid_frontmatter_missing_title(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.md"
        path.write_text("---\nscope: project\ntags: []\n---\nBody.\n")
        assert parse_convention_file(path) is None

    def test_invalid_frontmatter_bad_status(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.md"
        path.write_text("---\ntitle: Test\nstatus: archived\n---\nBody.\n")
        assert parse_convention_file(path) is None

    def test_invalid_frontmatter_bad_source(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.md"
        path.write_text("---\ntitle: Test\nsource: llm\n---\nBody.\n")
        assert parse_convention_file(path) is None

    def test_invalid_yaml(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.md"
        path.write_text("---\n: invalid: yaml: [[\n---\nBody.\n")
        assert parse_convention_file(path) is None

    def test_frontmatter_not_a_dict(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.md"
        path.write_text("---\n- item1\n- item2\n---\nBody.\n")
        assert parse_convention_file(path) is None

    def test_directory_scoped_convention(self, tmp_path: Path) -> None:
        text = (
            "---\ntitle: Auth conventions\nscope: src/auth\n---\n"
            "All auth modules must validate tokens.\n"
        )
        path = tmp_path / "auth-conventions.md"
        path.write_text(text)
        result = parse_convention_file(path)
        assert result is not None
        assert result.frontmatter.scope == "src/auth"
        assert result.scope == "src/auth"


class TestParseConventionFileAliases:
    def test_aliases_parsed(self, tmp_path: Path) -> None:
        path = tmp_path / "auth-decorator.md"
        path.write_text(CONVENTION_WITH_ALIASES)
        result = parse_convention_file(path)
        assert result is not None
        assert result.frontmatter.aliases == ["auth-decorator", "auth-conv"]

    def test_aliases_default_when_absent(self, tmp_path: Path) -> None:
        path = tmp_path / "no-aliases.md"
        path.write_text(VALID_CONVENTION)
        result = parse_convention_file(path)
        assert result is not None
        assert result.frontmatter.aliases == []


class TestParseConventionFileDeprecatedAt:
    def test_deprecated_at_parsed(self, tmp_path: Path) -> None:
        path = tmp_path / "old-logging.md"
        path.write_text(DEPRECATED_CONVENTION)
        result = parse_convention_file(path)
        assert result is not None
        assert result.frontmatter.deprecated_at == datetime(2026, 3, 4, 10, 0, 0)
        assert result.frontmatter.status == "deprecated"

    def test_deprecated_at_none_when_absent(self, tmp_path: Path) -> None:
        path = tmp_path / "active.md"
        path.write_text(VALID_CONVENTION)
        result = parse_convention_file(path)
        assert result is not None
        assert result.frontmatter.deprecated_at is None
