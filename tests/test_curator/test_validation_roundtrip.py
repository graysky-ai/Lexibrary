"""Integration tests for the validation bridge round-trip.

Each test builds a minimal self-contained library fixture in ``tmp_path``
with exactly one planted validation issue, runs the full curator pipeline
with ``check=...`` filtering, and asserts that re-running
``validate_library()`` no longer reports the planted issue.

These tests are the end-to-end counterpart to the unit tests in
``test_validation_fixers.py``.  Where the unit tests monkeypatch the
``FIXERS`` registry, these tests run the real fixers (except for
``fix_hash_freshness``, whose underlying ``update_file`` call requires a
BAML/LLM sub-agent — that sub-agent is replaced with a deterministic
stand-in that refreshes the footer hashes in place).

All fixtures are built fresh per test inside ``tmp_path`` rather than
extending the shared ``tests/fixtures/curator_library/`` tree.  This
avoids collisions with concurrent bead work that also touches the shared
fixture, and keeps each roundtrip test fully isolated so assertions about
which issues are present are not clouded by unrelated planted issues.
"""

from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from lexibrary.artifacts.design_file import (
    DesignFile,
    DesignFileFrontmatter,
    StalenessMetadata,
)
from lexibrary.artifacts.design_file_serializer import serialize_design_file
from lexibrary.config.schema import LexibraryConfig
from lexibrary.curator.coordinator import Coordinator
from lexibrary.validator import validate_library
from lexibrary.validator.fixes import FIXERS
from lexibrary.validator.report import ValidationIssue, ValidationReport

# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _write_design_file(
    project_root: Path,
    source_rel: str,
    *,
    source_hash: str,
    interface_hash: str | None = None,
    updated_by: str = "archivist",
    status: str = "active",
    deprecated_at: datetime | None = None,
    deprecated_reason: str | None = None,
    description: str = "Test design file",
) -> Path:
    """Write a design file for *source_rel* and return its absolute path.

    The design file is placed at
    ``<project_root>/.lexibrary/designs/<source_rel>.md`` to mirror the
    production layout.  Callers control the stored ``source_hash`` so
    tests can plant mismatches for ``hash_freshness``.
    """

    design_path = project_root / ".lexibrary" / "designs" / (source_rel + ".md")
    design_path.parent.mkdir(parents=True, exist_ok=True)

    frontmatter_kwargs: dict[str, Any] = {
        "description": description,
        "id": source_rel.replace("/", "-").replace(".", "-"),
        "updated_by": updated_by,
        "status": status,
    }
    if deprecated_at is not None:
        frontmatter_kwargs["deprecated_at"] = deprecated_at
    if deprecated_reason is not None:
        frontmatter_kwargs["deprecated_reason"] = deprecated_reason

    design = DesignFile(
        source_path=source_rel,
        frontmatter=DesignFileFrontmatter(**frontmatter_kwargs),
        summary="",
        interface_contract='"""Placeholder."""',
        dependencies=[],
        dependents=[],
        metadata=StalenessMetadata(
            source=source_rel,
            source_hash=source_hash,
            interface_hash=interface_hash,
            generated=datetime.now(UTC).replace(tzinfo=None),
            generator="lexibrary-v2-test",
        ),
    )
    design_path.write_text(serialize_design_file(design), encoding="utf-8")
    return design_path


def _write_source_file(project_root: Path, rel_path: str, content: str) -> Path:
    """Write a source file under *project_root* and return its absolute path."""

    abs_path = project_root / rel_path
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_text(content, encoding="utf-8")
    return abs_path


def _write_aindex(project_root: Path, source_rel_dir: str, body: str = "# Test aindex") -> Path:
    """Write a ``.aindex`` file at the mirrored design path."""

    aindex_path = project_root / ".lexibrary" / "designs" / source_rel_dir / ".aindex"
    aindex_path.parent.mkdir(parents=True, exist_ok=True)
    aindex_path.write_text(body + "\n", encoding="utf-8")
    return aindex_path


def _write_config(project_root: Path, body: str | None = None) -> Path:
    """Write a minimal ``.lexibrary/config.yaml`` so ``load_config`` succeeds."""

    config_path = project_root / ".lexibrary" / "config.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if body is None:
        body = "project:\n  name: roundtrip-test\n  type: application\n  source_roots:\n    - src\n"
    config_path.write_text(body, encoding="utf-8")
    return config_path


def _build_minimal_library(tmp_path: Path, *, name: str = "project") -> Path:
    """Create a minimal library root under *tmp_path* and return the path."""

    project = tmp_path / name
    project.mkdir()
    (project / ".lexibrary").mkdir()
    (project / ".lexibrary" / "designs").mkdir()
    _write_config(project)
    return project


def _sha256_of_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _snapshot_all_files(project_root: Path) -> dict[Path, str]:
    """Return a ``{path: sha256}`` snapshot of every file in *project_root*.

    Used by ``test_fixers_dont_touch_unrelated_files`` to assert that
    unrelated fixture files are not mutated as a side effect of a single
    fixer run.  Walks the entire tree — including ``.lexibrary/`` — so
    curator write contracts that leak into adjacent files are detected.
    """

    snapshot: dict[Path, str] = {}
    for path in sorted(project_root.rglob("*")):
        if path.is_file():
            try:
                snapshot[path.relative_to(project_root)] = _sha256_of_file(path)
            except OSError:
                continue
    return snapshot


def _run_coordinator(
    project_root: Path,
    *,
    check: str | None = None,
    autonomy: str = "auto_low",
) -> Any:
    """Run the coordinator pipeline synchronously for the given library.

    ``consistency_collect`` is explicitly set to ``"off"`` so the Phase 3
    consistency checker (wired up by the parallel bead ``lexibrary-sq5.8``)
    never runs against these round-trip fixtures.  The validation bridge
    is the sole subject of these tests — isolating it from the consistency
    surface keeps each round-trip assertion focused on a single fixer.
    """

    config = LexibraryConfig.model_validate(
        {
            "curator": {
                "autonomy": autonomy,
                "consistency_collect": "off",
            }
        }
    )
    coord = Coordinator(project_root, config)
    return asyncio.run(coord.run(check=check))


def _filter_issues(report: ValidationReport, check: str) -> list[ValidationIssue]:
    return [issue for issue in report.issues if issue.check == check]


# ---------------------------------------------------------------------------
# Helpers to disable the archivist LLM pipeline for hash_freshness
# ---------------------------------------------------------------------------


@pytest.fixture()
def deterministic_hash_freshness(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the archivist pipeline call used by ``fix_hash_freshness``.

    ``fix_hash_freshness`` normally invokes ``archivist.pipeline.update_file``,
    which requires a BAML runtime to regenerate the design body via LLM.
    Round-trip tests cannot depend on a live LLM, so this fixture swaps
    the pipeline call for a deterministic stand-in that simply refreshes
    the footer hashes of the existing design file in place.

    The stand-in matches ``update_file``'s return contract
    (``FileResult``) closely enough for the fixer to read ``result.failed``
    and ``result.change``.
    """

    from lexibrary.archivist import pipeline as archivist_pipeline
    from lexibrary.archivist.change_checker import ChangeLevel
    from lexibrary.archivist.pipeline import FileResult, _refresh_footer_hashes
    from lexibrary.ast_parser import compute_hashes
    from lexibrary.utils.paths import mirror_path

    async def deterministic_update_file(
        source_path: Path,
        project_root: Path,
        config: Any,
        archivist: Any,
        available_artifacts: list[str] | None = None,
        *,
        force: bool = False,
        unlimited: bool = False,
    ) -> FileResult:
        design_path = mirror_path(project_root, source_path)
        if not design_path.exists():
            return FileResult(
                change=ChangeLevel.UNCHANGED,
                failed=True,
                failure_reason="design file missing",
            )
        content_hash, interface_hash = compute_hashes(source_path)
        _refresh_footer_hashes(design_path, content_hash, interface_hash, project_root)
        return FileResult(change=ChangeLevel.CONTENT_ONLY)

    monkeypatch.setattr(archivist_pipeline, "update_file", deterministic_update_file)
    # ``fix_hash_freshness`` imports ``update_file`` inside the function
    # body from ``lexibrary.archivist.pipeline``.  Patching the attribute
    # on the module itself is therefore sufficient.


# ---------------------------------------------------------------------------
# Individual round-trip tests
# ---------------------------------------------------------------------------


class TestHashFreshnessRoundtrip:
    """A stale ``source_hash`` is cleared after running the coordinator."""

    def test_hash_freshness_roundtrip(
        self,
        tmp_path: Path,
        deterministic_hash_freshness: None,
    ) -> None:
        project = _build_minimal_library(tmp_path, name="hash-freshness")
        source = _write_source_file(
            project,
            "src/utils/helpers.py",
            '"""Helpers."""\n\n\ndef slugify(text: str) -> str:\n    return text\n',
        )
        _write_design_file(
            project,
            "src/utils/helpers.py",
            source_hash="deadbeef" * 8,  # deliberately wrong
        )

        before = validate_library(project, project / ".lexibrary")
        stale_before = _filter_issues(before, "hash_freshness")
        assert len(stale_before) == 1, "expected planted hash_freshness issue"

        report = _run_coordinator(project, check="hash_freshness")
        assert report.checked >= 1

        after = validate_library(project, project / ".lexibrary")
        stale_after = _filter_issues(after, "hash_freshness")
        assert stale_after == [], (
            f"hash_freshness should be fixed, got: {[i.artifact for i in stale_after]}"
        )

        # Sanity — the design footer should now carry the real SHA-256.
        design_path = project / ".lexibrary" / "designs" / "src/utils/helpers.py.md"
        design_text = design_path.read_text(encoding="utf-8")
        assert _sha256_of_file(source)[:16] in design_text


class TestOrphanedAindexRoundtrip:
    """An orphaned ``.aindex`` is deleted and its parent dir cleaned up."""

    def test_orphaned_aindex_roundtrip(self, tmp_path: Path) -> None:
        project = _build_minimal_library(tmp_path, name="orphaned-aindex")
        # Create a source directory so aindex_coverage doesn't flood the report
        _write_source_file(project, "src/auth/login.py", '"""Login."""\n')
        _write_aindex(project, "src/auth")

        # Orphan: the source directory for this aindex does NOT exist.
        _write_aindex(project, "src/deleted")

        before = validate_library(project, project / ".lexibrary")
        orphan_before = _filter_issues(before, "orphaned_aindex")
        assert len(orphan_before) == 1
        assert "deleted" in orphan_before[0].artifact

        _run_coordinator(project, check="orphaned_aindex")

        after = validate_library(project, project / ".lexibrary")
        orphan_after = _filter_issues(after, "orphaned_aindex")
        assert orphan_after == []

        # The orphan aindex and its empty parent directory are gone.
        orphan_path = project / ".lexibrary" / "designs" / "src" / "deleted"
        assert not orphan_path.exists()
        # The healthy aindex is untouched.
        assert (project / ".lexibrary" / "designs" / "src" / "auth" / ".aindex").exists()


class TestAindexCoverageRoundtrip:
    """A directory without a ``.aindex`` gets one after the fixer runs."""

    def test_aindex_coverage_roundtrip(self, tmp_path: Path) -> None:
        project = _build_minimal_library(tmp_path, name="aindex-coverage")
        _write_source_file(project, "src/auth/login.py", '"""Login."""\n')

        before = validate_library(project, project / ".lexibrary")
        missing_before = _filter_issues(before, "aindex_coverage")
        before_dirs = {issue.artifact for issue in missing_before}
        # Every walked directory (at least project root and src/auth) is missing a .aindex.
        assert "src/auth" in before_dirs, f"expected src/auth in missing: {before_dirs}"

        _run_coordinator(project, check="aindex_coverage")

        after = validate_library(project, project / ".lexibrary")
        missing_after = _filter_issues(after, "aindex_coverage")
        after_dirs = {issue.artifact for issue in missing_after}
        assert "src/auth" not in after_dirs, (
            f"src/auth still missing after fixer, remaining: {after_dirs}"
        )

        # A concrete .aindex file now exists at the expected path.
        aindex_path = project / ".lexibrary" / "designs" / "src" / "auth" / ".aindex"
        assert aindex_path.exists()


class TestOrphanedDesignsRoundtrip:
    """A design file whose source is missing is rewritten with deprecation status.

    ``fix_orphaned_designs`` is Medium risk and only runs under
    ``autonomy="full"``.  Without git history in ``tmp_path``,
    ``_is_committed_deletion`` returns True (no tracked file), so the
    fixer takes the ``deprecate_design`` branch rather than
    ``mark_unlinked``.
    """

    def test_orphaned_designs_roundtrip(self, tmp_path: Path) -> None:
        project = _build_minimal_library(tmp_path, name="orphaned-designs")
        # Write a design file WITHOUT its backing source.
        design_path = _write_design_file(
            project,
            "src/removed/gone.py",
            source_hash="feedface" * 8,
        )

        before = validate_library(project, project / ".lexibrary")
        orphan_before = _filter_issues(before, "orphaned_designs")
        assert len(orphan_before) == 1

        report = _run_coordinator(project, check="orphaned_designs", autonomy="full")
        assert report.checked >= 1

        after = validate_library(project, project / ".lexibrary")
        orphan_after = _filter_issues(after, "orphaned_designs")
        # ``orphaned_designs`` skips files already marked deprecated, so after
        # the fixer runs the check returns zero issues for this artifact.
        assert orphan_after == []

        # The design file still exists but is now marked deprecated.
        assert design_path.exists()
        design_text = design_path.read_text(encoding="utf-8")
        assert "status: deprecated" in design_text
        assert "deprecated_at:" in design_text


class TestDeprecatedTtlRoundtrip:
    """An expired deprecated design file is hard-deleted."""

    def test_deprecated_ttl_roundtrip(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from lexibrary.ast_parser import compute_hashes  # noqa: PLC0415

        project = _build_minimal_library(tmp_path, name="deprecated-ttl")
        source_path = _write_source_file(project, "src/stale/mod.py", '"""Mod."""\n')
        # Use the CURRENT source hash so the staleness collector does not
        # also fire on this file.  Under the two-pass flow introduced in
        # group 5, hash-pass staleness regeneration runs BEFORE graph-pass
        # validation; if both signals fire, regeneration would overwrite
        # ``status: deprecated`` to ``status: active`` and the
        # ``deprecated_ttl`` validator check would no longer detect the
        # file by the time graph-pass runs.
        source_hash, _interface_hash = compute_hashes(source_path)

        design_path = _write_design_file(
            project,
            "src/stale/mod.py",
            source_hash=source_hash,
            status="deprecated",
            deprecated_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(days=365),
            deprecated_reason="source_deleted",
        )

        # Force both the validator's check and the fixer's re-check to
        # treat TTL as expired — there is no git history in tmp_path.
        def _always_expired(
            design_path_arg: Path,
            project_root_arg: Path,
            ttl_commits_arg: int,
        ) -> bool:
            return True

        monkeypatch.setattr(
            "lexibrary.validator.checks.check_ttl_expiry",
            _always_expired,
        )
        monkeypatch.setattr(
            "lexibrary.lifecycle.deprecation.check_ttl_expiry",
            _always_expired,
        )

        before = validate_library(project, project / ".lexibrary")
        expired_before = _filter_issues(before, "deprecated_ttl")
        assert len(expired_before) == 1

        _run_coordinator(project, check="deprecated_ttl")

        after = validate_library(project, project / ".lexibrary")
        expired_after = _filter_issues(after, "deprecated_ttl")
        assert expired_after == []

        # The expired design file has been hard-deleted.
        assert not design_path.exists()


# ---------------------------------------------------------------------------
# Defensive tests — checks without a fixer, and non-target file isolation
# ---------------------------------------------------------------------------


class TestUnfixableCheckRemains:
    """A triage item whose check has no fixer returns ``no_fixer_registered``."""

    def test_unfixable_check_remains(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        project = _build_minimal_library(tmp_path, name="unfixable")
        _write_source_file(project, "src/helpers.py", '"""Helpers."""\n')

        # ``wikilink_resolution`` has no registered fixer (it is not in FIXERS).
        # We synthesise a planted issue by patching the check to return one
        # deterministic issue, then verifying the curator surfaces a
        # ``no_fixer_registered:`` message in ``dispatched_details``.
        planted = ValidationIssue(
            severity="error",
            check="wikilink_resolution",
            message="broken wikilink to [[Nowhere]]",
            artifact="src/helpers.py",
        )

        def _return_planted(project_root: Path, lexibrary_dir: Path) -> list[ValidationIssue]:
            return [planted]

        monkeypatch.setattr(
            "lexibrary.validator.checks.check_wikilink_resolution",
            _return_planted,
        )
        monkeypatch.setitem(
            __import__("lexibrary.validator", fromlist=["AVAILABLE_CHECKS"]).AVAILABLE_CHECKS,
            "wikilink_resolution",
            (_return_planted, "error"),
        )

        # Sanity: the check is NOT in FIXERS.
        assert "wikilink_resolution" not in FIXERS

        report = _run_coordinator(project, check="wikilink_resolution")

        # The issue still exists (nothing fixed it).
        after = validate_library(project, project / ".lexibrary")
        assert any(issue.check == "wikilink_resolution" for issue in after.issues)

        # The dispatched_details list records the no_fixer_registered message.
        messages = [str(entry.get("message", "")) for entry in report.dispatched_details]
        assert any("no_fixer_registered:" in msg for msg in messages), (
            f"expected no_fixer_registered message, got: {messages}"
        )
        # And the fixer bridge reports outcome=no_fixer, so it is NOT counted as fixed.
        no_fixer_entries = [
            entry for entry in report.dispatched_details if entry.get("outcome") == "no_fixer"
        ]
        assert len(no_fixer_entries) == 1
        assert no_fixer_entries[0]["success"] is False


class TestFixersDontTouchUnrelatedFiles:
    """Running a single fixer must not mutate unrelated fixture files."""

    def test_fixers_dont_touch_unrelated_files(self, tmp_path: Path) -> None:
        project = _build_minimal_library(tmp_path, name="isolation")

        # Seed several unrelated files that the fixer has no reason to touch.
        _write_source_file(project, "src/auth/login.py", '"""Login."""\n')
        _write_source_file(project, "src/auth/session.py", '"""Session."""\n')
        _write_source_file(project, "src/utils/helpers.py", '"""Helpers."""\n')
        _write_aindex(project, "src/auth", body="# auth aindex (control)")
        _write_aindex(project, "src/utils", body="# utils aindex (control)")

        # Plant the single target: an orphaned .aindex under src/deleted.
        _write_aindex(project, "src/deleted", body="# orphan aindex")

        snapshot_before = _snapshot_all_files(project)

        _run_coordinator(project, check="orphaned_aindex")

        snapshot_after = _snapshot_all_files(project)

        # Identify files that changed.
        changed = {
            path
            for path in snapshot_before
            if path in snapshot_after and snapshot_before[path] != snapshot_after[path]
        }
        removed = set(snapshot_before) - set(snapshot_after)
        added = set(snapshot_after) - set(snapshot_before)

        # The only expected change is the deletion of the orphan aindex and
        # its empty parent directory's on-disk removal.  No file should have
        # been mutated, and no new file should have been created.
        expected_removed = {Path(".lexibrary/designs/src/deleted/.aindex")}
        assert removed == expected_removed, f"unexpected removals: {removed}"
        assert changed == set(), f"unexpected content changes: {changed}"
        # Curator may write a JSON report under .lexibrary/curator/reports/;
        # that is an allowable addition — confirm nothing else appeared.
        unexpected_additions = {
            p
            for p in added
            if not str(p).startswith(".lexibrary/curator/reports/")
            and not str(p).startswith(".lexibrary/curator/.curator.lock")
        }
        assert unexpected_additions == set(), f"unexpected additions: {unexpected_additions}"
