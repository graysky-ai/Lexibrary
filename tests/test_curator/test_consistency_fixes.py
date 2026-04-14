"""Unit tests for the consistency fix helpers (curator-fix Phase 3 — group 8).

Each helper is exercised in isolation with a fabricated
:class:`TriageItem` and a minimal :class:`DispatchContext`.  Helpers
that rewrite design files must go through
:func:`lexibrary.curator.write_contract.write_design_file_as_curator`
so the tests assert authorship (``updated_by="curator"``) and hash
recomputation post-fix.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from lexibrary.artifacts.design_file import (
    DesignFile,
    DesignFileFrontmatter,
    StalenessMetadata,
)
from lexibrary.artifacts.design_file_parser import parse_design_file
from lexibrary.artifacts.design_file_serializer import serialize_design_file
from lexibrary.curator.consistency_fixes import (
    apply_alias_dedup,
    apply_flag_stale_convention,
    apply_orphan_concept_delete,
    apply_orphaned_aindex_delete,
    apply_orphaned_comments_delete,
    apply_slug_suffix,
    apply_strip_wikilink,
    apply_substitute_wikilink,
)
from lexibrary.curator.dispatch_context import DispatchContext
from lexibrary.curator.models import CollectItem, TriageItem
from lexibrary.errors import ErrorSummary

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_project(tmp_path: Path) -> tuple[Path, Path]:
    project = tmp_path / "project"
    project.mkdir()
    lex_dir = project / ".lexibrary"
    lex_dir.mkdir()
    (lex_dir / "designs").mkdir()
    (lex_dir / "concepts").mkdir()
    (lex_dir / "conventions").mkdir()
    (lex_dir / "playbooks").mkdir()
    return project, lex_dir


def _make_ctx(project: Path, lex_dir: Path) -> DispatchContext:
    """Build a minimal DispatchContext with a real ErrorSummary.

    Loads the default LexibraryConfig so the ctx has a real config
    object for any helper that reads from it.
    """
    from lexibrary.config.schema import LexibraryConfig  # noqa: PLC0415

    return DispatchContext(
        project_root=project,
        config=LexibraryConfig(),
        summary=ErrorSummary(),
        lexibrary_dir=lex_dir,
        dry_run=False,
        uncommitted=set(),
        active_iwh=set(),
    )


def _make_source(project: Path, rel: str, content: str = "def foo(): pass\n") -> Path:
    src = project / rel
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text(content, encoding="utf-8")
    return src


def _make_design(
    project: Path,
    source_rel: str,
    *,
    wikilinks: list[str] | None = None,
    dependencies: list[str] | None = None,
    dependents: list[str] | None = None,
    id_override: str | None = None,
) -> Path:
    """Create a design file in the mirror with a real source file."""
    _make_source(project, source_rel)
    design_path = project / ".lexibrary" / "designs" / (source_rel + ".md")
    design_path.parent.mkdir(parents=True, exist_ok=True)

    df = DesignFile(
        source_path=source_rel,
        frontmatter=DesignFileFrontmatter(
            description=f"Design for {source_rel}",
            id=id_override or source_rel.replace("/", "-").replace(".", "-"),
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
            source_hash="abc123" * 10 + "abcd",  # fake 64-char hash
            interface_hash=None,
            generated=datetime.now(UTC),
            generator="test",
        ),
    )
    design_path.write_text(serialize_design_file(df), encoding="utf-8")
    return design_path


def _make_item(
    *,
    action_key: str,
    action_hint: str,
    target_path: Path | None,
    detail: str,
) -> TriageItem:
    """Fabricate a consistency_fix TriageItem."""
    collect = CollectItem(
        source="consistency",
        path=target_path,
        severity="info",
        message=detail,
        check="consistency",
        action_hint=action_hint,
        fix_instruction_detail=detail,
    )
    return TriageItem(
        source_item=collect,
        issue_type="consistency_fix",
        action_key=action_key,
        priority=15.0,
    )


# ---------------------------------------------------------------------------
# apply_strip_wikilink
# ---------------------------------------------------------------------------


class TestApplyStripWikilink:
    def test_apply_strip_wikilink_removes_wikilink(self, tmp_path: Path) -> None:
        project, lex_dir = _setup_project(tmp_path)
        design_path = _make_design(
            project,
            "src/foo.py",
            wikilinks=["NonexistentConcept", "KeepMe"],
        )
        item = _make_item(
            action_key="strip_unresolved_wikilink",
            action_hint="strip_unresolved_wikilink",
            target_path=design_path,
            detail="Wikilink [[NonexistentConcept]] cannot be resolved; strip it",
        )
        result = apply_strip_wikilink(item, _make_ctx(project, lex_dir))
        assert result.success is True
        assert result.outcome == "fixed"

        parsed = parse_design_file(design_path)
        assert parsed is not None
        assert "NonexistentConcept" not in parsed.wikilinks
        assert "KeepMe" in parsed.wikilinks

    def test_apply_strip_wikilink_preserves_code_fences(self, tmp_path: Path) -> None:
        """The strip helper edits only the ``## Wikilinks`` section."""
        project, lex_dir = _setup_project(tmp_path)
        design_path = _make_design(
            project,
            "src/foo.py",
            wikilinks=["NonexistentConcept"],
        )
        result = apply_strip_wikilink(
            _make_item(
                action_key="strip_unresolved_wikilink",
                action_hint="strip_unresolved_wikilink",
                target_path=design_path,
                detail="Wikilink [[NonexistentConcept]] cannot be resolved",
            ),
            _make_ctx(project, lex_dir),
        )
        assert result.success is True

        parsed = parse_design_file(design_path)
        assert parsed is not None
        # Interface contract code fence must still be intact (parser
        # handles fence stripping, so non-empty contract proves the
        # fences round-trip).
        assert "def foo" in parsed.interface_contract

    def test_apply_strip_wikilink_updated_by_curator(self, tmp_path: Path) -> None:
        project, lex_dir = _setup_project(tmp_path)
        design_path = _make_design(project, "src/foo.py", wikilinks=["Dead"])
        apply_strip_wikilink(
            _make_item(
                action_key="strip_unresolved_wikilink",
                action_hint="strip_unresolved_wikilink",
                target_path=design_path,
                detail="Wikilink [[Dead]] cannot be resolved",
            ),
            _make_ctx(project, lex_dir),
        )
        parsed = parse_design_file(design_path)
        assert parsed is not None
        assert parsed.frontmatter.updated_by == "curator"


# ---------------------------------------------------------------------------
# apply_substitute_wikilink
# ---------------------------------------------------------------------------


class TestApplySubstituteWikilink:
    def test_apply_substitute_wikilink_replaces_target(self, tmp_path: Path) -> None:
        project, lex_dir = _setup_project(tmp_path)
        design_path = _make_design(
            project,
            "src/foo.py",
            wikilinks=["Authentcation"],
        )
        item = _make_item(
            action_key="fix_broken_wikilink_fuzzy",
            action_hint="fix_broken_wikilink_fuzzy",
            target_path=design_path,
            detail="Wikilink [[Authentcation]] unresolved; suggestions: Authentication",
        )
        result = apply_substitute_wikilink(item, _make_ctx(project, lex_dir))
        assert result.success is True
        assert result.outcome == "fixed"

        parsed = parse_design_file(design_path)
        assert parsed is not None
        assert "Authentication" in parsed.wikilinks
        assert "Authentcation" not in parsed.wikilinks


# ---------------------------------------------------------------------------
# apply_slug_suffix
# ---------------------------------------------------------------------------


class TestApplySlugSuffix:
    def test_apply_slug_suffix_updates_frontmatter(self, tmp_path: Path) -> None:
        project, lex_dir = _setup_project(tmp_path)
        design_path = _make_design(
            project,
            "src/foo.py",
            id_override="DS-042",
        )
        result = apply_slug_suffix(
            _make_item(
                action_key="resolve_slug_collision",
                action_hint="resolve_slug_collision",
                target_path=design_path,
                detail="Slug 'foo' collides with artifacts: DS-042, DS-043",
            ),
            _make_ctx(project, lex_dir),
        )
        assert result.success is True

        parsed = parse_design_file(design_path)
        assert parsed is not None
        assert parsed.frontmatter.id != "DS-042"
        assert parsed.frontmatter.id.startswith("DS-042-")
        assert parsed.frontmatter.updated_by == "curator"


# ---------------------------------------------------------------------------
# apply_alias_dedup
# ---------------------------------------------------------------------------


class TestApplyAliasDedup:
    def test_apply_alias_dedup_removes_duplicates(self, tmp_path: Path) -> None:
        project, lex_dir = _setup_project(tmp_path)
        concept_path = lex_dir / "concepts" / "CN-001-foo.md"
        data = {
            "title": "Foo",
            "id": "CN-001",
            "status": "active",
            "aliases": ["Bar", "bar", "Baz"],  # Bar/bar collide
            "tags": [],
        }
        text = f"---\n{yaml.dump(data, default_flow_style=False, sort_keys=False)}---\n\n# Foo\n"
        concept_path.write_text(text, encoding="utf-8")

        result = apply_alias_dedup(
            _make_item(
                action_key="resolve_alias_collision",
                action_hint="resolve_alias_collision",
                target_path=concept_path,
                detail="Alias 'bar' shared by: concept:CN-001",
            ),
            _make_ctx(project, lex_dir),
        )
        assert result.success is True

        text_after = concept_path.read_text(encoding="utf-8")
        # Parse frontmatter block
        end = text_after.find("\n---\n", 4)
        fm = yaml.safe_load(text_after[4:end])
        aliases = fm["aliases"]
        # "Bar" kept, "bar" dropped, "Baz" kept
        assert "Bar" in aliases
        assert "Baz" in aliases
        assert "bar" not in aliases


# ---------------------------------------------------------------------------
# apply_bidirectional_dep — retired in Phase 1a of the curator-freshness
# OpenSpec change.  Bidirectional-deps reconciliation now lives on the
# validator side; see tests/test_archivist/test_reconcile_deps_only.py
# and tests/test_validator/test_info_checks.py::TestCheckBidirectionalDeps.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# apply_orphaned_aindex_delete / apply_orphaned_comments_delete
# ---------------------------------------------------------------------------


class TestOrphanedAindexDelete:
    def test_apply_orphaned_aindex_delete_removes_file(self, tmp_path: Path) -> None:
        project, lex_dir = _setup_project(tmp_path)
        orphan = lex_dir / "designs" / "src" / "gone" / ".aindex"
        orphan.parent.mkdir(parents=True)
        orphan.write_text("# orphan\n", encoding="utf-8")

        result = apply_orphaned_aindex_delete(
            _make_item(
                action_key="remove_orphaned_aindex",
                action_hint="remove_orphaned_aindex",
                target_path=orphan,
                detail="Orphaned .aindex",
            ),
            _make_ctx(project, lex_dir),
        )
        assert result.success is True
        assert not orphan.exists()


class TestOrphanedCommentsDelete:
    def test_apply_orphaned_comments_delete_removes_file(self, tmp_path: Path) -> None:
        project, lex_dir = _setup_project(tmp_path)
        orphan = lex_dir / "designs" / "src" / "x.py.comments.yaml"
        orphan.parent.mkdir(parents=True)
        orphan.write_text("- comment: hi\n", encoding="utf-8")

        result = apply_orphaned_comments_delete(
            _make_item(
                action_key="delete_orphaned_comments",
                action_hint="delete_orphaned_comments",
                target_path=orphan,
                detail="Orphaned .comments.yaml",
            ),
            _make_ctx(project, lex_dir),
        )
        assert result.success is True
        assert not orphan.exists()


# ---------------------------------------------------------------------------
# apply_orphan_concept_delete
# ---------------------------------------------------------------------------


class TestApplyOrphanConceptDelete:
    def test_apply_orphan_concept_delete_removes_file(self, tmp_path: Path) -> None:
        project, lex_dir = _setup_project(tmp_path)
        concept = lex_dir / "concepts" / "CN-099-orphan.md"
        concept.write_text(
            "---\ntitle: Orphan\nid: CN-099\nstatus: active\n---\n\nBody\n",
            encoding="utf-8",
        )
        sibling = lex_dir / "concepts" / "CN-099-orphan.comments.yaml"
        sibling.write_text("- note: stale\n", encoding="utf-8")

        result = apply_orphan_concept_delete(
            _make_item(
                action_key="remove_orphan_zero_deps",
                action_hint="remove_orphan_zero_deps",
                target_path=concept,
                detail="Zero inbound",
            ),
            _make_ctx(project, lex_dir),
        )
        assert result.success is True
        assert not concept.exists()
        # Sibling should also be deleted per tasks.md 8.7.
        assert not sibling.exists()

    def test_apply_orphan_concept_delete_without_sibling(self, tmp_path: Path) -> None:
        project, lex_dir = _setup_project(tmp_path)
        concept = lex_dir / "concepts" / "CN-099-orphan.md"
        concept.write_text(
            "---\ntitle: Orphan\nid: CN-099\nstatus: active\n---\n\nBody\n",
            encoding="utf-8",
        )
        result = apply_orphan_concept_delete(
            _make_item(
                action_key="remove_orphan_zero_deps",
                action_hint="remove_orphan_zero_deps",
                target_path=concept,
                detail="Zero inbound",
            ),
            _make_ctx(project, lex_dir),
        )
        assert result.success is True
        assert not concept.exists()


# ---------------------------------------------------------------------------
# Shared contract properties for design-file-rewriting helpers
# ---------------------------------------------------------------------------


class TestHelperContractProperties:
    def test_apply_helpers_set_updated_by_curator(self, tmp_path: Path) -> None:
        """Every helper that rewrites a design file stamps updated_by=curator."""
        project, lex_dir = _setup_project(tmp_path)
        design_path = _make_design(
            project,
            "src/foo.py",
            wikilinks=["DeadLink"],
            dependents=[],
        )
        # Use the strip helper as a representative rewriter.
        apply_strip_wikilink(
            _make_item(
                action_key="strip_unresolved_wikilink",
                action_hint="strip_unresolved_wikilink",
                target_path=design_path,
                detail="Wikilink [[DeadLink]] cannot be resolved",
            ),
            _make_ctx(project, lex_dir),
        )
        parsed = parse_design_file(design_path)
        assert parsed is not None
        assert parsed.frontmatter.updated_by == "curator"

    def test_apply_helpers_recompute_hashes(self, tmp_path: Path) -> None:
        """Helpers must recompute source_hash to match the current source file."""
        from lexibrary.utils.hashing import hash_file  # noqa: PLC0415

        project, lex_dir = _setup_project(tmp_path)
        design_path = _make_design(
            project,
            "src/foo.py",
            wikilinks=["Stripped"],
        )
        # Source file was created by _make_design; compute its hash.
        src_hash = hash_file(project / "src" / "foo.py")
        apply_strip_wikilink(
            _make_item(
                action_key="strip_unresolved_wikilink",
                action_hint="strip_unresolved_wikilink",
                target_path=design_path,
                detail="Wikilink [[Stripped]] cannot be resolved",
            ),
            _make_ctx(project, lex_dir),
        )
        from lexibrary.artifacts.design_file_parser import (  # noqa: PLC0415
            parse_design_file_metadata,
        )

        metadata = parse_design_file_metadata(design_path)
        assert metadata is not None
        assert metadata.source_hash == src_hash


# ---------------------------------------------------------------------------
# IWH-flagging helpers
# ---------------------------------------------------------------------------


class TestFlagStaleConvention:
    def test_apply_flag_stale_convention_writes_iwh(self, tmp_path: Path) -> None:
        project, lex_dir = _setup_project(tmp_path)
        conv = lex_dir / "conventions" / "CV-001-old.md"
        conv.write_text(
            "---\ntitle: Old\nid: CV-001\nscope: src/gone/\nstatus: active\n---\n\nBody\n",
            encoding="utf-8",
        )
        result = apply_flag_stale_convention(
            _make_item(
                action_key="flag_stale_convention",
                action_hint="flag_stale_convention",
                target_path=conv,
                detail="Convention references path 'src/gone/' which no longer exists",
            ),
            _make_ctx(project, lex_dir),
        )
        assert result.success is True
        # IWH should be written into the conventions mirror directory.
        iwh_path = lex_dir / "conventions" / ".iwh"
        assert iwh_path.exists()
        assert "Stale convention" in iwh_path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Failure / edge cases
# ---------------------------------------------------------------------------


class TestHelperFailureModes:
    def test_strip_wikilink_missing_detail_target(self, tmp_path: Path) -> None:
        project, lex_dir = _setup_project(tmp_path)
        design_path = _make_design(project, "src/foo.py", wikilinks=["Something"])
        result = apply_strip_wikilink(
            _make_item(
                action_key="strip_unresolved_wikilink",
                action_hint="strip_unresolved_wikilink",
                target_path=design_path,
                detail="no brackets here",
            ),
            _make_ctx(project, lex_dir),
        )
        assert result.success is False
        assert result.outcome == "fixer_failed"

    def test_orphaned_aindex_delete_missing_path(self, tmp_path: Path) -> None:
        project, lex_dir = _setup_project(tmp_path)
        result = apply_orphaned_aindex_delete(
            _make_item(
                action_key="remove_orphaned_aindex",
                action_hint="remove_orphaned_aindex",
                target_path=None,
                detail="Orphaned",
            ),
            _make_ctx(project, lex_dir),
        )
        assert result.success is False

    def test_substitute_wikilink_no_suggestion(self, tmp_path: Path) -> None:
        project, lex_dir = _setup_project(tmp_path)
        design_path = _make_design(project, "src/foo.py", wikilinks=["X"])
        result = apply_substitute_wikilink(
            _make_item(
                action_key="fix_broken_wikilink_fuzzy",
                action_hint="fix_broken_wikilink_fuzzy",
                target_path=design_path,
                detail="Wikilink [[X]] unresolved; no suggestions",
            ),
            _make_ctx(project, lex_dir),
        )
        assert result.success is False


# ---------------------------------------------------------------------------
# Smoke: all CONSISTENCY_ACTION_KEYS keys have a registered handler
# ---------------------------------------------------------------------------


def test_consistency_action_keys_map_is_authoritative() -> None:
    """Every key in CONSISTENCY_ACTION_KEYS must match its value (identity).

    The mapping exists so future aliases can be added without changing
    the dispatch router, but today every key maps to itself.
    """
    from lexibrary.curator.consistency_fixes import CONSISTENCY_ACTION_KEYS

    for hint, key in CONSISTENCY_ACTION_KEYS.items():
        assert hint == key, f"{hint!r} should map to itself, got {key!r}"


@pytest.mark.parametrize(
    "action_key",
    [
        "strip_unresolved_wikilink",
        "fix_broken_wikilink_fuzzy",
        "resolve_slug_collision",
        "resolve_alias_collision",
        "remove_orphaned_aindex",
        "delete_orphaned_comments",
        "remove_orphan_zero_deps",
        "add_missing_reverse_dep",
        "flag_stale_convention",
        "flag_stale_playbook",
        "suggest_new_concept",
        "promote_blocked_iwh",
    ],
)
def test_consistency_action_keys_registered_in_taxonomy(action_key: str) -> None:
    """Each emitted consistency action key must have a taxonomy entry."""
    from lexibrary.curator.risk_taxonomy import RISK_TAXONOMY

    assert action_key in RISK_TAXONOMY, f"{action_key} missing from RISK_TAXONOMY"
