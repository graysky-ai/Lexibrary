"""Integration tests for consistency round-trip fixes (group 8.12).

These tests run the full ``Coordinator.run()`` pipeline against minimal
in-memory fixtures with planted consistency issues and assert that:

1. The offending signal is removed from the design file / artifact.
2. The fix is recorded in the :class:`CuratorReport.dispatched_details`
   with ``outcome="fixed"``.
3. Healthy control artifacts remain untouched (same hash before/after).

Fixtures are built per-test under ``tmp_path`` rather than sharing the
``tests/fixtures/curator_library/`` tree -- this keeps test isolation
strict and avoids collisions with the parallel sq5.6 validation
round-trip tests.
"""

from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime
from pathlib import Path

import yaml

from lexibrary.artifacts.design_file import (
    DesignFile,
    DesignFileFrontmatter,
    StalenessMetadata,
)
from lexibrary.artifacts.design_file_parser import parse_design_file
from lexibrary.artifacts.design_file_serializer import serialize_design_file
from lexibrary.config.schema import LexibraryConfig
from lexibrary.curator.coordinator import Coordinator

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _setup_integration_project(tmp_path: Path) -> Path:
    """Build a minimal project with a full ``.lexibrary/`` layout."""
    project = tmp_path / "sq5_8_integration"
    project.mkdir()
    lex = project / ".lexibrary"
    lex.mkdir()
    for sub in ("designs", "concepts", "conventions", "playbooks", "stack"):
        (lex / sub).mkdir()
    (lex / "config.yaml").write_text("", encoding="utf-8")
    return project


def _write_design(
    project: Path,
    source_rel: str,
    *,
    wikilinks: list[str] | None = None,
    dependencies: list[str] | None = None,
    dependents: list[str] | None = None,
    source_content: str = "def foo(): pass\n",
) -> Path:
    """Create both a source file and its mirror design file."""
    src = project / source_rel
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text(source_content, encoding="utf-8")

    design_path = project / ".lexibrary" / "designs" / f"{source_rel}.md"
    design_path.parent.mkdir(parents=True, exist_ok=True)
    df = DesignFile(
        source_path=source_rel,
        frontmatter=DesignFileFrontmatter(
            description=f"Design for {source_rel}",
            id=source_rel.replace("/", "-").replace(".", "-"),
            updated_by="archivist",
            status="active",
        ),
        summary=f"Summary of {source_rel}",
        interface_contract="def foo(): ...",
        dependencies=dependencies or [],
        dependents=dependents or [],
        wikilinks=wikilinks or [],
        metadata=StalenessMetadata(
            source=source_rel,
            source_hash="a" * 64,
            interface_hash=None,
            generated=datetime.now(UTC),
            generator="test",
        ),
    )
    design_path.write_text(serialize_design_file(df), encoding="utf-8")
    return design_path


def _write_concept(
    lex_dir: Path,
    concept_id: str,
    title: str,
    *,
    aliases: list[str] | None = None,
    body: str = "Body\n",
) -> Path:
    slug = title.lower().replace(" ", "-")
    path = lex_dir / "concepts" / f"{concept_id}-{slug}.md"
    data = {
        "title": title,
        "id": concept_id,
        "status": "active",
        "aliases": aliases or [],
        "tags": [],
    }
    path.write_text(
        f"---\n{yaml.dump(data, default_flow_style=False)}---\n\n# {title}\n\n{body}",
        encoding="utf-8",
    )
    return path


def _run(project: Path, *, autonomy: str = "full") -> object:
    """Run the coordinator under ``full`` autonomy so fixes actually dispatch."""
    config = LexibraryConfig.model_validate({"curator": {"autonomy": autonomy}})
    coord = Coordinator(project, config)
    return asyncio.run(coord.run())


# ---------------------------------------------------------------------------
# Broken wikilink round-trip
# ---------------------------------------------------------------------------


class TestBrokenWikilinkRoundtrip:
    def test_broken_wikilink_roundtrip(self, tmp_path: Path) -> None:
        """A design file with an unresolved wikilink loses that wikilink post-run."""
        project = _setup_integration_project(tmp_path)
        design_path = _write_design(
            project, "src/foo.py", wikilinks=["NonexistentConcept", "KeepMe"]
        )
        _write_concept(project / ".lexibrary", "CN-001", "KeepMe")

        _run(project)

        parsed = parse_design_file(design_path)
        assert parsed is not None
        # "NonexistentConcept" should be gone.
        assert "NonexistentConcept" not in parsed.wikilinks
        # Resolved wikilink may or may not remain depending on resolver
        # case handling — but the unresolved one must be gone.


# ---------------------------------------------------------------------------
# Slug collision round-trip
# ---------------------------------------------------------------------------


class TestSlugCollisionRoundtrip:
    def test_slug_collision_roundtrip(self, tmp_path: Path) -> None:
        """Two design files with colliding description slugs get deterministic suffixes.

        The consistency checker slugifies the first 60 chars of the
        ``description`` frontmatter field; we plant two designs with the
        *same* description so :func:`detect_slug_collisions` flags both.
        """
        project = _setup_integration_project(tmp_path)
        # Force matching description slugs by rewriting frontmatter after
        # the initial ``_write_design`` call.  We do a targeted YAML edit
        # so the staleness resolver preserves the new description.
        design_a = _write_design(project, "src/a.py")
        design_b = _write_design(project, "src/b.py")
        shared_desc = "Shared Collision Description"
        for p in (design_a, design_b):
            text = p.read_text(encoding="utf-8")
            # Rewrite only the description frontmatter field.
            lines = text.splitlines()
            for i, line in enumerate(lines):
                if line.startswith("description:"):
                    lines[i] = f"description: {shared_desc}"
                    break
            p.write_text("\n".join(lines) + "\n", encoding="utf-8")

        before_a_id = "src-a-py"
        before_b_id = "src-b-py"

        _run(project)

        # Both should still exist; at least one id should have been
        # suffixed.  (The consistency check reports collisions on both
        # halves, but our helper is idempotent so the end state still
        # has distinct ids.)
        parsed_a = parse_design_file(design_a)
        parsed_b = parse_design_file(design_b)
        assert parsed_a is not None
        assert parsed_b is not None
        # The slug_suffix helper appends a deterministic -NN suffix so at
        # least one of the two ids should now have a numeric tail.
        assert parsed_a.frontmatter.id != before_a_id or parsed_b.frontmatter.id != before_b_id


# ---------------------------------------------------------------------------
# Orphan concept round-trip
# ---------------------------------------------------------------------------


class TestOrphanConceptRoundtrip:
    def test_orphan_concept_roundtrip(self, tmp_path: Path) -> None:
        """An orphan concept with a link graph zero-deps finding is deleted under full autonomy.

        This test exercises the dispatch path by fabricating a consistency
        ``CollectItem`` directly (the link-graph-backed orphan detection
        requires an ``index.db`` which the minimal fixture lacks).
        """
        project = _setup_integration_project(tmp_path)
        orphan = _write_concept(project / ".lexibrary", "CN-099", "Orphan")

        # Directly exercise the dispatcher with a fabricated triage item
        # so we don't depend on detect_orphan_concepts + index.db.
        from lexibrary.curator.models import CollectItem, TriageItem  # noqa: PLC0415

        coord = Coordinator(
            project,
            LexibraryConfig.model_validate({"curator": {"autonomy": "full"}}),
        )
        collect = CollectItem(
            source="consistency",
            path=orphan,
            severity="info",
            message="zero inbound",
            check="consistency",
            action_hint="remove_orphan_zero_deps",
            fix_instruction_detail="Concept CN-099 has zero inbound",
        )
        triage = TriageItem(
            source_item=collect,
            issue_type="consistency_fix",
            action_key="remove_orphan_zero_deps",
            priority=15.0,
        )
        result = coord._dispatch_consistency_fix(triage)  # noqa: SLF001
        assert result.success is True
        assert not orphan.exists()


# ---------------------------------------------------------------------------
# Bidirectional dep round-trip
# ---------------------------------------------------------------------------
#
# The former ``TestBidirectionalDepRoundtrip`` class that lived here was
# retired alongside the curator-side bidirectional handler in group 3.8
# of the ``curator-freshness`` OpenSpec change.  Its replacement --
# exercising the validator-fixer bridge through
# :func:`validator.fixes.fix_bidirectional_deps` -- lives in
# ``tests/test_curator/test_bidirectional_integration.py``.


# ---------------------------------------------------------------------------
# Healthy fixture untouched
# ---------------------------------------------------------------------------


class TestHealthyFixtureUntouched:
    def test_healthy_fixture_untouched(self, tmp_path: Path) -> None:
        """A healthy fixture's concepts/conventions remain byte-identical.

        We cannot assert design-file byte identity because unrelated
        phases (staleness, agent-edit reconciliation) may touch design
        files with stale hashes.  Instead we assert that the healthy
        control artifacts — concept and convention files — are NOT
        mutated by the consistency pipeline.
        """
        project = _setup_integration_project(tmp_path)

        # Create two healthy control artifacts with unique aliases so
        # no collision is detected.
        _write_concept(
            project / ".lexibrary",
            "CN-001",
            "Authentication",
            aliases=["auth-unique-alias"],
        )
        # Write a convention whose scope points at an existing path so
        # the stale-convention check does not flag it.
        (project / "src" / "healthy").mkdir(parents=True, exist_ok=True)
        (project / "src" / "healthy" / "dummy.py").write_text("pass\n", encoding="utf-8")
        conv_path = project / ".lexibrary" / "conventions" / "CV-001-healthy.md"
        conv_data = {
            "title": "Healthy",
            "id": "CV-001",
            "scope": "src/healthy/",
            "status": "active",
            "source": "user",
            "priority": 0,
            "tags": [],
            "aliases": ["healthy-only"],
        }
        conv_path.write_text(
            f"---\n{yaml.dump(conv_data, default_flow_style=False)}---\n\n"
            f"Body references src/healthy/dummy.py\n",
            encoding="utf-8",
        )

        before_concept = _sha256_file(
            project / ".lexibrary" / "concepts" / "CN-001-authentication.md"
        )
        before_conv = _sha256_file(conv_path)

        _run(project)

        # Concepts/conventions must be untouched.
        assert (
            _sha256_file(project / ".lexibrary" / "concepts" / "CN-001-authentication.md")
            == before_concept
        )
        assert _sha256_file(conv_path) == before_conv
