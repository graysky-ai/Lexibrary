"""Tests for :func:`lexibrary.validator.fixes.fix_bidirectional_deps`.

Phase 1b of the ``curator-freshness`` OpenSpec change registers a
non-LLM fixer that reconciles a design file's ``Dependencies`` and
``Dependents`` sections against the archivist AST extractor and the
link graph.  The tests cover the two behaviours pinned down by the
group-4 spec:

* Stale Dependencies AND stale Dependents with a live ``index.db``:
  the fixer wraps :func:`archivist.pipeline.reconcile_deps_only` and
  rewrites both sections, returning ``FixResult(fixed=True)``.
* Missing ``index.db``: the fixer catches
  :class:`linkgraph.LinkGraphUnavailable` and returns
  ``FixResult(fixed=False)`` with the documented
  "link graph not built" message so the CLI / curator can surface a
  graceful-degradation hint.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from lexibrary.artifacts.design_file import (
    DesignFile,
    DesignFileFrontmatter,
    StalenessMetadata,
)
from lexibrary.artifacts.design_file_parser import parse_design_file
from lexibrary.artifacts.design_file_serializer import serialize_design_file
from lexibrary.config.schema import LexibraryConfig, ScopeRoot, TokenBudgetConfig
from lexibrary.validator.fixes import fix_bidirectional_deps
from lexibrary.validator.report import ValidationIssue
from tests._index_fixtures import _create_index_with_links

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config() -> LexibraryConfig:
    return LexibraryConfig(
        scope_roots=[ScopeRoot(path=".")],
        token_budgets=TokenBudgetConfig(design_file_tokens=400),
    )


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
            description="Fix bidirectional_deps fixture.",
            id="DS-FIX",
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


def _make_issue(artifact: str) -> ValidationIssue:
    return ValidationIssue(
        severity="warning",
        check="bidirectional_deps",
        message="dependencies drift: stale listing",
        artifact=artifact,
    )


# ---------------------------------------------------------------------------
# Happy path: stale Dependencies AND Dependents with live index.db
# ---------------------------------------------------------------------------


class TestFixBidirectionalDepsSuccessful:
    """Both sections drift; fixer reconciles them in place."""

    def test_stale_lists_reconciled_and_flag_flipped(self, tmp_path: Path) -> None:
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

        # Stale design: wrong Dependencies, empty Dependents.
        # dependents_complete=True so the reconciler writes the reverse
        # list on the first pass and the test asserts the graph-derived
        # value replaces it.
        design_path = _write_design(
            lexibrary_dir,
            "src/api/auth.py",
            dependencies=["src/wrong/path.py"],
            dependents=[],
            dependents_complete=True,
            updated_by="agent",
        )

        # ``issue.artifact`` is lexibrary-relative per the fixer's contract.
        issue = _make_issue("designs/src/api/auth.py.md")
        config = _make_config()

        result = fix_bidirectional_deps(issue, project_root, config)

        assert result.fixed is True
        assert result.check == "bidirectional_deps"
        assert result.path == design_path
        assert "reconciled" in result.message

        parsed = parse_design_file(design_path)
        assert parsed is not None
        # Dependencies rewritten from AST
        assert parsed.dependencies == ["src/utils/crypto.py"]
        # Dependents rewritten from the reverse ``ast_import`` edge
        assert parsed.dependents == ["src/ui/login.py"]
        # Reconciler flips the flag to True (reverse graph succeeded)
        assert parsed.metadata.dependents_complete is True
        # Reconciler rebrands authorship
        assert parsed.frontmatter.updated_by == "archivist"


# ---------------------------------------------------------------------------
# Degraded path: missing index.db
# ---------------------------------------------------------------------------


class TestFixBidirectionalDepsMissingIndex:
    """No index.db on disk -> graceful degradation."""

    def test_missing_index_returns_not_fixed_with_docs_message(self, tmp_path: Path) -> None:
        project_root, lexibrary_dir = _seed_project(tmp_path)
        _seed_python_sources(project_root)

        design_path = _write_design(
            lexibrary_dir,
            "src/api/auth.py",
            dependencies=[],
            dependents=[],
            dependents_complete=True,
        )

        # Sanity: no index.db so reconcile_deps_only will raise
        # LinkGraphUnavailable, which the fixer must catch.
        assert not (lexibrary_dir / "index.db").exists()

        issue = _make_issue("designs/src/api/auth.py.md")
        config = _make_config()

        result = fix_bidirectional_deps(issue, project_root, config)

        assert result.fixed is False
        assert result.path == design_path
        # Exact message pinned by tasks.md group 4.1.
        assert result.message == "link graph not built — run `lexictl update` first"
