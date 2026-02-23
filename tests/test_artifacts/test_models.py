"""Tests for artifact Pydantic 2 data models."""

from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from lexibrary.artifacts.aindex import AIndexEntry, AIndexFile
from lexibrary.artifacts.concept import ConceptFile, ConceptFileFrontmatter
from lexibrary.artifacts.design_file import DesignFile, DesignFileFrontmatter, StalenessMetadata

# ---------------------------------------------------------------------------
# StalenessMetadata
# ---------------------------------------------------------------------------


def _meta(**overrides: object) -> dict:
    """Return a minimal valid StalenessMetadata dict, with optional overrides."""
    base: dict = {
        "source": "src/foo.py",
        "source_hash": "abc123",
        "generated": datetime(2026, 1, 1),
        "generator": "lexibrary-v2",
    }
    base.update(overrides)
    return base


class TestStalenessMetadata:
    def test_valid_defaults(self) -> None:
        meta = StalenessMetadata(**_meta())
        assert meta.source == "src/foo.py"
        assert meta.interface_hash is None

    def test_interface_hash_optional(self) -> None:
        meta = StalenessMetadata(**_meta(interface_hash="xyz"))
        assert meta.interface_hash == "xyz"

    def test_missing_required_field(self) -> None:
        with pytest.raises(ValidationError):
            StalenessMetadata(source="x", source_hash="y", generator="z")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# DesignFile
# ---------------------------------------------------------------------------


def _frontmatter(**overrides: object) -> DesignFileFrontmatter:
    base: dict = {"description": "A module."}
    base.update(overrides)
    return DesignFileFrontmatter(**base)


class TestDesignFile:
    def test_minimal_valid(self) -> None:
        df = DesignFile(
            source_path="src/foo.py",
            frontmatter=_frontmatter(),
            summary="A module",
            interface_contract="def foo()",
            metadata=StalenessMetadata(**_meta()),
        )
        assert df.dependencies == []
        assert df.tags == []

    def test_full_fields(self) -> None:
        df = DesignFile(
            source_path="src/foo.py",
            frontmatter=_frontmatter(),
            summary="A module",
            interface_contract="def foo()",
            dependencies=["bar.py"],
            dependents=["baz.py"],
            tests="test_foo.py",
            complexity_warning="high",
            wikilinks=["[[bar]]"],
            tags=["auth"],
            stack_refs=["ST-001"],
            metadata=StalenessMetadata(**_meta()),
        )
        assert df.dependencies == ["bar.py"]
        assert df.stack_refs == ["ST-001"]

    def test_missing_metadata_raises(self) -> None:
        with pytest.raises(ValidationError):
            DesignFile(
                source_path="x",
                frontmatter=_frontmatter(),
                summary="y",
                interface_contract="z",
            )  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# AIndexFile
# ---------------------------------------------------------------------------


class TestAIndexFile:
    def test_minimal_valid(self) -> None:
        entry = AIndexEntry(name="foo.py", entry_type="file", description="A file")
        aindex = AIndexFile(
            directory_path="src/",
            billboard="Source code",
            entries=[entry],
            metadata=StalenessMetadata(**_meta()),
        )
        assert len(aindex.entries) == 1
        assert aindex.local_conventions == []

    def test_dir_entry_type(self) -> None:
        entry = AIndexEntry(name="config", entry_type="dir", description="Contains 3 files")
        assert entry.entry_type == "dir"

    def test_invalid_entry_type_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AIndexEntry(name="foo", entry_type="symlink", description="bad")  # type: ignore[arg-type]

    def test_entry_missing_field(self) -> None:
        with pytest.raises(ValidationError):
            AIndexEntry(name="foo.py", description="A file")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# ConceptFileFrontmatter
# ---------------------------------------------------------------------------


class TestConceptFileFrontmatter:
    def test_defaults(self) -> None:
        fm = ConceptFileFrontmatter(title="JWT Auth")
        assert fm.title == "JWT Auth"
        assert fm.aliases == []
        assert fm.tags == []
        assert fm.status == "draft"
        assert fm.superseded_by is None

    def test_all_fields(self) -> None:
        fm = ConceptFileFrontmatter(
            title="JWT Auth",
            aliases=["json-web-token"],
            tags=["auth", "security"],
            status="active",
        )
        assert fm.aliases == ["json-web-token"]
        assert fm.tags == ["auth", "security"]
        assert fm.status == "active"

    def test_invalid_status_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ConceptFileFrontmatter(title="Bad", status="archived")  # type: ignore[arg-type]

    def test_deprecated_with_superseded_by(self) -> None:
        fm = ConceptFileFrontmatter(
            title="OldAuth",
            status="deprecated",
            superseded_by="NewAuth",
        )
        assert fm.status == "deprecated"
        assert fm.superseded_by == "NewAuth"

    def test_all_valid_statuses(self) -> None:
        for status in ("draft", "active", "deprecated"):
            fm = ConceptFileFrontmatter(title="Test", status=status)  # type: ignore[arg-type]
            assert fm.status == status


# ---------------------------------------------------------------------------
# ConceptFile
# ---------------------------------------------------------------------------


class TestConceptFile:
    def test_minimal_valid(self) -> None:
        fm = ConceptFileFrontmatter(title="auth")
        cf = ConceptFile(frontmatter=fm, body="")
        assert cf.summary == ""
        assert cf.related_concepts == []
        assert cf.linked_files == []
        assert cf.decision_log == []

    def test_name_property(self) -> None:
        fm = ConceptFileFrontmatter(title="Authentication")
        cf = ConceptFile(frontmatter=fm)
        assert cf.name == "Authentication"

    def test_full_fields(self) -> None:
        fm = ConceptFileFrontmatter(
            title="JWT Auth",
            aliases=["json-web-token"],
            tags=["auth"],
            status="active",
        )
        cf = ConceptFile(
            frontmatter=fm,
            body="# JWT Auth\nSome content",
            summary="Token-based authentication",
            related_concepts=["OAuth", "Sessions"],
            linked_files=["src/auth.py"],
            decision_log=["Use RS256 algorithm"],
        )
        assert cf.name == "JWT Auth"
        assert cf.related_concepts == ["OAuth", "Sessions"]
        assert cf.linked_files == ["src/auth.py"]
        assert cf.decision_log == ["Use RS256 algorithm"]

    def test_importable_from_artifacts(self) -> None:
        from lexibrary.artifacts import ConceptFile, ConceptFileFrontmatter

        assert ConceptFile is not None
        assert ConceptFileFrontmatter is not None
