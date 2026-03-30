"""Tests for wiki concept file serializer and round-trip integrity."""

from __future__ import annotations

from pathlib import Path

from lexibrary.artifacts.concept import ConceptFile, ConceptFileFrontmatter
from lexibrary.wiki.parser import parse_concept_file
from lexibrary.wiki.serializer import serialize_concept_file


class TestSerializeConceptFile:
    def test_fully_populated(self) -> None:
        cf = ConceptFile(
            frontmatter=ConceptFileFrontmatter(
                title="JWT Auth",
                id="CN-001",
                aliases=["JSON Web Token"],
                tags=["auth", "security"],
                status="active",
            ),
            body="This is the body.\n\n## Details\n\nSome details.\n",
        )
        result = serialize_concept_file(cf)
        assert result.startswith("---\n")
        assert "title: JWT Auth" in result
        assert "status: active" in result
        assert "This is the body." in result
        assert result.endswith("\n")

    def test_empty_aliases_and_tags(self) -> None:
        cf = ConceptFile(
            frontmatter=ConceptFileFrontmatter(title="Minimal", id="CN-001"),
            body="Body.\n",
        )
        result = serialize_concept_file(cf)
        assert "aliases: []" in result
        assert "tags: []" in result

    def test_superseded_by_included(self) -> None:
        cf = ConceptFile(
            frontmatter=ConceptFileFrontmatter(
                title="Old",
                id="CN-001",
                status="deprecated",
                superseded_by="NewConcept",
            ),
            body="Deprecated.\n",
        )
        result = serialize_concept_file(cf)
        assert "superseded_by: NewConcept" in result

    def test_superseded_by_omitted_when_none(self) -> None:
        cf = ConceptFile(
            frontmatter=ConceptFileFrontmatter(title="Active", id="CN-001"),
            body="Active concept.\n",
        )
        result = serialize_concept_file(cf)
        assert "superseded_by" not in result

    def test_body_preserved_exactly(self) -> None:
        body = "See [[JWT Auth]] and `src/foo/bar.py`.\n\n## Decision Log\n\n- Did a thing\n"
        cf = ConceptFile(
            frontmatter=ConceptFileFrontmatter(title="Test", id="CN-001"),
            body=body,
        )
        result = serialize_concept_file(cf)
        assert body in result

    def test_trailing_newline(self) -> None:
        cf = ConceptFile(
            frontmatter=ConceptFileFrontmatter(title="T", id="CN-001"),
            body="No trailing newline",
        )
        result = serialize_concept_file(cf)
        assert result.endswith("\n")


class TestRoundTrip:
    def test_round_trip_all_fields(self, tmp_path: Path) -> None:
        original = ConceptFile(
            frontmatter=ConceptFileFrontmatter(
                title="Round Trip",
                id="CN-001",
                aliases=["RT", "Roundtrip"],
                tags=["test", "roundtrip"],
                status="active",
            ),
            body=(
                "\nA concept about round trips.\n\nSee [[Other Concept]]."
                "\n\n## Details\n\nDetails here."
                "\n\n## Decision Log\n\n- First decision\n- Second decision\n"
            ),
        )
        serialized = serialize_concept_file(original)
        path = tmp_path / "RoundTrip.md"
        path.write_text(serialized)
        parsed = parse_concept_file(path)

        assert parsed is not None
        assert parsed.frontmatter.title == original.frontmatter.title
        assert parsed.frontmatter.aliases == original.frontmatter.aliases
        assert parsed.frontmatter.tags == original.frontmatter.tags
        assert parsed.frontmatter.status == original.frontmatter.status
        assert parsed.frontmatter.superseded_by == original.frontmatter.superseded_by
        assert parsed.body == original.body

    def test_round_trip_minimal(self, tmp_path: Path) -> None:
        original = ConceptFile(
            frontmatter=ConceptFileFrontmatter(title="Minimal", id="CN-001"),
            body="\nJust a body.\n",
        )
        serialized = serialize_concept_file(original)
        path = tmp_path / "Minimal.md"
        path.write_text(serialized)
        parsed = parse_concept_file(path)

        assert parsed is not None
        assert parsed.frontmatter.title == "Minimal"
        assert parsed.body == original.body
