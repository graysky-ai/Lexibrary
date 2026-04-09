"""Tests for the curator consistency checker.

Covers: wikilink hygiene, identifier normalisation, bidirectional
dependency repair, orphaned .aindex cleanup, orphaned .comments.yaml
detection, orphan concept detection, convention/playbook staleness
detection, and blocked IWH promotion.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

from lexibrary.artifacts.design_file import (
    DesignFile,
    DesignFileFrontmatter,
    StalenessMetadata,
)
from lexibrary.artifacts.design_file_serializer import serialize_design_file
from lexibrary.curator.consistency import (
    ConsistencyChecker,
)
from lexibrary.wiki.resolver import UnresolvedLink, WikilinkResolver

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_project(tmp_path: Path) -> tuple[Path, Path]:
    """Create a minimal project with .lexibrary structure.

    Returns (project_root, lexibrary_dir).
    """
    project = tmp_path / "project"
    project.mkdir()
    lex_dir = project / ".lexibrary"
    lex_dir.mkdir()
    (lex_dir / "designs").mkdir()
    (lex_dir / "concepts").mkdir()
    (lex_dir / "conventions").mkdir()
    (lex_dir / "playbooks").mkdir()
    (lex_dir / "stack").mkdir()
    return project, lex_dir


def _make_design_file(
    project: Path,
    source_rel: str,
    *,
    source_hash: str = "abc123",
    interface_hash: str | None = None,
    updated_by: str = "archivist",
    wikilinks: list[str] | None = None,
    dependencies: list[str] | None = None,
    dependents: list[str] | None = None,
) -> Path:
    """Create a design file in the .lexibrary/designs/ mirror."""
    design_path = project / ".lexibrary" / "designs" / (source_rel + ".md")
    design_path.parent.mkdir(parents=True, exist_ok=True)

    df = DesignFile(
        source_path=source_rel,
        frontmatter=DesignFileFrontmatter(
            description=f"Design for {source_rel}",
            id=source_rel.replace("/", "-").replace(".", "-"),
            updated_by=updated_by,
            status="active",
        ),
        summary=f"Summary of {source_rel}",
        interface_contract="def foo(): ...",
        dependencies=dependencies or [],
        dependents=dependents or [],
        wikilinks=wikilinks or [],
        metadata=StalenessMetadata(
            source=source_rel,
            source_hash=source_hash,
            interface_hash=interface_hash,
            generated=datetime.now(UTC),
            generator="test",
        ),
    )
    content = serialize_design_file(df)
    design_path.write_text(content, encoding="utf-8")
    return design_path


def _make_concept_file(
    lex_dir: Path,
    concept_id: str,
    title: str,
    *,
    aliases: list[str] | None = None,
) -> Path:
    """Create a minimal concept file."""
    from lexibrary.artifacts.slugs import slugify  # noqa: PLC0415

    slug = slugify(title)
    path = lex_dir / "concepts" / f"{concept_id}-{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    fm = {
        "title": title,
        "id": concept_id,
        "status": "active",
        "aliases": aliases or [],
        "tags": [],
    }
    content = f"---\n{yaml.dump(fm, default_flow_style=False)}---\n\n# {title}\n\nDescription.\n"
    path.write_text(content, encoding="utf-8")
    return path


def _make_convention_file(
    lex_dir: Path,
    conv_id: str,
    title: str,
    *,
    scope: str = "project",
    body: str = "",
    aliases: list[str] | None = None,
) -> Path:
    """Create a minimal convention file."""
    from lexibrary.artifacts.slugs import slugify  # noqa: PLC0415

    slug = slugify(title)
    path = lex_dir / "conventions" / f"{conv_id}-{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    fm = {
        "title": title,
        "id": conv_id,
        "scope": scope,
        "status": "active",
        "source": "user",
        "priority": 0,
        "tags": [],
        "aliases": aliases or [],
    }
    text = f"---\n{yaml.dump(fm, default_flow_style=False)}---\n\n{body}\n"
    path.write_text(text, encoding="utf-8")
    return path


def _make_playbook_file(
    lex_dir: Path,
    pb_id: str,
    title: str,
    *,
    body: str = "",
) -> Path:
    """Create a minimal playbook file."""
    from lexibrary.artifacts.slugs import slugify  # noqa: PLC0415

    slug = slugify(title)
    path = lex_dir / "playbooks" / f"{pb_id}-{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    fm = {
        "title": title,
        "id": pb_id,
        "status": "active",
        "aliases": [],
        "tags": [],
        "triggers": [],
    }
    text = f"---\n{yaml.dump(fm, default_flow_style=False)}---\n\n{body}\n"
    path.write_text(text, encoding="utf-8")
    return path


def _make_iwh_file(
    lex_dir: Path,
    rel_dir: str,
    *,
    scope: str = "blocked",
    body: str = "test iwh",
    hours_ago: int = 100,
) -> Path:
    """Create an IWH signal file."""
    mirror_dir = lex_dir / rel_dir
    mirror_dir.mkdir(parents=True, exist_ok=True)
    iwh_path = mirror_dir / ".iwh"
    created = datetime.now(UTC) - timedelta(hours=hours_ago)
    content = (
        f"---\nauthor: test-agent\ncreated: {created.isoformat()}\nscope: {scope}\n---\n{body}\n"
    )
    iwh_path.write_text(content, encoding="utf-8")
    return iwh_path


def _build_resolver(lex_dir: Path) -> WikilinkResolver:
    """Build a WikilinkResolver that resolves based on concept files present."""
    from lexibrary.wiki.index import ConceptIndex  # noqa: PLC0415
    from lexibrary.wiki.resolver import WikilinkResolver  # noqa: PLC0415

    concept_index = ConceptIndex.load(lex_dir / "concepts")

    resolver = WikilinkResolver(
        index=concept_index,
        convention_dir=lex_dir / "conventions",
        playbook_dir=lex_dir / "playbooks",
        designs_dir=lex_dir / "designs",
    )
    return resolver


# ---------------------------------------------------------------------------
# Wikilink Hygiene
# ---------------------------------------------------------------------------


class TestWikilinkHygiene:
    """Test wikilink checking in design files."""

    def test_broken_wikilink_stripped(self, tmp_path: Path) -> None:
        """A wikilink that cannot be resolved should produce a strip instruction."""
        project, lex_dir = _setup_project(tmp_path)
        design_path = _make_design_file(project, "src/foo.py", wikilinks=["NonexistentConcept"])
        resolver = _build_resolver(lex_dir)
        checker = ConsistencyChecker(project, lex_dir, resolver=resolver)

        instructions = checker.check_wikilinks(design_path)
        assert len(instructions) >= 1
        strip_instr = [i for i in instructions if i.action == "strip_unresolved_wikilink"]
        assert len(strip_instr) == 1
        assert "NonexistentConcept" in strip_instr[0].detail

    def test_valid_wikilink_untouched(self, tmp_path: Path) -> None:
        """A wikilink that resolves should NOT produce any instruction."""
        project, lex_dir = _setup_project(tmp_path)
        _make_concept_file(lex_dir, "CN-001", "Authentication")
        design_path = _make_design_file(project, "src/foo.py", wikilinks=["Authentication"])
        resolver = _build_resolver(lex_dir)
        checker = ConsistencyChecker(project, lex_dir, resolver=resolver)

        instructions = checker.check_wikilinks(design_path)
        assert len(instructions) == 0

    def test_fuzzy_match_detected(self, tmp_path: Path) -> None:
        """A wikilink with a fuzzy match should produce a fix instruction.

        The WikilinkResolver auto-resolves fuzzy matches against concepts.
        To test the fuzzy-suggestion path in the consistency checker, we
        mock the resolver to return an UnresolvedLink with suggestions.
        """
        project, lex_dir = _setup_project(tmp_path)
        design_path = _make_design_file(project, "src/foo.py", wikilinks=["Authentcation"])

        # Mock the resolver to return an UnresolvedLink with suggestions
        mock_resolver = MagicMock(spec=WikilinkResolver)
        mock_resolver.resolve.return_value = UnresolvedLink(
            raw="[[Authentcation]]",
            suggestions=["Authentication"],
        )

        checker = ConsistencyChecker(project, lex_dir, resolver=mock_resolver)
        instructions = checker.check_wikilinks(design_path)

        assert len(instructions) == 1
        assert instructions[0].action == "fix_broken_wikilink_fuzzy"
        assert "suggestions" in instructions[0].detail
        assert "Authentication" in instructions[0].detail

    def test_no_resolver_returns_empty(self, tmp_path: Path) -> None:
        """When no resolver is provided, wikilink checks return empty."""
        project, lex_dir = _setup_project(tmp_path)
        design_path = _make_design_file(project, "src/foo.py", wikilinks=["Anything"])
        checker = ConsistencyChecker(project, lex_dir, resolver=None)

        instructions = checker.check_wikilinks(design_path)
        assert instructions == []


class TestDomainTermDetection:
    """Test domain term detection across design files."""

    def test_domain_term_in_3_plus_files_suggested(self, tmp_path: Path) -> None:
        """A term in 3+ files without a concept should be flagged."""
        project, lex_dir = _setup_project(tmp_path)
        paths = []
        for i in range(3):
            p = _make_design_file(project, f"src/mod{i}.py", wikilinks=["UnmappedTerm"])
            paths.append(p)
        resolver = _build_resolver(lex_dir)
        checker = ConsistencyChecker(project, lex_dir, resolver=resolver)

        suggestions = checker.detect_domain_terms(paths, threshold=3)
        assert len(suggestions) >= 1
        assert suggestions[0].action == "suggest_new_concept"
        assert suggestions[0].risk == "medium"

    def test_domain_term_below_threshold_not_flagged(self, tmp_path: Path) -> None:
        """A term in fewer than threshold files should not be flagged."""
        project, lex_dir = _setup_project(tmp_path)
        paths = []
        for i in range(2):
            p = _make_design_file(project, f"src/mod{i}.py", wikilinks=["RareTerm"])
            paths.append(p)
        resolver = _build_resolver(lex_dir)
        checker = ConsistencyChecker(project, lex_dir, resolver=resolver)

        suggestions = checker.detect_domain_terms(paths, threshold=3)
        assert len(suggestions) == 0


# ---------------------------------------------------------------------------
# Identifier Normalisation
# ---------------------------------------------------------------------------


class TestAliasCollisions:
    """Test alias collision detection."""

    def test_shared_alias_detected(self, tmp_path: Path) -> None:
        """Two artifacts sharing an alias should be flagged."""
        project, lex_dir = _setup_project(tmp_path)
        _make_concept_file(lex_dir, "CN-001", "Authentication", aliases=["auth"])
        _make_convention_file(lex_dir, "CV-001", "Auth Convention", aliases=["auth"])

        checker = ConsistencyChecker(project, lex_dir)
        instructions = checker.detect_alias_collisions(
            lex_dir / "concepts", lex_dir / "conventions"
        )
        assert len(instructions) >= 2
        assert all(i.action == "resolve_alias_collision" for i in instructions)

    def test_no_collision_no_instruction(self, tmp_path: Path) -> None:
        """When aliases are unique, no instruction should be returned."""
        project, lex_dir = _setup_project(tmp_path)
        _make_concept_file(lex_dir, "CN-001", "Authentication", aliases=["auth"])
        _make_convention_file(lex_dir, "CV-001", "Convention", aliases=["conv"])

        checker = ConsistencyChecker(project, lex_dir)
        instructions = checker.detect_alias_collisions(
            lex_dir / "concepts", lex_dir / "conventions"
        )
        assert len(instructions) == 0


# ---------------------------------------------------------------------------
# Bidirectional Dependency Repair
# ---------------------------------------------------------------------------


class TestBidirectionalDeps:
    """Test bidirectional dependency detection."""

    def test_missing_reverse_dep_detected(self, tmp_path: Path) -> None:
        """If A depends on B, B should list A as a dependent."""
        project, lex_dir = _setup_project(tmp_path)
        # A depends on B
        a_path = _make_design_file(
            project,
            "src/a.py",
            dependencies=["src/b.py"],
            dependents=[],
        )
        # B does NOT list A as dependent
        b_path = _make_design_file(
            project,
            "src/b.py",
            dependencies=[],
            dependents=[],
        )

        checker = ConsistencyChecker(project, lex_dir)
        instructions = checker.check_bidirectional_deps([a_path, b_path])
        assert len(instructions) >= 1
        add_instr = [i for i in instructions if i.action == "add_missing_bidirectional_dep"]
        assert len(add_instr) == 1
        assert "src/a.py" in add_instr[0].detail
        assert "src/b.py" in add_instr[0].detail

    def test_correct_bidirectional_no_instruction(self, tmp_path: Path) -> None:
        """When deps are bidirectional, no instruction should be produced."""
        project, lex_dir = _setup_project(tmp_path)
        a_path = _make_design_file(
            project,
            "src/a.py",
            dependencies=["src/b.py"],
            dependents=[],
        )
        b_path = _make_design_file(
            project,
            "src/b.py",
            dependencies=[],
            dependents=["src/a.py"],
        )

        checker = ConsistencyChecker(project, lex_dir)
        instructions = checker.check_bidirectional_deps([a_path, b_path])
        assert len(instructions) == 0

    def test_resulting_fix_produces_valid_file(self, tmp_path: Path) -> None:
        """The fix instruction should reference a valid design file."""
        project, lex_dir = _setup_project(tmp_path)
        a_path = _make_design_file(
            project,
            "src/a.py",
            dependencies=["src/b.py"],
        )
        b_path = _make_design_file(
            project,
            "src/b.py",
            dependencies=[],
            dependents=[],
        )

        checker = ConsistencyChecker(project, lex_dir)
        instructions = checker.check_bidirectional_deps([a_path, b_path])
        # The instruction target should be the file that needs editing (B)
        assert instructions[0].target_path == b_path


# ---------------------------------------------------------------------------
# Orphaned .aindex Cleanup
# ---------------------------------------------------------------------------


class TestOrphanedAindex:
    """Test orphaned .aindex detection and cleanup."""

    def test_orphaned_aindex_detected(self, tmp_path: Path) -> None:
        """An .aindex for a deleted source directory should be flagged."""
        project, lex_dir = _setup_project(tmp_path)
        # Create .aindex mirror but NO source directory
        aindex_dir = lex_dir / "designs" / "src" / "deleted"
        aindex_dir.mkdir(parents=True)
        (aindex_dir / ".aindex").write_text("# deleted dir\n", encoding="utf-8")

        checker = ConsistencyChecker(project, lex_dir)
        instructions = checker.detect_orphaned_aindex()
        assert len(instructions) == 1
        assert instructions[0].action == "remove_orphaned_aindex"
        assert "deleted" in instructions[0].detail

    def test_valid_aindex_not_flagged(self, tmp_path: Path) -> None:
        """An .aindex for an existing source directory should NOT be flagged."""
        project, lex_dir = _setup_project(tmp_path)
        # Create both source directory AND .aindex mirror
        (project / "src" / "auth").mkdir(parents=True)
        aindex_dir = lex_dir / "designs" / "src" / "auth"
        aindex_dir.mkdir(parents=True)
        (aindex_dir / ".aindex").write_text("# auth dir\n", encoding="utf-8")

        checker = ConsistencyChecker(project, lex_dir)
        instructions = checker.detect_orphaned_aindex()
        assert len(instructions) == 0


class TestOrphanedComments:
    """Test orphaned .comments.yaml detection."""

    def test_orphaned_comments_detected(self, tmp_path: Path) -> None:
        """A .comments.yaml with no sibling design .md should be flagged."""
        project, lex_dir = _setup_project(tmp_path)
        # Create .comments.yaml without a sibling design file
        comments_dir = lex_dir / "designs" / "src" / "removed"
        comments_dir.mkdir(parents=True)
        (comments_dir / ".comments.yaml").write_text("- comment: test\n", encoding="utf-8")

        checker = ConsistencyChecker(project, lex_dir)
        instructions = checker.detect_orphaned_comments()
        assert len(instructions) == 1
        assert instructions[0].action == "delete_orphaned_comments"

    def test_comments_with_sibling_not_flagged(self, tmp_path: Path) -> None:
        """A .comments.yaml with a sibling .md file should NOT be flagged."""
        project, lex_dir = _setup_project(tmp_path)
        # Create .comments.yaml WITH a sibling design file
        design_dir = lex_dir / "designs" / "src"
        design_dir.mkdir(parents=True)
        (design_dir / "foo.py.md").write_text("---\ndescription: test\n---\n", encoding="utf-8")
        (design_dir / ".comments.yaml").write_text("- comment: test\n", encoding="utf-8")

        checker = ConsistencyChecker(project, lex_dir)
        instructions = checker.detect_orphaned_comments()
        assert len(instructions) == 0


# ---------------------------------------------------------------------------
# Orphan Concept Detection
# ---------------------------------------------------------------------------


class TestOrphanConcepts:
    """Test orphan concept detection via link graph."""

    def test_orphan_concept_detected_with_graph(self, tmp_path: Path) -> None:
        """A concept with zero inbound links should be flagged."""
        project, lex_dir = _setup_project(tmp_path)
        _make_concept_file(lex_dir, "CN-042", "OrphanConcept")

        # Mock the link graph to return zero reverse deps
        mock_graph = MagicMock()
        mock_graph.reverse_deps.return_value = []

        with patch("lexibrary.linkgraph.query.LinkGraph.open", return_value=mock_graph):
            checker = ConsistencyChecker(project, lex_dir)
            instructions = checker.detect_orphan_concepts(
                lex_dir / "concepts", link_graph_available=True
            )

        assert len(instructions) == 1
        assert instructions[0].action == "remove_orphan_zero_deps"
        detail_lower = instructions[0].detail.lower()
        assert "orphanconcept" in detail_lower or "orphan" in detail_lower
        mock_graph.close.assert_called_once()

    def test_linked_concept_not_flagged(self, tmp_path: Path) -> None:
        """A concept with inbound links should NOT be flagged."""
        project, lex_dir = _setup_project(tmp_path)
        _make_concept_file(lex_dir, "CN-001", "UsedConcept")

        mock_graph = MagicMock()
        mock_graph.reverse_deps.return_value = [MagicMock()]  # has links

        with patch("lexibrary.linkgraph.query.LinkGraph.open", return_value=mock_graph):
            checker = ConsistencyChecker(project, lex_dir)
            instructions = checker.detect_orphan_concepts(
                lex_dir / "concepts", link_graph_available=True
            )

        assert len(instructions) == 0
        mock_graph.close.assert_called_once()

    def test_no_graph_skips_detection(self, tmp_path: Path) -> None:
        """When link graph is unavailable, orphan detection should be skipped."""
        project, lex_dir = _setup_project(tmp_path)
        _make_concept_file(lex_dir, "CN-001", "MaybOrphan")

        checker = ConsistencyChecker(project, lex_dir)
        instructions = checker.detect_orphan_concepts(
            lex_dir / "concepts", link_graph_available=False
        )

        assert len(instructions) == 0


# ---------------------------------------------------------------------------
# Convention/Playbook Staleness Detection
# ---------------------------------------------------------------------------


class TestConventionStaleness:
    """Test convention staleness detection."""

    def test_stale_path_flagged(self, tmp_path: Path) -> None:
        """A convention referencing a deleted path should be flagged."""
        project, lex_dir = _setup_project(tmp_path)
        _make_convention_file(
            lex_dir,
            "CV-001",
            "Old Convention",
            body="This applies to files in `src/old_module/` which is important.",
        )

        checker = ConsistencyChecker(project, lex_dir)
        instructions = checker.detect_stale_conventions(lex_dir / "conventions")
        assert len(instructions) >= 1
        assert instructions[0].action == "flag_stale_convention"
        assert "src/old_module/" in instructions[0].detail

    def test_valid_path_not_flagged(self, tmp_path: Path) -> None:
        """A convention referencing an existing path should NOT be flagged."""
        project, lex_dir = _setup_project(tmp_path)
        (project / "src" / "auth").mkdir(parents=True)
        _make_convention_file(
            lex_dir,
            "CV-001",
            "Auth Convention",
            body="This applies to src/auth/ directory.",
        )

        checker = ConsistencyChecker(project, lex_dir)
        instructions = checker.detect_stale_conventions(lex_dir / "conventions")
        assert len(instructions) == 0


class TestPlaybookStaleness:
    """Test playbook staleness detection."""

    def test_stale_playbook_path_flagged(self, tmp_path: Path) -> None:
        """A playbook referencing a deleted path should be flagged."""
        project, lex_dir = _setup_project(tmp_path)
        _make_playbook_file(
            lex_dir,
            "PB-001",
            "Old Playbook",
            body="Run tests in src/old_tests/ directory.",
        )

        checker = ConsistencyChecker(project, lex_dir)
        instructions = checker.detect_stale_playbooks(lex_dir / "playbooks")
        assert len(instructions) >= 1
        assert instructions[0].action == "flag_stale_playbook"

    def test_valid_playbook_path_not_flagged(self, tmp_path: Path) -> None:
        """A playbook referencing an existing path should NOT be flagged."""
        project, lex_dir = _setup_project(tmp_path)
        (project / "src" / "utils").mkdir(parents=True)
        _make_playbook_file(
            lex_dir,
            "PB-001",
            "Valid Playbook",
            body="Check src/utils/ for helpers.",
        )

        checker = ConsistencyChecker(project, lex_dir)
        instructions = checker.detect_stale_playbooks(lex_dir / "playbooks")
        assert len(instructions) == 0


# ---------------------------------------------------------------------------
# Blocked IWH Promotion
# ---------------------------------------------------------------------------


class TestBlockedIWHPromotion:
    """Test blocked IWH signal promotion to Stack post."""

    def test_old_blocked_iwh_promoted(self, tmp_path: Path) -> None:
        """A blocked IWH signal older than threshold should be flagged for promotion."""
        project, lex_dir = _setup_project(tmp_path)
        _make_iwh_file(lex_dir, "src/stuck_module", scope="blocked", hours_ago=100)

        checker = ConsistencyChecker(project, lex_dir)
        instructions = checker.detect_promotable_iwh(ttl_hours=72)
        assert len(instructions) == 1
        assert instructions[0].action == "promote_blocked_iwh"
        assert instructions[0].risk == "medium"

    def test_recent_blocked_iwh_not_promoted(self, tmp_path: Path) -> None:
        """A recent blocked IWH signal should NOT be promoted."""
        project, lex_dir = _setup_project(tmp_path)
        _make_iwh_file(lex_dir, "src/recent_block", scope="blocked", hours_ago=1)

        checker = ConsistencyChecker(project, lex_dir)
        instructions = checker.detect_promotable_iwh(ttl_hours=72)
        assert len(instructions) == 0

    def test_incomplete_iwh_not_promoted(self, tmp_path: Path) -> None:
        """Non-blocked IWH signals should not be promoted regardless of age."""
        project, lex_dir = _setup_project(tmp_path)
        _make_iwh_file(lex_dir, "src/old_incomplete", scope="incomplete", hours_ago=200)

        checker = ConsistencyChecker(project, lex_dir)
        instructions = checker.detect_promotable_iwh(ttl_hours=72)
        assert len(instructions) == 0


# ---------------------------------------------------------------------------
# Integration: Full checker run covers multiple checks
# ---------------------------------------------------------------------------


class TestIntegration:
    """Integration tests covering multiple consistency check types."""

    def test_full_checker_run(self, tmp_path: Path) -> None:
        """A full consistency check produces instructions from multiple sources."""
        project, lex_dir = _setup_project(tmp_path)

        # Create an orphaned .aindex
        orphan_dir = lex_dir / "designs" / "src" / "deleted_mod"
        orphan_dir.mkdir(parents=True)
        (orphan_dir / ".aindex").write_text("# orphan\n", encoding="utf-8")

        # Create a design file with broken wikilink
        design_path = _make_design_file(project, "src/foo.py", wikilinks=["BrokenLink"])

        # Create an old blocked IWH
        _make_iwh_file(lex_dir, "src/blocked_mod", scope="blocked", hours_ago=200)

        resolver = _build_resolver(lex_dir)
        checker = ConsistencyChecker(project, lex_dir, resolver=resolver)

        # Run multiple checks
        wikilink_instr = checker.check_wikilinks(design_path)
        orphan_instr = checker.detect_orphaned_aindex()
        iwh_instr = checker.detect_promotable_iwh(ttl_hours=72)

        # Should find issues from each source
        assert len(wikilink_instr) >= 1
        assert len(orphan_instr) >= 1
        assert len(iwh_instr) >= 1

    def test_uncommitted_files_context(self, tmp_path: Path) -> None:
        """Verify checker works with scope-limited file sets."""
        project, lex_dir = _setup_project(tmp_path)

        # Only pass specific design files (simulating scope filtering)
        d1 = _make_design_file(project, "src/included.py", wikilinks=["Missing"])
        _make_design_file(project, "src/excluded.py", wikilinks=["AlsoMissing"])

        resolver = _build_resolver(lex_dir)
        checker = ConsistencyChecker(project, lex_dir, resolver=resolver)

        # Check only the included file
        instructions = checker.check_wikilinks(d1)
        assert len(instructions) >= 1
        assert all(i.target_path == d1 for i in instructions)
