"""Tests for the migration execution module.

Covers ``validate_successor_chain()``, ``apply_migration_edits()``, and
``verify_migration()`` using mocked parsers, ``atomic_write()``, and
``reverse_deps()``.  Uses ``tmp_path`` for filesystem tests.
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lexibrary.baml_client.types import MigrationEdit, MigrationEditType
from lexibrary.curator.migration import (
    apply_migration_edits,
    validate_successor_chain,
    verify_migration,
)
from lexibrary.linkgraph.query import LinkResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_link_result(source_path: str, link_type: str = "wikilink") -> LinkResult:
    """Create a ``LinkResult`` with sensible defaults."""
    return LinkResult(
        source_id=hash(source_path) % 10000,
        source_path=source_path,
        link_type=link_type,
        link_context=None,
    )


def _write_concept_file(
    path: Path,
    title: str,
    status: str,
    superseded_by: str | None = None,
) -> None:
    """Write a minimal concept file with frontmatter."""
    lines = [
        "---",
        f"title: {title}",
        f"id: CN-{hash(title) % 1000:03d}",
        f"status: {status}",
    ]
    if superseded_by:
        lines.append(f"superseded_by: {superseded_by}")
    lines.extend(
        [
            "---",
            "",
            f"# {title}",
            "",
            "Body text here.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_convention_file(path: Path, title: str, status: str) -> None:
    """Write a minimal convention file with frontmatter."""
    lines = [
        "---",
        f"title: {title}",
        f"id: CV-{hash(title) % 1000:03d}",
        "scope: project",
        f"status: {status}",
        "---",
        "",
        f"# {title}",
        "",
        "Body text here.",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_design_file(path: Path, description: str, body: str = "Design body.") -> None:
    """Write a design file that ``parse_design_file()`` can round-trip.

    Creates the full structure: YAML frontmatter, H1 heading (source path),
    Interface Contract section, Dependencies section, Dependents section,
    and HTML comment metadata footer.
    """
    from datetime import UTC, datetime

    source_path = "src/test_file.py"
    generated = datetime.now(UTC).isoformat()
    lines = [
        "---",
        f"description: {description}",
        "id: design-001",
        "updated_by: archivist",
        "status: active",
        "---",
        "",
        f"# {source_path}",
        "",
        "## Interface Contract",
        "",
        "```python",
        "def example(): ...",
        "```",
        "",
        "## Dependencies",
        "",
        "(none)",
        "",
        "## Dependents",
        "",
        "*(see `lexi lookup` for live reverse references)*",
        "",
        "(none)",
        "",
        "## Body",
        "",
        body,
        "",
        "<!-- lexibrary:meta",
        f"source: {source_path}",
        "source_hash: abc123",
        "interface_hash: def456",
        "design_hash: ghi789",
        f"generated: {generated}",
        "generator: test",
        "-->",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _make_migration_edit(
    artifact_path: str,
    edit_type: MigrationEditType,
    old_value: str,
    new_value: str | None = None,
) -> MigrationEdit:
    """Create a MigrationEdit with the given parameters."""
    return MigrationEdit(
        artifact_path=artifact_path,
        edit_type=edit_type,
        old_value=old_value,
        new_value=new_value,
    )


# ===========================================================================
# validate_successor_chain tests
# ===========================================================================


class TestValidateSuccessorChain:
    """Tests for ``validate_successor_chain()``."""

    def test_valid_chain_active_successor(self, tmp_path: Path) -> None:
        """Valid chain: successor exists and has active status.

        Task 13.1: valid chain returns (True, "").
        """
        # Create an active concept file as the successor
        successor_path = tmp_path / "concepts" / "new-concept.md"
        _write_concept_file(successor_path, "New Concept", "active")

        with patch(
            "lexibrary.curator.migration.Path.cwd",
            return_value=tmp_path,
        ):
            valid, reason = validate_successor_chain(
                str(successor_path),
                link_graph=None,
            )

        assert valid is True
        assert reason == ""

    def test_deprecated_successor_returns_failure(self, tmp_path: Path) -> None:
        """Deprecated successor returns (False, "successor is deprecated: ...").

        Task 13.1: deprecated successor returns failure.
        """
        successor_path = tmp_path / "concepts" / "old-concept.md"
        _write_concept_file(successor_path, "Old Concept", "deprecated")

        with patch(
            "lexibrary.curator.migration.Path.cwd",
            return_value=tmp_path,
        ):
            valid, reason = validate_successor_chain(
                str(successor_path),
                link_graph=None,
            )

        assert valid is False
        assert "successor is deprecated" in reason

    def test_cycle_detection_a_to_b_to_a(self, tmp_path: Path) -> None:
        """Cycle A -> B -> A returns (False, "cycle detected: ...").

        Task 13.1: cycle (A -> B -> A) returns failure with cycle description.
        """
        concept_a = tmp_path / "concepts" / "concept-a.md"
        concept_b = tmp_path / "concepts" / "concept-b.md"

        # A superseded by B, B superseded by A (cycle)
        _write_concept_file(
            concept_a,
            "Concept A",
            "active",
            superseded_by=str(concept_b),
        )
        _write_concept_file(
            concept_b,
            "Concept B",
            "active",
            superseded_by=str(concept_a),
        )

        with patch(
            "lexibrary.curator.migration.Path.cwd",
            return_value=tmp_path,
        ):
            valid, reason = validate_successor_chain(
                str(concept_a),
                link_graph=None,
            )

        assert valid is False
        assert "cycle detected" in reason

    def test_nonexistent_successor(self, tmp_path: Path) -> None:
        """Non-existent successor returns (False, "successor does not exist: ...")."""
        with patch(
            "lexibrary.curator.migration.Path.cwd",
            return_value=tmp_path,
        ):
            valid, reason = validate_successor_chain(
                str(tmp_path / "concepts" / "nonexistent.md"),
                link_graph=None,
            )

        assert valid is False
        assert "successor does not exist" in reason

    def test_empty_superseded_by(self) -> None:
        """Empty superseded_by returns (False, "superseded_by is empty")."""
        valid, reason = validate_successor_chain("", link_graph=None)

        assert valid is False
        assert "superseded_by is empty" in reason

    def test_chain_of_three_valid(self, tmp_path: Path) -> None:
        """A -> B -> C chain where C is active and has no successor is valid."""
        concept_a = tmp_path / "concepts" / "concept-a.md"
        concept_b = tmp_path / "concepts" / "concept-b.md"
        concept_c = tmp_path / "concepts" / "concept-c.md"

        _write_concept_file(
            concept_a,
            "Concept A",
            "active",
            superseded_by=str(concept_b),
        )
        _write_concept_file(
            concept_b,
            "Concept B",
            "active",
            superseded_by=str(concept_c),
        )
        _write_concept_file(concept_c, "Concept C", "active")

        with patch(
            "lexibrary.curator.migration.Path.cwd",
            return_value=tmp_path,
        ):
            valid, reason = validate_successor_chain(
                str(concept_a),
                link_graph=None,
            )

        assert valid is True
        assert reason == ""


# ===========================================================================
# apply_migration_edits tests
# ===========================================================================


class TestApplyMigrationEdits:
    """Tests for ``apply_migration_edits()``."""

    def test_replace_wikilink_with_superseded_by(self, tmp_path: Path) -> None:
        """Wikilinks [[OldConcept]] replaced with [[NewConcept]] in dependent artifacts.

        Task 13.2: migration with superseded_by replaces wikilinks.
        """
        # Create a concept file that references the old concept
        dependent_path = tmp_path / "concepts" / "dependent.md"
        _write_concept_file(dependent_path, "Dependent", "active")
        # Overwrite body to include a wikilink
        text = dependent_path.read_text(encoding="utf-8")
        text = text.replace(
            "Body text here.",
            "This depends on [[OldConcept]] for context.",
        )
        dependent_path.write_text(text, encoding="utf-8")

        edits = [
            _make_migration_edit(
                artifact_path=str(dependent_path.relative_to(tmp_path)),
                edit_type=MigrationEditType.ReplaceWikilink,
                old_value="OldConcept",
                new_value="NewConcept",
            ),
        ]

        report = apply_migration_edits(edits, tmp_path)

        assert report.success_count == 1
        assert report.failure_count == 0

        # Verify the wikilink was replaced
        updated_text = dependent_path.read_text(encoding="utf-8")
        assert "[[NewConcept]]" in updated_text
        assert "[[OldConcept]]" not in updated_text

    def test_remove_reference_without_superseded_by(self, tmp_path: Path) -> None:
        """References removed (not replaced) when no superseded_by.

        Task 13.3: migration without superseded_by removes references.
        """
        dependent_path = tmp_path / "concepts" / "dependent.md"
        _write_concept_file(dependent_path, "Dependent", "active")
        text = dependent_path.read_text(encoding="utf-8")
        text = text.replace(
            "Body text here.",
            "This depends on [[OldConcept]] for context.",
        )
        dependent_path.write_text(text, encoding="utf-8")

        edits = [
            _make_migration_edit(
                artifact_path=str(dependent_path.relative_to(tmp_path)),
                edit_type=MigrationEditType.RemoveReference,
                old_value="OldConcept",
                new_value=None,
            ),
        ]

        report = apply_migration_edits(edits, tmp_path)

        assert report.success_count == 1
        assert report.failure_count == 0

        updated_text = dependent_path.read_text(encoding="utf-8")
        # Wikilink brackets removed, but text preserved
        assert "[[OldConcept]]" not in updated_text
        assert "OldConcept" in updated_text

    def test_single_edit_failure_isolation(self, tmp_path: Path) -> None:
        """5 edits, 1 fails -- verify other 4 succeed and report shows 4+1.

        Task 13.4: single edit failure isolation.
        """
        # Create 4 valid target files
        valid_files = []
        for i in range(4):
            path = tmp_path / "concepts" / f"valid-{i}.md"
            _write_concept_file(path, f"Valid {i}", "active")
            text = path.read_text(encoding="utf-8")
            text = text.replace(
                "Body text here.",
                "References [[OldConcept]] here.",
            )
            path.write_text(text, encoding="utf-8")
            valid_files.append(path)

        edits = []
        # 4 valid edits
        for path in valid_files:
            edits.append(
                _make_migration_edit(
                    artifact_path=str(path.relative_to(tmp_path)),
                    edit_type=MigrationEditType.ReplaceWikilink,
                    old_value="OldConcept",
                    new_value="NewConcept",
                ),
            )
        # 1 edit targeting non-existent file
        edits.append(
            _make_migration_edit(
                artifact_path="concepts/nonexistent.md",
                edit_type=MigrationEditType.ReplaceWikilink,
                old_value="OldConcept",
                new_value="NewConcept",
            ),
        )

        report = apply_migration_edits(edits, tmp_path)

        assert report.success_count == 4
        assert report.failure_count == 1
        assert len(report.outcomes) == 5

        # Verify the 4 successful files were updated
        for path in valid_files:
            updated_text = path.read_text(encoding="utf-8")
            assert "[[NewConcept]]" in updated_text

        # Verify outcomes track success/failure correctly
        successes = [o for o in report.outcomes if o.success]
        failures = [o for o in report.outcomes if not o.success]
        assert len(successes) == 4
        assert len(failures) == 1
        assert failures[0].error != ""

    def test_design_file_edit_sets_updated_by_curator(self, tmp_path: Path) -> None:
        """Design file edits set updated_by to 'curator' in frontmatter."""
        designs_dir = tmp_path / ".lexibrary" / "designs" / "src"
        design_path = designs_dir / "test_file.py.md"
        _write_design_file(
            design_path,
            "Test file design",
            body="References [[OldConcept]] here.",
        )

        edits = [
            _make_migration_edit(
                artifact_path=str(design_path.relative_to(tmp_path)),
                edit_type=MigrationEditType.ReplaceWikilink,
                old_value="OldConcept",
                new_value="NewConcept",
            ),
        ]

        report = apply_migration_edits(edits, tmp_path)

        assert report.success_count == 1

        # Verify updated_by was set to curator
        updated_text = design_path.read_text(encoding="utf-8")
        assert "updated_by: curator" in updated_text
        assert "[[NewConcept]]" in updated_text

    def test_case_insensitive_wikilink_replacement(self, tmp_path: Path) -> None:
        """Wikilink replacement is case-insensitive."""
        dependent_path = tmp_path / "concepts" / "dependent.md"
        _write_concept_file(dependent_path, "Dependent", "active")
        text = dependent_path.read_text(encoding="utf-8")
        text = text.replace(
            "Body text here.",
            "References [[oldconcept]] and [[OLDCONCEPT]] here.",
        )
        dependent_path.write_text(text, encoding="utf-8")

        edits = [
            _make_migration_edit(
                artifact_path=str(dependent_path.relative_to(tmp_path)),
                edit_type=MigrationEditType.ReplaceWikilink,
                old_value="OldConcept",
                new_value="NewConcept",
            ),
        ]

        report = apply_migration_edits(edits, tmp_path)

        assert report.success_count == 1
        updated_text = dependent_path.read_text(encoding="utf-8")
        assert updated_text.count("[[NewConcept]]") == 2
        assert "[[oldconcept]]" not in updated_text
        assert "[[OLDCONCEPT]]" not in updated_text

    def test_update_concept_ref_edit_type(self, tmp_path: Path) -> None:
        """UpdateConceptRef edit type replaces wikilinks (same as ReplaceWikilink)."""
        dependent_path = tmp_path / "concepts" / "dependent.md"
        _write_concept_file(dependent_path, "Dependent", "active")
        text = dependent_path.read_text(encoding="utf-8")
        text = text.replace(
            "Body text here.",
            "Has a ref to [[OldRef]] in body.",
        )
        dependent_path.write_text(text, encoding="utf-8")

        edits = [
            _make_migration_edit(
                artifact_path=str(dependent_path.relative_to(tmp_path)),
                edit_type=MigrationEditType.UpdateConceptRef,
                old_value="OldRef",
                new_value="NewRef",
            ),
        ]

        report = apply_migration_edits(edits, tmp_path)

        assert report.success_count == 1
        updated_text = dependent_path.read_text(encoding="utf-8")
        assert "[[NewRef]]" in updated_text
        assert "[[OldRef]]" not in updated_text

    def test_empty_edits_list(self, tmp_path: Path) -> None:
        """Empty edit list returns empty report with zero counts."""
        report = apply_migration_edits([], tmp_path)

        assert report.success_count == 0
        assert report.failure_count == 0
        assert report.outcomes == []

    def test_replace_wikilink_with_none_new_value_removes(self, tmp_path: Path) -> None:
        """ReplaceWikilink with None new_value degrades to remove."""
        dependent_path = tmp_path / "concepts" / "dependent.md"
        _write_concept_file(dependent_path, "Dependent", "active")
        text = dependent_path.read_text(encoding="utf-8")
        text = text.replace(
            "Body text here.",
            "References [[OldConcept]] here.",
        )
        dependent_path.write_text(text, encoding="utf-8")

        edits = [
            _make_migration_edit(
                artifact_path=str(dependent_path.relative_to(tmp_path)),
                edit_type=MigrationEditType.ReplaceWikilink,
                old_value="OldConcept",
                new_value=None,
            ),
        ]

        report = apply_migration_edits(edits, tmp_path)

        assert report.success_count == 1
        updated_text = dependent_path.read_text(encoding="utf-8")
        assert "[[OldConcept]]" not in updated_text
        assert "OldConcept" in updated_text


# ===========================================================================
# verify_migration tests
# ===========================================================================


class TestVerifyMigration:
    """Tests for ``verify_migration()``."""

    def test_no_remaining_references_success(self) -> None:
        """Empty reverse_deps after migration means full success.

        Task 13.5: reverse_deps returning empty after migration = success.
        """
        mock_graph = MagicMock()
        mock_graph.reverse_deps.return_value = []

        remaining = verify_migration("concepts/deprecated.md", mock_graph)

        assert remaining == []
        mock_graph.reverse_deps.assert_called_once_with("concepts/deprecated.md")

    def test_remaining_references_partial_migration(self) -> None:
        """Non-empty reverse_deps after migration means partial migration.

        Task 13.5: reverse_deps returning non-empty = partial migration.
        """
        mock_graph = MagicMock()
        mock_graph.reverse_deps.return_value = [
            _make_link_result("designs/still-referencing.md"),
            _make_link_result("concepts/still-referencing.md"),
        ]

        remaining = verify_migration("concepts/deprecated.md", mock_graph)

        assert len(remaining) == 2
        assert "concepts/still-referencing.md" in remaining
        assert "designs/still-referencing.md" in remaining

    def test_link_graph_none_returns_empty(self) -> None:
        """When link_graph is None, return empty list (cannot verify)."""
        remaining = verify_migration("concepts/deprecated.md", None)

        assert remaining == []

    def test_deduplicates_source_paths(self) -> None:
        """Duplicate source paths from different link types are deduplicated."""
        mock_graph = MagicMock()
        mock_graph.reverse_deps.return_value = [
            _make_link_result("designs/a.md", "wikilink"),
            _make_link_result("designs/a.md", "ast_import"),
        ]

        remaining = verify_migration("concepts/deprecated.md", mock_graph)

        assert remaining == ["designs/a.md"]

    def test_results_sorted(self) -> None:
        """Remaining paths are sorted alphabetically."""
        mock_graph = MagicMock()
        mock_graph.reverse_deps.return_value = [
            _make_link_result("z-file.md"),
            _make_link_result("a-file.md"),
            _make_link_result("m-file.md"),
        ]

        remaining = verify_migration("concepts/deprecated.md", mock_graph)

        assert remaining == ["a-file.md", "m-file.md", "z-file.md"]

    def test_logs_warning_on_remaining(self, caplog: pytest.LogCaptureFixture) -> None:
        """Warning is logged when remaining references exist."""
        mock_graph = MagicMock()
        mock_graph.reverse_deps.return_value = [
            _make_link_result("designs/still-ref.md"),
        ]

        verify_migration("concepts/deprecated.md", mock_graph)

        assert any(
            "still has" in record.message and "inbound reference" in record.message
            for record in caplog.records
        )

    def test_logs_success_on_empty(self, caplog: pytest.LogCaptureFixture) -> None:
        """Info is logged when no remaining references."""
        mock_graph = MagicMock()
        mock_graph.reverse_deps.return_value = []

        with caplog.at_level(logging.INFO, logger="lexibrary.curator.migration"):
            verify_migration("concepts/deprecated.md", mock_graph)

        assert any("no remaining inbound references" in record.message for record in caplog.records)


# ===========================================================================
# Fixture-based tests (Group 9 curator_library fixtures)
# ===========================================================================


class TestMigrationWithFixtures:
    """Fixture-backed tests exercising migration against realistic artifacts.

    Uses the ``curator_library_path`` fixture from Group 9 which provides:
    - CN-006 (Superseded Concept) with ``superseded_by: Authentication``
    - CN-001 (Authentication) as the active successor
    - Design files (formatting.py.md, helpers.py.md) referencing
      ``[[Superseded Concept]]``
    """

    def test_validate_successor_chain_fixture_cn006(
        self,
        curator_library_path: Path,
    ) -> None:
        """CN-006's successor (Authentication / CN-001) is active -- chain valid.

        Task 13.1: valid chain using fixture data.
        """
        successor_path = (
            curator_library_path / ".lexibrary" / "concepts" / "CN-001-authentication.md"
        )

        with patch(
            "lexibrary.curator.migration.Path.cwd",
            return_value=curator_library_path,
        ):
            valid, reason = validate_successor_chain(
                str(successor_path),
                link_graph=None,
            )

        assert valid is True
        assert reason == ""

    def test_apply_migration_edits_fixture_design_file(
        self,
        curator_library_path: Path,
    ) -> None:
        """Replace [[Superseded Concept]] with [[Authentication]] in fixture design files.

        Task 13.2: wikilinks replaced in real fixture design files.
        """
        # formatting.py.md references [[Superseded Concept]]
        design_rel = ".lexibrary/designs/src/utils/formatting.py.md"
        design_abs = curator_library_path / design_rel

        original_text = design_abs.read_text(encoding="utf-8")
        assert "[[Superseded Concept]]" in original_text

        edits = [
            _make_migration_edit(
                artifact_path=design_rel,
                edit_type=MigrationEditType.ReplaceWikilink,
                old_value="Superseded Concept",
                new_value="Authentication",
            ),
        ]

        report = apply_migration_edits(edits, curator_library_path)

        assert report.success_count == 1
        assert report.failure_count == 0

        updated_text = design_abs.read_text(encoding="utf-8")
        assert "[[Authentication]]" in updated_text
        assert "[[Superseded Concept]]" not in updated_text
        # Design files should have updated_by set to curator
        assert "updated_by: curator" in updated_text

    def test_apply_migration_edits_fixture_multiple_design_files(
        self,
        curator_library_path: Path,
    ) -> None:
        """Replace [[Superseded Concept]] in both formatting.py.md and helpers.py.md.

        Task 13.2: batch wikilink replacement across multiple fixture files.
        """
        formatting_rel = ".lexibrary/designs/src/utils/formatting.py.md"
        helpers_rel = ".lexibrary/designs/src/utils/helpers.py.md"

        edits = [
            _make_migration_edit(
                artifact_path=formatting_rel,
                edit_type=MigrationEditType.ReplaceWikilink,
                old_value="Superseded Concept",
                new_value="Authentication",
            ),
            _make_migration_edit(
                artifact_path=helpers_rel,
                edit_type=MigrationEditType.ReplaceWikilink,
                old_value="Superseded Concept",
                new_value="Authentication",
            ),
        ]

        report = apply_migration_edits(edits, curator_library_path)

        assert report.success_count == 2
        assert report.failure_count == 0

        for rel_path in (formatting_rel, helpers_rel):
            updated = (curator_library_path / rel_path).read_text(encoding="utf-8")
            assert "[[Authentication]]" in updated
            assert "[[Superseded Concept]]" not in updated

    def test_apply_migration_edits_fixture_remove_reference(
        self,
        curator_library_path: Path,
    ) -> None:
        """Remove [[Superseded Concept]] references (no successor) in fixture file.

        Task 13.3: references removed from design file.  Design files are
        processed via parse/serialize, which removes the entry from the
        wikilinks list entirely rather than leaving plain text inline.
        """
        helpers_rel = ".lexibrary/designs/src/utils/helpers.py.md"
        helpers_abs = curator_library_path / helpers_rel

        original_text = helpers_abs.read_text(encoding="utf-8")
        assert "[[Superseded Concept]]" in original_text

        edits = [
            _make_migration_edit(
                artifact_path=helpers_rel,
                edit_type=MigrationEditType.RemoveReference,
                old_value="Superseded Concept",
                new_value=None,
            ),
        ]

        report = apply_migration_edits(edits, curator_library_path)

        assert report.success_count == 1
        updated_text = helpers_abs.read_text(encoding="utf-8")
        assert "[[Superseded Concept]]" not in updated_text
        # Other wikilinks in the file should be preserved
        assert "[[NonexistentConcept]]" in updated_text
        assert "[[Authentcation]]" in updated_text

    def test_apply_migration_edits_fixture_mixed_success_failure(
        self,
        curator_library_path: Path,
    ) -> None:
        """Mix of valid fixture edits and one targeting non-existent file.

        Task 13.4: failure isolation with fixture data -- valid edits succeed,
        invalid edit fails, report tracks both.
        """
        formatting_rel = ".lexibrary/designs/src/utils/formatting.py.md"
        helpers_rel = ".lexibrary/designs/src/utils/helpers.py.md"

        edits = [
            _make_migration_edit(
                artifact_path=formatting_rel,
                edit_type=MigrationEditType.ReplaceWikilink,
                old_value="Superseded Concept",
                new_value="Authentication",
            ),
            _make_migration_edit(
                artifact_path=".lexibrary/concepts/DOES-NOT-EXIST.md",
                edit_type=MigrationEditType.ReplaceWikilink,
                old_value="Superseded Concept",
                new_value="Authentication",
            ),
            _make_migration_edit(
                artifact_path=helpers_rel,
                edit_type=MigrationEditType.ReplaceWikilink,
                old_value="Superseded Concept",
                new_value="Authentication",
            ),
        ]

        report = apply_migration_edits(edits, curator_library_path)

        assert report.success_count == 2
        assert report.failure_count == 1
        assert len(report.outcomes) == 3

        # The valid files were updated
        assert "[[Authentication]]" in (curator_library_path / formatting_rel).read_text(
            encoding="utf-8"
        )
        assert "[[Authentication]]" in (curator_library_path / helpers_rel).read_text(
            encoding="utf-8"
        )

        # Failure recorded with error message
        failures = [o for o in report.outcomes if not o.success]
        assert len(failures) == 1
        assert "DOES-NOT-EXIST" in failures[0].error

    def test_verify_migration_fixture_with_mock_graph(self) -> None:
        """Post-migration verification using mock graph returning empty (success).

        Task 13.5: verify_migration returns empty list when no remaining refs.
        """
        mock_graph = MagicMock()
        mock_graph.reverse_deps.return_value = []

        remaining = verify_migration(
            ".lexibrary/concepts/CN-006-superseded-concept.md",
            mock_graph,
        )

        assert remaining == []
        mock_graph.reverse_deps.assert_called_once_with(
            ".lexibrary/concepts/CN-006-superseded-concept.md",
        )

    def test_verify_migration_fixture_partial_with_mock_graph(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Post-migration verification with remaining references (partial migration).

        Task 13.5: verify_migration returns remaining paths and logs warning.
        """
        mock_graph = MagicMock()
        mock_graph.reverse_deps.return_value = [
            _make_link_result(".lexibrary/designs/src/utils/formatting.py.md"),
        ]

        remaining = verify_migration(
            ".lexibrary/concepts/CN-006-superseded-concept.md",
            mock_graph,
        )

        assert len(remaining) == 1
        assert ".lexibrary/designs/src/utils/formatting.py.md" in remaining

        assert any(
            "still has" in record.message and "inbound reference" in record.message
            for record in caplog.records
        )
