"""Tests for :func:`archivist.pipeline.reconcile_deps_only`.

Phase 1a of the ``curator-freshness`` OpenSpec change introduced a
non-LLM reconciler that rewrites a design file's Dependencies and
Dependents sections from AST + link-graph state.  The tests cover the
three behaviours the spec pins down:

* Stale lists -> the file is rewritten and ``dependents_complete`` is
  flipped to ``True``.
* Idempotent second call -> no rewrite when lists already match.
* ``LinkGraphUnavailable`` propagates when ``index.db`` is missing --
  the caller (validator fixer / post-``build_index`` sweep) owns the
  graceful-degradation branch.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from lexibrary.archivist.pipeline import reconcile_deps_only
from lexibrary.artifacts.design_file import (
    DesignFile,
    DesignFileFrontmatter,
    StalenessMetadata,
)
from lexibrary.artifacts.design_file_parser import parse_design_file
from lexibrary.artifacts.design_file_serializer import serialize_design_file
from lexibrary.linkgraph.query import LinkGraphUnavailable
from tests._index_fixtures import _create_index_with_links

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_project(tmp_path: Path) -> tuple[Path, Path]:
    """Create ``project/.lexibrary/designs/`` under *tmp_path*.

    Returns ``(project_root, lexibrary_dir)``.
    """
    project_root = tmp_path
    lexibrary_dir = project_root / ".lexibrary"
    (lexibrary_dir / "designs").mkdir(parents=True)
    return project_root, lexibrary_dir


def _write_source(project_root: Path, rel: str, body: str) -> Path:
    """Write a source file under *project_root* and return its absolute path."""
    path = project_root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _seed_python_sources(project_root: Path) -> None:
    """Seed a Python import graph: ``src/api/auth.py`` imports ``src/utils/crypto.py``.

    Includes the ``__init__.py`` package markers that
    :func:`resolve_python_module` needs to resolve the import to a
    project-relative path.  Uses ``from src.utils.crypto import encrypt``
    (module-level, not package-level) so the resolver picks
    ``src/utils/crypto.py`` rather than ``src/utils/__init__.py``.
    """
    _write_source(project_root, "src/__init__.py", "")
    _write_source(project_root, "src/api/__init__.py", "")
    _write_source(project_root, "src/utils/__init__.py", "")
    _write_source(project_root, "src/utils/crypto.py", "def encrypt(): pass\n")
    _write_source(
        project_root,
        "src/api/auth.py",
        "from src.utils.crypto import encrypt\n",
    )


def _write_design(
    lexibrary_dir: Path,
    source_rel: str,
    *,
    dependencies: list[str] | None = None,
    dependents: list[str] | None = None,
    dependents_complete: bool = False,
    updated_by: str = "agent",
) -> Path:
    """Serialize a minimal design file onto disk at the mirror path."""
    design_path = lexibrary_dir / "designs" / f"{source_rel}.md"
    design_path.parent.mkdir(parents=True, exist_ok=True)
    df = DesignFile(
        source_path=source_rel,
        frontmatter=DesignFileFrontmatter(
            description="Reconcile fixture.",
            id="DS-RECONCILE",
            updated_by=updated_by,  # type: ignore[arg-type]
        ),
        summary="Fixture summary.",
        interface_contract="def foo(): ...",
        dependencies=dependencies or [],
        dependents=dependents or [],
        metadata=StalenessMetadata(
            source=source_rel,
            source_hash="src-hash",
            design_hash="design-hash",
            generated=datetime.now(UTC).replace(tzinfo=None),
            generator="test",
            dependents_complete=dependents_complete,
        ),
    )
    design_path.write_text(serialize_design_file(df), encoding="utf-8")
    return design_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestReconcileDepsOnlyStale:
    """Stale Dependencies / Dependents get rewritten in place."""

    @pytest.mark.asyncio()
    async def test_stale_lists_rewritten_and_flag_flipped(
        self, tmp_path: Path
    ) -> None:
        project_root, lexibrary_dir = _seed_project(tmp_path)
        _seed_python_sources(project_root)

        # Reverse graph: src/ui/login.py imports src/api/auth.py.
        _create_index_with_links(
            lexibrary_dir,
            artifacts=[
                (1, "src/api/auth.py", "source"),
                (2, "src/ui/login.py", "source"),
            ],
            links=[
                (2, 1, "ast_import"),
            ],
        )

        # Seed a stale design: wrong Dependencies, empty Dependents,
        # dependents_complete=False (as if update_file had written it
        # before the index existed).
        design_path = _write_design(
            lexibrary_dir,
            "src/api/auth.py",
            dependencies=["src/wrong/path.py"],
            dependents=[],
            dependents_complete=False,
            updated_by="agent",
        )
        pre_mtime = design_path.stat().st_mtime_ns

        await reconcile_deps_only(design_path, project_root)

        parsed = parse_design_file(design_path)
        assert parsed is not None
        # Dependencies rewritten from AST
        assert parsed.dependencies == ["src/utils/crypto.py"]
        # Dependents rewritten from reverse graph
        assert parsed.dependents == ["src/ui/login.py"]
        # Flag flipped — reverse graph succeeded
        assert parsed.metadata.dependents_complete is True
        # updated_by rebranded to "archivist" (reconciler identity)
        assert parsed.frontmatter.updated_by == "archivist"
        # File actually rewritten
        assert design_path.stat().st_mtime_ns >= pre_mtime


class TestReconcileDepsOnlyIdempotent:
    """Second call with no state change is a no-op (no rewrite)."""

    @pytest.mark.asyncio()
    async def test_idempotent_second_call_does_not_rewrite(
        self, tmp_path: Path
    ) -> None:
        project_root, lexibrary_dir = _seed_project(tmp_path)
        _seed_python_sources(project_root)

        _create_index_with_links(
            lexibrary_dir,
            artifacts=[
                (1, "src/api/auth.py", "source"),
                (2, "src/ui/login.py", "source"),
            ],
            links=[
                (2, 1, "ast_import"),
            ],
        )

        design_path = _write_design(
            lexibrary_dir,
            "src/api/auth.py",
            dependencies=["src/wrong/path.py"],
            dependents=[],
            dependents_complete=False,
        )

        # First call rewrites.
        await reconcile_deps_only(design_path, project_root)
        first_mtime = design_path.stat().st_mtime_ns
        first_bytes = design_path.read_bytes()

        # Second call on the now-reconciled file must be a no-op — the
        # dependencies + dependents already match AST / graph, so the
        # early-return branch fires before atomic_write.
        await reconcile_deps_only(design_path, project_root)
        assert design_path.stat().st_mtime_ns == first_mtime
        assert design_path.read_bytes() == first_bytes


class TestReconcileDepsOnlyMissingIndex:
    """``LinkGraphUnavailable`` propagates up to the caller."""

    @pytest.mark.asyncio()
    async def test_missing_index_raises(self, tmp_path: Path) -> None:
        project_root, lexibrary_dir = _seed_project(tmp_path)
        _seed_python_sources(project_root)

        design_path = _write_design(
            lexibrary_dir,
            "src/api/auth.py",
            dependencies=[],
            dependents=[],
            dependents_complete=False,
        )

        # Sanity: no index.db
        assert not (lexibrary_dir / "index.db").exists()

        with pytest.raises(LinkGraphUnavailable):
            await reconcile_deps_only(design_path, project_root)
