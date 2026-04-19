"""Round-trip tests for new curator-4 frontmatter fields.

Covers the three new optional frontmatter fields added by Group 1:

- ``ConceptFileFrontmatter.deprecated_reason`` (free-text str)
- ``ConceptFileFrontmatter.last_verified`` (date)
- ``ConventionFileFrontmatter.deprecated_reason`` (free-text str)
- ``PlaybookFileFrontmatter.deprecated_reason`` (free-text str)

Each test confirms that (a) artifacts without the new field parse with
``None``, and (b) writing an artifact that sets the field then re-reading
it preserves the value.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

from lexibrary.artifacts.concept import ConceptFile, ConceptFileFrontmatter
from lexibrary.artifacts.convention import ConventionFile, ConventionFileFrontmatter
from lexibrary.artifacts.playbook import PlaybookFile, PlaybookFileFrontmatter
from lexibrary.conventions.parser import parse_convention_file
from lexibrary.conventions.serializer import serialize_convention_file
from lexibrary.playbooks.parser import parse_playbook_file
from lexibrary.playbooks.serializer import serialize_playbook_file
from lexibrary.wiki.parser import parse_concept_file
from lexibrary.wiki.serializer import serialize_concept_file

# ---------------------------------------------------------------------------
# Concept: deprecated_reason + last_verified
# ---------------------------------------------------------------------------


def test_concept_without_deprecated_reason_parses_as_none(tmp_path: Path) -> None:
    """An existing concept file without ``deprecated_reason`` parses with ``None``."""
    src = tmp_path / "CN-001-jwt-auth.md"
    src.write_text(
        "---\ntitle: JWT Auth\nid: CN-001\naliases: []\ntags: []\nstatus: active\n---\nBody.\n"
    )
    concept = parse_concept_file(src)
    assert concept is not None
    assert concept.frontmatter.deprecated_reason is None


def test_concept_without_last_verified_parses_as_none(tmp_path: Path) -> None:
    """An existing concept file without ``last_verified`` parses with ``None``."""
    src = tmp_path / "CN-002-sample.md"
    src.write_text(
        "---\ntitle: Sample\nid: CN-002\naliases: []\ntags: []\nstatus: active\n---\nBody.\n"
    )
    concept = parse_concept_file(src)
    assert concept is not None
    assert concept.frontmatter.last_verified is None


def test_concept_deprecated_reason_round_trip(tmp_path: Path) -> None:
    """Writing a concept with ``deprecated_reason`` and re-reading preserves the value."""
    path = tmp_path / "CN-003-old-auth.md"
    fm = ConceptFileFrontmatter(
        title="OldAuth",
        id="CN-003",
        status="deprecated",
        deprecated_at=datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC),
        deprecated_reason="no_inbound_links",
    )
    concept = ConceptFile(frontmatter=fm, body="# OldAuth\n\nBody.\n")
    path.write_text(serialize_concept_file(concept))

    reloaded = parse_concept_file(path)
    assert reloaded is not None
    assert reloaded.frontmatter.deprecated_reason == "no_inbound_links"
    assert reloaded.frontmatter.status == "deprecated"


def test_concept_last_verified_round_trip(tmp_path: Path) -> None:
    """Writing a concept with ``last_verified`` and re-reading preserves the value."""
    path = tmp_path / "CN-004-sample.md"
    fm = ConceptFileFrontmatter(
        title="Sample",
        id="CN-004",
        last_verified=date(2026, 4, 15),
    )
    concept = ConceptFile(frontmatter=fm, body="Body.\n")
    path.write_text(serialize_concept_file(concept))

    reloaded = parse_concept_file(path)
    assert reloaded is not None
    assert reloaded.frontmatter.last_verified == date(2026, 4, 15)


def test_concept_round_trip_without_new_fields_unchanged(tmp_path: Path) -> None:
    """Writing a concept without the new fields omits them from serialized output.

    Guards against accidental injection of empty keys that would alter
    byte-compatibility with existing artifacts on disk.
    """
    path = tmp_path / "CN-005-basic.md"
    fm = ConceptFileFrontmatter(title="Basic", id="CN-005")
    concept = ConceptFile(frontmatter=fm, body="Body.\n")
    serialized = serialize_concept_file(concept)

    assert "deprecated_reason" not in serialized
    assert "last_verified" not in serialized

    path.write_text(serialized)
    reloaded = parse_concept_file(path)
    assert reloaded is not None
    assert reloaded.frontmatter.deprecated_reason is None
    assert reloaded.frontmatter.last_verified is None


# ---------------------------------------------------------------------------
# Convention: deprecated_reason
# ---------------------------------------------------------------------------


def test_convention_without_deprecated_reason_parses_as_none(tmp_path: Path) -> None:
    """An existing convention file without ``deprecated_reason`` parses with ``None``."""
    src = tmp_path / "CV-001-use-utc.md"
    src.write_text(
        "---\n"
        "title: Use UTC Everywhere\n"
        "id: CV-001\n"
        "scope: project\n"
        "tags: []\n"
        "status: active\n"
        "source: user\n"
        "priority: 0\n"
        "---\n"
        "Body.\n"
    )
    convention = parse_convention_file(src)
    assert convention is not None
    assert convention.frontmatter.deprecated_reason is None


def test_convention_deprecated_reason_round_trip(tmp_path: Path) -> None:
    """Writing a convention with ``deprecated_reason`` and re-reading preserves the value."""
    path = tmp_path / "CV-002-old-rule.md"
    fm = ConventionFileFrontmatter(
        title="Old Rule",
        id="CV-002",
        scope="project",
        status="deprecated",
        source="user",
        deprecated_at=datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC),
        deprecated_reason="scope_path_missing",
    )
    convention = ConventionFile(frontmatter=fm, body="Old rule body.\n")
    path.write_text(serialize_convention_file(convention))

    reloaded = parse_convention_file(path)
    assert reloaded is not None
    assert reloaded.frontmatter.deprecated_reason == "scope_path_missing"
    assert reloaded.frontmatter.status == "deprecated"


def test_convention_round_trip_without_deprecated_reason_unchanged(tmp_path: Path) -> None:
    """Writing a convention without ``deprecated_reason`` omits it from output."""
    path = tmp_path / "CV-003-basic.md"
    fm = ConventionFileFrontmatter(
        title="Basic",
        id="CV-003",
        scope="project",
        status="active",
        source="user",
    )
    convention = ConventionFile(frontmatter=fm, body="Body.\n")
    serialized = serialize_convention_file(convention)

    assert "deprecated_reason" not in serialized

    path.write_text(serialized)
    reloaded = parse_convention_file(path)
    assert reloaded is not None
    assert reloaded.frontmatter.deprecated_reason is None


# ---------------------------------------------------------------------------
# Playbook: deprecated_reason
# ---------------------------------------------------------------------------


def test_playbook_without_deprecated_reason_parses_as_none(tmp_path: Path) -> None:
    """An existing playbook file without ``deprecated_reason`` parses with ``None``."""
    src = tmp_path / "PB-001-sample.md"
    src.write_text(
        "---\n"
        "# title: use a semantic name that describes the procedure\n"
        "title: Sample Playbook\n"
        "id: PB-001\n"
        "trigger_files: []\n"
        "tags: []\n"
        "status: active\n"
        "source: user\n"
        "---\n"
        "Body.\n"
    )
    playbook = parse_playbook_file(src)
    assert playbook is not None
    assert playbook.frontmatter.deprecated_reason is None


def test_playbook_deprecated_reason_round_trip(tmp_path: Path) -> None:
    """Writing a playbook with ``deprecated_reason`` and re-reading preserves the value."""
    path = tmp_path / "PB-002-old-procedure.md"
    fm = PlaybookFileFrontmatter(
        title="Old Procedure",
        id="PB-002",
        status="deprecated",
        source="user",
        deprecated_at=datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC),
        deprecated_reason="past_last_verified",
    )
    playbook = PlaybookFile(frontmatter=fm, body="Old procedure body.\n")
    path.write_text(serialize_playbook_file(playbook))

    reloaded = parse_playbook_file(path)
    assert reloaded is not None
    assert reloaded.frontmatter.deprecated_reason == "past_last_verified"
    assert reloaded.frontmatter.status == "deprecated"


def test_playbook_round_trip_without_deprecated_reason_unchanged(tmp_path: Path) -> None:
    """Writing a playbook without ``deprecated_reason`` omits it from output."""
    path = tmp_path / "PB-003-basic.md"
    fm = PlaybookFileFrontmatter(
        title="Basic Playbook",
        id="PB-003",
        status="active",
        source="user",
    )
    playbook = PlaybookFile(frontmatter=fm, body="Body.\n")
    serialized = serialize_playbook_file(playbook)

    assert "deprecated_reason" not in serialized

    path.write_text(serialized)
    reloaded = parse_playbook_file(path)
    assert reloaded is not None
    assert reloaded.frontmatter.deprecated_reason is None
