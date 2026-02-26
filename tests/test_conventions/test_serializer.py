"""Tests for convention file serializer and round-trip integrity."""

from __future__ import annotations

from pathlib import Path

from lexibrary.artifacts.convention import ConventionFile, ConventionFileFrontmatter
from lexibrary.conventions.parser import parse_convention_file
from lexibrary.conventions.serializer import serialize_convention_file


class TestSerializeConventionFile:
    def test_fully_populated(self) -> None:
        cf = ConventionFile(
            frontmatter=ConventionFileFrontmatter(
                title="Future annotations",
                scope="project",
                tags=["python", "style"],
                status="active",
                source="config",
                priority=10,
            ),
            body="Every module must use future annotations.\n\n**Rationale**: PEP 604.\n",
            rule="Every module must use future annotations.",
        )
        result = serialize_convention_file(cf)
        assert result.startswith("---\n")
        assert "title: Future annotations" in result
        assert "scope: project" in result
        assert "status: active" in result
        assert "source: config" in result
        assert "priority: 10" in result
        assert "Every module must use future annotations." in result
        assert result.endswith("\n")

    def test_empty_tags(self) -> None:
        cf = ConventionFile(
            frontmatter=ConventionFileFrontmatter(title="Minimal"),
            body="Body.\n",
        )
        result = serialize_convention_file(cf)
        assert "tags: []" in result

    def test_default_values_serialized(self) -> None:
        cf = ConventionFile(
            frontmatter=ConventionFileFrontmatter(title="Defaults"),
            body="Use defaults.\n",
        )
        result = serialize_convention_file(cf)
        assert "scope: project" in result
        assert "status: draft" in result
        assert "source: user" in result
        assert "priority: 0" in result

    def test_body_preserved_exactly(self) -> None:
        body = "Use `from __future__ import annotations`.\n\n**Rationale**: Consistency.\n"
        cf = ConventionFile(
            frontmatter=ConventionFileFrontmatter(title="Test"),
            body=body,
        )
        result = serialize_convention_file(cf)
        assert body in result

    def test_trailing_newline(self) -> None:
        cf = ConventionFile(
            frontmatter=ConventionFileFrontmatter(title="T"),
            body="No trailing newline",
        )
        result = serialize_convention_file(cf)
        assert result.endswith("\n")

    def test_empty_body(self) -> None:
        cf = ConventionFile(
            frontmatter=ConventionFileFrontmatter(title="Empty"),
            body="",
        )
        result = serialize_convention_file(cf)
        assert result.startswith("---\n")
        assert result.endswith("\n")

    def test_directory_scope(self) -> None:
        cf = ConventionFile(
            frontmatter=ConventionFileFrontmatter(title="Auth", scope="src/auth"),
            body="Validate tokens.\n",
        )
        result = serialize_convention_file(cf)
        assert "scope: src/auth" in result


class TestRoundTrip:
    def test_round_trip_all_fields(self, tmp_path: Path) -> None:
        original = ConventionFile(
            frontmatter=ConventionFileFrontmatter(
                title="Future annotations",
                scope="src/lexibrary",
                tags=["python", "imports"],
                status="active",
                source="user",
                priority=5,
            ),
            body=(
                "\nEvery module must use future annotations.\n\n"
                "**Rationale**: PEP 604 union syntax and no runtime evaluation.\n"
            ),
            rule="Every module must use future annotations.",
        )
        serialized = serialize_convention_file(original)
        path = tmp_path / "future-annotations.md"
        path.write_text(serialized)
        parsed = parse_convention_file(path)

        assert parsed is not None
        assert parsed.frontmatter.title == original.frontmatter.title
        assert parsed.frontmatter.scope == original.frontmatter.scope
        assert parsed.frontmatter.tags == original.frontmatter.tags
        assert parsed.frontmatter.status == original.frontmatter.status
        assert parsed.frontmatter.source == original.frontmatter.source
        assert parsed.frontmatter.priority == original.frontmatter.priority
        assert parsed.body == original.body

    def test_round_trip_minimal(self, tmp_path: Path) -> None:
        original = ConventionFile(
            frontmatter=ConventionFileFrontmatter(title="Minimal"),
            body="\nJust a rule.\n",
        )
        serialized = serialize_convention_file(original)
        path = tmp_path / "minimal.md"
        path.write_text(serialized)
        parsed = parse_convention_file(path)

        assert parsed is not None
        assert parsed.frontmatter.title == "Minimal"
        assert parsed.body == original.body

    def test_round_trip_preserves_rule_extraction(self, tmp_path: Path) -> None:
        original = ConventionFile(
            frontmatter=ConventionFileFrontmatter(title="Rule test"),
            body="\nFirst paragraph is the rule.\n\nSecond paragraph is rationale.\n",
            rule="First paragraph is the rule.",
        )
        serialized = serialize_convention_file(original)
        path = tmp_path / "rule-test.md"
        path.write_text(serialized)
        parsed = parse_convention_file(path)

        assert parsed is not None
        assert parsed.rule == "First paragraph is the rule."
